from __future__ import annotations
import re, unicodedata
from dataclasses import dataclass
from catalog.loader import CatalogoNSI
from models.catalog_models import EntradaCatalogo

@dataclass
class CandidatoCategoria:
    entrada: EntradaCatalogo
    termo_encontrado: str
    tipo_match: str

def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in sem_acento if not unicodedata.combining(c))

def _contem_termo(texto_normalizado: str, termo: str) -> bool:
    termo_normalizado = _normalizar(termo)
    if " " in termo_normalizado:
        return termo_normalizado in texto_normalizado
    return bool(re.search(rf"\b{re.escape(termo_normalizado)}\b", texto_normalizado))

def buscar_candidatos(texto: str, catalogo: CatalogoNSI) -> list[CandidatoCategoria]:
    texto_normalizado = _normalizar(texto)
    candidatos = []
    for entrada in catalogo.todas_entradas():
        if _contem_termo(texto_normalizado, entrada.subcategoria):
            candidatos.append(CandidatoCategoria(entrada, entrada.subcategoria, "subcategoria"))
        for sinonimo in entrada.sinonimos:
            if _contem_termo(texto_normalizado, sinonimo):
                candidatos.append(CandidatoCategoria(entrada, sinonimo, "sinonimo"))
        for giria in entrada.girias:
            if _contem_termo(texto_normalizado, giria):
                candidatos.append(CandidatoCategoria(entrada, giria, "giria"))
        for regionalismo in entrada.regionalismos:
            if _contem_termo(texto_normalizado, regionalismo.termo):
                candidatos.append(CandidatoCategoria(entrada, regionalismo.termo, "regionalismo"))
    return candidatos

def codigos_candidatos(texto: str, catalogo: CatalogoNSI) -> set[str]:
    return {c.entrada.codigo for c in buscar_candidatos(texto, catalogo)}
