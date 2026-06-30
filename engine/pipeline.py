"""
engine/pipeline.py

Pipeline principal do Motor NSI.
Especificação Técnica v1, Seção 3.

Responsabilidade: orquestrar as camadas na ordem oficial, propagar
o contexto entre elas, detectar fallback (IA indisponível), e entregar
a saída final montada pelo Output Builder.

ORDEM OFICIAL (Especificação Técnica Seção 3.1):
    [1] math_processor          → matematica (sempre executa)
    [2] linguistic_processor    → linguistica por resposta + agregada (sempre executa)
    [3] fallback_handler        → verifica disponibilidade da IA (portão)
    [4] catalog/loader          → carrega catálogo na versao_catalogo vigente
    [5] semantic_processor      → semantica por resposta + agregada
    [6] confidence_rules        → já aplicado dentro do semantic_processor (Fase 5)
    [7] experience_processor    → experiencia_humana por resposta + agregada
    [8] evolution_processor     → evolucao_temporal (se houver lote anterior)
    [9] executive_processor     → executiva (ICE, rankings, resumos, ações)
    [10] output_builder         → JSON final completo ou parcial

O pipeline nunca para por indisponibilidade da IA — as camadas
determinísticas (Matemática e Linguística) sempre completam, e o
resultado parcial é entregue com status_semantico='pendente' (Contrato
Seção 1.2).
"""

from __future__ import annotations

from models.input_models import Lote, RespostaCliente
from models.output_models import (
    ModeloClassificacao,
    RespostaIndividualCompleta,
    ResultadoExperienciaHumana,
    SaidaMotorCompleta,
)
from catalog.loader import CatalogoNSI
from engine.context import ContextoPipeline
from outputs.output_builder import montar_saida_completa, montar_saida_parcial
from processors.evolution_processor import LoteAnteriorComparavel
from processors.executive_processor import processar_executiva
from processors.experience_processor import (
    agregar_experiencia_humana_lote,
    processar_experiencia_humana_resposta,
)
from processors.evolution_processor import processar_evolucao_temporal
from processors.linguistic_processor import (
    agregar_linguistica_lote,
    processar_linguistica_resposta,
)
from processors.math_processor import processar_matematica
from processors.semantic_processor import (
    agregar_semantica_lote,
    processar_semantica_resposta,
)
from services.ai_classifier import ClienteIA, ErroIAIndisponivel
from services.fallback_handler import chamar_com_fallback, determinar_status_semantico


def _modelo_classificacao_placeholder() -> ModeloClassificacao:
    """
    Placeholder para execuções parciais (fallback) onde nenhuma chamada
    de IA foi feita — o campo é obrigatório no schema (Contrato Seção 1.1)
    mesmo quando a IA não foi usada.
    """
    return ModeloClassificacao(
        provider="nao_utilizado", modelo="nao_utilizado", versao_prompt="nao_utilizado"
    )


