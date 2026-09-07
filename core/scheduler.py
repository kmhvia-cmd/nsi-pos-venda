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


def calcular_d8(data_upload: str) -> dict:
    """
    Recebe data de criação do lote (ISO format).
    Retorna informações do D+8.
    """
    criado_em = datetime.fromisoformat(data_upload)
    data_disparo = criado_em + timedelta(days=8)
    agora = datetime.now()
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