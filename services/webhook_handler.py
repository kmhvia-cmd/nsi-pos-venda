# -*- coding: utf-8 -*-
"""
NSI - services/webhook_handler.py
Responsabilidade: processar payload do webhook da Meta.
Recebe resposta do cliente, identifica, salva. NAO responde.
"""

from datetime import datetime
from adapters.storage import buscar_lote_por_telefone, salvar_resposta_cliente


def processar_webhook(payload: dict) -> dict:
    try:
        entry = payload.get("entry", [{}])[0]
        changes = entry.get("changes", [{}])[0]
        value = changes.get("value", {})

        messages = value.get("messages", [])
        if not messages:
            return {"status": "ignorado", "motivo": "sem mensagens"}

        msg = messages[0]
        telefone = msg.get("from", "")
        tipo = msg.get("type", "")

        if tipo != "text":
            return {"status": "ignorado", "motivo": f"tipo nao suportado: {tipo}"}

        texto = msg.get("text", {}).get("body", "").strip()

        if not texto:
            return {"status": "ignorado", "motivo": "mensagem vazia"}

        lote_id = buscar_lote_por_telefone(telefone)
        if not lote_id:
            return {"status": "ignorado", "motivo": f"telefone {telefone} nao encontrado em nenhum lote"}

        resultado = salvar_resposta_cliente(lote_id, telefone, texto)

        return {"status": "salvo", "telefone": telefone, "lote_id": lote_id, "resultado": resultado}

    except Exception as e:
        return {"status": "erro", "detalhe": str(e)}