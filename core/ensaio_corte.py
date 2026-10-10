# -*- coding: utf-8 -*-
"""
NSI — core/ensaio_corte.py
Responsabilidade: parte PURA das ferramentas do ensaio de corte da B6
(ADR-008, Secao 16; SPRINT-B6-ESPECIFICACAO-ENSAIO-DE-CORTE.md, Secoes 11,
17, 22 a 24, 28 e 56): area de ensaio, inventario de diretorio (C4), copia
congelada do escopo (C5), levantamento estrutural (C6), indice de
evidencias e varredura de privacidade.

Modulo sem acesso a banco, sem configuracao e sem estado: so le e grava
nos diretorios que recebe. O escopo da importacao, o SHA-256 e a leitura
de arquivos vem de core/importacao_legado.py - a implementacao UNICA.

PRIVACIDADE - regra de todo o modulo: nenhuma saida contem valor pessoal.
  - o inventario lista caminho, tamanho e SHA-256 somente dos arquivos do
    ESCOPO (lotes/<dir>/lote.json e correcoes_rejeitadas/<data>/<uuid>.json,
    cujos caminhos nao sao dado pessoal). Tudo o que esta fora do escopo
    entra apenas como contagem, bytes e um resumo agregado: os nomes dos
    logs de resposta contem telefone e NUNCA sao devolvidos nem gravados;
  - o levantamento estrutural devolve nomes de chave e tipos, nunca valores;
  - nenhuma excecao interpola caminho absoluto nem conteudo de arquivo.

A classificacao por geracao e os destinos sao do banco (migration 0006). O
levantamento estrutural apenas ANTECIPA divergencias contra as listas
fechadas do item 6.2 da B5.2, para decisao humana antes da importacao - nunca
decide destino.
"""
from __future__ import annotations

import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path

from core.importacao_legado import (
    DIRETORIO_LOTES,
    DIRETORIO_TENTATIVAS_RECUSADAS,
    TIPO_LOTE,
    ArquivoDoEscopo,
    enumerar_escopo,
    sha256_bytes,
)

SUBDIRETORIOS_DA_RODADA = ("backup", "origem", "evidencias", "restauracao")
SUBDIRETORIO_ORIGEM = "origem"
SUBDIRETORIO_EVIDENCIAS = "evidencias"
ARQUIVO_DO_INDICE = "indice.json"

_ENSAIO_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\Z")
_TAMANHO_MAXIMO_DE_CHAVE = 60

# Listas fechadas do item 6.2 da B5.2 - as mesmas da migration 0006
# (fn_importar_lote_legado). Um teste estatico compara as duas.
CHAVES_DE_RAIZ_PERMITIDAS = frozenset({
    "lote_id", "empresa", "nome_lote", "data_inicial", "data_final", "csv_original", "criado_em",
    "total_clientes", "total_recebido", "total_valido", "total_invalido", "status", "data_disparo",
    "status_pipeline", "clientes", "clientes_invalidos", "historico_versoes",
})
CHAVES_DE_CLIENTES_PERMITIDAS = frozenset({
    "registro_coleta_id", "nome", "telefone", "produto", "resposta", "data_resposta", "status_entrega",
    "data_envio_mensagem",
})
CHAVES_DE_CLIENTES_INVALIDOS_PERMITIDAS = frozenset({
    "registro_coleta_id", "nome_bruto", "whatsapp_bruto", "produto_bruto", "motivos",
})
_CAMPOS_ESTRUTURAIS = ("lote_id", "criado_em", "clientes", "clientes_invalidos", "historico_versoes",
                       "status", "status_pipeline", "total_recebido", "total_valido", "total_invalido")


class AreaDeEnsaioInvalida(ValueError):
    """A area de ensaio, a rodada ou a origem nao podem ser usadas. Mensagem
    fixa: nunca interpola o caminho recebido."""


class CopiaDivergente(RuntimeError):
    """A copia congelada nao confere com o inventario de referencia."""

    def __init__(self) -> None:
        super().__init__("a copia congelada nao confere com o inventario de referencia")


# ============================================================
# Area de ensaio (Secao 11; decisao D5)
# ============================================================

def _real(caminho) -> str:
    return os.path.normcase(os.path.realpath(os.fspath(caminho)))


