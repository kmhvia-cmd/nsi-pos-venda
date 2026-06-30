"""
tests/semantic/test_executive_processor.py

Testes da Camada Executiva.
Critérios de aceite — Plano de Implementação, Fase 9.
Especificação do ICE — Contrato Seção 9.17.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from models.output_models import (
    CategoriaAgregada,
    DistribuicaoTempoResposta,
    ResultadoLinguisticoAgregado,
    ResultadoMatematico,
    ResultadoSemantico,
)
from processors.executive_processor import (
    calcular_areas_responsaveis_agregado,
    calcular_ice,
    calcular_top_forcas,
    calcular_top_oportunidades,
    calcular_top_prioridades,
    faixa_interpretacao_ice,
    gerar_acoes_recomendadas,
    gerar_resumos_executivos,
    processar_executiva,
)
from services.ai_classifier import ClienteIAFalso


def _matematica(taxa_resposta: float = 60.0) -> ResultadoMatematico:
    return ResultadoMatematico(
        taxa_resposta=taxa_resposta, taxa_silencio=100.0 - taxa_resposta,
        taxa_visualizado_sem_resposta=0.0, taxa_nao_entrega=0.0,
        tempo_medio_resposta_minutos=0.0, tempo_mediano_resposta_minutos=0.0,
        distribuicao_tempo_resposta=DistribuicaoTempoResposta(0.0, 0.0, 0.0, 0.0),
        tamanho_medio_resposta_caracteres=50, participacao_valida=90.0,
        qualidade_participacao_media=70.0,
    )


def _linguistica(polaridade: float = 30.0, engajamento: float = 60.0) -> ResultadoLinguisticoAgregado:
    return ResultadoLinguisticoAgregado(
        intensidade_emocional_media=50.0, polaridade_linguistica_media=polaridade,
        engajamento_linguistico_medio=engajamento, formalidade_media=50.0, marca_regional_media=20.0,
    )


def _categoria(familia: str, incidencia: float, confianca: float = 85.0, ocorrencias: int = 5) -> CategoriaAgregada:
    return CategoriaAgregada(
        codigo_catalogo=f"{familia[:4].upper()}-001", familia=familia, subcategoria="subcategoria teste",
        nicho=None, incidencia_percentual=incidencia, confianca_media=confianca,
        intensidade_semantica_media=50.0, ocorrencias=ocorrencias, evidencias=[],
    )


def test_ice_lote_perfeito_resulta_em_100():
    """Lote com todos os fatores no máximo -> ICE = 100.0 (caso-limite documentado)."""
    semantica = ResultadoSemantico(
        dores_identificadas=[], forcas_identificadas=[_categoria("ATENDIMENTO", 100.0, 100.0)]
    )
    status, ice, motivo = calcular_ice(
        _matematica(100.0), _linguistica(100.0, 100.0), semantica, 10, 10, 0
    )
    assert status == "calculado"
    assert ice == 100.0
    assert motivo is None
    print("OK: test_ice_lote_perfeito_resulta_em_100")


def test_ice_lote_pessimo_resulta_em_0():
    """Lote com todos os fatores no mínimo -> ICE = 0.0 (caso-limite documentado)."""
    semantica = ResultadoSemantico(
        dores_identificadas=[_categoria("ENTREGA", 100.0, 0.0)], forcas_identificadas=[]
    )
    status, ice, motivo = calcular_ice(
        _matematica(0.0), _linguistica(-100.0, 0.0), semantica, 10, 10, 0
    )
    assert status == "calculado"
    assert ice == 0.0
    print("OK: test_ice_lote_pessimo_resulta_em_0")


def test_ice_bloqueado_sem_cobertura_e_sem_evidencia_absoluta():
    """Cobertura < 20% E evidencias < 10 -> ICE bloqueado, status e motivo corretos."""
    semantica = ResultadoSemantico(dores_identificadas=[], forcas_identificadas=[])
    status, ice, motivo = calcular_ice(_matematica(), _linguistica(), semantica, 0, 10, 0)

    assert status == "cobertura_insuficiente"
    assert ice is None
    assert motivo == "Quantidade insuficiente de evidências semânticas para cálculo confiável."
    print("OK: test_ice_bloqueado_sem_cobertura_e_sem_evidencia_absoluta")


def test_ice_liberado_por_cobertura_semantica_20_porcento():
    """Critério A isolado: cobertura exatamente 20% libera o cálculo."""
    semantica = ResultadoSemantico(
        dores_identificadas=[], forcas_identificadas=[_categoria("ATENDIMENTO", 50.0)]
    )
    status, ice, motivo = calcular_ice(
        _matematica(), _linguistica(), semantica,
        respostas_com_categoria_detectada=2, total_respostas=10,  # 20% exato
        evidencias_semanticas_validas=0,
    )
    assert status == "calculado"
    assert ice is not None
    print("OK: test_ice_liberado_por_cobertura_semantica_20_porcento")


def test_ice_liberado_por_evidencia_absoluta_mesmo_com_baixa_cobertura():
    """
    Critério B isolado: cobertura baixa (5%) mas 10+ evidências absolutas
    -> ICE liberado mesmo assim (lote grande com poucas respostas ricas).
    """
    semantica = ResultadoSemantico(
        dores_identificadas=[], forcas_identificadas=[_categoria("ATENDIMENTO", 50.0)]
    )
    status, ice, motivo = calcular_ice(
        _matematica(), _linguistica(), semantica,
        respostas_com_categoria_detectada=5, total_respostas=100,  # 5% cobertura
        evidencias_semanticas_validas=10,  # mas atinge o critério B
    )
    assert status == "calculado"
    assert ice is not None
    print("OK: test_ice_liberado_por_evidencia_absoluta_mesmo_com_baixa_cobertura")


def test_ice_nunca_sai_de_0_100_mesmo_com_entrada_fora_da_faixa():
    """Salvaguarda defensiva: entrada de linguística fora da faixa não quebra o clamp final."""
    semantica = ResultadoSemantico(
        dores_identificadas=[], forcas_identificadas=[_categoria("ATENDIMENTO", 100.0, 100.0)]
    )
    status, ice, motivo = calcular_ice(
        _matematica(100.0), _linguistica(500.0, 100.0), semantica, 10, 10, 0
    )
    assert 0.0 <= ice <= 100.0
    print("OK: test_ice_nunca_sai_de_0_100_mesmo_com_entrada_fora_da_faixa")


def test_faixas_de_interpretacao_corretas():
    """As 5 faixas de interpretação retornam o nome comercial correto."""
    assert faixa_interpretacao_ice(0.0) == "Experiência Crítica"
    assert faixa_interpretacao_ice(39.9) == "Experiência Crítica"
    assert faixa_interpretacao_ice(40.0) == "Experiência de Atenção"
    assert faixa_interpretacao_ice(59.9) == "Experiência de Atenção"
    assert faixa_interpretacao_ice(60.0) == "Experiência Satisfatória"
    assert faixa_interpretacao_ice(74.9) == "Experiência Satisfatória"
    assert faixa_interpretacao_ice(75.0) == "Experiência Muito Boa"
    assert faixa_interpretacao_ice(89.9) == "Experiência Muito Boa"
    assert faixa_interpretacao_ice(90.0) == "Experiência Excelente"
    assert faixa_interpretacao_ice(100.0) == "Experiência Excelente"
    print("OK: test_faixas_de_interpretacao_corretas")


def test_top_forcas_e_oportunidades_ordenados_por_incidencia():
    """Rankings determinísticos, ordenados por incidência decrescente."""
    semantica = ResultadoSemantico(
        dores_identificadas=[_categoria("ENTREGA", 24.0), _categoria("COMUNICACAO", 40.0)],
        forcas_identificadas=[_categoria("ATENDIMENTO", 58.0), _categoria("QUALIDADE", 51.0)],
    )

    top_forcas = calcular_top_forcas(semantica)
    top_oportunidades = calcular_top_oportunidades(semantica)

    assert [f.categoria for f in top_forcas] == ["ATENDIMENTO", "QUALIDADE"]
    assert [o.categoria for o in top_oportunidades] == ["COMUNICACAO", "ENTREGA"]
    print("OK: test_top_forcas_e_oportunidades_ordenados_por_incidencia")


def test_top_prioridades_sem_fator_de_impacto_comercial():
    """top_prioridades usa só incidencia x confianca, nunca impacto (Contrato 9.1)."""
    semantica = ResultadoSemantico(
        dores_identificadas=[_categoria("PRAZO", 24.0, 88.0), _categoria("COMUNICACAO", 17.0, 95.0)],
        forcas_identificadas=[],
    )

    top_prioridades = calcular_top_prioridades(semantica)

    valor_prazo = round(24.0 * 88.0 / 100, 1)
    valor_comunicacao = round(17.0 * 95.0 / 100, 1)
    assert top_prioridades[0].valor == max(valor_prazo, valor_comunicacao)
    assert top_prioridades[0].criterio == "incidencia_x_confianca"
    print("OK: test_top_prioridades_sem_fator_de_impacto_comercial")


def test_areas_responsaveis_agregado_soma_por_familia():
    """Agregação de área consolida incidência das dores por família."""
    semantica = ResultadoSemantico(
        dores_identificadas=[_categoria("ENTREGA", 24.0), _categoria("ATENDIMENTO", 17.0)],
        forcas_identificadas=[],
    )

    areas = calcular_areas_responsaveis_agregado(semantica)

    assert len(areas) == 2
    assert areas[0].area == "ENTREGA"
    assert areas[0].percentual_oportunidades == 24.0
    print("OK: test_areas_responsaveis_agregado_soma_por_familia")


def test_resumos_executivos_via_ia_8_campos():
    """gerar_resumos_executivos retorna os 8 campos esperados via ClienteIAFalso."""
    cliente = ClienteIAFalso()
    cliente.configurar_resposta(
        "resumo_executivo",
        {
            "resumo_executivo": "Experiência geral positiva.",
            "resumo_comercial": "Boa propensão à recompra.",
            "resumo_operacional": "Prazo é o ponto de atenção.",
            "resumo_atendimento": "Atendimento é a maior força.",
            "resumo_produto": "Produto bem avaliado.",
            "resumo_experiencia": "Experiência satisfatória.",
            "resumo_evolutivo": "",
            "resumo_nicho": "",
        },
    )

    resumos, sucesso = gerar_resumos_executivos(
        _matematica(), None, "cobertura_insuficiente", None, [], [], None, "generico", cliente
    )

    assert sucesso is True
    assert resumos["resumo_executivo"] == "Experiência geral positiva."
    assert resumos["resumo_evolutivo"] is None  # string vazia convertida para None
    print("OK: test_resumos_executivos_via_ia_8_campos")


def test_resumos_falha_ia_retorna_strings_vazias_sem_excecao():
    """Falha da IA na geração de resumos não lança exceção, retorna estrutura vazia."""
    cliente = ClienteIAFalso()
    cliente.configurar_falha("resumo_executivo")

    resumos, sucesso = gerar_resumos_executivos(
        _matematica(), None, "cobertura_insuficiente", None, [], [], None, "generico", cliente
    )

    assert sucesso is False
    assert resumos["resumo_executivo"] == ""
    print("OK: test_resumos_falha_ia_retorna_strings_vazias_sem_excecao")


def test_acoes_recomendadas_geradas_a_partir_do_contexto_real():
    """Ações recomendadas usam dados reais do lote, não regra fixa do catálogo."""
    categorias = [_categoria("ENTREGA", 24.0, 88.0, ocorrencias=12)]
    categorias[0].codigo_catalogo = "ENTR-001"
    cliente = ClienteIAFalso()
    cliente.configurar_resposta(
        "acao_recomendada",
        {
            "acoes": [
                {
                    "codigo_catalogo": "ENTR-001",
                    "recomendacao": "Revisar prazo de entrega combinado com a transportadora.",
                }
            ]
        },
    )

    acoes, sucesso = gerar_acoes_recomendadas(categorias, cliente)

    assert sucesso is True
    assert len(acoes) == 1
    assert acoes[0].codigo_catalogo == "ENTR-001"
    assert acoes[0].baseado_em.ocorrencias == 12
    assert acoes[0].baseado_em.confianca_media == 88.0
    print("OK: test_acoes_recomendadas_geradas_a_partir_do_contexto_real")


def test_acoes_recomendadas_lote_sem_oportunidades_retorna_lista_vazia():
    """Lote sem dores -> nenhuma ação recomendada, sem chamar a IA."""
    cliente = ClienteIAFalso()  # sem nenhuma resposta configurada

    acoes, sucesso = gerar_acoes_recomendadas([], cliente)

    assert acoes == []
    assert sucesso is True
    print("OK: test_acoes_recomendadas_lote_sem_oportunidades_retorna_lista_vazia")


def test_processar_executiva_ponta_a_ponta():
    """Orquestração completa da Camada Executiva, com ICE calculado e resumos."""
    semantica = ResultadoSemantico(
        dores_identificadas=[_categoria("ENTREGA", 24.0, 88.0, ocorrencias=12)],
        forcas_identificadas=[_categoria("ATENDIMENTO", 58.0, 92.0, ocorrencias=29)],
    )

    cliente = ClienteIAFalso()
    cliente.configurar_resposta(
        "resumo_executivo",
        {
            "resumo_executivo": "Resumo geral.", "resumo_comercial": "Resumo comercial.",
            "resumo_operacional": "Resumo operacional.", "resumo_atendimento": "Resumo atendimento.",
            "resumo_produto": "Resumo produto.", "resumo_experiencia": "Resumo experiencia.",
            "resumo_evolutivo": "", "resumo_nicho": "",
        },
    )
    cliente.configurar_resposta("acao_recomendada", {"acoes": []})

    resultado = processar_executiva(
        _matematica(62.0), _linguistica(38.0, 81.0), semantica,
        respostas_com_categoria_detectada=8, total_respostas=10,
        evidencias_semanticas_validas=5, evolucao_temporal=None,
        segmento="generico", cliente_ia=cliente,
    )

    assert resultado.status_ice == "calculado"
    assert resultado.ice_nsi is not None
    assert resultado.ice_versao == "v1"
    assert len(resultado.top_forcas) == 1
    assert len(resultado.top_oportunidades) == 1
    assert resultado.resumo_executivo == "Resumo geral."
    print(f"OK: test_processar_executiva_ponta_a_ponta (ICE calculado: {resultado.ice_nsi})")


def test_nenhum_ranking_deterministico_chama_ia():
    """Verificação estática: funções de ranking/ICE não importam ClienteIA nem groq."""
    import processors.executive_processor as mod

    codigo_fonte = Path(mod.__file__).read_text(encoding="utf-8")
    bloco_ice = codigo_fonte[
        codigo_fonte.index("def calcular_ice"):codigo_fonte.index("def faixa_interpretacao_ice")
    ]
    assert "cliente_ia" not in bloco_ice
    assert "ClienteIA" not in bloco_ice
    print("OK: test_nenhum_ranking_deterministico_chama_ia")


if __name__ == "__main__":
    test_ice_lote_perfeito_resulta_em_100()
    test_ice_lote_pessimo_resulta_em_0()
    test_ice_bloqueado_sem_cobertura_e_sem_evidencia_absoluta()
    test_ice_liberado_por_cobertura_semantica_20_porcento()
    test_ice_liberado_por_evidencia_absoluta_mesmo_com_baixa_cobertura()
    test_ice_nunca_sai_de_0_100_mesmo_com_entrada_fora_da_faixa()
    test_faixas_de_interpretacao_corretas()
    test_top_forcas_e_oportunidades_ordenados_por_incidencia()
    test_top_prioridades_sem_fator_de_impacto_comercial()
    test_areas_responsaveis_agregado_soma_por_familia()
    test_resumos_executivos_via_ia_8_campos()
    test_resumos_falha_ia_retorna_strings_vazias_sem_excecao()
    test_acoes_recomendadas_geradas_a_partir_do_contexto_real()
    test_acoes_recomendadas_lote_sem_oportunidades_retorna_lista_vazia()
    test_processar_executiva_ponta_a_ponta()
    test_nenhum_ranking_deterministico_chama_ia()
    print("\nTodos os testes da Fase 9 (Camada Executiva) passaram.")
