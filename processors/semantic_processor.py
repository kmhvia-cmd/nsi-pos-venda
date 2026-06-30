"""
processors/semantic_processor.py

Camada Semântica do Motor NSI.
Contrato Oficial do Motor NSI v3.1, Seção 4.

Responsabilidade: identificar O QUE o cliente disse, classificando o
texto contra o Catálogo NSI v1.1. Toda decisão de classificação fina
(qual categoria, com qual confiança, com qual intensidade semântica)
é feita pela IA via `services/ai_classifier.py` — este módulo NUNCA
decide sozinho.

REGRAS OBRIGATÓRIAS DESTA IMPLEMENTAÇÃO (decisão aprovada, Fase 5):
    - Usa exclusivamente a interface ClienteIA (nunca importa Groq direto).
    - Usa exclusivamente o Catálogo NSI v1.1 como referência.
    - Respeita o limite de 5 categorias (confidence/confidence_rules.py).
    - Toda saída tem evidência, confiança e intensidade semântica.
    - Nenhuma heurística manual fora do contrato.
    - Nenhuma regra semântica codificada em Python — este módulo só
      orquestra: busca candidatos lexicais (catalog/matcher.py) -> monta
      prompt -> chama IA -> aplica limite -> agrega. A decisão de "isso
      é ATEND-006 com 92% de confiança" vem inteiramente da IA.

O matcher determinístico (Fase 3) fornece candidatos como CONTEXTO para
a IA — nunca decide a classificação final. Isso preserva a Hermenêutica
(Contrato Seção 3) como responsabilidade exclusiva da IA: a IA pode
confirmar, rejeitar, ou até classificar uma categoria que o matcher não
sugeriu, se a leitura semântica do contexto indicar isso.
"""

from __future__ import annotations

from collections import defaultdict
from statistics import mean

from catalog.loader import CatalogoNSI
from catalog.matcher import buscar_candidatos
from confidence.confidence_rules import ordenar_e_aplicar_limite
from models.catalog_models import EntradaCatalogo
from models.output_models import CategoriaAgregada, CategoriaDetectada, Evidencia, ResultadoSemantico
from services.ai_classifier import ClienteIA, RequisicaoIA
from services.fallback_handler import chamar_com_fallback

VERSAO_PROMPT_SEMANTICA = "v1"

_PROMPT_SISTEMA = """\
Você é o Motor Semântico do NSI (Núcleo de Inteligência Semântica).

O NSI NÃO mede sentimento. O NSI mede experiência comercial. Uma resposta
pode parecer positiva e esconder uma oportunidade de melhoria; pode
parecer negativa e esconder uma força. Avalie sempre por contexto, nunca
por tom isolado.

Você recebe um texto de cliente e uma lista de categorias candidatas,
encontradas por correspondência lexical (sinônimo/gíria/regionalismo
cadastrado). Essas candidatas são um ponto de partida, NÃO uma resposta
pronta — você pode confirmar, rejeitar, ou identificar categorias que o
candidato lexical não capturou, desde que estejam na lista de códigos
permitidos fornecida no contexto.

DECISÃO DE ARQUITETURA (obrigatória): o Catálogo NSI é a única fonte de
verdade para metadados estruturais. Você NUNCA informa tipo (força/dor),
família, subcategoria, área responsável ou nicho — esses dados já
existem no Catálogo e são preenchidos automaticamente a partir do código
que você identificar. Sua única responsabilidade é IDENTIFICAR O CÓDIGO
correto e avaliar confiança/intensidade/evidência.

Para cada categoria que você identificar no texto, retorne apenas:
- codigo_catalogo: o código exato (ex: "ATEND-001"), só dos códigos permitidos
- confianca: 0 a 100, sua certeza desta classificação
- intensidade_semantica: 0 a 100, a GRAVIDADE/FORÇA do fato relatado,
  independente de como foi dito. Ex: "demorou" tem intensidade menor que
  "demorou tanto que perdi meu compromisso".
- trecho_evidencia: a frase ou trecho exato do texto original que
  sustenta esta classificação — nunca invente ou paráfrase o trecho.

Uma mesma resposta pode ter força E dor simultaneamente — uma nunca
anula a outra. Nunca retorne uma categoria sem trecho de evidência real
extraído do texto fornecido.

Responda APENAS em JSON estruturado, sem texto narrativo, sem explicação
fora da estrutura, no formato:
{"categorias": [{"codigo_catalogo": "...", "confianca": 0.0, "intensidade_semantica": 0.0, "trecho_evidencia": "..."}]}

Se nenhuma categoria do texto corresponder a nenhum código permitido,
retorne {"categorias": []}.
"""


