# -*- coding: utf-8 -*-
"""
NSI - core/scheduler.py
Responsabilidade: controle temporal real do D+8
"""
from datetime import datetime, timedelta
from adapters.storage import carregar_lote, listar_lotes, salvar_lote_atomico
import json
from pathlib import Path
from config import Config


def calcular_d8(data_upload: str, agora: datetime | None = None) -> dict:
    """
    Recebe data de criação do lote (ISO format).
    Retorna informações do D+8.

    'agora' e opcional (Sprint A3) - permite injetar um relogio
    controlado para testes deterministas da fronteira exata M0+192h,
    sem alterar o comportamento padrao: quando omitido, usa
    datetime.now() exatamente como antes.
    """
    criado_em = datetime.fromisoformat(data_upload)
    data_disparo = criado_em + timedelta(days=8)
    agora = agora if agora is not None else datetime.now()
    dias_restantes = (data_disparo - agora).days
    horas_restantes = int((data_disparo - agora).total_seconds() / 3600)
    pronto = agora >= data_disparo

    return {
        "data_upload":      criado_em.strftime("%d/%m/%Y %H:%M"),
        "data_disparo":     data_disparo.strftime("%d/%m/%Y %H:%M"),
        "dias_restantes":   max(0, dias_restantes),
        "horas_restantes":  max(0, horas_restantes),
        "pronto":           pronto,
        "percentual":       min(100, int(((agora - criado_em).total_seconds() / timedelta(days=8).total_seconds()) * 100))
    }


def atualizar_status_pipeline(lote_id: str, campo: str, valor: bool):
    """
    Atualiza um campo do status_pipeline no JSON do lote.
    """
    caminho = Path(Config.LOTES_DIR) / lote_id / "lote.json"
    if not caminho.exists():
        return False
    with open(caminho, encoding="utf-8") as f:
        lote = json.load(f)
    lote["status_pipeline"][campo] = valor
    salvar_lote_atomico(lote_id, lote)
    return True


def _contar_validos(lote: dict) -> int:
    """
    Contagem de registros validos, com fallback de compatibilidade em
    CASCATA para lotes anteriores a Sprint A2 - nunca confunde um campo
    AUSENTE com valor zero (um .get(chave, 0) encadeado faria isso
    quando total_valido E total_clientes estivessem ambos ausentes,
    como em fixtures de teste anteriores a esta sprint):
      1. total_valido, se o campo existir (mesmo que seja 0);
      2. total_clientes, se o campo existir (mesmo que seja 0);
      3. len(clientes) - ultimo recurso, sempre presente e correto,
         pois "clientes" sempre significou "registros enviaveis".
    """
    if "total_valido" in lote:
        return lote["total_valido"]
    if "total_clientes" in lote:
        return lote["total_clientes"]
    return len(lote.get("clientes", []))


def verificar_lotes_prontos() -> list:
    """
    Verifica todos os lotes e retorna quais já passaram do D+8
    e ainda não foram disparados.
    """
    lotes = listar_lotes()
    prontos = []
    for lote in lotes:
        pipeline = lote.get("status_pipeline", {})
        if pipeline.get("lote_criado") and not pipeline.get("disparo_whatsapp"):
            lote_completo = carregar_lote(lote["lote_id"])
            # Sprint A2 - bloqueio de nivel 1 (listagem). Status e a
            # regra principal - sempre prevalece e sempre bloqueia; a
            # contagem (com fallback em cascata para lotes anteriores
            # a Sprint A2) e defesa de consistencia.
            if lote_completo.get("status") == "sem_registros_validos":
                continue
            if _contar_validos(lote_completo) == 0:
                continue
            d8 = calcular_d8(lote_completo.get("criado_em", ""))
            if d8["pronto"]:
                prontos.append({
                    "lote_id": lote["lote_id"],
                    "empresa": lote.get("empresa"),
                    "d8":      d8
                })
    return prontos

def atualizar_status_lote(lote_id: str, novo_status: str) -> bool:
    """
    Atualiza o campo 'status' principal do lote no JSON.
    """
    caminho = Path(Config.LOTES_DIR) / lote_id / "lote.json"
    if not caminho.exists():
        return False
    with open(caminho, encoding="utf-8") as f:
        lote = json.load(f)
    lote["status"] = novo_status
    salvar_lote_atomico(lote_id, lote)
    return True
