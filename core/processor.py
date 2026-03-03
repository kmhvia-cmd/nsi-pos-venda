import json
import os
from datetime import datetime, timedelta
from config.settings import DAYS_TO_DISPATCH

DATA_PATH = "data/lotes"

os.makedirs(DATA_PATH, exist_ok=True)


def create_lote(nome_arquivo: str):
    now = datetime.utcnow()
    dispatch_at = now + timedelta(days=DAYS_TO_DISPATCH)

    lote = {
        "id": nome_arquivo,
        "created_at": now.isoformat(),
        "dispatch_at": dispatch_at.isoformat(),
        "status": "WAITING"
    }

    with open(f"{DATA_PATH}/{nome_arquivo}.json", "w") as f:
        json.dump(lote, f, indent=4)

    return lote


def load_lotes():
    lotes = []
    for file in os.listdir(DATA_PATH):
        if file.endswith(".json"):
            with open(f"{DATA_PATH}/{file}", "r") as f:
                lotes.append(json.load(f))
    return lotes


def update_lote(lote):
    with open(f"{DATA_PATH}/{lote['id']}.json", "w") as f:
        json.dump(lote, f, indent=4)