def _montar_contexto(
    texto: str, candidatos_lexicais: list[EntradaCatalogo], catalogo: CatalogoNSI
) -> dict:
    """
    Monta o contexto enviado à IA: os candidatos lexicais encontrados pelo
    matcher, mais a lista de TODOS os códigos válidos do catálogo (para a
    IA poder classificar uma categoria que o matcher não sugeriu, mas que
    está dentro do universo permitido).
    """
    return {
        "candidatos_lexicais": [
            {"codigo_catalogo": e.codigo, "familia": e.familia, "subcategoria": e.subcategoria}
            for e in candidatos_lexicais
        ],
        "codigos_validos": [e.codigo for e in catalogo.todas_entradas()],
    }


def _entrada_para_categoria_detectada(
    entrada: EntradaCatalogo,
    tipo: str,
    confianca: float,
    intensidade_semantica: float,
) -> CategoriaDetectada:
    """Monta um CategoriaDetectada a partir da entrada do catálogo + julgamento da IA."""
    return CategoriaDetectada(
        tipo=tipo,
        codigo_catalogo=entrada.codigo,
        familia=entrada.familia,
        subcategoria=entrada.subcategoria,
        nicho=entrada.nicho,
        area_responsavel=entrada.areas.primaria,
        confianca=confianca,
        intensidade_semantica=intensidade_semantica,
    )


def processar_semantica_resposta(
    cliente_id: str,
    texto: str,
    catalogo: CatalogoNSI,
    cliente_ia: ClienteIA,
) -> tuple[list[CategoriaDetectada], list[Evidencia], bool]:
    """
    Classifica semanticamente uma resposta individual.

    Retorna (categorias_detectadas, evidencias, sucesso_ia).
    `sucesso_ia=False` significa que a IA falhou para esta resposta —
    quem orquestra o pipeline decide o que fazer (normalmente, acionar
    o fallback do lote inteiro via services/fallback_handler.py).

    `categorias_detectadas` já respeita o limite de 5 (Contrato 4.3).
    """
    candidatos_lexicais_brutos = buscar_candidatos(texto, catalogo)
    entradas_candidatas = list({c.entrada.codigo: c.entrada for c in candidatos_lexicais_brutos}.values())

    requisicao = RequisicaoIA(
        tarefa="classificacao_semantica",
        texto=texto,
        contexto=_montar_contexto(texto, entradas_candidatas, catalogo),
        prompt_sistema=_PROMPT_SISTEMA,
        versao_prompt=VERSAO_PROMPT_SEMANTICA,
    )

    resultado = chamar_com_fallback(cliente_ia, requisicao)
    if not resultado.sucesso:
        return [], [], False

    categorias_brutas = resultado.resposta.conteudo.get("categorias", [])

    quantidade_evidencias_por_codigo: dict[str, int] = defaultdict(int)
    candidatos_indexados: list[tuple[CategoriaDetectada, Evidencia]] = []

    for item in categorias_brutas:
        codigo = item.get("codigo_catalogo")
        entrada = catalogo.buscar_por_codigo(codigo)
        if entrada is None:
            # IA retornou um código fora do catálogo -> descartado silenciosamente
            # não é erro de pipeline, é resposta da IA fora do universo permitido.
            continue

        confianca = float(item.get("confianca", 0.0))
        intensidade = float(item.get("intensidade_semantica", 0.0))
        trecho = item.get("trecho_evidencia", "")

        # O tipo (força/dor) vem da própria entrada do catálogo, não da IA —
        # a IA classifica a SUBCATEGORIA; se a subcategoria correta é
        # ATEND-006 (Cordialidade, tipo F no catálogo), o tipo é "forca"
        # por definição do catálogo, não por julgamento adicional da IA.
        # Isso evita uma fonte de inconsistência: a IA poderia em teoria
        # dizer "tipo: dor" para um código que o catálogo define como força.
        tipo = "forca" if entrada.tipo == "F" else "dor"

        categoria = _entrada_para_categoria_detectada(entrada, tipo, confianca, intensidade)
        evidencia = Evidencia(
            cliente_id=cliente_id,
            trecho=trecho,
            confianca=confianca,
            intensidade_semantica=intensidade,
        )
        candidatos_indexados.append((categoria, evidencia))
        quantidade_evidencias_por_codigo[codigo] += 1

    categorias_detectadas = [par[0] for par in candidatos_indexados]
    resultado_limite = ordenar_e_aplicar_limite(
        categorias_detectadas, dict(quantidade_evidencias_por_codigo)
    )

    # Pareamento robusto categoria <-> evidência: usa identidade de objeto
    # (id()), não igualdade de conteúdo, para nunca descolar o par em caso
    # de duas categorias com valores idênticos (mesmo código, mesma
    # confiança, mesma intensidade — caso raro mas possível).
    evidencia_por_id_categoria = {id(cat): evid for cat, evid in candidatos_indexados}
    evidencias_mantidas = [
        evidencia_por_id_categoria[id(c)] for c in resultado_limite.mantidas
    ]

    return resultado_limite.mantidas, evidencias_mantidas, True


