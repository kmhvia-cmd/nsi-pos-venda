"""
engine/context.py

Objeto de contexto compartilhado durante a execução do pipeline NSI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from models.output_models import (
    ModeloClassificacao,
    RespostaIndividualCompleta,
    ResultadoEvolucaoTemporal,
    ResultadoExecutivo,
    ResultadoExperienciaHumana,
    ResultadoExperienciaHumanaAgregado,
    ResultadoLinguistico,
    ResultadoLinguisticoAgregado,
    ResultadoMatematico,
    ResultadoSemantico,
)


@dataclass
class ContextoPipeline:
    empresa: str = ""
    segmento: str = ""
    lote_id: str = ""
    versao_catalogo: str = ""
    status_semantico: str = "pendente"
    ia_disponivel: bool = True
    motivo_fallback: Optional[str] = None
    modelo_classificacao: Optional[ModeloClassificacao] = None
    matematica: Optional[ResultadoMatematico] = None
    linguistica_agregada: Optional[ResultadoLinguisticoAgregado] = None
    semantica: Optional[ResultadoSemantico] = None
    experiencia_humana_agregada: Optional[ResultadoExperienciaHumanaAgregado] = None
    evolucao_temporal: Optional[ResultadoEvolucaoTemporal] = None
    executiva: Optional[ResultadoExecutivo] = None
    respostas_individuais: list[RespostaIndividualCompleta] = field(default_factory=list)
    respostas_com_categoria_detectada: int = 0
    evidencias_semanticas_validas: int = 0
    linguistica_por_resposta: list[ResultadoLinguistico] = field(default_factory=list)
    categorias_por_resposta: list[tuple] = field(default_factory=list)
    experiencia_por_resposta: list[tuple] = field(default_factory=list)