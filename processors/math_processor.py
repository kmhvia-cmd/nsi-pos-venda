"""
processors/math_processor.py

Camada Matemática do Motor NSI.
Contrato Oficial do Motor NSI v3.1, Seção 2.

Responsabilidade: calcular indicadores puramente operacionais do lote,
sem interpretar o conteúdo do texto. Não depende de IA, não depende
do catálogo — é a camada de execução mais barata e mais confiável do
pipeline (Especificação Técnica v1, Seção 7.2).

Esta camada NUNCA falha por indisponibilidade externa: roda sempre,
mesmo quando a Camada Semântica está em fallback (Contrato Seção 1.2).
"""

from __future__ import annotations

from datetime import datetime
from statistics import mean, median

from models.input_models import Lote, RespostaCliente
from models.output_models import DistribuicaoTempoResposta, ResultadoMatematico


# ---------------------------------------------------------------------------
# Qualidade da Participação — definição operacional desta implementação
# ---------------------------------------------------------------------------
#
# O Contrato (Seção 2, item "Qualidade da Participação" / Seção 9.11) define
# o QUE essa métrica mede — riqueza lexical, quantidade de evidências,
# profundidade, contexto, detalhamento — mas deixa a fórmula exata para a
# fase de implementação, sem fechar pesos. Esta é a decisão de implementação
# tomada aqui, documentada para que qualquer revisão futura saiba exatamente
# o que está sendo calculado e possa recalibrar sem arqueologia de código.
#
# Três sinais combinados, cada um normalizado a 0-100 antes da média:
#
#   1. Riqueza lexical (peso 0.4): proporção de palavras únicas sobre o
#      total de palavras da resposta (type-token ratio). Respostas que só
#      repetem a mesma palavra têm riqueza lexical baixa mesmo sendo longas.
#
#   2. Profundidade por tamanho (peso 0.35): tamanho da resposta em
#      caracteres, normalizado contra um teto de referência (200 caracteres
#      = profundidade máxima nesta escala). Acima do teto, satura em 100 —
#      não recompensa infinitamente respostas cada vez mais longas.
#
#   3. Presença de contexto (peso 0.25): proporção de palavras "de conteúdo"
#      (mais de 3 letras) sobre o total — penaliza respostas dominadas por
#      monossílabos ou partículas sem informação ("é", "tá", "ok", "sim").
#
# Resposta vazia ou só espaços → qualidade_participacao = 0.0, sem excecão.
_TETO_CARACTERES_PROFUNDIDADE = 200
_PESO_RIQUEZA_LEXICAL = 0.40
_PESO_PROFUNDIDADE_TAMANHO = 0.35
_PESO_CONTEXTO = 0.25


def _calcular_qualidade_participacao(texto: str) -> float:
    """
    Calcula a Qualidade da Participação de uma resposta individual.
    Ver nota de definição operacional acima. Retorna sempre 0.0-100.0.
    """
    texto = texto.strip()
    if not texto:
        return 0.0

    palavras = texto.split()
    if not palavras:
        return 0.0

    # 1. Riqueza lexical (type-token ratio), case-insensitive
    palavras_normalizadas = [p.lower().strip(".,!?;:\"'") for p in palavras]
    palavras_normalizadas = [p for p in palavras_normalizadas if p]
    if not palavras_normalizadas:
        return 0.0
    riqueza_lexical = (
        len(set(palavras_normalizadas)) / len(palavras_normalizadas)
    ) * 100

    # 2. Profundidade por tamanho, com teto de saturação
    profundidade_tamanho = min(
        (len(texto) / _TETO_CARACTERES_PROFUNDIDADE) * 100, 100.0
    )

    # 3. Presença de contexto: proporção de palavras com mais de 3 letras
    palavras_com_contexto = [p for p in palavras_normalizadas if len(p) > 3]
    presenca_contexto = (
        len(palavras_com_contexto) / len(palavras_normalizadas)
    ) * 100

    qualidade = (
        riqueza_lexical * _PESO_RIQUEZA_LEXICAL
        + profundidade_tamanho * _PESO_PROFUNDIDADE_TAMANHO
        + presenca_contexto * _PESO_CONTEXTO
    )

    return round(min(max(qualidade, 0.0), 100.0), 1)


def _classificar_faixa_tempo(minutos: float) -> str:
    """Classifica um tempo de resposta em uma das 4 faixas do Contrato Seção 2."""
    horas = minutos / 60
    if horas <= 1:
        return "ate_1h"
    if horas <= 24:
        return "ate_24h"
    if horas <= 24 * 3:
        return "ate_3_dias"
    return "acima_3_dias"