def esta_dentro(caminho, base) -> bool:
    """True se 'caminho' e 'base' ou esta contido nela, pelos caminhos reais."""
    real, real_base = _real(caminho), _real(base)
    try:
        return os.path.commonpath([real, real_base]) == real_base
    except ValueError:  # unidades diferentes
        return False


def validar_area_de_ensaio(area, diretorio_de_dados, raiz_do_repositorio) -> Path:
    """Confere a area de ensaio (D5): precisa ser informada - nao existe
    valor padrao, o sistema nunca assume um diretorio (fail closed) -, ser
    um diretorio existente e ser DISJUNTA do diretorio de dados da aplicacao
    e do repositorio: nem dentro deles, nem os contendo."""
    if area is None or not os.fspath(area).strip():
        raise AreaDeEnsaioInvalida("area de ensaio nao informada - nao existe valor padrao")
    caminho = Path(area)
    if not caminho.is_dir():
        raise AreaDeEnsaioInvalida("a area de ensaio nao e um diretorio existente")
    for proibido, rotulo in ((diretorio_de_dados, "o diretorio de dados da aplicacao"),
                             (raiz_do_repositorio, "o repositorio")):
        if proibido is None or not os.fspath(proibido).strip():
            raise AreaDeEnsaioInvalida("diretorio de referencia nao informado")
        if esta_dentro(caminho, proibido) or esta_dentro(proibido, caminho):
            raise AreaDeEnsaioInvalida(f"a area de ensaio nao pode coincidir com, conter ou estar dentro de {rotulo}")
    return caminho


def validar_ensaio_id(ensaio_id) -> str:
    """Identificador da rodada: letras, digitos, '_' e '-', ate 64
    caracteres - nunca um separador de caminho."""
    if not isinstance(ensaio_id, str) or not _ENSAIO_ID.match(ensaio_id):
        raise AreaDeEnsaioInvalida("identificador de ensaio invalido")
    return ensaio_id


def diretorio_da_rodada(area, ensaio_id, subdiretorio=None) -> Path:
    """<area>/<ensaio_id>[/<subdiretorio>] - estrutura fixa da Secao 11."""
    base = Path(area) / validar_ensaio_id(ensaio_id)
    if subdiretorio is None:
        return base
    if subdiretorio not in SUBDIRETORIOS_DA_RODADA:
        raise AreaDeEnsaioInvalida("subdiretorio de rodada desconhecido")
    return base / subdiretorio


def preparar_rodada(area, ensaio_id) -> Path:
    """Cria a estrutura fixa de uma rodada. Falha se a rodada ja existir: uma
    rodada nunca e reaproveitada (Secao 31)."""
    base = diretorio_da_rodada(area, ensaio_id)
    if base.exists():
        raise AreaDeEnsaioInvalida("a rodada ja existe - uma rodada nunca e reaproveitada")
    for subdiretorio in SUBDIRETORIOS_DA_RODADA:
        (base / subdiretorio).mkdir(parents=True)
    return base


def validar_origem_do_ensaio(origem, area) -> Path:
    """No ambiente de ensaio, a origem do executor precisa ser exatamente
    <area>/<ensaio_id>/origem - a copia congelada de uma rodada."""
    if origem is None or not os.fspath(origem).strip():
        raise AreaDeEnsaioInvalida("origem nao informada - nao existe valor padrao")
    caminho = Path(os.path.realpath(os.fspath(origem)))
    if (caminho.name != SUBDIRETORIO_ORIGEM
            or not _ENSAIO_ID.match(caminho.parent.name)
            or _real(caminho.parent.parent) != _real(area)):
        raise AreaDeEnsaioInvalida("a origem do ensaio precisa ser <area de ensaio>/<ensaio_id>/origem")
    if not caminho.is_dir():
        raise AreaDeEnsaioInvalida("a origem do ensaio nao e um diretorio existente")
    return caminho


# ============================================================
# C4 - Inventario de diretorio (Secoes 22 e 23)
# ============================================================

@dataclass(frozen=True)
class Inventario:
    """Retrato de um diretorio. Os arquivos do escopo sao listados; o
    restante so entra agregado - nenhum nome fora do escopo e guardado."""
    arquivos_do_escopo: tuple
    fora_do_escopo_arquivos: int
    fora_do_escopo_bytes: int
    fora_do_escopo_resumo: str