def disparar_lote(lote_id: str) -> dict:
    """
    Percorre todos os clientes do lote e dispara o template D+8.
    Atualiza status_pipeline.disparo_whatsapp = True ao final.

    Sprint A2 - bloqueio de nivel 2 (chamada direta): recusa
    deterministicamente qualquer tentativa de disparo para um lote sem
    nenhum registro valido, independentemente de como esta funcao foi
    acionada - verificar_lotes_prontos nao e o unico guardiao. Status e
    a regra principal; a contagem (mesmo fallback de compatibilidade) e
    defesa de consistencia. A recusa nunca chama services.whatsapp,
    nunca escreve em disco e nunca marca disparo_whatsapp/status como
    concluido.
    """
    lote = carregar_lote(lote_id)

    # Status e a regra principal - sempre prevalece e sempre bloqueia;
    # a contagem (fallback em cascata, ver _contar_validos) e defesa de
    # consistencia.
    if lote.get("status") == "sem_registros_validos":
        return {
            "lote_id": lote_id, "enviados": 0, "erros": 0,
            "recusado": True,
            "motivo": "lote sem nenhum registro valido - disparo recusado",
        }
    if _contar_validos(lote) == 0:
        return {
            "lote_id": lote_id, "enviados": 0, "erros": 0,
            "recusado": True,
            "motivo": "lote sem nenhum registro valido - disparo recusado",
        }

    from services.whatsapp import enviar_template_d8

    clientes = lote.get("clientes", [])
    empresa = lote.get("empresa", "")

    enviados = 0
    erros = 0

    for cliente in clientes:
        telefone = cliente.get("telefone", "")
        nome = cliente.get("nome", "")
        produto = cliente.get("produto", "")

        if not telefone:
            erros += 1
            continue

        resultado = enviar_template_d8(telefone, nome, empresa, produto)

        if resultado["status"] == 200:
            enviados += 1
            # Fato real: momento em que o envio foi confirmado (HTTP 200)
            # pela WhatsApp Cloud API. E o dado que integration/nsi_integration.py
            # precisa para calcular tempo de resposta por cliente.
            cliente["data_envio_mensagem"] = datetime.now().isoformat()
        else:
            erros += 1
            print(f"[ERRO] {nome} - {resultado}")

    salvar_lote_atomico(lote_id, lote)

    atualizar_status_pipeline(lote_id, "disparo_whatsapp", True)
    atualizar_status_lote(lote_id, "disparado")

    return {"lote_id": lote_id, "enviados": enviados, "erros": erros}


# ============================================================
# Sprint A3 - orquestracao do fluxo de correcao append-only
# (ADR-007 SS9). Funcoes INTERNAS apenas - nenhuma rota HTTP nesta
# sprint; app.py permanece intocado. Rotas, autenticacao e MFA do
# Operador Interno pertencem a Sprint D.
# ============================================================

