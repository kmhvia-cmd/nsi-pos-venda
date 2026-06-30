from __future__ import annotations
from dataclasses import dataclass
from models.output_models import CategoriaDetectada

LIMITE_CATEGORIAS_POR_RESPOSTA = 5

@dataclass
class ResultadoAplicacaoLimite:
    mantidas: list[CategoriaDetectada]
    excedentes: list[CategoriaDetectada]

def _chave_ordenacao(categoria: CategoriaDetectada, quantidade_evidencias: dict[str, int]):
    evidencias = quantidade_evidencias.get(categoria.codigo_catalogo, 0)
    return (-categoria.confianca, -categoria.intensidade_semantica, -evidencias, categoria.codigo_catalogo)

def ordenar_e_aplicar_limite(categorias: list[CategoriaDetectada], quantidade_evidencias: dict[str, int] | None = None) -> ResultadoAplicacaoLimite:
    quantidade_evidencias = quantidade_evidencias or {}
    ordenadas = sorted(categorias, key=lambda c: _chave_ordenacao(c, quantidade_evidencias))
    return ResultadoAplicacaoLimite(mantidas=ordenadas[:LIMITE_CATEGORIAS_POR_RESPOSTA], excedentes=ordenadas[LIMITE_CATEGORIAS_POR_RESPOSTA:])
