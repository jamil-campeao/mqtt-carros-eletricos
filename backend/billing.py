import paho.mqtt.client as mqtt
import json
from lamport_clock import LamportClock

PRECO_POR_KWW = 0.75

class BillingService:
    def __init__(self, broker_address="localhost"):
        self.broker_address = broker_address
        self.clock = LamportClock()

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
            if 'timestamp' in payload:
                self.clock.receive_event(payload['timestamp'])
                print(f"[Billing | Clock: {self.clock.get_time()}] Evento recebido: {payload}")
                self.processar_evento(payload)

        except (json.JSONDecodeError, KeyError) as e:
            print(f"Erro ao processar mensagem: {e}")

    def processar_evento(self, evento):
        carro_id = evento.get("carro")
        acao = evento.get("acao")

        if acao == "fim_carga":
            carro_id = evento.get("carro")
            energia_consumida = evento.get("energia_consumida_kWh")

            if carro_id and energia_consumida is not None:
                custo_total = energia_consumida * PRECO_POR_KWW

                transacao = {
                    "carro": carro_id,
                    "carregador": evento.get("carregador"),
                    "custo_total_brl": round(custo_total, 2),
                    "timestamp": self.clock.send_event()
                }

                self.client.publish(self.topic_transacoes, json.dumps(transacao))
                print(f"[Billing] Transação calculada e publicada para {carro_id}: {transacao}")
            else:
                print(f"[Billing] Evento 'fim_carga' recebido com dados incompletos: {evento}")

    def run(self):
        self.client.connect(self.broker_address, 1883, 60)
        self.client.loop_forever()

if __name__ == "__main__":
    billing = BillingService()
    billing.run()