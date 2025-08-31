# 1. Imagem Base: Usa a imagem oficial e mais recente do Mosquitto.
FROM eclipse-mosquitto:latest

# 2. Copiar Configuração: Copia seu arquivo de configuração local para o local
#    padrão que a imagem do Mosquitto espera encontrar.
#    Quando o Mosquitto iniciar, ele verá este arquivo e o usará automaticamente.
COPY mosquitto/config/mosquitto.conf /mosquitto/config/mosquitto.conf