def _resumo(linhas) -> str:
    return sha256_bytes("\n".join(sorted(linhas)).encode("utf-8"))


def inventariar(diretorio) -> Inventario:
    """Inventaria TODO o diretorio: SHA-256 e tamanho de cada arquivo. Os do
    escopo (item 6.1 da B5.2) ficam listados; os demais entram somente na
    contagem, nos bytes e num resumo agregado (SHA-256 das linhas
    'caminho|tamanho|sha256' ordenadas), que muda se qualquer arquivo for
    criado, removido, renomeado ou alterado."""
    raiz = Path(diretorio)
    if not raiz.is_dir():
        raise AreaDeEnsaioInvalida("o diretorio a inventariar nao existe")
    do_escopo = tuple(enumerar_escopo(raiz))
    caminhos_do_escopo = {a.caminho_relativo for a in do_escopo}

    linhas, quantidade, total_de_bytes = [], 0, 0
    for atual, _subdiretorios, arquivos in os.walk(raiz):
        for nome in arquivos:
            caminho = Path(atual) / nome
            relativo = caminho.relative_to(raiz).as_posix()
            if relativo in caminhos_do_escopo:
                continue
            if caminho.is_symlink():
                conteudo = os.readlink(caminho).encode("utf-8", "surrogateescape")
            else:
                conteudo = caminho.read_bytes()
            quantidade += 1
            total_de_bytes += len(conteudo)
            linhas.append(f"{relativo}|{len(conteudo)}|{sha256_bytes(conteudo)}")
    return Inventario(do_escopo, quantidade, total_de_bytes, _resumo(linhas))


def resumo_do_inventario(inventario: Inventario) -> dict:
    """Forma gravavel do inventario (evidencias E3 a E6), sem valor pessoal
    e sem nenhum nome de arquivo fora do escopo."""
    do_escopo = inventario.arquivos_do_escopo
    return {
        "escopo": {
            "lotes": sum(1 for a in do_escopo if a.tipo == TIPO_LOTE),
            "tentativas_recusadas": sum(1 for a in do_escopo if a.tipo != TIPO_LOTE),
            "bytes": sum(a.tamanho_bytes for a in do_escopo),
            "resumo": _resumo(f"{a.caminho_relativo}|{a.tamanho_bytes}|{a.sha256}" for a in do_escopo),
        },
        "fora_do_escopo": {
            "arquivos": inventario.fora_do_escopo_arquivos,
            "bytes": inventario.fora_do_escopo_bytes,
            "resumo": inventario.fora_do_escopo_resumo,
        },
        "arquivos_do_escopo": [
            {"caminho_relativo": a.caminho_relativo, "tipo": a.tipo, "tamanho_bytes": a.tamanho_bytes,
             "sha256": a.sha256} for a in do_escopo
        ],
    }


def inventario_do_resumo(resumo: dict) -> Inventario:
    """Reconstroi o inventario a partir da forma gravada."""
    fora = resumo["fora_do_escopo"]
    return Inventario(
        tuple(ArquivoDoEscopo(a["caminho_relativo"], a["tipo"], a["tamanho_bytes"], a["sha256"])
              for a in resumo["arquivos_do_escopo"]),
        fora["arquivos"], fora["bytes"], fora["resumo"])


def comparar_inventarios(antes: Inventario, depois: Inventario) -> dict:
    """Compara dois inventarios (prova de quiescencia I1 = I2 = I3, Secao 23).
    Devolve somente booleanos, contagens e caminhos do escopo."""
    a = {x.caminho_relativo: x for x in antes.arquivos_do_escopo}
    d = {x.caminho_relativo: x for x in depois.arquivos_do_escopo}
    adicionados = sorted(c for c in d if c not in a)
    removidos = sorted(c for c in a if c not in d)
    alterados = sorted(c for c in a if c in d and a[c] != d[c])
    fora_identico = (antes.fora_do_escopo_arquivos == depois.fora_do_escopo_arquivos
                     and antes.fora_do_escopo_bytes == depois.fora_do_escopo_bytes
                     and antes.fora_do_escopo_resumo == depois.fora_do_escopo_resumo)
    escopo_identico = not (adicionados or removidos or alterados)
    return {
        "identicos": escopo_identico and fora_identico,
        "escopo_identico": escopo_identico,
        "fora_do_escopo_identico": fora_identico,
        "escopo_adicionados": adicionados,
        "escopo_removidos": removidos,
        "escopo_alterados": alterados,
    }


