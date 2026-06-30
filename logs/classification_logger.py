from __future__ import annotations
import logging
from models.output_models import ModeloClassificacao

_logger = logging.getLogger("nsi.classification")

def log_classificacao_realizada(lote_id: str, tarefa: str, modelo_classificacao: ModeloClassificacao, categorias_detectadas: list[str], cliente_id: str | None = None) -> None:
    _logger.info(f"[{lote_id}] Classificacao | tarefa={tarefa!r} | provider={modelo_classificacao.provider!r} | modelo={modelo_classificacao.modelo!r} | versao_prompt={modelo_classificacao.versao_prompt!r} | categorias={categorias_detectadas}")

def log_classificacao_ausente(lote_id: str, tarefa: str, motivo: str, cliente_id: str | None = None) -> None:
    _logger.info(f"[{lote_id}] Sem classificacao | tarefa={tarefa!r} | motivo={motivo!r}")