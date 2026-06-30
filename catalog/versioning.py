from __future__ import annotations
from catalog.loader import CatalogoNSI

def versao_catalogo_corrente(catalogo: CatalogoNSI) -> str:
    return catalogo.versao_catalogo

def mesma_versao(versao_a: str, versao_b: str) -> bool:
    return versao_a == versao_b
