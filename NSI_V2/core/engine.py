class NSIEngine:
    """
    Motor principal do NSI V2.
    Responsável por analisar respostas de pós-venda
    e retornar as 10 maiores fricções em escala 0–100.
    """

    def _init_(self, dores_config):
        """
        dores_config: lista ou dict com as 110 dores cadastradas.
        """
        self.dores = dores_config

    def analisar_respostas(self, respostas):
        """
        respostas: lista de textos recebidos do WhatsApp.
        """
        resultados = {}

        for resposta in respostas:
            # Aqui entra lógica semântica real futuramente
            for dor in self.dores:
                if dor.lower() in resposta.lower():
                    resultados[dor] = resultados.get(dor, 0) + 1

        # Ordena por frequência
        ordenado = sorted(resultados.items(), key=lambda x: x[1], reverse=True)

        # Retorna Top 10 com escala 0–100
        top_10 = [
            {"dor": dor, "score": min(freq * 10, 100)}
            for dor, freq in ordenado[:10]
        ]

        return top_10