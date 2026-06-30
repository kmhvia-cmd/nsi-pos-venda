"""
tests/unit/test_output_builder.py

Testes do Output Builder.
Critérios de aceite — Plano de Implementação, Fase 10.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from models.output_models import (
    CategoriaAgregada,
    DistribuicaoTempoResposta,
    ModeloClassificacao,
    ResultadoEvolucaoTemporal,
    ResultadoExecutivo,
    ResultadoExperienciaHumanaAgregado,
    ResultadoLinguisticoAgregado,
    ResultadoMatematico,
    ResultadoSemantico,
)
from outputs.output_builder import (
    ErroSchemaInvalido,
    montar_saida_completa,
    montar_saida_parcial,
    saida_para_dict,
)


def _matematica() -> ResultadoMatematico:
    return ResultadoMatematico(
        taxa_resposta=62.0, taxa_silencio=38.0, taxa_visualizado_sem_resposta=0.0,
        taxa_nao_entrega=0.0, tempo_medio_resposta_minutos=100.0, tempo_mediano_resposta_minutos=90.0,
        distribuicao_tempo_resposta=DistribuicaoTempoResposta(20.0, 50.0, 20.0, 10.0),
        tamanho_medio_resposta_caracteres=120, participacao_valida=92.0,
        qualidade_participacao_media=71.0,
    )


def _linguistica() -> ResultadoLinguisticoAgregado:
    return ResultadoLinguisticoAgregado(
        intensidade_emocional_media=45.0, polaridade_linguistica_media=38.0,
        engajamento_linguistico_medio=81.0, formalidade_media=60.0, marca_regional_media=20.0,
    )


def _semantica() -> ResultadoSemantico:
    return ResultadoSemantico(
        dores_identificadas=[
            CategoriaAgregada(
                codigo_catalogo="ENTR-001", familia="ENTREGA", subcategoria="atraso",
                nicho=None, incidencia_percentual=24.0, confianca_media=88.0,
                intensidade_semantica_media=45.0, ocorrencias=15, evidencias=[],
            )
        ],
        forcas_identificadas=[
            CategoriaAgregada(
                codigo_catalogo="ATEND-006", familia="ATENDIMENTO", subcategoria="cordialidade",
                nicho=None, incidencia_percentual=58.0, confianca_media=92.0,
                intensidade_semantica_media=68.0, ocorrencias=36, evidencias=[],
            )
        ],
    )


def _experiencia() -> ResultadoExperienciaHumanaAgregado:
    return ResultadoExperienciaHumanaAgregado(
        entusiasmo_medio=55.0, confianca_cliente_media=70.0, frustracao_media=30.0,
        envolvimento_medio=65.0, empolgacao_media=40.0, seguranca_media=68.0,
        indiferenca_media=15.0, lealdade_media=62.0, gratidao_media=45.0, desgaste_medio=22.0,
    )


def _executiva() -> ResultadoExecutivo:
    return ResultadoExecutivo(
        status_ice="calculado", ice_nsi=72.9, ice_versao="v1", motivo=None,
        resumo_executivo="Experiência positiva.", resumo_comercial="Boa retenção.",
        resumo_operacional="Entrega a melhorar.", resumo_atendimento="Atendimento forte.",
        resumo_produto="Produto aprovado.", resumo_experiencia="Satisfação geral alta.",
    )


def _modelo_classificacao() -> ModeloClassificacao:
    return ModeloClassificacao(provider="groq", modelo="llama", versao_prompt="v1")


def test_saida_completa_valida_schema_campo_a_campo():
    """
    JSON final de um lote de teste completo valida corretamente campo a
    campo contra o Contrato Seção 8. Nenhum ErroSchemaInvalido deve
    ser levantado.
    """
    saida = montar_saida_completa(
        empresa="empresa_teste", segmento="generico", lote_id="NSI-TESTE-001",
        versao_catalogo="1.1", modelo_classificacao=_modelo_classificacao(),
        matematica=_matematica(), linguistica_agregada=_linguistica(),
        semantica=_semantica(), experiencia_humana_agregada=_experiencia(),
        evolucao_temporal=None, executiva=_executiva(),
        respostas_individuais=[], evidencias_semanticas_validas=41,
    )

    assert saida.status_semantico == "concluido"
    assert saida.empresa == "empresa_teste"
    assert saida.lote_id == "NSI-TESTE-001"
    assert saida.versao_motor == "3.1"
    assert saida.versao_catalogo == "1.1"
    assert saida.evidencias_semanticas_validas == 41
    assert saida.semantica is not None
    assert saida.executiva is not None
    print("OK: test_saida_completa_valida_schema_campo_a_campo")


def test_saida_parcial_fallback_tem_apenas_matematica_e_linguistica():
    """
    JSON parcial (fallback) contém exatamente matematica, linguistica_agregada,
    status_semantico='pendente' — nada além, nada faltando.
    """
    saida = montar_saida_parcial(
        empresa="empresa_teste", segmento="generico", lote_id="NSI-TESTE-001",
        versao_catalogo="1.1", modelo_classificacao=_modelo_classificacao(),
        matematica=_matematica(), linguistica_agregada=_linguistica(),
    )

    assert saida.status_semantico == "pendente"
    assert saida.matematica is not None
    assert saida.linguistica_agregada is not None
    assert saida.semantica is None
    assert saida.experiencia_humana_agregada is None
    assert saida.evolucao_temporal is None
    assert saida.executiva is None
    assert saida.respostas_individuais == []
    assert saida.evidencias_semanticas_validas == 0
    print("OK: test_saida_parcial_fallback_tem_apenas_matematica_e_linguistica")


def test_saida_completa_sem_semantica_levanta_erro():
    """
    Saída marcada como 'concluido' mas sem bloco semantica deve levantar
    ErroSchemaInvalido — nunca deixa uma saída mal formada passar.
    """
    erro_detectado = False
    try:
        saida = montar_saida_completa(
            empresa="empresa_teste", segmento="generico", lote_id="NSI-TESTE-001",
            versao_catalogo="1.1", modelo_classificacao=_modelo_classificacao(),
            matematica=_matematica(), linguistica_agregada=_linguistica(),
            semantica=_semantica(), experiencia_humana_agregada=_experiencia(),
            evolucao_temporal=None, executiva=_executiva(),
            respostas_individuais=[], evidencias_semanticas_validas=41,
        )
        # força o campo para None depois de montar (simula bug em camada anterior)
        saida.semantica = None
        from outputs.output_builder import _validar_saida_completa
        _validar_saida_completa(saida)
    except ErroSchemaInvalido:
        erro_detectado = True

    assert erro_detectado, "ErroSchemaInvalido deveria ter sido levantado"
    print("OK: test_saida_completa_sem_semantica_levanta_erro")


def test_saida_parcial_com_semantica_levanta_erro():
    """
    Saída marcada como 'pendente' mas com bloco semantica presente deve
    levantar ErroSchemaInvalido.
    """
    erro_detectado = False
    try:
        saida = montar_saida_parcial(
            empresa="empresa_teste", segmento="generico", lote_id="NSI-TESTE-001",
            versao_catalogo="1.1", modelo_classificacao=_modelo_classificacao(),
            matematica=_matematica(), linguistica_agregada=_linguistica(),
        )
        saida.semantica = _semantica()  # injeta semantica indevida
        from outputs.output_builder import _validar_saida_completa
        _validar_saida_completa(saida)
    except ErroSchemaInvalido:
        erro_detectado = True

    assert erro_detectado, "ErroSchemaInvalido deveria ter sido levantado"
    print("OK: test_saida_parcial_com_semantica_levanta_erro")


def test_saida_para_dict_serializavel():
    """saida_para_dict retorna dicionário com data_processamento como string ISO 8601."""
    saida = montar_saida_completa(
        empresa="empresa_teste", segmento="generico", lote_id="NSI-TESTE-001",
        versao_catalogo="1.1", modelo_classificacao=_modelo_classificacao(),
        matematica=_matematica(), linguistica_agregada=_linguistica(),
        semantica=_semantica(), experiencia_humana_agregada=_experiencia(),
        evolucao_temporal=None, executiva=_executiva(),
        respostas_individuais=[], evidencias_semanticas_validas=41,
    )

    d = saida_para_dict(saida)

    assert isinstance(d["data_processamento"], str)
    assert "T" in d["data_processamento"]  # formato ISO 8601
    assert isinstance(d["matematica"], dict)
    assert isinstance(d["evidencias_semanticas_validas"], int)
    print("OK: test_saida_para_dict_serializavel")


def test_output_builder_nao_calcula_nada():
    """
    Verificação estática: output_builder.py não importa nenhum processor
    nem serviço de IA — só compõe o que já foi calculado.
    """
    import outputs.output_builder as mod

    codigo_fonte = Path(mod.__file__).read_text(encoding="utf-8")
    proibidos = [
        "math_processor", "linguistic_processor", "semantic_processor",
        "experience_processor", "evolution_processor", "executive_processor",
        "ai_classifier", "groq",
    ]
    for termo in proibidos:
        assert termo not in codigo_fonte, f"Encontrada referência proibida: {termo!r}"
    print("OK: test_output_builder_nao_calcula_nada")


if __name__ == "__main__":
    test_saida_completa_valida_schema_campo_a_campo()
    test_saida_parcial_fallback_tem_apenas_matematica_e_linguistica()
    test_saida_completa_sem_semantica_levanta_erro()
    test_saida_parcial_com_semantica_levanta_erro()
    test_saida_para_dict_serializavel()
    test_output_builder_nao_calcula_nada()
    print("\nTodos os testes da Fase 10 (Output Builder) passaram.")
