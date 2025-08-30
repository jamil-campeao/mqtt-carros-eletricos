import paho.mqtt.client as mqtt
import json
from lamport_clock import LamportClock
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

PRECO_POR_KWH = 0.75
DATABASE_URL = os.getenv("DATABASE_URL")
MQTT_BROKER_HOST = os.getenv("MQTT_BROKER_HOST", "localhost")


def salvar_transacao_db(transacao):
    conn = None
    
    try:
        conn = psycopg2.connect(DATABASE_URL)

        sql = """
            INSERT INTO transacoes (carro_id, carregador_id, energia_total_kWh, custo_total_brl, timestamp_transacao)
            VALUES (%s, %s, %s, %s, %s);
        """

        with conn as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (transacao['carro'], transacao['carregador'], transacao['energia_total_kWh'], transacao['custo_total_brl'], transacao['timestamp_transacao']))
                conn.commit()
    except Exception as e:
        print(f"[DB] Erro ao salvar transação: {e}")

class BillingService:
    def __init__(self, broker_address="localhost"):
        self.broker_address = broker_address
        self.clock = LamportClock()
        self.topic_eventos = "carregadores/+/eventos"
        self.topic_transacoes = "billing/transacoes"
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
        if evento.get("acao") == "fim_carga":
            carro_id = evento.get("carro")
            energia_consumida = evento.get("energia_consumida_kWh")

            if carro_id and energia_consumida is not None:
                custo_total = energia_consumida * PRECO_POR_KWH

                transacao = {
                    "carro": carro_id,
                    "carregador": evento.get("carregador"),
                    "energia_total_kWh": energia_consumida,
                    "custo_total_brl": round(custo_total, 2),
                    "timestamp_transacao": self.clock.send_event()
                }

                # 1. Publica no MQTT (para o frontend ou outros serviços ouvirem)
                self.client.publish(self.topic_transacoes, json.dumps(transacao))
                print(f"[MQTT] Transação publicada para {carro_id}: {transacao}")

                # 2. Salva a mesma transação no banco de dados
                salvar_transacao_db(transacao)
            else:
                print(f"[Billing] Evento 'fim_carga' recebido com dados incompletos: {evento}")

    def run(self):
        if not DATABASE_URL:
            print("ERRO: A variável de ambiente DATABASE_URL não foi definida.")
            return
        self.client.connect(MQTT_BROKER_HOST, 1883, 60)
        self.client.loop_forever()

if __name__ == "__main__":
    billing = BillingService()
    billing.run()