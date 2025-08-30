import os 
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")


def criar_tabelas_transacoes():
    conn = None

    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS transacoes (
                id SERIAL PRIMARY KEY,
                carro_id VARCHAR(255) NOT NULL,
                carregador_id VARCHAR(255) NOT NULL,
                energia_total_kWh NUMERIC(10, 2) NOT NULL,
                custo_total_brl NUMERIC(10, 2) NOT NULL,
                timestamp_transacao BIGINT NOT NULL,
                registrado_em TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
        print("Tabelas 'transacoes' criadas com sucesso!")

        cur.close()
    except (Exception, psycopg2.DatabaseError) as error:
        print("Erro ao conectar ou criar a tabela:", error)
    finally:
        if conn is not None:
            conn.close()
            print('Conexão com o banco fechada')


if __name__ == '__main__':
    criar_tabelas_transacoes()