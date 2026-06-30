"""
processors/experience_processor.py

Camada de Experiência Humana do Motor NSI.
Contrato Oficial do Motor NSI v3.1, Seção 5.

Responsabilidade: inferir o estado emocional do cliente (entusiasmo,
frustração, lealdade etc.), cruzando forma (Linguística) + tema
(Semântica) + contexto. Mede O QUE FOI SENTIDO, nunca COMO FOI DITO
(isso é a Linguística) nem O QUE FOI DITO (isso é a Semântica).

REGRAS OBRIGATÓRIAS DESTA IMPLEMENTAÇÃO (mesma filosofia da Fase 5,
generalizada e formalizada após aprovação):
    - Usa exclusivamente a interface ClienteIA.
    - Nenhum metadado estrutural é solicitado à IA — não há metadado
      estrutural nesta camada (os 10 indicadores SÃO o conteúdo, não há
      catálogo de "tipos de experiência" para consultar como fonte de
      verdade externa). Isso distingue esta camada da Semântica.
    - A IA produz EXCLUSIVAMENTE dados estruturados (10 floats 0-100).
      NENHUMA saída narrativa — nenhum campo de texto livre é solicitado
      ou aceito desta camada. Narrativas pertencem exclusivamente à
      Camada Executiva (Contrato Seção 7).
    - Toda resposta da IA é validável: cada um dos 10 campos é
      explicitamente verificado como número em 0-100 antes de aceito;
      valores fora da faixa ou ausentes são tratados como 0.0, nunca
      propagados sem validação.

Regra de fronteira com a Linguística (Contrato Seção 5.0): a IA recebe
os sinais linguísticos já calculados (forma) e as categorias semânticas
já detectadas (tema) como CONTEXTO de entrada — ela não recalcula forma
nem tema, apenas infere o estado emocional cruzando os dois.

PREMISSA FORMALIZADA (decisão de produto registrada, não-negociável):
os 10 indicadores desta camada representam uma INTERPRETAÇÃO da IA sobre
o estado emocional PERCEBIDO do cliente a partir do texto de uma resposta
de pesquisa comercial. Eles NÃO constituem, e nunca devem ser tratados
ou apresentados como, um diagnóstico psicológico, uma avaliação clínica,
ou qualquer afirmação sobre a saúde mental ou bem-estar real da pessoa.
Qualquer consumidor desta saída (Dashboard, PDF, documentação futura)
deve preservar essa distinção e nunca rotular os indicadores como
"diagnóstico" ou equivalente.
"""

from __future__ import annotations

from statistics import mean

from models.output_models import (
    CategoriaDetectada,
    ResultadoExperienciaHumana,
    ResultadoExperienciaHumanaAgregado,
    ResultadoLinguistico,
)
from services.ai_classifier import ClienteIA, RequisicaoIA
from services.fallback_handler import chamar_com_fallback

VERSAO_PROMPT_EXPERIENCIA = "v1"

_CAMPOS_EXPERIENCIA = (
    "entusiasmo", "confianca_cliente", "frustracao", "envolvimento",
    "empolgacao", "seguranca", "indiferenca", "lealdade", "gratidao", "desgaste",
)

_PROMPT_SISTEMA = """\
Você é a Camada de Experiência Humana do Motor NSI.

Você NÃO mede a forma da fala (isso já foi calculado e está no contexto
como "linguistica"). Você NÃO mede o tema/categoria (isso já foi
calculado e está no contexto como "categorias_semanticas"). Você mede
o ESTADO EMOCIONAL INFERIDO do cliente, cruzando forma + tema + o texto
original.

Exemplo de fronteira (Contrato NSI, Seção 5.0): a frase "Foi bom." tem
polaridade linguística positiva e intensidade emocional baixa (frase
curta, sem pontuação intensa, sem emoji) — isso já está no contexto.
Sua tarefa é decidir, a partir disso, se o cliente está "Indiferente"
(baixo entusiasmo apesar de polaridade positiva) ou em estado de
"Confiança tranquila" (positivo sem precisar de entusiasmo). Essa
distinção fina é exclusivamente sua.

Retorne EXATAMENTE estes 10 campos, cada um um número de 0 a 100,
SEM NENHUM TEXTO NARRATIVO, SEM EXPLICAÇÃO, APENAS OS NÚMEROS:
- entusiasmo: intensidade de empolgação expressa
- confianca_cliente: segurança percebida na relação com a empresa
- frustracao: insatisfação com componente emocional
- envolvimento: grau de engajamento emocional com a experiência
- empolgacao: pico emocional positivo momentâneo
- seguranca: ausência de receio/dúvida na relação
- indiferenca: ausência de carga emocional, mesmo com polaridade definida
- lealdade: sinal de vínculo contínuo, não pontual
- gratidao: reconhecimento explícito de benefício recebido
- desgaste: sinal de cansaço/saturação na relação

Responda APENAS em JSON estruturado, sem nenhum campo de texto livre,
no formato exato:
{"entusiasmo": 0.0, "confianca_cliente": 0.0, "frustracao": 0.0, "envolvimento": 0.0, "empolgacao": 0.0, "seguranca": 0.0, "indiferenca": 0.0, "lealdade": 0.0, "gratidao": 0.0, "desgaste": 0.0}
"""


