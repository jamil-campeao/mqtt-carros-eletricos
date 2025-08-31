import asyncio
import json
import threading
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import paho.mqtt.client as mqtt
import subprocess
from pydantic import BaseModel
import sys
import os

MQTT_BROKER_HOST = os.getenv("MQTT_BROKER_HOST", "localhost")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

carregadores_ativos = {}
billing_process = None

class CarregadorRequest(BaseModel):
    carregador_id: str

# --- Gerenciador de Conexões WebSocket ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

manager = ConnectionManager()

# --- Estado Global da Aplicação ---
# Dicionário para armazenar o último status de cada carregador e a lista de eventos
app_state = {
    "carregadores": {},
    "eventos": []
}

# --- Lógica do Cliente MQTT ---
def setup_mqtt_client(loop):
    client = mqtt.Client(client_id="api-service")
    
    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            print("API conectada ao Broker MQTT!")
            # Subscreve aos tópicos de status e eventos
            client.subscribe("carregadores/+/status")
            client.subscribe("carregadores/+/eventos")
        else:
            print(f"Falha na conexão MQTT, código de retorno: {rc}\n")

    def on_message(client, userdata, msg):
        try:
            payload_str = msg.payload.decode()
            payload = json.loads(payload_str)
            
            # Atualiza o estado da aplicação com base no tópico
            if "status" in msg.topic:
                carregador_id = payload.get("carregador")
                if carregador_id:
                    app_state["carregadores"][carregador_id] = payload
            elif "eventos" in msg.topic:
                app_state["eventos"].append(payload)
                # Limita a lista de eventos para não crescer indefinidamente
                if len(app_state["eventos"]) > 50:
                    app_state["eventos"].pop(0)

            asyncio.run_coroutine_threadsafe(
                manager.broadcast(json.dumps({"topic": msg.topic, "payload": payload})), 
                loop
            )

        except Exception as e:
            print(f"Erro ao processar mensagem MQTT: {e}")

    client.on_connect = on_connect
    client.on_message = on_message
    return client

@app.on_event("startup")
async def startup_event():
    """
    Este código é executado quando a aplicação FastAPI inicia.
    """
    # Guardamos o cliente no estado da aplicação para poder acessá-lo no shutdown
    main_loop = asyncio.get_running_loop()
    app.state.mqtt_client = setup_mqtt_client(main_loop)
    app.state.mqtt_client.connect(MQTT_BROKER_HOST, 1883, 60)
    
    # Inicia o loop do MQTT em uma thread separada
    threading.Thread(target=app.state.mqtt_client.loop_forever, daemon=True).start()

@app.on_event("shutdown")
async def shutdown_event():
    """
    Este código é executado quando a aplicação FastAPI desliga.
    """
    print("Desconectando do MQTT...")
    app.state.mqtt_client.loop_stop()
    app.state.mqtt_client.disconnect()
# ----------------------------------------------------


# --- Endpoints da API ---

@app.post("/api/carregadores", status_code=201)
async def iniciar_carregador(request: CarregadorRequest):
    """
    Inicia um novo processo de carregador.
    """
    carregador_id = request.carregador_id
    if carregador_id in carregadores_ativos:
        return {"status": "erro", "mensagem": f"Carregador {carregador_id} já está em execução."}

    try:
        # sys.executable garante que estamos usando o mesmo interpretador Python
        # que está rodando a API para executar o script.
        comando = [sys.executable, "backend/carregador.py", carregador_id]
        
        # Popen inicia o processo em segundo plano, sem bloquear a API
        processo = subprocess.Popen(comando, env=os.environ.copy())
        
        # Armazena o objeto do processo no nosso dicionário
        carregadores_ativos[carregador_id] = processo
        
        print(f"[API] Iniciado carregador {carregador_id} com PID: {processo.pid}")
        return {"status": "sucesso", "mensagem": f"Carregador {carregador_id} iniciado.", "pid": processo.pid}
    except Exception as e:
        return {"status": "erro", "mensagem": f"Falha ao iniciar carregador: {e}"}
    
@app.delete("/api/carregadores/{carregador_id}", status_code=200)
async def parar_carregador(carregador_id: str):
    """
    Para um processo de carregador em execução.
    """
    if carregador_id not in carregadores_ativos:
        return {"status": "erro", "mensagem": f"Carregador {carregador_id} não encontrado ou não está em execução."}

    try:
        processo = carregadores_ativos[carregador_id]
        processo.terminate()  # Envia um sinal para o processo terminar
        processo.wait(timeout=5) # Espera um pouco para o processo encerrar
        
        del carregadores_ativos[carregador_id]
        
        print(f"[API] Parado carregador {carregador_id} com PID: {processo.pid}")
        return {"status": "sucesso", "mensagem": f"Carregador {carregador_id} parado."}
    except Exception as e:
        return {"status": "erro", "mensagem": f"Falha ao parar carregador: {e}"}
    
@app.get("/api/carregadores/ativos")
async def listar_carregadores_ativos():
    """
    Lista os IDs de todos os carregadores atualmente gerenciados pela API.
    """
    # Verifica se os processos ainda estão rodando
    ativos = []
    for cid, processo in list(carregadores_ativos.items()):
        if processo.poll() is None: # poll() retorna None se o processo ainda está rodando
            ativos.append(cid)
        else:
            # Limpa processos que morreram sozinhos
            del carregadores_ativos[cid]
            
    return {"carregadores_ativos": ativos}

@app.post("/api/billing/start", status_code=201)
async def iniciar_billing():
    """
    Inicia o processo do serviço de billing.
    """
    global billing_process
    # Verifica se o processo já não está rodando
    if billing_process and billing_process.poll() is None:
        return {"status": "erro", "mensagem": "O serviço de billing já está em execução."}

    try:
        comando = [sys.executable, "backend/billing.py"]
        billing_process = subprocess.Popen(comando, env=os.environ.copy())
        
        print(f"[API] Iniciado serviço de billing com PID: {billing_process.pid}")
        return {"status": "sucesso", "mensagem": "Serviço de billing iniciado.", "pid": billing_process.pid}
    except Exception as e:
        billing_process = None
        return {"status": "erro", "mensagem": f"Falha ao iniciar o serviço de billing: {e}"}
    
@app.post("/api/billing/stop", status_code=200)
async def parar_billing():
    """
    Para o processo do serviço de billing.
    """
    global billing_process
    if not billing_process or billing_process.poll() is not None:
        return {"status": "erro", "mensagem": "O serviço de billing não está em execução."}

    try:
        pid = billing_process.pid
        billing_process.terminate()
        billing_process.wait(timeout=5)
        billing_process = None
        
        print(f"[API] Parado serviço de billing com PID: {pid}")
        return {"status": "sucesso", "mensagem": "Serviço de billing parado."}
    except Exception as e:
        return {"status": "erro", "mensagem": f"Falha ao parar o serviço de billing: {e}"}
    
@app.get("/api/billing/status")
async def status_billing():
    """
    Verifica e retorna o status do serviço de billing.
    """
    if billing_process and billing_process.poll() is None:
        return {"status": "ativo", "pid": billing_process.pid}
    return {"status": "inativo", "pid": None}

@app.get("/api/estado-inicial")
async def get_initial_state():
    """
    Fornece o estado completo atual quando o frontend carrega a página.
    """
    return app_state

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    Mantém a conexão em tempo real com o frontend.
    """
    await manager.connect(websocket)
    try:
        while True:
            # Mantém a conexão viva. Pode ser usado para receber mensagens do frontend se necessário.
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        print("Cliente WebSocket desconectado")