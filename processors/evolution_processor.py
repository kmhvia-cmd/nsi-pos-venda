"""
processors/evolution_processor.py

Camada de Evolução Temporal do Motor NSI.
Contrato Oficial do Motor NSI v3.1, Seção 6.

Responsabilidade: comparar indicadores entre o lote atual e um lote
anterior da MESMA empresa, calculando diferenças objetivas.

REGRAS OBRIGATÓRIAS DESTA IMPLEMENTAÇÃO (decisão aprovada, Fase 8):
    - Compara somente lotes da mesma empresa (validado explicitamente).
    - Usa somente resultados estruturados já produzidos pelo Motor
      (ResultadoMatematico e ResultadoSemantico das Fases 1 e 5) —
      nunca recalcula nada a partir de texto bruto.
    - Nunca compara lotes de versões diferentes do catálogo sem
      sinalizar `comparabilidade: "parcial"` (Contrato Seção 6.1).
    - Comparação 100% determinística — nenhuma chamada a IA, nenhuma
      aleatoriedade. Para a mesma entrada, o resultado é sempre idêntico.
    - "Tendência" (subindo/estável/caindo) é calculada por um limiar
      numérico fixo e documentado abaixo — NUNCA decidida por IA. A IA
      só poderá produzir INTERPRETAÇÃO desses números na Camada
      Executiva (Contrato Seção 7), nunca nesta camada.

Esta camada NUNCA aparece na saída do motor quando não há lote anterior
comparável (Contrato Seção 6.2) — ausência completa, não `null`.
"""

from __future__ import annotations

from dataclasses import dataclass

from catalog.versioning import mesma_versao
from engine.config import LIMIAR_ESTABILIDADE_PERCENTUAL_EVOLUCAO
from models.output_models import (
    Comparabilidade,
    ResultadoEvolucaoTemporal,
    ResultadoMatematico,
    ResultadoSemantico,
    VariacaoFamilia,
    VariacaoMatematica,
)

# Limiar de tendência: configuração calibrável, ver engine/config.py
# (Fase 8 aprovação: "esse valor passa a ser considerado um parâmetro de
# configuração do Motor, e não uma constante fixa de negócio").


@dataclass
class LoteAnteriorComparavel:
    """
    Estrutura mínima de um lote anterior, já processado, necessária para
    a comparação. Não é o Lote de entrada (models/input_models.py) — é o
    resultado JÁ CALCULADO de uma execução anterior do motor para a
    mesma empresa, conforme a Especificação Técnica Seção 4
    (evolution_processor depende de "acesso de leitura a saídas
    anteriores persistidas", fora do escopo deste motor).
    """
    lote_id: str
    empresa: str
    versao_catalogo: str
    matematica: ResultadoMatematico
    semantica: ResultadoSemantico | None


def _classificar_tendencia(variacao: float) -> str:
    """
    Classifica a variação em "subindo", "estavel" ou "caindo", usando
    o limiar configurável (engine/config.py). Determinístico, sem IA.
    """
    if abs(variacao) < LIMIAR_ESTABILIDADE_PERCENTUAL_EVOLUCAO:
        return "estavel"
    return "subindo" if variacao > 0 else "caindo"


def _comparar_familias(
    semantica_atual: ResultadoSemantico | None,
    semantica_anterior: ResultadoSemantico | None,
) -> list[VariacaoFamilia]:
    """
    Compara incidência por família entre o lote atual e o anterior.
    Usa apenas os ResultadoSemantico já calculados (Fase 5) — nunca
    reprocessa texto.
    """
    if semantica_atual is None or semantica_anterior is None:
        return []

    def _incidencia_por_familia(semantica: ResultadoSemantico) -> dict[str, float]:
        mapa: dict[str, float] = {}
        for categoria in semantica.dores_identificadas + semantica.forcas_identificadas:
            # Se houver múltiplas subcategorias da mesma família, soma a
            # incidência (aproximação determinística simples — decisão de
            # implementação documentada, sem heurística adicional).
            mapa[categoria.familia] = mapa.get(categoria.familia, 0.0) + categoria.incidencia_percentual
        return mapa

    incidencia_atual = _incidencia_por_familia(semantica_atual)
    incidencia_anterior = _incidencia_por_familia(semantica_anterior)

    todas_familias = sorted(set(incidencia_atual) | set(incidencia_anterior))

    variacoes = []
    for familia in todas_familias:
        percentual_atual = round(incidencia_atual.get(familia, 0.0), 1)
        percentual_anterior = round(incidencia_anterior.get(familia, 0.0), 1)
        variacao = round(percentual_atual - percentual_anterior, 1)

        variacoes.append(
            VariacaoFamilia(
                familia=familia,
                percentual_anterior=percentual_anterior,
                percentual_atual=percentual_atual,
                variacao=variacao,
                tendencia=_classificar_tendencia(variacao),
            )
        )

    return variacoes


_INDICADORES_MATEMATICA_COMPARAVEIS = (
    "taxa_resposta", "taxa_silencio", "tempo_medio_resposta_minutos",
    "participacao_valida", "qualidade_participacao_media",
)


def _comparar_matematica(
    atual: ResultadoMatematico, anterior: ResultadoMatematico
) -> list[VariacaoMatematica]:
    """Compara os indicadores matemáticos comparáveis entre dois lotes."""
    variacoes = []
    for indicador in _INDICADORES_MATEMATICA_COMPARAVEIS:
        valor_atual = getattr(atual, indicador)
        valor_anterior = getattr(anterior, indicador)
        variacoes.append(
            VariacaoMatematica(
                indicador=indicador,
                anterior=valor_anterior,
                atual=valor_atual,
                variacao=round(valor_atual - valor_anterior, 1),
            )
        )
    return variacoes


def processar_evolucao_temporal(
    empresa_atual: str,
    versao_catalogo_atual: str,
    matematica_atual: ResultadoMatematico,
    semantica_atual: ResultadoSemantico | None,
    lote_anterior: LoteAnteriorComparavel | None,
) -> ResultadoEvolucaoTemporal | None:
    """
    Calcula a Evolução Temporal comparando o lote atual com o anterior.

    Retorna None quando não há lote anterior comparável — o chamador
    (engine/pipeline.py) deve OMITIR completamente o campo
    `evolucao_temporal` da saída final neste caso, nunca atribuir `null`
    (Contrato Seção 6.2).

    Levanta ValueError se `lote_anterior` pertencer a empresa diferente
    da atual — comparar lotes de empresas diferentes nunca é uma
    ambiguidade silenciosa, é erro de uso da função.
    """
    if lote_anterior is None:
        return None

    if lote_anterior.empresa != empresa_atual:
        raise ValueError(
            f"Lote anterior pertence à empresa {lote_anterior.empresa!r}, "
            f"mas a comparação foi solicitada para {empresa_atual!r}. "
            f"A Evolução Temporal só compara lotes da mesma empresa."
        )

    comparabilidade: Comparabilidade = (
        "total"
        if mesma_versao(versao_catalogo_atual, lote_anterior.versao_catalogo)
        else "parcial"
    )

    variacoes_familia = _comparar_familias(semantica_atual, lote_anterior.semantica)
    variacoes_matematica = _comparar_matematica(matematica_atual, lote_anterior.matematica)

    return ResultadoEvolucaoTemporal(
        lote_comparado_id=lote_anterior.lote_id,
        comparabilidade=comparabilidade,
        variacoes_familia=variacoes_familia,
        variacoes_matematica=variacoes_matematica,
    )
