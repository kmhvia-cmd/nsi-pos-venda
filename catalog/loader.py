from __future__ import annotations
import json
from pathlib import Path
from models.catalog_models import AreaResponsavel, EntradaCatalogo, Regionalismo

_CAMINHO_PADRAO = Path(__file__).parent / "catalogo_v1.1.json"


def _dict_para_entrada(dados: dict) -> EntradaCatalogo:
    areas = AreaResponsavel(
        primaria=dados["areas"]["primaria"],
        secundaria=dados["areas"]["secundaria"],
    )
    regionalismos = [
        Regionalismo(termo=r["termo"], regiao=r["regiao"], significado=r["significado"])
        for r in dados["regionalismos"]
    ]
    return EntradaCatalogo(
        codigo=dados["codigo"],
        tipo=dados["tipo"],
        familia=dados["familia"],
        subcategoria=dados["subcategoria"],
        areas=areas,
        sinonimos=dados["sinonimos"],
        girias=dados["girias"],
        regionalismos=regionalismos,
        emojis=dados["emojis"],
        nicho=dados.get("nicho"),
    )


class CatalogoNSI:
    def __init__(self, versao_catalogo: str, entradas: list[EntradaCatalogo]):
        self.versao_catalogo = versao_catalogo
        self._entradas_por_codigo: dict[str, EntradaCatalogo] = {
            e.codigo: e for e in entradas
        }

    @property
    def total_entradas(self) -> int:
        return len(self._entradas_por_codigo)

    def todas_entradas(self) -> list[EntradaCatalogo]:
        return list(self._entradas_por_codigo.values())

    def buscar_por_codigo(self, codigo: str) -> EntradaCatalogo | None:
        return self._entradas_por_codigo.get(codigo)


def carregar_catalogo(caminho=None) -> CatalogoNSI:
    caminho = caminho or _CAMINHO_PADRAO
    dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    entradas = [_dict_para_entrada(e) for e in dados["entradas"]]
    return CatalogoNSI(versao_catalogo=dados["versao_catalogo"], entradas=entradas)