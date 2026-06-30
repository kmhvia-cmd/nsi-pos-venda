"""
processors/executive_processor.py

Camada Executiva do Motor NSI.
Contrato Oficial do Motor NSI v3.1.1, Seção 7 e Seção 9.17 (ICE NSI v1).

Responsabilidade: consolidar todas as camadas anteriores em uma leitura
de negócio — ICE, rankings, áreas agregadas, ações recomendadas e
resumos textuais.

Divisão de responsabilidade dentro desta camada:
    - ICE, rankings (top forças/oportunidades/prioridades) e áreas
      agregadas são 100% DETERMINÍSTICOS — nenhuma chamada a IA.
    - Resumos textuais (8 campos `resumo_*`) e ações recomendadas usam
      a IA via ClienteIA, pois exigem geração de linguagem natural a
      partir do contexto do lote (Contrato Seção 7.4).

Critério de liberação do ICE (Contrato Seção 9.17, congelado):
    (cobertura_semantica >= 20%) OU (evidencias_semanticas_validas >= 10)
Quando nenhum dos dois é atendido: status_ice="cobertura_insuficiente",
ice_nsi=None, motivo preenchido. Esta é a única situação em que o ICE
não é apresentado.
"""

from __future__ import annotations

from models.output_models import (
    AcaoRecomendada,
    AreaAgregada,
    BaseadoEm,
    CategoriaAgregada,
    ItemPrioridade,
    ItemRanking,
    ResultadoEvolucaoTemporal,
    ResultadoExecutivo,
    ResultadoExperienciaHumanaAgregado,
    ResultadoLinguisticoAgregado,
    ResultadoMatematico,
    ResultadoSemantico,
)
from services.ai_classifier import ClienteIA, RequisicaoIA
from services.fallback_handler import chamar_com_fallback

VERSAO_PROMPT_EXECUTIVA = "v1"
ICE_VERSAO = "v1"

# Critério de liberação do ICE (Contrato Seção 9.17, congelado)
_LIMIAR_COBERTURA_SEMANTICA_PERCENTUAL = 20.0
_LIMIAR_EVIDENCIAS_SEMANTICAS_ABSOLUTAS = 10

# Pesos oficiais do ICE v1 (Contrato Seção 9.17, congelado)
_PESO_INCIDENCIA_FORCAS = 0.25
_PESO_INCIDENCIA_DORES = 0.25
_PESO_CONFIANCA_SEMANTICA = 0.20
_PESO_POLARIDADE_LINGUISTICA = 0.10
_PESO_ENGAJAMENTO_LINGUISTICO = 0.10
_PESO_TAXA_RESPOSTA = 0.10

# Faixas de interpretação do ICE (Contrato Seção 9.17, congelado)
_FAIXAS_ICE = (
    (39.9, "Experiência Crítica"),
    (59.9, "Experiência de Atenção"),
    (74.9, "Experiência Satisfatória"),
    (89.9, "Experiência Muito Boa"),
    (100.0, "Experiência Excelente"),
)

_MOTIVO_COBERTURA_INSUFICIENTE = (
    "Quantidade insuficiente de evidências semânticas para cálculo confiável."
)

_PROMPT_SISTEMA_RESUMOS = """\
Você é a Camada Executiva do Motor NSI.

Você recebe dados JÁ CALCULADOS pelo Motor (indicadores matemáticos,
linguísticos, semânticos e o ICE) e deve gerar resumos em linguagem
empresarial simples, para que qualquer empresário entenda imediatamente
— sem jargão técnico de linguística, estatística ou IA.

Você NÃO recalcula nada. Você NÃO inventa números. Você apenas
interpreta, em texto, os números fornecidos no contexto.

Gere exatamente 8 resumos, cada um uma string curta (2-3 frases):
- resumo_executivo: leitura geral do lote, visão de topo
- resumo_comercial: foco em conversão, recompra e indicação
- resumo_operacional: foco em processos, prazo e logística
- resumo_atendimento: foco na família Atendimento
- resumo_produto: foco na família Produto/Qualidade
- resumo_experiencia: foco na percepção geral do cliente
- resumo_evolutivo: leitura da variação frente ao lote anterior (ou
  string vazia "" se não houver dados de evolução no contexto)
- resumo_nicho: leitura de subcategorias de segmento (ou string vazia
  "" se o segmento for "generico")

Responda APENAS em JSON estruturado, no formato exato:
{"resumo_executivo": "...", "resumo_comercial": "...", "resumo_operacional": "...", "resumo_atendimento": "...", "resumo_produto": "...", "resumo_experiencia": "...", "resumo_evolutivo": "...", "resumo_nicho": "..."}
"""

