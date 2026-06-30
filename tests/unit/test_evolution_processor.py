"""
tests/unit/test_evolution_processor.py

Testes da Camada de Evolução Temporal.
Critérios de aceite — Plano de Implementação, Fase 8.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from models.output_models import (
    CategoriaAgregada,
    DistribuicaoTempoResposta,
    ResultadoMatematico,
    ResultadoSemantico,
)
from processors.evolution_processor import LoteAnteriorComparavel, processar_evolucao_temporal


def _matematica(taxa_resposta: float = 60.0, tempo_medio: float = 100.0) -> ResultadoMatematico:
    return ResultadoMatematico(
        taxa_resposta=taxa_resposta,
        taxa_silencio=100.0 - taxa_resposta,
        taxa_visualizado_sem_resposta=0.0,
        taxa_nao_entrega=0.0,
        tempo_medio_resposta_minutos=tempo_medio,
        tempo_mediano_resposta_minutos=tempo_medio,
        distribuicao_tempo_resposta=DistribuicaoTempoResposta(0.0, 0.0, 0.0, 0.0),
        tamanho_medio_resposta_caracteres=50,
        participacao_valida=90.0,
        qualidade_participacao_media=70.0,
    )


def _semantica(familia: str, incidencia: float) -> ResultadoSemantico:
    categoria = CategoriaAgregada(
        codigo_catalogo=f"{familia[:4]}-001",
        familia=familia,
        subcategoria="subcategoria teste",
        nicho=None,
        incidencia_percentual=incidencia,
        confianca_media=90.0,
        intensidade_semantica_media=50.0,
        ocorrencias=1,
        evidencias=[],
    )
    return ResultadoSemantico(dores_identificadas=[], forcas_identificadas=[categoria])


def test_primeiro_lote_sem_historico_retorna_none():
    """Primeiro lote de uma empresa (sem histórico) -> campo omitido (None), não null."""
    resultado = processar_evolucao_temporal(
        empresa_atual="empresa_teste",
        versao_catalogo_atual="1.1",
        matematica_atual=_matematica(),
        semantica_atual=None,
        lote_anterior=None,
    )
    assert resultado is None
    print("OK: test_primeiro_lote_sem_historico_retorna_none")


def test_dois_lotes_mesma_versao_comparabilidade_total():
    """2 lotes sintéticos da mesma versao_catalogo -> variação calculada corretamente."""
    lote_anterior = LoteAnteriorComparavel(
        lote_id="LOTE-ANTERIOR",
        empresa="empresa_teste",
        versao_catalogo="1.1",
        matematica=_matematica(taxa_resposta=55.0, tempo_medio=120.0),
        semantica=_semantica("ATENDIMENTO", 72.0),
    )

    resultado = processar_evolucao_temporal(
        empresa_atual="empresa_teste",
        versao_catalogo_atual="1.1",
        matematica_atual=_matematica(taxa_resposta=62.0, tempo_medio=100.0),
        semantica_atual=_semantica("ATENDIMENTO", 88.0),
        lote_anterior=lote_anterior,
    )

    assert resultado is not None
    assert resultado.comparabilidade == "total"
    assert resultado.lote_comparado_id == "LOTE-ANTERIOR"

    variacao_taxa = next(v for v in resultado.variacoes_matematica if v.indicador == "taxa_resposta")
    assert variacao_taxa.anterior == 55.0
    assert variacao_taxa.atual == 62.0
    assert variacao_taxa.variacao == 7.0

    variacao_familia = next(v for v in resultado.variacoes_familia if v.familia == "ATENDIMENTO")
    assert variacao_familia.percentual_anterior == 72.0
    assert variacao_familia.percentual_atual == 88.0
    assert variacao_familia.variacao == 16.0
    assert variacao_familia.tendencia == "subindo"
    print("OK: test_dois_lotes_mesma_versao_comparabilidade_total")


def test_dois_lotes_versao_catalogo_diferente_comparabilidade_parcial():
    """2 lotes com versao_catalogo diferente -> comparabilidade: 'parcial' sinalizada."""
    lote_anterior = LoteAnteriorComparavel(
        lote_id="LOTE-ANTERIOR",
        empresa="empresa_teste",
        versao_catalogo="1.0",  # versão diferente da atual
        matematica=_matematica(),
        semantica=_semantica("ATENDIMENTO", 72.0),
    )

    resultado = processar_evolucao_temporal(
        empresa_atual="empresa_teste",
        versao_catalogo_atual="1.1",
        matematica_atual=_matematica(),
        semantica_atual=_semantica("ATENDIMENTO", 88.0),
        lote_anterior=lote_anterior,
    )

    assert resultado is not None
    assert resultado.comparabilidade == "parcial"
    print("OK: test_dois_lotes_versao_catalogo_diferente_comparabilidade_parcial")


def test_comparar_lotes_de_empresas_diferentes_levanta_erro():
    """Comparar lotes de empresas diferentes nunca é silencioso — levanta ValueError."""
    lote_anterior = LoteAnteriorComparavel(
        lote_id="LOTE-OUTRA-EMPRESA",
        empresa="empresa_diferente",
        versao_catalogo="1.1",
        matematica=_matematica(),
        semantica=None,
    )

    erro_levantado = False
    try:
        processar_evolucao_temporal(
            empresa_atual="empresa_teste",
            versao_catalogo_atual="1.1",
            matematica_atual=_matematica(),
            semantica_atual=None,
            lote_anterior=lote_anterior,
        )
    except ValueError as exc:
        erro_levantado = True
        assert "empresa_diferente" in str(exc)
        assert "empresa_teste" in str(exc)

    assert erro_levantado, "ValueError não foi levantado para empresas diferentes"
    print("OK: test_comparar_lotes_de_empresas_diferentes_levanta_erro")


def test_variacao_pequena_classificada_como_estavel():
    """Variação dentro do limiar de estabilidade -> tendência 'estavel', não 'subindo'/'caindo'."""
    lote_anterior = LoteAnteriorComparavel(
        lote_id="LOTE-ANTERIOR",
        empresa="empresa_teste",
        versao_catalogo="1.1",
        matematica=_matematica(),
        semantica=_semantica("PRODUTO", 50.0),
    )

    resultado = processar_evolucao_temporal(
        empresa_atual="empresa_teste",
        versao_catalogo_atual="1.1",
        matematica_atual=_matematica(),
        semantica_atual=_semantica("PRODUTO", 51.5),  # variação de 1.5, abaixo do limiar de 3.0
        lote_anterior=lote_anterior,
    )

    variacao_produto = next(v for v in resultado.variacoes_familia if v.familia == "PRODUTO")
    assert variacao_produto.tendencia == "estavel"
    print("OK: test_variacao_pequena_classificada_como_estavel")


def test_variacao_negativa_classificada_como_caindo():
    """Variação negativa acima do limiar -> tendência 'caindo'."""
    lote_anterior = LoteAnteriorComparavel(
        lote_id="LOTE-ANTERIOR",
        empresa="empresa_teste",
        versao_catalogo="1.1",
        matematica=_matematica(),
        semantica=_semantica("ENTREGA", 85.0),
    )

    resultado = processar_evolucao_temporal(
        empresa_atual="empresa_teste",
        versao_catalogo_atual="1.1",
        matematica_atual=_matematica(),
        semantica_atual=_semantica("ENTREGA", 58.0),
        lote_anterior=lote_anterior,
    )

    variacao_entrega = next(v for v in resultado.variacoes_familia if v.familia == "ENTREGA")
    assert variacao_entrega.variacao == -27.0
    assert variacao_entrega.tendencia == "caindo"
    print("OK: test_variacao_negativa_classificada_como_caindo")


def test_determinismo_mesma_entrada_mesmo_resultado():
    """Para a mesma entrada, o resultado é sempre idêntico em execuções repetidas."""
    lote_anterior = LoteAnteriorComparavel(
        lote_id="LOTE-ANTERIOR",
        empresa="empresa_teste",
        versao_catalogo="1.1",
        matematica=_matematica(taxa_resposta=55.0),
        semantica=_semantica("ATENDIMENTO", 72.0),
    )

    resultados = []
    for _ in range(20):
        r = processar_evolucao_temporal(
            empresa_atual="empresa_teste",
            versao_catalogo_atual="1.1",
            matematica_atual=_matematica(taxa_resposta=62.0),
            semantica_atual=_semantica("ATENDIMENTO", 88.0),
            lote_anterior=lote_anterior,
        )
        resultados.append((r.comparabilidade, r.variacoes_familia[0].variacao))

    assert all(r == resultados[0] for r in resultados)
    print("OK: test_determinismo_mesma_entrada_mesmo_resultado")


def test_nenhuma_chamada_a_ia():
    """Verificação estática: este processor não importa ClienteIA nem Groq."""
    import processors.evolution_processor as mod

    codigo_fonte = Path(mod.__file__).read_text(encoding="utf-8")
    proibidos = ["ClienteIA", "ai_classifier", "import groq", "from groq", "import random"]
    for termo in proibidos:
        assert termo not in codigo_fonte, f"Encontrada referência proibida: {termo!r}"
    print("OK: test_nenhuma_chamada_a_ia")


if __name__ == "__main__":
    test_primeiro_lote_sem_historico_retorna_none()
    test_dois_lotes_mesma_versao_comparabilidade_total()
    test_dois_lotes_versao_catalogo_diferente_comparabilidade_parcial()
    test_comparar_lotes_de_empresas_diferentes_levanta_erro()
    test_variacao_pequena_classificada_como_estavel()
    test_variacao_negativa_classificada_como_caindo()
    test_determinismo_mesma_entrada_mesmo_resultado()
    test_nenhuma_chamada_a_ia()
    print("\nTodos os testes da Fase 8 (Camada de Evolução Temporal) passaram.")