# ============================================================
# C5 - Copia congelada do escopo (Secao 24)
# ============================================================

def copiar_escopo(instalacao, destino, referencia: Inventario) -> dict:
    """Copia, da instalacao de origem para 'destino', SOMENTE os arquivos do
    escopo (minimizacao), byte a byte, preservando a estrutura; marca a copia
    somente leitura; e confere que ela tem exatamente os arquivos do escopo
    do inventario de referencia, com os mesmos tamanhos e SHA-256, e nada
    alem deles. O destino precisa existir vazio e ser disjunto da
    instalacao. Divergencia levanta CopiaDivergente (falha F4)."""
    raiz, alvo = Path(instalacao), Path(destino)
    if not raiz.is_dir():
        raise AreaDeEnsaioInvalida("a instalacao de origem nao e um diretorio existente")
    if not alvo.is_dir() or any(alvo.iterdir()):
        raise AreaDeEnsaioInvalida("o destino da copia precisa existir e estar vazio")
    if esta_dentro(alvo, raiz) or esta_dentro(raiz, alvo):
        raise AreaDeEnsaioInvalida("o destino da copia nao pode coincidir com, conter ou estar dentro da instalacao")

    copiados = 0
    for arquivo in referencia.arquivos_do_escopo:
        conteudo = (raiz / arquivo.caminho_relativo).read_bytes()
        caminho = alvo / arquivo.caminho_relativo
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_bytes(conteudo)
        os.chmod(caminho, stat.S_IREAD)
        copiados += 1

    copia = inventariar(alvo)
    comparacao = comparar_inventarios(
        Inventario(referencia.arquivos_do_escopo, 0, 0, _resumo([])), copia)
    resultado = {
        "arquivos_copiados": copiados,
        "bytes_copiados": sum(a.tamanho_bytes for a in copia.arquivos_do_escopo),
        "lotes": sum(1 for a in copia.arquivos_do_escopo if a.tipo == TIPO_LOTE),
        "tentativas_recusadas": sum(1 for a in copia.arquivos_do_escopo if a.tipo != TIPO_LOTE),
        "confere": comparacao["identicos"],
        "somente_leitura": True,
    }
    if not comparacao["identicos"]:
        raise CopiaDivergente()
    return resultado


# ============================================================
# C6 - Levantamento estrutural (Secao 17; risco RT1)
# ============================================================

def _tipo(valor) -> str:
    if valor is None:
        return "nulo"
    if isinstance(valor, bool):
        return "booleano"
    if isinstance(valor, (int, float)):
        return "numero"
    if isinstance(valor, str):
        return "texto"
    if isinstance(valor, list):
        return "lista"
    return "objeto"


def _chave(nome) -> str:
    """Nome de chave, truncado: chave e estrutura, mas uma chave inesperada
    e texto livre do documento."""
    return str(nome)[:_TAMANHO_MAXIMO_DE_CHAVE]