_PROMPT_SISTEMA_ACOES = """\
Você é a Camada Executiva do Motor NSI, gerando Ações Recomendadas.

Para cada uma das principais oportunidades (dores) do lote fornecidas
no contexto, gere uma recomendação de ação concreta, baseada SOMENTE
nos dados fornecidos (incidência, confiança, evidências, tendência) —
nunca uma regra fixa genérica desvinculada do lote real.

Responda APENAS em JSON estruturado, no formato exato:
{"acoes": [{"codigo_catalogo": "...", "recomendacao": "texto da ação concreta"}]}
"""


# ---------------------------------------------------------------------------
# ICE NSI v1 — determinístico, Contrato Seção 9.17
# ---------------------------------------------------------------------------


def _calcular_cobertura_semantica(
    respostas_com_categoria_detectada: int, total_respostas: int
) -> float:
    if total_respostas <= 0:
        return 0.0
    return round(respostas_com_categoria_detectada / total_respostas * 100, 1)


def _incidencia_total(categorias: list[CategoriaAgregada]) -> float:
    """
    Soma de incidência das categorias de um tipo (forças ou dores),
    limitada a 100 — múltiplas subcategorias podem, em conjunto, somar
    mais que 100% de incidência bruta (uma resposta pode ter múltiplas
    dores), então o agregado para o ICE é limitado ao teto de 0-100
    exigido pela fórmula (Contrato Seção 9.17).
    """
    if not categorias:
        return 0.0
    soma = sum(c.incidencia_percentual for c in categorias)
    return min(soma, 100.0)


def _confianca_media_semantica(semantica: ResultadoSemantico) -> float:
    todas = semantica.dores_identificadas + semantica.forcas_identificadas
    if not todas:
        return 0.0
    soma_ponderada = sum(c.confianca_media * c.ocorrencias for c in todas)
    soma_ocorrencias = sum(c.ocorrencias for c in todas)
    if soma_ocorrencias == 0:
        return 0.0
    return round(soma_ponderada / soma_ocorrencias, 1)


def _clamp(valor: float, minimo: float = 0.0, maximo: float = 100.0) -> float:
    """Salvaguarda defensiva de robustez (Contrato Seção 9.17)."""
    return max(minimo, min(valor, maximo))


def calcular_ice(
    matematica: ResultadoMatematico,
    linguistica: ResultadoLinguisticoAgregado,
    semantica: ResultadoSemantico | None,
    respostas_com_categoria_detectada: int,
    total_respostas: int,
    evidencias_semanticas_validas: int,
) -> tuple[str, float | None, str | None]:
    """
    Calcula o ICE NSI v1, aplicando o critério híbrido de liberação
    (Contrato Seção 9.17).

    Retorna (status_ice, ice_nsi, motivo).
    """
    cobertura_semantica = _calcular_cobertura_semantica(
        respostas_com_categoria_detectada, total_respostas
    )

    cobertura_suficiente = cobertura_semantica >= _LIMIAR_COBERTURA_SEMANTICA_PERCENTUAL
    evidencia_suficiente = evidencias_semanticas_validas >= _LIMIAR_EVIDENCIAS_SEMANTICAS_ABSOLUTAS

    if not (cobertura_suficiente or evidencia_suficiente) or semantica is None:
        return "cobertura_insuficiente", None, _MOTIVO_COBERTURA_INSUFICIENTE

    incidencia_forcas = _clamp(_incidencia_total(semantica.forcas_identificadas))
    incidencia_dores = _clamp(_incidencia_total(semantica.dores_identificadas))
    confianca_semantica = _clamp(_confianca_media_semantica(semantica))
    polaridade_normalizada = _clamp((linguistica.polaridade_linguistica_media + 100) / 2)
    engajamento = _clamp(linguistica.engajamento_linguistico_medio)
    taxa_resposta = _clamp(matematica.taxa_resposta)

    ice = (
        _PESO_INCIDENCIA_FORCAS * incidencia_forcas
        + _PESO_INCIDENCIA_DORES * (100.0 - incidencia_dores)
        + _PESO_CONFIANCA_SEMANTICA * confianca_semantica
        + _PESO_POLARIDADE_LINGUISTICA * polaridade_normalizada
        + _PESO_ENGAJAMENTO_LINGUISTICO * engajamento
        + _PESO_TAXA_RESPOSTA * taxa_resposta
    )
    ice = round(_clamp(ice), 1)

    return "calculado", ice, None


