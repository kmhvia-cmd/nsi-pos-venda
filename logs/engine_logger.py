from __future__ import annotations
import logging, time
from contextlib import contextmanager

_logger = logging.getLogger("nsi.engine")

def configurar_logging(nivel: int = logging.INFO) -> None:
    if not logging.getLogger("nsi").handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        logging.getLogger("nsi").addHandler(handler)
        logging.getLogger("nsi").setLevel(nivel)

def log_inicio_pipeline(lote_id: str, empresa: str) -> None:
    _logger.info(f"[{lote_id}] Pipeline iniciado | empresa={empresa!r}")

def log_fim_pipeline(lote_id: str, status_semantico: str, tempo_total_s: float) -> None:
    _logger.info(f"[{lote_id}] Pipeline concluido | status={status_semantico} | tempo_total={tempo_total_s:.3f}s")

def log_etapa(lote_id: str, etapa: str, tempo_s: float) -> None:
    _logger.info(f"[{lote_id}] Etapa: {etapa} | tempo={tempo_s:.3f}s")

def log_fallback(lote_id: str, motivo: str) -> None:
    _logger.warning(f"[{lote_id}] FALLBACK ativado | motivo={motivo!r}")

def log_erro(lote_id: str, etapa: str, erro: Exception, cliente_id: str | None = None) -> None:
    _logger.error(f"[{lote_id}] Erro em {etapa!r} | {type(erro).__name__}: {erro}")

@contextmanager
def medir_etapa(lote_id: str, nome_etapa: str):
    inicio = time.monotonic()
    try:
        yield
    finally:
        log_etapa(lote_id, nome_etapa, time.monotonic() - inicio)
