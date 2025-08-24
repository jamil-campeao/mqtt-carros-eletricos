import paho.mqtt.client as mqtt
import json
from lamport_clock import LamportClock
import random

class BillingService:
    def __init__(self, broker_address="localhost"):
        self.broker_address = broker_address
        self.clock = LamportClock()
        self.sessoes_ativas = {} # Dicionário para guardar dados de carregamento

        # Tópicos
        self.topic_eventos = "carregadores/+/eventos"
        self.topic_transacoes = "billing/transacoes"

        # Cliente MQTT
        self.client = mqtt.Client(client_id="billing-service")
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    def on_connect(self, client, userdata, flags, rc):
        print("Serviço de Billing conectado!")
        client.subscribe(self.topic_eventos)
        print(f"Subscrito a '{self.topic_eventos}'")

    def on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            self.clock.receive_event(payload['timestamp'])
            print(f"[Billing | Clock: {self.clock.get_time()}] Evento recebido: {payload}")
            
            self.processar_evento(payload)
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Erro ao processar mensagem: {e}")

    def processar_evento(self, evento):
        carro_id = evento.get("carro")
        acao = evento.get("acao")
        
        if acao == "inicio_carga":
            # Armazena o início da sessão
            self.sessoes_ativas[carro_id] = {
                "carregador": evento.get("carregador"),
                "timestamp_inicio": evento.get("timestamp"),
                "status": "carregando"
            }
            print(f"[Billing] Sessão iniciada para o carro {carro_id}.")

        elif acao == "fim_carga":
            if carro_id in self.sessoes_ativas:
                # Calcula o custo (exemplo simples) e finaliza a sessão
                custo = random.uniform(5, 50) # Lógica de cálculo real viria aqui
                
                transacao = {
                    "carro": carro_id,
                    "carregador": self.sessoes_ativas[carro_id]['carregador'],
                    "custo_total": round(custo, 2),
                    "timestamp": self.clock.send_event()
                }
                
                self.client.publish(self.topic_transacoes, json.dumps(transacao))
                print(f"[Billing] Transação finalizada para {carro_id}: {transacao}")
                del self.sessoes_ativas[carro_id]

    def run(self):
        self.client.connect(self.broker_address, 1883, 60)
        self.client.loop_forever()

if __name__ == "__main__":
    billing = BillingService()
    billing.run()