def agregar_semantica_lote(
    categorias_por_resposta: list[tuple[str, list[CategoriaDetectada], list[Evidencia]]],
    total_respostas: int,
) -> ResultadoSemantico:
    """
    Agrega as classificações semânticas de todas as respostas no nível
    do lote, calculando incidência, confiança média, intensidade
    semântica média e ocorrências por código de catálogo.

    `categorias_por_resposta` é uma lista de (cliente_id, categorias, evidencias)
    por resposta — já com o limite de 5 aplicado por resposta individual.
    """
    por_codigo: dict[str, list[CategoriaDetectada]] = defaultdict(list)
    evidencias_por_codigo: dict[str, list[Evidencia]] = defaultdict(list)

    for cliente_id, categorias, evidencias in categorias_por_resposta:
        for cat in categorias:
            por_codigo[cat.codigo_catalogo].append(cat)
        # Evidências são associadas por ordem posicional às categorias da
        # mesma resposta (mesmo código), já que Evidencia não carrega
        # codigo_catalogo no Contrato — a correlação é feita aqui, no
        # momento da agregação, pela mesma ordem em que foram geradas.
        for cat, evid in zip(categorias, evidencias):
            evidencias_por_codigo[cat.codigo_catalogo].append(evid)

    dores: list[CategoriaAgregada] = []
    forcas: list[CategoriaAgregada] = []

    for codigo, categorias in por_codigo.items():
        primeira = categorias[0]
        ocorrencias = len(categorias)
        incidencia = round(ocorrencias / total_respostas * 100, 1) if total_respostas > 0 else 0.0
        confianca_media = round(mean(c.confianca for c in categorias), 1)
        intensidade_media = round(mean(c.intensidade_semantica for c in categorias), 1)

        agregada = CategoriaAgregada(
            codigo_catalogo=codigo,
            familia=primeira.familia,
            subcategoria=primeira.subcategoria,
            nicho=primeira.nicho,
            incidencia_percentual=incidencia,
            confianca_media=confianca_media,
            intensidade_semantica_media=intensidade_media,
            ocorrencias=ocorrencias,
            evidencias=evidencias_por_codigo[codigo],
        )

        if primeira.tipo == "forca":
            forcas.append(agregada)
        else:
            dores.append(agregada)

    dores.sort(key=lambda d: -d.incidencia_percentual)
    forcas.sort(key=lambda f: -f.incidencia_percentual)

    return ResultadoSemantico(dores_identificadas=dores, forcas_identificadas=forcas)
