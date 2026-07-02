# -*- coding: utf-8 -*-
"""
integration/nsi_integration.py

Integration Layer — fronteira única entre o sistema legado (storage.py,
lote.json, respostas/*.json) e o Motor NSI (engine/pipeline.py).

PRINCÍPIO ARQUITETURAL (aprovado em revisão, não-negociável):
Este é o único módulo do sistema autorizado a conhecer simultaneamente
o formato de persistência legado e o contrato de entrada do Motor.
Nenhum outro módulo (dispatcher.py, rotas Flask, futuro CLI) deve
importar `storage.py` para montar dados para o Motor, nem deve importar
`engine.pipeline` diretamente.

PRINCÍPIO METODOLÓGICO DO NSI (decisão permanente do projeto):
"O NSI nunca inventa fatos." Quando uma informação operacional (status
de entrega, data de envio) não existir na fonte legada, ela permanece
ausente (None) na montagem do `RespostaCliente` — nunca é inferida a
partir de pistas indiretas (como a simples presença de um texto de
resposta). A existência de uma resposta textual não autoriza a criação
de um evento operacional que nunca foi registrado.

Responsabilidade desta camada:
    1. Carregar o lote legado (lote.json via storage.carregar_lote).
    2. Consolidar com respostas/*.json quando existirem (ver nota abaixo).
    3. Adaptar (nunca enriquecer) para o contrato Lote/RespostaCliente.
    4. Compor as dependências do Motor exatamente como demonstrado em
       tests/integration/test_pipeline.py: carregar_catalogo() +
       ClienteGroq() + executar_pipeline(lote, catalogo, cliente_ia).
    5. Retornar SaidaMotorCompleta — nenhum dict bruto, nenhum detalhe
       de persistência escapa desta função para quem a chama.

NOTA SOBRE respostas/*.json (Config.RESPOSTAS_DIR):
Esta primeira versão consome apenas lote.json, porque é a única fonte
hoje disponível nos lotes reais auditados (clientes[].resposta). A
consolidação com adapters.storage.carregar_analises_lote() (saída de
análises já processadas) e com adapters.storage.salvar_resposta_cliente()
(respostas recebidas via webhook, hoje gravadas em data/empresas/<slug>/
respostas/, não em Config.RESPOSTAS_DIR) fica para uma etapa futura,
quando o webhook estiver de fato implementado — não foi inventada uma
consolidação que ainda não tem caso de uso real para testar.
"""

from __future__ import annotations

from datetime import datetime

from adapters.storage import carregar_lote, salvar_saida_motor
from catalog.loader import carregar_catalogo
from engine.pipeline import executar_pipeline
from models.input_models import Lote, RespostaCliente
from models.output_models import SaidaMotorCompleta
from outputs.output_builder import saida_para_dict
from services.ai_classifier import ClienteGroq, ClienteIA


def _montar_resposta_cliente(cliente: dict) -> RespostaCliente:
    """
    Adapta um cliente do formato legado (lote.json) para RespostaCliente.

    REGRA DO CONTRATO (decisão arquitetural aprovada — Bloco 3, Opção A):
    um cliente só é promovido ao estado "respondido" perante o Motor
    quando existir o CONJUNTO COMPLETO de três fatos observados na fonte
    legada: status_entrega == "respondido" e data_resposta (ambos
    gravados por adapters.storage.salvar_resposta_cliente, acionado pelo
    webhook) e data_envio_mensagem (gravado por
    core.scheduler.disparar_lote, no momento da confirmação HTTP 200 do
    envio). Se qualquer um dos três faltar, o cliente permanece com
    status_entrega=None e é excluído do cálculo de respondidos pelo
    Motor — nunca é promovido por aproximação, fallback ou inferência.

    Por que essa regra existe: processors/math_processor.py calcula
    tempo de resposta como `data_resposta - data_envio_mensagem` para
    todo cliente com status_entrega == "respondido". Se um cliente
    responder (via webhook) sem que o lote jamais tenha sido de fato
    disparado — cenário operacional real, não hipotético: o operador
    pode esquecer de chamar /api/lote/<lote_id>/disparar antes de uma
    resposta chegar — data_envio_mensagem ficaria ausente, e essa
    subtração quebraria com TypeError (datetime - None). Exigir o
    conjunto completo elimina esse risco sem tocar em processors/.

    Princípio "o NSI nunca inventa fatos" (decisão permanente do
    projeto): nenhum fallback, nenhuma data aproximada (não usa datas do
    lote), nenhuma inferência a partir de dado parcial. A ausência de
    qualquer um dos três fatos é tratada como "ainda não respondido"
    para o Motor — não é um erro, é um estado real ainda incompleto.

    cliente_id usa o telefone como identificador — não é um dado novo,
    é o mesmo identificador já usado em todo o sistema legado
    (adapters.storage.buscar_lote_por_telefone, salvar_resposta_cliente).
    """
    telefone = cliente.get("telefone", "")

    status_entrega_bruto = cliente.get("status_entrega")
    data_resposta_str = cliente.get("data_resposta")
    data_envio_str = cliente.get("data_envio_mensagem")

    conjunto_completo = (
        status_entrega_bruto == "respondido"
        and data_resposta_str is not None
        and data_envio_str is not None
    )

    if conjunto_completo:
        status_entrega = "respondido"
        data_resposta = datetime.fromisoformat(data_resposta_str)
        data_envio_mensagem = datetime.fromisoformat(data_envio_str)
    else:
        status_entrega = None
        data_resposta = None
        data_envio_mensagem = None

    return RespostaCliente(
        cliente_id=telefone,
        telefone=telefone,
        nome=cliente.get("nome", ""),
        produto=cliente.get("produto", ""),
        resposta=cliente.get("resposta", ""),
        data_envio_mensagem=data_envio_mensagem,
        data_resposta=data_resposta,
        status_entrega=status_entrega,
    )