def processar_uma_correcao(lote_id: str, codigo_tecnico_bruto: str,
                            nome_bruto: str, whatsapp_bruto: str, produto_bruto: str,
                            agora: datetime | None = None) -> dict:
    """
    Processa UMA linha do CSV de correcao. Codigo ausente/malformado
    NUNCA dispara nenhuma busca (local ou global) e NUNCA adquire o
    lock do lote - a invalidez e puramente sintatica, decidida antes
    de tocar em qualquer lote.json. Resolucao restrita ao lote_id
    informado (escopo da Operacao) - nunca busca global para ACEITAR.

    'agora' e opcional (Sprint A3) - propagado a calcular_d8 para
    testes deterministas da fronteira M0+192h; None usa o relogio real.
    """
    from adapters.storage import (
        _normalizar_codigo_tecnico, carregar_lote, _obter_lock_lote, _escrever_lote_em_disco,
        _buscar_em_clientes, _buscar_em_clientes_invalidos, _existe_em_outro_lote,
        _inicializar_historico_se_necessario, _aplicar_versao_correcao,
        _recalcular_contagens_e_status, _registrar_tentativa_rejeitada,
    )

    codigo_tecnico, motivo_codigo = _normalizar_codigo_tecnico(codigo_tecnico_bruto)
    if motivo_codigo is not None:
        _registrar_tentativa_rejeitada(lote_id, codigo_tecnico_bruto, nome_bruto, whatsapp_bruto, produto_bruto, motivo_codigo)
        return {"codigo_tecnico": codigo_tecnico_bruto, "status": motivo_codigo, "motivos": []}

    # UMA UNICA aquisicao do lock, por toda a secao critica - ler,
    # validar, versionar e escrever ocorrem sob a mesma posse.
    with _obter_lock_lote(lote_id):
        try:
            lote = carregar_lote(lote_id)
        except FileNotFoundError:
            _registrar_tentativa_rejeitada(lote_id, codigo_tecnico, nome_bruto, whatsapp_bruto, produto_bruto, "codigo_inexistente")
            return {"codigo_tecnico": codigo_tecnico, "status": "codigo_inexistente", "motivos": []}

        if _buscar_em_clientes(lote, codigo_tecnico) is not None:
            _registrar_tentativa_rejeitada(lote_id, codigo_tecnico, nome_bruto, whatsapp_bruto, produto_bruto, "registro_ja_valido")
            return {"codigo_tecnico": codigo_tecnico, "status": "registro_ja_valido", "motivos": []}

        original = _buscar_em_clientes_invalidos(lote, codigo_tecnico)
        if original is None:
            motivo = "registro_de_outra_operacao" if _existe_em_outro_lote(lote_id, codigo_tecnico) else "codigo_inexistente"
            _registrar_tentativa_rejeitada(lote_id, codigo_tecnico, nome_bruto, whatsapp_bruto, produto_bruto, motivo)
            return {"codigo_tecnico": codigo_tecnico, "status": motivo, "motivos": []}

        if calcular_d8(lote.get("criado_em", ""), agora=agora)["pronto"]:  # >= M0+192h ja e tardia
            _registrar_tentativa_rejeitada(lote_id, codigo_tecnico, nome_bruto, whatsapp_bruto, produto_bruto, "correcao_tardia")
            return {"codigo_tecnico": codigo_tecnico, "status": "correcao_tardia", "motivos": []}

        _inicializar_historico_se_necessario(lote, codigo_tecnico, original)
        versao = _aplicar_versao_correcao(lote, codigo_tecnico, nome_bruto, whatsapp_bruto, produto_bruto)
        _recalcular_contagens_e_status(lote)
        _escrever_lote_em_disco(lote_id, lote)  # NUNCA salvar_lote_atomico aqui dentro

        status = "aceita" if versao["status_versao"] == "valida" else "ainda_invalida"
        return {"codigo_tecnico": codigo_tecnico, "status": status, "motivos": versao["motivos"]}


def processar_lote_correcoes(lote_id: str, linhas: list) -> dict:
    """Processa cada linha independentemente - uma linha recusada
    nunca bloqueia as demais."""
    resultados = [
        processar_uma_correcao(lote_id, l["codigo_tecnico"], l["nome"], l["whatsapp"], l["produto"])
        for l in linhas
    ]
    recusados = {
        "correcao_tardia", "codigo_inexistente", "registro_de_outra_operacao",
        "registro_ja_valido", "codigo_tecnico_ausente", "codigo_tecnico_invalido",
    }
    return {
        "total_recebido": len(resultados),
        "total_aceito": sum(1 for r in resultados if r["status"] == "aceita"),
        "total_ainda_invalido": sum(1 for r in resultados if r["status"] == "ainda_invalida"),
        "total_recusado": sum(1 for r in resultados if r["status"] in recusados),
        "resultados": resultados,
    }


def processar_correcao_csv(lote_id: str, conteudo_bruto) -> dict:
    """
    Ponto de entrada unico: parsing estrutural + processamento linha a
    linha. Falha estrutural do CSV (cabecalho invalido, campo count
    errado, ou "csv_correcao_sem_registros") retorna {"erro": ...} SEM
    processar nenhuma linha, sem criar historico nem auditoria - nao
    houve nenhuma tentativa de correcao individual apresentada.
    """
    from adapters.storage import _parsear_csv_correcao
    linhas, erro = _parsear_csv_correcao(conteudo_bruto)
    if erro:
        return {"erro": erro}
    return processar_lote_correcoes(lote_id, linhas)