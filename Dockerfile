# 1. Imagem Base: Começa com uma imagem oficial do Python, leve e otimizada.
FROM python:3.10-slim

# 2. Diretório de Trabalho: Define o diretório padrão dentro do contêiner.
#    Todos os comandos a seguir serão executados a partir daqui.
WORKDIR /app

# 3. Copiar Dependências: Copia apenas o requirements.txt primeiro.
#    O Docker é inteligente e só reinstalará as dependências se este arquivo mudar.
COPY requirements.txt requirements.txt

# 4. Instalar Dependências: Instala as bibliotecas Python listadas no requirements.txt.
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copiar Código da Aplicação: Copia todo o resto do seu código para dentro do contêiner.
COPY . .

# 6. Expor a Porta: Informa ao Docker que a aplicação dentro do contêiner
#    estará ouvindo na porta 8000. (A Railway usará a variável $PORT para mapear isso).
EXPOSE 8000

# 7. Comando de Inicialização: Este é o comando que a Railway vai executar para iniciar sua API.
#    (Ele pode ser sobrescrito pelo "Start Command" nas configurações da Railway,
#    mas é uma boa prática tê-lo aqui).
#    --host 0.0.0.0 é crucial para ser acessível na rede.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]