def executar_pipeline(
    lote: Lote,
    catalogo: CatalogoNSI,
    cliente_ia: ClienteIA,
    lote_anterior: LoteAnteriorComparavel | None = None,
) -> SaidaMotorCompleta:
    """
    Executa o pipeline completo do Motor NSI para um lote.

    Parâmetros:
        lote: o lote completo com todas as respostas
        catalogo: catálogo NSI já carregado (CatalogoNSI da Fase 3)
        cliente_ia: provider de IA (ClienteGroq ou ClienteIAFalso)
        lote_anterior: saída anterior da mesma empresa para Evolução
                       Temporal (None se for o primeiro lote)

    Retorna SaidaMotorCompleta (completa ou parcial se fallback).
    """
    ctx = ContextoPipeline(
        empresa=lote.empresa,
        segmento=lote.segmento,
        lote_id=lote.lote_id,
        versao_catalogo=catalogo.versao_catalogo,
    )

    # -----------------------------------------------------------------------
    # [1] Camada Matemática — sempre executa
    # -----------------------------------------------------------------------
    ctx.matematica = processar_matematica(lote)

    # -----------------------------------------------------------------------
    # [2] Camada Linguística (sinais determinísticos) — sempre executa
    # -----------------------------------------------------------------------
    for resposta in lote.respostas:
        if resposta.status_entrega == "respondido" and resposta.resposta.strip():
            ling = processar_linguistica_resposta(resposta.resposta)
            ctx.linguistica_por_resposta.append(ling)

    ctx.linguistica_agregada = agregar_linguistica_lote(ctx.linguistica_por_resposta)

    # -----------------------------------------------------------------------
    # [3] Portão de fallback — verifica disponibilidade da IA
    # -----------------------------------------------------------------------
    try:
        # Tenta instanciar / fazer ping mínimo verificando que o cliente
        # responde — usamos uma requisição trivial ao fallback_handler
        from services.ai_classifier import RequisicaoIA
        from services.fallback_handler import chamar_com_fallback as _verificar
        _req_teste = RequisicaoIA(
            tarefa="classificacao_semantica", texto="ping",
            contexto={}, prompt_sistema="Responda apenas em formato json.", versao_prompt="v1",
        )
        _resultado_teste = _verificar(cliente_ia, _req_teste)
        ctx.ia_disponivel = True
        # Captura modelo_classificacao do primeiro retorno bem-sucedido
        if _resultado_teste.sucesso and _resultado_teste.resposta:
            ctx.modelo_classificacao = _resultado_teste.resposta.modelo_classificacao
    except Exception:
        ctx.ia_disponivel = False

    if not ctx.ia_disponivel:
        ctx.status_semantico = "pendente"
        return montar_saida_parcial(
            empresa=ctx.empresa, segmento=ctx.segmento, lote_id=ctx.lote_id,
            versao_catalogo=ctx.versao_catalogo,
            modelo_classificacao=ctx.modelo_classificacao or _modelo_classificacao_placeholder(),
            matematica=ctx.matematica,
            linguistica_agregada=ctx.linguistica_agregada,
        )

    # -----------------------------------------------------------------------
    # [5] + [6] Camada Semântica (com confidence_rules aplicado internamente)
    # -----------------------------------------------------------------------
    respostas_validas = [
        r for r in lote.respostas
        if r.status_entrega == "respondido" and r.resposta.strip()
    ]

    categorias_por_resposta = []
    ia_falhou_em_alguma = False

    for resposta, ling in zip(respostas_validas, ctx.linguistica_por_resposta):
        categorias, evidencias, sucesso_ia = processar_semantica_resposta(
            resposta.cliente_id, resposta.resposta, catalogo, cliente_ia
        )
        if not sucesso_ia:
            ia_falhou_em_alguma = True
            break
        if categorias:
            ctx.respostas_com_categoria_detectada += 1
            ctx.evidencias_semanticas_validas += len(evidencias)
        categorias_por_resposta.append((resposta.cliente_id, categorias, evidencias))

        # captura modelo_classificacao da primeira chamada semântica bem-sucedida
        if ctx.modelo_classificacao is None or ctx.modelo_classificacao.provider == "nao_utilizado":
            pass  # já capturado no portão ou será preenchido pelo executive

    if ia_falhou_em_alguma:
        ctx.status_semantico = "pendente"
        return montar_saida_parcial(
            empresa=ctx.empresa, segmento=ctx.segmento, lote_id=ctx.lote_id,
            versao_catalogo=ctx.versao_catalogo,
            modelo_classificacao=ctx.modelo_classificacao or _modelo_classificacao_placeholder(),
            matematica=ctx.matematica,
            linguistica_agregada=ctx.linguistica_agregada,
        )

    ctx.semantica = agregar_semantica_lote(categorias_por_resposta, len(respostas_validas))

    # -----------------------------------------------------------------------
    # [7] Camada de Experiência Humana
    # -----------------------------------------------------------------------
    experiencias_individuais: list[ResultadoExperienciaHumana] = []
    respostas_individuais_completas: list[RespostaIndividualCompleta] = []

    for (resposta, ling), (_, categorias, _) in zip(
        zip(respostas_validas, ctx.linguistica_por_resposta),
        categorias_por_resposta,
    ):
        exp, sucesso_exp = processar_experiencia_humana_resposta(
            resposta.resposta, ling, categorias, cliente_ia
        )
        if exp is not None:
            experiencias_individuais.append(exp)

        respostas_individuais_completas.append(
            RespostaIndividualCompleta(
                cliente_id=resposta.cliente_id,
                telefone=resposta.telefone,
                resposta=resposta.resposta,
                qualidade_participacao=ctx.matematica.qualidade_participacao_media,
                linguistica=ling,
                experiencia_humana=exp if exp is not None else _experiencia_humana_vazia(),
                categorias_detectadas=categorias,
            )
        )

    ctx.experiencia_humana_agregada = agregar_experiencia_humana_lote(experiencias_individuais)
    ctx.respostas_individuais = respostas_individuais_completas

    # -----------------------------------------------------------------------
    # [8] Camada de Evolução Temporal
    # -----------------------------------------------------------------------
    ctx.evolucao_temporal = processar_evolucao_temporal(
        empresa_atual=ctx.empresa,
        versao_catalogo_atual=ctx.versao_catalogo,
        matematica_atual=ctx.matematica,
        semantica_atual=ctx.semantica,
        lote_anterior=lote_anterior,
    )

    # -----------------------------------------------------------------------
    # [9] Camada Executiva
    # -----------------------------------------------------------------------
    ctx.executiva = processar_executiva(
        matematica=ctx.matematica,
        linguistica=ctx.linguistica_agregada,
        semantica=ctx.semantica,
        respostas_com_categoria_detectada=ctx.respostas_com_categoria_detectada,
        total_respostas=len(respostas_validas),
        evidencias_semanticas_validas=ctx.evidencias_semanticas_validas,
        evolucao_temporal=ctx.evolucao_temporal,
        segmento=ctx.segmento,
        cliente_ia=cliente_ia,
    )

    # -----------------------------------------------------------------------
    # [10] Output Builder — monta o JSON final
    # -----------------------------------------------------------------------
    ctx.status_semantico = "concluido"

    return montar_saida_completa(
        empresa=ctx.empresa,
        segmento=ctx.segmento,
        lote_id=ctx.lote_id,
        versao_catalogo=ctx.versao_catalogo,
        modelo_classificacao=ctx.modelo_classificacao or _modelo_classificacao_placeholder(),
        matematica=ctx.matematica,
        linguistica_agregada=ctx.linguistica_agregada,
        semantica=ctx.semantica,
        experiencia_humana_agregada=ctx.experiencia_humana_agregada,
        evolucao_temporal=ctx.evolucao_temporal,
        executiva=ctx.executiva,
        respostas_individuais=ctx.respostas_individuais,
        evidencias_semanticas_validas=ctx.evidencias_semanticas_validas,
    )


def _experiencia_humana_vazia():
    """Placeholder para respostas onde a IA de experiência falhou."""
    from models.output_models import ResultadoExperienciaHumana
    return ResultadoExperienciaHumana(
        entusiasmo=0.0, confianca_cliente=0.0, frustracao=0.0,
        envolvimento=0.0, empolgacao=0.0, seguranca=0.0,
        indiferenca=0.0, lealdade=0.0, gratidao=0.0, desgaste=0.0,
    )