def faixa_interpretacao_ice(ice_nsi: float) -> str:
    """Retorna o nome comercial da faixa de interpretação (Contrato Seção 9.17)."""
    for limite_superior, nome in _FAIXAS_ICE:
        if ice_nsi <= limite_superior:
            return nome
    return _FAIXAS_ICE[-1][1]  # salvaguarda defensiva, nunca deveria ser alcançado


# ---------------------------------------------------------------------------
# Rankings — determinísticos, Contrato Seção 7.1 / 7.2
# ---------------------------------------------------------------------------


def calcular_top_forcas(semantica: ResultadoSemantico | None, limite: int = 15) -> list[ItemRanking]:
    if semantica is None:
        return []
    ordenadas = sorted(semantica.forcas_identificadas, key=lambda c: -c.incidencia_percentual)
    return [
        ItemRanking(posicao=i + 1, categoria=c.familia, percentual=c.incidencia_percentual)
        for i, c in enumerate(ordenadas[:limite])
    ]


def calcular_top_oportunidades(
    semantica: ResultadoSemantico | None, limite: int = 15
) -> list[ItemRanking]:
    if semantica is None:
        return []
    ordenadas = sorted(semantica.dores_identificadas, key=lambda c: -c.incidencia_percentual)
    return [
        ItemRanking(posicao=i + 1, categoria=c.familia, percentual=c.incidencia_percentual)
        for i, c in enumerate(ordenadas[:limite])
    ]


def calcular_top_prioridades(
    semantica: ResultadoSemantico | None, limite: int = 15
) -> list[ItemPrioridade]:
    """
    Critério: incidencia_percentual x confianca_media (Contrato Seção 7.2).
    NÃO inclui nenhum fator de impacto comercial (Contrato 9.1).
    """
    if semantica is None:
        return []
    candidatas = [
        (c, round(c.incidencia_percentual * c.confianca_media / 100, 1))
        for c in semantica.dores_identificadas
    ]
    candidatas.sort(key=lambda par: -par[1])
    return [
        ItemPrioridade(
            posicao=i + 1,
            categoria=categoria.familia,
            criterio="incidencia_x_confianca",
            valor=valor,
        )
        for i, (categoria, valor) in enumerate(candidatas[:limite])
    ]


# ---------------------------------------------------------------------------
# Áreas responsáveis agregadas — determinístico, Contrato Seção 7.3
# ---------------------------------------------------------------------------


def calcular_areas_responsaveis_agregado(
    semantica: ResultadoSemantico | None,
) -> list[AreaAgregada]:
    """
    Consolida area_responsavel das dores do lote. Usa a área primária
    de cada subcategoria (Contrato Seção 4.7) — a priorização de área
    secundária por padrão de evidências do lote é responsabilidade do
    motor de classificação (Fase 5), já refletida em
    CategoriaAgregada.area_responsavel quando presente; este cálculo
    apenas consolida o que já foi decidido anteriormente, sem nova
    lógica de priorização aqui.
    """
    if semantica is None or not semantica.dores_identificadas:
        return []

    por_area: dict[str, float] = {}
    for dor in semantica.dores_identificadas:
        # CategoriaAgregada não carrega area_responsavel diretamente
        # (esse campo vive em CategoriaDetectada, por resposta) — a
        # agregação por área no nível do lote usa a família como proxy
        # determinístico estável, já que area_responsavel é derivada da
        # família/subcategoria do catálogo de forma consistente.
        por_area[dor.familia] = por_area.get(dor.familia, 0.0) + dor.incidencia_percentual

    total = sum(por_area.values())
    if total == 0:
        return []

    resultado = [
        AreaAgregada(area=area, percentual_oportunidades=round(valor, 1))
        for area, valor in sorted(por_area.items(), key=lambda item: -item[1])
    ]
    return resultado


