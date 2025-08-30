import asyncio
import json
import threading
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import paho.mqtt.client as mqtt

# --- Configuração da API FastAPI ---
app = FastAPI()

# Permite que o frontend (rodando em outra porta/endereço) acesse a API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Em produção, restrinja para o endereço do seu frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
def setup_mqtt_client():
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

            # Transmite a atualização para todos os clientes WebSocket conectados
            # Precisamos usar o loop de eventos do asyncio para rodar a função async
            asyncio.run(manager.broadcast(json.dumps({"topic": msg.topic, "payload": payload})))

        except Exception as e:
            print(f"Erro ao processar mensagem MQTT: {e}")

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect("localhost", 1883, 60)
    return client

# Inicia o cliente MQTT em uma thread separada para não bloquear a API
mqtt_client = setup_mqtt_client()
threading.Thread(target=mqtt_client.loop_forever, daemon=True).start()


# --- Endpoints da API ---

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