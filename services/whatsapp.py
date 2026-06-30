# -*- coding: utf-8 -*-
"""
NSI - services/whatsapp.py
Responsabilidade: disparar template D+8 via WhatsApp Cloud API
NAO e um chatbot. NAO responde mensagens. Apenas dispara.
"""

import requests
from config import Config


def enviar_template_d8(telefone: str, nome: str, empresa: str, produto: str) -> dict:
    telefone = (
        telefone.strip()
        .replace(" ", "")
        .replace("-", "")
        .replace("(", "")
        .replace(")", "")
    )
    if not telefone.startswith("55"):
        telefone = "55" + telefone

    payload = {
        "messaging_product": "whatsapp",
        "to": telefone,
        "type": "template",
        "template": {
            "name": "nsi_pesquisa_v4",
            "language": {"code": "pt_BR"},
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": nome},
                        {"type": "text", "text": empresa},
                        {"type": "text", "text": produto}
                    ]
                }
            ]
        }
    }

    headers = {
        "Authorization": f"Bearer {Config.WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }

    r = requests.post(Config.WHATSAPP_URL, headers=headers, json=payload)
    return {"status": r.status_code, "resposta": r.json()}