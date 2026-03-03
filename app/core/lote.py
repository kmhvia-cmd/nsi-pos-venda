from datetime import datetime, timedelta


class Lote:
    def __init__(self, data_criacao: datetime):
        self.data_criacao = data_criacao
        self.status = "aguardando_d8"
        self.disparado = False
        self.respostas_recebidas = 0

    def dias_passados(self):
        return (datetime.now() - self.data_criacao).days

    def verificar_d8(self):
        if self.dias_passados() >= 8:
            return True
        return False

    def progresso(self):
        dias = self.dias_passados()
        if dias >= 8:
            return 100
        return int((dias / 8) * 100)
