import threading

class LamportClock:
    def __init__(self):
        self.time = 0
        self._lock = threading.Lock()

    def tick(self):
        """
        Incrementa o relógio local. Chamado antes de um evento interno.
        """
        with self._lock:
            self.time += 1
            return self.time

    def send_event(self):
        """
        Incrementa o relógio antes de enviar uma mensagem.
        Retorna o timestamp a ser enviado.
        """
        with self._lock:
            self.time += 1
            return self.time

    def receive_event(self, received_timestamp):
        """
        Atualiza o relógio ao receber uma mensagem.
        """
        with self._lock:
            self.time = max(self.time, received_timestamp) + 1
            return self.time

    def get_time(self):
        with self._lock:
            return self.time