def _montar_lote(lote_id: str) -> Lote:
    """
    Carrega o lote.json legado via storage.py e monta o objeto Lote
    esperado pelo Motor. Único ponto do sistema que faz essa tradução.
    """
    lote_legado = carregar_lote(lote_id)

    clientes = lote_legado.get("clientes", [])
    respostas = [_montar_resposta_cliente(c) for c in clientes]

    quantidade_enviada = lote_legado.get("total_clientes", len(clientes))
    quantidade_respondida = sum(
        1 for c in clientes if (c.get("resposta") or "").strip()
    )

    criado_em_str = lote_legado.get("criado_em", "")
    try:
        data_envio = datetime.fromisoformat(criado_em_str) if criado_em_str else datetime.now()
    except ValueError:
        data_envio = datetime.now()

    return Lote(
        empresa=lote_legado.get("empresa", ""),
        segmento="generico",
        lote_id=lote_legado.get("lote_id", lote_id),
        data_envio=data_envio,
        quantidade_enviada=quantidade_enviada,
        quantidade_respondida=quantidade_respondida,
        respostas=respostas,
    )


def _compor_cliente_ia() -> ClienteIA:
    """
    Ponto único de composição do provider de IA, reutilizando exatamente
    o mecanismo já demonstrado pelos testes do Motor
    (tests/integration/test_pipeline.py): ClienteGroq() lê
    GROQ_API_KEY/GROQ_MODEL do ambiente sozinho, sem nenhum parâmetro
    adicional exigido por esta camada.
    """
    return ClienteGroq()


def executar_pipeline_nsi(lote_id: str, lote_anterior=None) -> SaidaMotorCompleta:
    """
    Ponto de entrada único da Integration Layer.

    Encapsula toda a sequência: carregar lote legado, montar o objeto
    de domínio do Motor, compor catálogo e cliente IA, executar o
    Pipeline, e retornar a saída completa.

    Nenhum chamador (dispatcher.py, futuras rotas, CLI) precisa
    conhecer storage.py, lote.json, catalog.loader ou
    services.ai_classifier — apenas este ponto de entrada.

    Parâmetros:
        lote_id: identificador do lote a processar.
        lote_anterior: saída anterior da mesma empresa, para a Camada
                       de Evolução Temporal (None se for o primeiro
                       lote processado para essa empresa). A busca
                       automática do lote anterior fica para uma etapa
                       futura — hoje é responsabilidade de quem chama
                       fornecer, se desejado.

    Retorna SaidaMotorCompleta (completa ou parcial, conforme decisão
    interna do Pipeline em caso de fallback de IA).
    """
    lote = _montar_lote(lote_id)
    catalogo = carregar_catalogo()
    cliente_ia = _compor_cliente_ia()

    saida = executar_pipeline(lote, catalogo, cliente_ia, lote_anterior=lote_anterior)

    # Persistência: a saída agregada do lote (não por cliente) é salva
    # ao lado do lote.json original, via outputs.output_builder.saida_para_dict
    # (função já existente e testada do Motor — nenhuma lógica de
    # serialização nova foi inventada aqui).
    salvar_saida_motor(lote_id, saida_para_dict(saida))

    return saida