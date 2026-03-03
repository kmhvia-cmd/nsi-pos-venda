import time
from datetime import datetime
from core.processor import load_lotes, update_lote
from config.settings import DISPATCHER_INTERVAL_SECONDS


def run_dispatcher():
    print("Dispatcher iniciado...")

    while True:
        now = datetime.utcnow()

        lotes = load_lotes()

        for lote in lotes:
            if lote["status"] == "WAITING":
                dispatch_time = datetime.fromisoformat(lote["dispatch_at"])

                if dispatch_time <= now:
                    print(f"Lote {lote['id']} pronto para disparo.")

                    # Aqui futuramente entra envio WhatsApp
                    lote["status"] = "DISPATCHED"
                    update_lote(lote)

                    print(f"Lote {lote['id']} marcado como DISPATCHED.")

        time.sleep(DISPATCHER_INTERVAL_SECONDS)
