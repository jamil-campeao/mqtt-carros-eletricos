from paho.mqtt import client as mqtt_client
import json
import time
import random
import sys
from lamport_clock import LamportClock

class Carregador:
    def __init__(self, carregador_id, broker_address="localhost"):
        self.carregador_id = carregador_id
        self.broker_address = broker_address
        self.clock = LamportClock()
        self.carro_conectado = None
        self.energia_consumida = 0.0

        # Tópicos MQTT
        self.topic_eventos = f"carregadores/{self.carregador_id}/eventos"
        self.topic_status = f"carregadores/{self.carregador_id}/status"
        # Todos os carregadores escutam os eventos de todos os outros para manter o relógio sincronizado
        self.topic_global_eventos = "carregadores/+/eventos"

        # Configuração do cliente MQTT
        self.client = mqtt_client.Client(client_id=f"carregador-{self.carregador_id}")
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

        # --- IMPLEMENTAÇÃO DO LAST WILL AND TESTAMENT (LWT) ---
        # 1. Defino a mensagem do "testamento"
        lwt_payload = json.dumps({
            "carregador": self.carregador_id,
            "status": "offline",
            "carro_conectado": None,
            "energia_consumida_kWh": 0
        })

        # 2. Configuração do LWT:
        # Tópico: O próprio tópico de status do carregador
        # Payload: A mensagem de offline
        # QoS: 1 (garante que a mensagem seja entregue pelo menos uma vez)
        # Retain: True (a mensagem de 'offline' fica retida no tópico)
        self.client.will_set(self.topic_status, payload=lwt_payload, qos=1, retain=True)
        # ---------------------------------------------------------

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print(f"Carregador {self.carregador_id} conectado ao Broker MQTT!")
            # Subscreve ao tópico global de eventos para ouvir outras estações
            client.subscribe(self.topic_global_eventos)
            print(f"Carregador {self.carregador_id} subscrito a '{self.topic_global_eventos}'")
        else:
            print(f"Falha na conexão, código de retorno: {rc}\n")

    def on_message(self, client, userdata, msg):
        # Ignora as próprias mensagens
        if self.carregador_id in msg.topic:
            return

        try:
            payload = json.loads(msg.payload.decode())
            received_timestamp = payload.get("timestamp")

            if received_timestamp is not None:
                # Atualiza o relógio lógico ao receber um evento de outro carregador
                self.clock.receive_event(received_timestamp)
                print(f"[{self.carregador_id}] Evento recebido de '{msg.topic}'. Relógio atualizado para: {self.clock.get_time()}")
        except json.JSONDecodeError:
            print(f"[{self.carregador_id}] Erro ao decodificar mensagem: {msg.payload.decode()}")


    def publicar_evento(self, acao, carro_id=None):
        """Publica um evento com o timestamp de Lamport."""
        timestamp = self.clock.send_event()
        payload = {
            "carregador": self.carregador_id,
            "carro": carro_id or self.carro_conectado,
            "acao": acao,
            "timestamp": timestamp
        }
        self.client.publish(self.topic_eventos, json.dumps(payload))
        print(f"[{self.carregador_id} | Clock: {timestamp}] Evento publicado: {payload}")

    def publicar_status(self):
        """Publica o status atual do carregador."""
        payload = {
            "carregador": self.carregador_id,
            "status": "ocupado" if self.carro_conectado else "livre",
            "carro_conectado": self.carro_conectado,
            "energia_consumida_kWh": round(self.energia_consumida, 2)
        }
        self.client.publish(self.topic_status, json.dumps(payload), retain=True) # Retain para que novos clientes saibam o último estado

    def conectar_carro(self, carro_id):
        if self.carro_conectado:
            print(f"[{self.carregador_id}] Já existe um carro conectado.")
            return

        self.carro_conectado = carro_id
        self.energia_consumida = 0.0
        self.publicar_evento("inicio_carga", self.carro_conectado)
        self.publicar_status()

    def finalizar_carregamento(self):
        if not self.carro_conectado:
            print(f"[{self.carregador_id}] Nenhum carro para desconectar.")
            return

        timestamp = self.clock.send_event()
        payload = {
            "carregador": self.carregador_id,
            "carro": self.carro_conectado,
            "acao": "fim_carga",
            "timestamp": timestamp,
            "energia_consumida_kWh": round(self.energia_consumida, 2)
        }
        self.client.publish(self.topic_eventos, json.dumps(payload))
        print(f"[{self.carregador_id} | Clock: {timestamp}] Evento publicado: {payload}")

        self.carro_conectado = None
        self.publicar_status()

    def simular_carregamento(self):
        if self.carro_conectado:
            # Simula um consumo de energia
            self.energia_consumida += random.uniform(0.5, 2.0)
            self.publicar_status()
            print(f"[{self.carregador_id}] Carro {self.carro_conectado} - Consumo: {self.energia_consumida:.2f} kWh")

    def run(self):
        self.client.connect(self.broker_address, 1883, 60)
        self.client.loop_start() # Inicia a thread de rede do MQTT

        # Simulação principal
        try:
            while True:
                if not self.carro_conectado:
                    # Chance de um novo carro conectar
                    if random.random() < 0.3: # 30% de chance a cada 5 segundos
                        novo_carro = f"Carro_{random.randint(100, 999)}"
                        self.conectar_carro(novo_carro)
                else:
                    # Simula o carregamento e chance de finalizar
                    self.simular_carregamento()
                    if random.random() < 0.2: # 20% de chance de finalizar
                        self.finalizar_carregamento()

                time.sleep(5)
        except KeyboardInterrupt:
            print(f"\n[{self.carregador_id}] Desligando...")
            if self.carro_conectado:
                self.finalizar_carregamento()
            self.client.loop_stop()
            self.client.disconnect()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python carregador.py <ID_DO_CARREGADOR>")
        sys.exit(1)

    carregador_id = sys.argv[1]
    carregador = Carregador(carregador_id)
    carregador.run()