def _montar_contexto(
    texto: str,
    linguistica: ResultadoLinguistico,
    categorias_semanticas: list[CategoriaDetectada],
) -> dict:
    """
    Monta o contexto enviado à IA: sinais de forma (linguística) e tema
    (semântica) já calculados — a IA cruza isso com o texto, não recalcula.
    """
    return {
        "linguistica": {
            "intensidade_emocional": linguistica.intensidade_emocional,
            "polaridade_linguistica": linguistica.polaridade_linguistica,
            "engajamento_linguistico": linguistica.engajamento_linguistico,
            "formalidade": linguistica.formalidade,
            "marca_regional": linguistica.marca_regional,
        },
        "categorias_semanticas": [
            {
                "tipo": c.tipo,
                "familia": c.familia,
                "subcategoria": c.subcategoria,
                "confianca": c.confianca,
            }
            for c in categorias_semanticas
        ],
    }


def _validar_e_extrair_campo(conteudo: dict, campo: str) -> float:
    """
    Valida que um campo é um número em 0-100. Valores ausentes, não
    numéricos, ou fora da faixa são tratados como 0.0 — nunca propagados
    sem validação (regra de "toda resposta validável" desta fase).
    """
    valor = conteudo.get(campo)
    try:
        valor_float = float(valor)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(valor_float, 100.0))


def processar_experiencia_humana_resposta(
    texto: str,
    linguistica: ResultadoLinguistico,
    categorias_semanticas: list[CategoriaDetectada],
    cliente_ia: ClienteIA,
) -> tuple[ResultadoExperienciaHumana | None, bool]:
    """
    Infere a Experiência Humana de uma resposta individual.

    Retorna (resultado, sucesso_ia). Em falha, resultado é None e
    sucesso_ia é False — quem orquestra decide o que fazer (fallback
    do lote inteiro).
    """
    requisicao = RequisicaoIA(
        tarefa="experiencia_humana",
        texto=texto,
        contexto=_montar_contexto(texto, linguistica, categorias_semanticas),
        prompt_sistema=_PROMPT_SISTEMA,
        versao_prompt=VERSAO_PROMPT_EXPERIENCIA,
    )

    resultado = chamar_com_fallback(cliente_ia, requisicao)
    if not resultado.sucesso:
        return None, False

    conteudo = resultado.resposta.conteudo
    valores = {campo: _validar_e_extrair_campo(conteudo, campo) for campo in _CAMPOS_EXPERIENCIA}

    return ResultadoExperienciaHumana(**valores), True


def agregar_experiencia_humana_lote(
    resultados: list[ResultadoExperienciaHumana],
) -> ResultadoExperienciaHumanaAgregado:
    """Agrega a Experiência Humana de todas as respostas no nível do lote."""
    if not resultados:
        return ResultadoExperienciaHumanaAgregado(
            entusiasmo_medio=0.0,
            confianca_cliente_media=0.0,
            frustracao_media=0.0,
            envolvimento_medio=0.0,
            empolgacao_media=0.0,
            seguranca_media=0.0,
            indiferenca_media=0.0,
            lealdade_media=0.0,
            gratidao_media=0.0,
            desgaste_medio=0.0,
        )

    return ResultadoExperienciaHumanaAgregado(
        entusiasmo_medio=round(mean(r.entusiasmo for r in resultados), 1),
        confianca_cliente_media=round(mean(r.confianca_cliente for r in resultados), 1),
        frustracao_media=round(mean(r.frustracao for r in resultados), 1),
        envolvimento_medio=round(mean(r.envolvimento for r in resultados), 1),
        empolgacao_media=round(mean(r.empolgacao for r in resultados), 1),
        seguranca_media=round(mean(r.seguranca for r in resultados), 1),
        indiferenca_media=round(mean(r.indiferenca for r in resultados), 1),
        lealdade_media=round(mean(r.lealdade for r in resultados), 1),
        gratidao_media=round(mean(r.gratidao for r in resultados), 1),
        desgaste_medio=round(mean(r.desgaste for r in resultados), 1),
    )