def processar_matematica(lote: Lote) -> ResultadoMatematico:
    """
    Calcula a saída completa da Camada Matemática para um lote.
    Contrato Oficial do Motor NSI v3.1, Seção 2.

    Não lança excecão para lote vazio ou sem respostas — retorna uma
    estrutura válida com zeros, conforme exigido pelo critério de aceite
    da Fase 1 (Plano de Implementação).
    """
    enviadas = lote.quantidade_enviada
    respostas = lote.respostas

    respondidas = [r for r in respostas if r.status_entrega == "respondido"]
    visualizado_sem_resposta = [
        r for r in respostas if r.status_entrega == "visualizado_sem_resposta"
    ]
    nao_entregues = [r for r in respostas if r.status_entrega == "nao_entregue"]

    # --- Taxas básicas -----------------------------------------------------
    if enviadas > 0:
        taxa_resposta = round(len(respondidas) / enviadas * 100, 1)
        taxa_silencio = round((enviadas - len(respondidas)) / enviadas * 100, 1)
        taxa_visualizado_sem_resposta = round(
            len(visualizado_sem_resposta) / enviadas * 100, 1
        )
        taxa_nao_entrega = round(len(nao_entregues) / enviadas * 100, 1)
    else:
        taxa_resposta = 0.0
        taxa_silencio = 0.0
        taxa_visualizado_sem_resposta = 0.0
        taxa_nao_entrega = 0.0

    # --- Tempo de resposta ---------------------------------------------------
    tempos_minutos: list[float] = []
    for r in respondidas:
        if r.data_resposta is not None:
            delta = r.data_resposta - r.data_envio_mensagem
            tempos_minutos.append(delta.total_seconds() / 60)

    if tempos_minutos:
        tempo_medio_resposta_minutos = round(mean(tempos_minutos), 1)
        tempo_mediano_resposta_minutos = round(median(tempos_minutos), 1)
    else:
        tempo_medio_resposta_minutos = 0.0
        tempo_mediano_resposta_minutos = 0.0

    # --- Distribuição de tempo de resposta ----------------------------------
    contagem_faixas = {"ate_1h": 0, "ate_24h": 0, "ate_3_dias": 0, "acima_3_dias": 0}
    for minutos in tempos_minutos:
        contagem_faixas[_classificar_faixa_tempo(minutos)] += 1

    total_com_tempo = len(tempos_minutos)
    if total_com_tempo > 0:
        distribuicao = DistribuicaoTempoResposta(
            ate_1h=round(contagem_faixas["ate_1h"] / total_com_tempo * 100, 1),
            ate_24h=round(contagem_faixas["ate_24h"] / total_com_tempo * 100, 1),
            ate_3_dias=round(contagem_faixas["ate_3_dias"] / total_com_tempo * 100, 1),
            acima_3_dias=round(
                contagem_faixas["acima_3_dias"] / total_com_tempo * 100, 1
            ),
        )
    else:
        distribuicao = DistribuicaoTempoResposta(
            ate_1h=0.0, ate_24h=0.0, ate_3_dias=0.0, acima_3_dias=0.0
        )

    # --- Tamanho e participação válida --------------------------------------
    respostas_com_texto = [r for r in respondidas if r.resposta.strip()]

    if respondidas:
        tamanhos = [len(r.resposta) for r in respostas_com_texto]
        tamanho_medio_resposta_caracteres = (
            round(mean(tamanhos)) if tamanhos else 0
        )
        participacao_valida = round(
            len(respostas_com_texto) / len(respondidas) * 100, 1
        )
    else:
        tamanho_medio_resposta_caracteres = 0
        participacao_valida = 0.0

    # --- Qualidade da participação -------------------------------------------
    if respostas_com_texto:
        qualidades = [
            _calcular_qualidade_participacao(r.resposta) for r in respostas_com_texto
        ]
        qualidade_participacao_media = round(mean(qualidades), 1)
    else:
        qualidade_participacao_media = 0.0

    return ResultadoMatematico(
        taxa_resposta=taxa_resposta,
        taxa_silencio=taxa_silencio,
        taxa_visualizado_sem_resposta=taxa_visualizado_sem_resposta,
        taxa_nao_entrega=taxa_nao_entrega,
        tempo_medio_resposta_minutos=tempo_medio_resposta_minutos,
        tempo_mediano_resposta_minutos=tempo_mediano_resposta_minutos,
        distribuicao_tempo_resposta=distribuicao,
        tamanho_medio_resposta_caracteres=tamanho_medio_resposta_caracteres,
        participacao_valida=participacao_valida,
        qualidade_participacao_media=qualidade_participacao_media,
    )