def _levantar_lote(conteudo: bytes, diretorio: str) -> dict:
    resultado = {
        "legivel": False, "inicia_com_bom": conteudo.startswith(b"\xef\xbb\xbf"),
        "contem_escape_nulo": b"\\u0000" in conteudo, "tamanho_bytes": len(conteudo),
        "divergencias": [],
    }
    try:
        documento = json.loads(conteudo.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        resultado["divergencias"].append("documento_ilegivel")
        return resultado
    resultado["legivel"] = True
    if resultado["inicia_com_bom"] or resultado["contem_escape_nulo"]:
        # Legivel em Python, mas recusado pelo tipo jsonb (item 6.2).
        resultado["divergencias"].append("documento_ilegivel_para_o_banco")

    resultado["tipo_da_raiz"] = _tipo(documento)
    if not isinstance(documento, dict):
        resultado["divergencias"].append("raiz_nao_e_objeto")
        return resultado

    resultado["chaves_de_raiz"] = sorted(_chave(k) for k in documento)
    fora = sorted(_chave(k) for k in documento if k not in CHAVES_DE_RAIZ_PERMITIDAS)
    resultado["chaves_de_raiz_fora_da_lista"] = fora
    if fora:
        resultado["divergencias"].append("chave_de_raiz_fora_da_lista")
    resultado["tipos"] = {campo: _tipo(documento[campo]) for campo in _CAMPOS_ESTRUTURAIS if campo in documento}

    lote_id = documento.get("lote_id")
    resultado["lote_id_confere_com_o_diretorio"] = isinstance(lote_id, str) and lote_id == diretorio
    if not isinstance(lote_id, str):
        resultado["divergencias"].append("lote_id_nao_e_texto")
    elif lote_id != diretorio:
        resultado["divergencias"].append("identidade_divergente")
    if not isinstance(documento.get("criado_em"), str):
        resultado["divergencias"].append("criado_em_nao_e_texto")

    for lista, permitidas in (("clientes", CHAVES_DE_CLIENTES_PERMITIDAS),
                              ("clientes_invalidos", CHAVES_DE_CLIENTES_INVALIDOS_PERMITIDAS)):
        if lista not in documento:
            if lista == "clientes":
                resultado["divergencias"].append("clientes_ausente")
            continue
        registros = documento[lista]
        if not isinstance(registros, list):
            resultado["divergencias"].append(f"{lista}_nao_e_lista")
            continue
        objetos = [r for r in registros if isinstance(r, dict)]
        com_identidade = [r for r in objetos if "registro_coleta_id" in r]
        chaves = sorted({_chave(k) for r in objetos for k in r})
        fora = sorted({_chave(k) for r in objetos for k in r if k not in permitidas})
        identidade_malformada = sum(
            1 for r in com_identidade
            if not isinstance(r["registro_coleta_id"], str) or not _UUID.match(r["registro_coleta_id"]))
        resultado[lista] = {
            "registros": len(registros),
            "registros_que_nao_sao_objeto": len(registros) - len(objetos),
            "com_registro_coleta_id": len(com_identidade),
            "sem_registro_coleta_id": len(objetos) - len(com_identidade),
            "registro_coleta_id_fora_do_formato": identidade_malformada,
            "chaves": chaves,
            "chaves_fora_da_lista": fora,
        }
        if len(registros) != len(objetos):
            resultado["divergencias"].append(f"{lista}_com_registro_que_nao_e_objeto")
        if fora:
            resultado["divergencias"].append(f"chave_de_{lista}_fora_da_lista")
        if identidade_malformada:
            resultado["divergencias"].append("registro_coleta_id_fora_do_formato")
        if com_identidade and len(com_identidade) != len(objetos):
            resultado["divergencias"].append("mistura_de_identidade")

    historico = documento.get("historico_versoes")
    if "historico_versoes" in documento and (
            not isinstance(historico, dict) or any(not isinstance(v, list) for v in historico.values())):
        resultado["divergencias"].append("historico_versoes_fora_do_formato")
    return resultado


def levantar_estrutura(origem) -> dict:
    """Levantamento estrutural dos lotes de uma origem (evidencia E7):
    legibilidade, chaves e tipos - NUNCA valores -, com as divergencias
    contra as listas fechadas do item 6.2 da B5.2. E indicativo: a
    classificacao e a decisao de destino sao do banco. Um lote com
    divergencia provavelmente sera recusado e, portanto, nao preservado."""
    raiz = Path(origem)
    lotes, contagem = [], {}
    for arquivo in enumerar_escopo(raiz):
        if arquivo.tipo != TIPO_LOTE:
            continue
        diretorio = arquivo.caminho_relativo.split("/")[1]
        item = _levantar_lote((raiz / arquivo.caminho_relativo).read_bytes(), diretorio)
        item["caminho_relativo"] = arquivo.caminho_relativo
        lotes.append(item)
        for divergencia in item["divergencias"]:
            contagem[divergencia] = contagem.get(divergencia, 0) + 1
    com_divergencia = [l["caminho_relativo"] for l in lotes if l["divergencias"]]
    return {
        "lotes": len(lotes),
        "lotes_sem_divergencia": len(lotes) - len(com_divergencia),
        "lotes_com_divergencia": len(com_divergencia),
        "divergencias": dict(sorted(contagem.items())),
        "caminhos_com_divergencia": com_divergencia,
        "chaves_de_raiz_fora_da_lista": sorted({k for l in lotes for k in l.get("chaves_de_raiz_fora_da_lista", [])}),
        "detalhe": lotes,
    }


# ============================================================
# Evidencias (Secoes 28 e 56)
# ============================================================

def gravar_evidencia(diretorio_de_evidencias, nome: str, conteudo: dict) -> Path:
    """Grava uma evidencia como JSON canonico (chaves ordenadas, UTF-8).
    Nunca sobrescreve: uma evidencia ja gravada e definitiva."""
    if not re.match(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,120}\.json\Z", nome) or nome == ARQUIVO_DO_INDICE:
        raise AreaDeEnsaioInvalida("nome de evidencia invalido")
    caminho = Path(diretorio_de_evidencias) / nome
    if caminho.exists():
        raise AreaDeEnsaioInvalida("a evidencia ja existe - evidencias nunca sao sobrescritas")
    caminho.write_bytes(json.dumps(conteudo, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8"))
    return caminho


def fechar_indice(diretorio_de_evidencias) -> dict:
    """Fecha o indice unico das evidencias de uma rodada (Secao 56): cada
    arquivo com tamanho e SHA-256. Devolve o indice e o SHA-256 dele, que
    vai para o relatorio final - qualquer alteracao posterior e detectavel."""
    raiz = Path(diretorio_de_evidencias)
    if (raiz / ARQUIVO_DO_INDICE).exists():
        raise AreaDeEnsaioInvalida("o indice de evidencias ja foi fechado")
    arquivos = []
    for caminho in sorted(p for p in raiz.iterdir() if p.is_file()):
        conteudo = caminho.read_bytes()
        arquivos.append({"arquivo": caminho.name, "tamanho_bytes": len(conteudo), "sha256": sha256_bytes(conteudo)})
    conteudo_do_indice = json.dumps({"arquivos": arquivos}, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
    (raiz / ARQUIVO_DO_INDICE).write_bytes(conteudo_do_indice)
    return {"arquivos": len(arquivos), "indice_sha256": sha256_bytes(conteudo_do_indice)}


def conferir_indice(diretorio_de_evidencias) -> dict:
    """Confere as evidencias contra o indice fechado."""
    raiz = Path(diretorio_de_evidencias)
    conteudo_do_indice = (raiz / ARQUIVO_DO_INDICE).read_bytes()
    registrados = {a["arquivo"]: a for a in json.loads(conteudo_do_indice)["arquivos"]}
    presentes = {p.name for p in raiz.iterdir() if p.is_file() and p.name != ARQUIVO_DO_INDICE}
    alterados = sorted(
        nome for nome in presentes & set(registrados)
        if sha256_bytes((raiz / nome).read_bytes()) != registrados[nome]["sha256"])
    return {
        "confere": not alterados and presentes == set(registrados),
        "indice_sha256": sha256_bytes(conteudo_do_indice),
        "alterados": alterados,
        "ausentes": sorted(set(registrados) - presentes),
        "nao_registrados": sorted(presentes - set(registrados)),
    }


def varrer_evidencias(diretorio_de_evidencias, valores) -> dict:
    """Varredura de privacidade (Secao 28, parte D): procura, em cada
    evidencia, os valores pessoais recebidos - amostrados em memoria pelo
    chamador e NUNCA gravados aqui. Devolve somente nomes de arquivo e
    contagens; os valores encontrados nao sao devolvidos."""
    procurados = {v.encode("utf-8") for v in valores if isinstance(v, str) and len(v.strip()) >= 4}
    com_ocorrencia = []
    arquivos = sorted(p for p in Path(diretorio_de_evidencias).iterdir() if p.is_file())
    for caminho in arquivos:
        conteudo = caminho.read_bytes()
        if any(valor in conteudo for valor in procurados):
            com_ocorrencia.append(caminho.name)
    return {
        "arquivos_varridos": len(arquivos),
        "valores_procurados": len(procurados),
        "arquivos_com_valor_pessoal": com_ocorrencia,
        "sem_valor_pessoal": not com_ocorrencia,
    }


# ============================================================
# Avaliacao da auditoria (Secao 28, partes A e B)
# ============================================================

QUATRO_FUNCOES_DE_IMPORTACAO = ("fn_concluir_importacao_legado", "fn_importar_lote_legado",
                                "fn_iniciar_importacao_legado", "fn_verificar_paridade_legado")
REVISAO_DO_ENSAIO = "0006"


def avaliar_auditoria(resultado: dict, banco: str, papeis_com_acesso, login: str, fuso,
                      impressao_de_referencia=None) -> dict:
    """Avalia o resultado das consultas de auditoria_b6_ensaio.sql contra o
    estado exigido pela especificacao da B6 (Secoes 14 e 28). Devolve a
    lista de divergencias - cada uma um codigo fixo, sem valor - e
    'aprovada'. 'impressao_de_referencia' e a impressao digital do catalogo
    de nsi_test; ausente, a comparacao de catalogo fica registrada como nao
    realizada, e a auditoria nao e aprovada."""
    divergencias = []

    def exigir(condicao: bool, codigo: str) -> None:
        if not condicao:
            divergencias.append(codigo)

    # Parte A - integridade estrutural.
    exigir(resultado["a_revisao"] == {"banco": banco, "revisao": REVISAO_DO_ENSAIO}, "a_banco_ou_revisao")
    exigir(all(v == 0 for v in resultado["a_objetos_invalidos"].values()), "a_objeto_invalido")
    concessoes = resultado["a_concessoes"]
    exigir(concessoes["connect_no_banco"] == sorted(papeis_com_acesso), "a_connect_fora_do_previsto")
    exigir(concessoes["usage_no_schema"] == sorted(papeis_com_acesso), "a_usage_fora_do_previsto")
    exigir(concessoes["concessoes_em_tabela"] == 0, "a_concessao_em_tabela")
    exigir(concessoes["execute_de_nsi_importacao"] == sorted(QUATRO_FUNCOES_DE_IMPORTACAO), "a_execute_fora_do_previsto")
    if impressao_de_referencia is None:
        divergencias.append("a_catalogo_nao_comparado")
    else:
        exigir(resultado["a_catalogo"]["impressao_digital"] == impressao_de_referencia, "a_catalogo_diferente_do_de_teste")

    # Parte B - invariantes da importacao.
    exigir(all(v == 0 for v in resultado["b_tabelas_que_devem_estar_vazias"].values()), "b_evento_recibo_ou_claim")
    execucoes = resultado["b_execucoes"]
    exigir(execucoes["execucoes"] == 1 and execucoes["concluidas"] == 1, "b_execucao_unica_e_concluida")
    exigir(execucoes["logins"] == [login], "b_identidade_tecnica")
    exigir(execucoes["fusos_declarados"] == [fuso], "b_fuso_declarado")
    exigir(execucoes["conclusoes_com_total_divergente"] == 0, "b_total_de_arquivos")
    exigir(execucoes["conclusoes_com_sha256_divergente"] == 0, "b_sha256_do_manifesto")
    for nome, valor in sorted(resultado["b_invariantes"].items()):
        exigir(valor == 0, f"b_{nome}")

    return {"aprovada": not divergencias, "divergencias": divergencias}


__all__ = [
    "ARQUIVO_DO_INDICE", "AreaDeEnsaioInvalida", "CHAVES_DE_CLIENTES_INVALIDOS_PERMITIDAS",
    "CHAVES_DE_CLIENTES_PERMITIDAS", "CHAVES_DE_RAIZ_PERMITIDAS", "CopiaDivergente", "DIRETORIO_LOTES",
    "DIRETORIO_TENTATIVAS_RECUSADAS", "Inventario", "SUBDIRETORIOS_DA_RODADA", "SUBDIRETORIO_EVIDENCIAS",
    "SUBDIRETORIO_ORIGEM", "comparar_inventarios", "conferir_indice", "copiar_escopo", "diretorio_da_rodada",
    "esta_dentro", "fechar_indice", "gravar_evidencia", "inventariar", "inventario_do_resumo",
    "levantar_estrutura", "preparar_rodada", "resumo_do_inventario", "validar_area_de_ensaio",
    "QUATRO_FUNCOES_DE_IMPORTACAO", "REVISAO_DO_ENSAIO", "avaliar_auditoria", "validar_ensaio_id", "validar_origem_do_ensaio", "varrer_evidencias",
]