# ---------------------------------------------------------------------------
# Resumos e Ações Recomendadas — via IA, saída estruturada, sem narrativa fora do escopo
# ---------------------------------------------------------------------------


def _montar_contexto_resumos(
    matematica: ResultadoMatematico,
    semantica: ResultadoSemantico | None,
    status_ice: str,
    ice_nsi: float | None,
    top_forcas: list[ItemRanking],
    top_oportunidades: list[ItemRanking],
    evolucao_temporal: ResultadoEvolucaoTemporal | None,
    segmento: str,
) -> dict:
    return {
        "taxa_resposta": matematica.taxa_resposta,
        "status_ice": status_ice,
        "ice_nsi": ice_nsi,
        "top_forcas": [{"categoria": f.categoria, "percentual": f.percentual} for f in top_forcas],
        "top_oportunidades": [
            {"categoria": o.categoria, "percentual": o.percentual} for o in top_oportunidades
        ],
        "tem_evolucao_temporal": evolucao_temporal is not None,
        "variacoes_familia": (
            [
                {"familia": v.familia, "variacao": v.variacao, "tendencia": v.tendencia}
                for v in evolucao_temporal.variacoes_familia
            ]
            if evolucao_temporal is not None
            else []
        ),
        "segmento": segmento,
    }


def gerar_resumos_executivos(
    matematica: ResultadoMatematico,
    semantica: ResultadoSemantico | None,
    status_ice: str,
    ice_nsi: float | None,
    top_forcas: list[ItemRanking],
    top_oportunidades: list[ItemRanking],
    evolucao_temporal: ResultadoEvolucaoTemporal | None,
    segmento: str,
    cliente_ia: ClienteIA,
) -> tuple[dict, bool]:
    """
    Gera os 8 resumos textuais via IA, a partir de dados já calculados.
    Retorna (resumos, sucesso_ia). Em falha, resumos é um dict com
    todas as strings vazias.
    """
    requisicao = RequisicaoIA(
        tarefa="resumo_executivo",
        texto="",
        contexto=_montar_contexto_resumos(
            matematica, semantica, status_ice, ice_nsi, top_forcas,
            top_oportunidades, evolucao_temporal, segmento,
        ),
        prompt_sistema=_PROMPT_SISTEMA_RESUMOS,
        versao_prompt=VERSAO_PROMPT_EXECUTIVA,
    )

    resultado = chamar_com_fallback(cliente_ia, requisicao)
    if not resultado.sucesso:
        return {
            "resumo_executivo": "", "resumo_comercial": "", "resumo_operacional": "",
            "resumo_atendimento": "", "resumo_produto": "", "resumo_experiencia": "",
            "resumo_evolutivo": None, "resumo_nicho": None,
        }, False

    conteudo = resultado.resposta.conteudo
    resumos = {
        campo: str(conteudo.get(campo, "")) or ""
        for campo in (
            "resumo_executivo", "resumo_comercial", "resumo_operacional",
            "resumo_atendimento", "resumo_produto", "resumo_experiencia",
        )
    }
    resumo_evolutivo = conteudo.get("resumo_evolutivo") or None
    resumo_nicho = conteudo.get("resumo_nicho") or None
    resumos["resumo_evolutivo"] = resumo_evolutivo if resumo_evolutivo else None
    resumos["resumo_nicho"] = resumo_nicho if resumo_nicho else None

    return resumos, True


