"""
models/catalog_models.py

Estruturas que espelham uma entrada do Catálogo NSI v1.1 (91 entradas, 20 famílias).
Espelha catalogo_nsi_v1_operacional.md — nenhum campo aqui existe que não esteja
no catálogo congelado, e nenhum campo do catálogo ficou de fora.

Nenhuma lógica de carregamento ou de matching vive aqui — apenas tipos.
"""

from dataclasses import dataclass, field
from typing import Literal, Optional


TipoEntradaCatalogo = Literal["F", "D"]  # F = Força, D = Dor/Oportunidade


@dataclass
class AreaResponsavel:
    """
    Área de negócio responsável por uma subcategoria do catálogo.
    Contrato v3.1, Seção 4.7 / 9.9 — até 2 áreas por entrada, orientação
    de partida para o motor, nunca verdade fixa.
    """
    primaria: str
    secundaria: Optional[str] = None


@dataclass
class Regionalismo:
    """Uma variação diatópica de um termo, com a região de maior uso."""
    termo: str
    regiao: str
    significado: str


@dataclass
class EntradaCatalogo:
    """
    Uma entrada (subcategoria) do Catálogo NSI v1.1.

    `nicho` é None para subcategorias universais e recebe o nome do segmento
    (ex: "moda") quando a subcategoria for específica de nicho (Contrato Seção 4.4).
    """
    codigo: str  # ex: "ATEND-001"
    tipo: TipoEntradaCatalogo
    familia: str
    subcategoria: str
    areas: AreaResponsavel
    sinonimos: list[str] = field(default_factory=list)
    girias: list[str] = field(default_factory=list)
    regionalismos: list[Regionalismo] = field(default_factory=list)
    emojis: list[str] = field(default_factory=list)
    nicho: Optional[str] = None
