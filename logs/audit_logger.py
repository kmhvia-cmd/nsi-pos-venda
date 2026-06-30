from __future__ import annotations
import logging
from models.output_models import SaidaMotorCompleta

_logger = logging.getLogger("nsi.audit")

def log_saida_final(saida: SaidaMotorCompleta) -> None:
    status_ice = saida.executiva.status_ice if saida.executiva else "N/A"
    ice_nsi = str(saida.executiva.ice_nsi) if saida.executiva else "N/A"
    _logger.info(f"[{saida.lote_id}] Auditoria | empresa={saida.empresa!r} | status={saida.status_semantico!r} | versao_motor={saida.versao_motor!r} | versao_catalogo={saida.versao_catalogo!r} | provider={saida.modelo_classificacao.provider!r} | modelo={saida.modelo_classificacao.modelo!r} | versao_prompt={saida.modelo_classificacao.versao_prompt!r} | evidencias={saida.evidencias_semanticas_validas} | status_ice={status_ice!r} | ice_nsi={ice_nsi} | respostas_individuais={len(saida.respostas_individuais)}")