def gerar_acoes_recomendadas(
    top_oportunidades_detalhe: list[CategoriaAgregada],
    cliente_ia: ClienteIA,
    limite: int = 15,
) -> tuple[list[AcaoRecomendada], bool]:
    """
    Gera ações recomendadas via IA, a partir do contexto real do lote
    (Contrato Seção 7.4 / 9.8) — nunca regra fixa do catálogo.
    """
    if not top_oportunidades_detalhe:
        return [], True

    contexto = {
        "oportunidades": [
            {
                "codigo_catalogo": c.codigo_catalogo,
                "familia": c.familia,
                "incidencia_percentual": c.incidencia_percentual,
                "confianca_media": c.confianca_media,
                "ocorrencias": c.ocorrencias,
            }
            for c in top_oportunidades_detalhe[:limite]
        ]
    }

    requisicao = RequisicaoIA(
        tarefa="acao_recomendada",
        texto="",
        contexto=contexto,
        prompt_sistema=_PROMPT_SISTEMA_ACOES,
        versao_prompt=VERSAO_PROMPT_EXECUTIVA,
    )

    resultado = chamar_com_fallback(cliente_ia, requisicao)
    if not resultado.sucesso:
        return [], False

    acoes_brutas = resultado.resposta.conteudo.get("acoes", [])
    mapa_categorias = {c.codigo_catalogo: c for c in top_oportunidades_detalhe}

    acoes: list[AcaoRecomendada] = []
    for i, item in enumerate(acoes_brutas[:limite]):
        codigo = item.get("codigo_catalogo")
        categoria = mapa_categorias.get(codigo)
        if categoria is None:
            continue

        acoes.append(
            AcaoRecomendada(
                posicao=i + 1,
                categoria=categoria.familia,
                codigo_catalogo=codigo,
                area_responsavel=categoria.familia,  # ver nota em calcular_areas_responsaveis_agregado
                recomendacao=str(item.get("recomendacao", "")),
                baseado_em=BaseadoEm(
                    ocorrencias=categoria.ocorrencias,
                    confianca_media=categoria.confianca_media,
                ),
            )
        )

    return acoes, True


# ---------------------------------------------------------------------------
# Orquestração da Camada Executiva
# ---------------------------------------------------------------------------


def processar_executiva(
    matematica: ResultadoMatematico,
    linguistica: ResultadoLinguisticoAgregado,
    semantica: ResultadoSemantico | None,
    respostas_com_categoria_detectada: int,
    total_respostas: int,
    evidencias_semanticas_validas: int,
    evolucao_temporal: ResultadoEvolucaoTemporal | None,
    segmento: str,
    cliente_ia: ClienteIA,
) -> ResultadoExecutivo:
    """
    Orquestra a Camada Executiva completa: ICE, rankings, áreas
    agregadas (determinísticos) + resumos e ações (via IA).
    """
    status_ice, ice_nsi, motivo = calcular_ice(
        matematica, linguistica, semantica,
        respostas_com_categoria_detectada, total_respostas,
        evidencias_semanticas_validas,
    )

    top_forcas = calcular_top_forcas(semantica)
    top_oportunidades = calcular_top_oportunidades(semantica)
    top_prioridades = calcular_top_prioridades(semantica)
    areas_agregadas = calcular_areas_responsaveis_agregado(semantica)

    resumos, _ = gerar_resumos_executivos(
        matematica, semantica, status_ice, ice_nsi, top_forcas,
        top_oportunidades, evolucao_temporal, segmento, cliente_ia,
    )

    oportunidades_detalhe = semantica.dores_identificadas if semantica else []
    ordenadas_para_acoes = sorted(oportunidades_detalhe, key=lambda c: -c.incidencia_percentual)
    acoes, _ = gerar_acoes_recomendadas(ordenadas_para_acoes, cliente_ia)

    return ResultadoExecutivo(
        status_ice=status_ice,
        ice_nsi=ice_nsi,
        ice_versao=ICE_VERSAO,
        motivo=motivo,
        top_forcas=top_forcas,
        top_oportunidades=top_oportunidades,
        top_prioridades=top_prioridades,
        areas_responsaveis_agregado=areas_agregadas,
        acoes_recomendadas=acoes,
        resumo_executivo=resumos["resumo_executivo"],
        resumo_comercial=resumos["resumo_comercial"],
        resumo_operacional=resumos["resumo_operacional"],
        resumo_atendimento=resumos["resumo_atendimento"],
        resumo_produto=resumos["resumo_produto"],
        resumo_experiencia=resumos["resumo_experiencia"],
        resumo_evolutivo=resumos["resumo_evolutivo"],
        resumo_nicho=resumos["resumo_nicho"],
    )
