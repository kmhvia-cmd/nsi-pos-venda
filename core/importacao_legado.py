# -*- coding: utf-8 -*-
"""
NSI — core/importacao_legado.py
Responsabilidade: parte PURA da importacao do legado operacional em JSON
(ADR-010, Secoes 18 a 20; Especificacao Tecnica da Sprint B, Secao 18,
B5.2, itens 5, 6.1, 7, 13 e 14): enumeracao do escopo, SHA-256 de arquivos,
manifesto canonico, conferencia da origem e relatorio.

Modulo de producao sem acesso a banco, sem configuracao e sem estado: so
le arquivos da origem que recebe. E a implementacao UNICA, em Python, do
SHA-256 e do manifesto canonico - usada pelo executor
(scripts/importar_legado.py) e pelos testes. O banco recalcula os dois
SHA-256 (fn_importar_lote_legado e fn_concluir_importacao_legado); o
SHA-256 de cada registro do snapshot e calculado somente no banco e nunca
aqui (item 13).

Escopo (item 6.1), relativo a origem:
    lotes/<diretorio>/lote.json                         -> lote
    correcoes_rejeitadas/<AAAA-MM-DD>/<uuid>.json       -> tentativa recusada
Qualquer outro arquivo e ignorado e NUNCA e enumerado: somente esses dois
diretorios sao listados, e so nessa profundidade. Os nomes de arquivo dos
logs de resposta contem telefone - por isso respostas/, pdfs/, empresas/,
saida_motor.json e CSVs nao sao sequer percorridos.

Privacidade: nenhuma funcao devolve ou interpola valor pessoal. O conteudo
de um lote.json so trafega como bytes, do arquivo para a funcao SQL; o
manifesto e o relatorio carregam apenas caminhos, tamanhos, hashes,
identificadores, enums e contagens. Nenhuma excecao deste modulo interpola
conteudo de arquivo.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

FORMATO_MANIFESTO = "nsi-manifesto-legado/1"

TIPO_LOTE = "lote"
TIPO_TENTATIVA_RECUSADA = "tentativa_recusada"
DESTINO_SOMENTE_MANIFESTO = "somente_manifesto"
DESTINOS_DE_LOTE = ("preservado", "promovido", "recusado", "ja_importado")

DIRETORIO_LOTES = "lotes"
DIRETORIO_TENTATIVAS_RECUSADAS = "correcoes_rejeitadas"
ARQUIVO_DE_LOTE = "lote.json"

_DATA_AAAA_MM_DD = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")
_ARQUIVO_UUID_JSON = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\.json\Z"
)

# Campos de uma entrada do manifesto (item 7), alem de caminho, tamanho,
# SHA-256 e tipo.
_CAMPOS_DO_RETORNO = ("geracao", "destino", "motivo", "lote_id_legado", "lote_id_promovido")


class OrigemInvalida(ValueError):
    """A origem informada nao pode ser usada. Mensagem fixa: nunca interpola
    o caminho recebido."""


class ArquivoDeOrigemAlterado(RuntimeError):
    """Um arquivo do escopo mudou entre a enumeracao e a leitura para a
    importacao. Mensagem fixa: nunca interpola caminho nem conteudo."""

    def __init__(self) -> None:
        super().__init__("arquivo de origem alterado durante a execucao")


@dataclass(frozen=True)
class ArquivoDoEscopo:
    """Um arquivo do escopo, como enumerado: caminho relativo com separador
    '/', tipo, tamanho e SHA-256 dos bytes brutos."""
    caminho_relativo: str
    tipo: str
    tamanho_bytes: int
    sha256: str


def sha256_bytes(conteudo: bytes) -> str:
    """SHA-256 dos bytes brutos, sem nenhuma normalizacao, em hexadecimal
    minusculo com 64 caracteres (item 13)."""
    return hashlib.sha256(conteudo).hexdigest()


def _caminho_normalizado(caminho) -> str:
    return os.path.normcase(os.path.realpath(os.fspath(caminho)))


def validar_origem(origem, diretorio_de_dados) -> Path:
    """Confere a origem ANTES de qualquer leitura: precisa ser informada,
    ser um diretorio existente e nao ser o diretorio de dados da aplicacao
    nem estar dentro dele (B5.2, item 5, passo 2; B6, componente C3 -
    nenhuma execucao abre data/: no ensaio, o executor le somente a copia
    congelada). A comparacao e feita sobre os caminhos reais, de modo que um
    caminho relativo, um link ou uma grafia diferente tambem sao recusados."""
    if origem is None or not os.fspath(origem).strip():
        raise OrigemInvalida("origem nao informada - nao existe valor padrao")
    if diretorio_de_dados is None or not os.fspath(diretorio_de_dados).strip():
        raise OrigemInvalida("diretorio de dados da aplicacao nao informado")
    real_da_origem, real_dos_dados = _caminho_normalizado(origem), _caminho_normalizado(diretorio_de_dados)
    if real_da_origem == real_dos_dados:
        raise OrigemInvalida("a origem nao pode ser o diretorio de dados da aplicacao")
    try:
        contida = os.path.commonpath([real_da_origem, real_dos_dados]) == real_dos_dados
    except ValueError:  # unidades diferentes
        contida = False
    if contida:
        raise OrigemInvalida("a origem nao pode estar dentro do diretorio de dados da aplicacao")
    caminho = Path(origem)
    if not caminho.is_dir():
        raise OrigemInvalida("a origem nao e um diretorio existente")
    return caminho


def _subdiretorios(diretorio: Path) -> list:
    if not diretorio.is_dir():
        return []
    return [d for d in diretorio.iterdir() if d.is_dir()]


def enumerar_escopo(origem) -> list:
    """Enumera os arquivos do escopo (item 6.1), em ordem lexicografica do
    caminho relativo, com tamanho e SHA-256 dos bytes brutos. Lista somente
    lotes/ e correcoes_rejeitadas/, na profundidade exata dos dois padroes -
    nenhum outro diretorio da origem e percorrido."""
    raiz = Path(origem)
    encontrados = []

    for diretorio in _subdiretorios(raiz / DIRETORIO_LOTES):
        arquivo = diretorio / ARQUIVO_DE_LOTE
        if arquivo.is_file():
            encontrados.append((f"{DIRETORIO_LOTES}/{diretorio.name}/{ARQUIVO_DE_LOTE}", TIPO_LOTE, arquivo))

    for diretorio in _subdiretorios(raiz / DIRETORIO_TENTATIVAS_RECUSADAS):
        if not _DATA_AAAA_MM_DD.match(diretorio.name):
            continue
        for arquivo in diretorio.iterdir():
            if arquivo.is_file() and _ARQUIVO_UUID_JSON.match(arquivo.name):
                encontrados.append((
                    f"{DIRETORIO_TENTATIVAS_RECUSADAS}/{diretorio.name}/{arquivo.name}",
                    TIPO_TENTATIVA_RECUSADA, arquivo))

    arquivos = []
    for caminho_relativo, tipo, arquivo in encontrados:
        conteudo = arquivo.read_bytes()
        arquivos.append(ArquivoDoEscopo(caminho_relativo, tipo, len(conteudo), sha256_bytes(conteudo)))
    # Ordem dos pontos de codigo - a mesma da ordenacao por bytes UTF-8 que
    # o banco usa na paridade (COLLATE "C").
    return sorted(arquivos, key=lambda a: a.caminho_relativo)


def ler_arquivo_do_escopo(origem, arquivo: ArquivoDoEscopo) -> bytes:
    """Le os bytes brutos de um arquivo enumerado e confirma que ainda sao
    os da enumeracao. Se mudaram, a execucao nao pode prosseguir com um
    manifesto que ja registrou outro SHA-256."""
    conteudo = (Path(origem) / arquivo.caminho_relativo).read_bytes()
    if len(conteudo) != arquivo.tamanho_bytes or sha256_bytes(conteudo) != arquivo.sha256:
        raise ArquivoDeOrigemAlterado()
    return conteudo


def entrada_de_lote(arquivo: ArquivoDoEscopo, retorno: dict) -> dict:
    """Entrada de tipo 'lote' do manifesto (item 7), com o retorno de
    fn_importar_lote_legado. Somente os campos previstos sao copiados -
    'constraint_violada' e 'destino_original' ficam no registro tecnico e
    no relatorio, nao no manifesto."""
    if arquivo.tipo != TIPO_LOTE:
        raise ValueError("entrada de lote exige arquivo de tipo 'lote'")
    if retorno.get("destino") not in DESTINOS_DE_LOTE:
        raise ValueError("retorno de importacao sem destino reconhecido")
    return {
        "caminho_relativo": arquivo.caminho_relativo,
        "tamanho_bytes": arquivo.tamanho_bytes,
        "sha256": arquivo.sha256,
        "tipo": TIPO_LOTE,
        **{campo: retorno.get(campo) for campo in _CAMPOS_DO_RETORNO},
    }


def entrada_de_tentativa_recusada(arquivo: ArquivoDoEscopo) -> dict:
    """Entrada de tipo 'tentativa_recusada' (item 7): a tentativa recusada
    da A3 entra so no manifesto, nunca e importada nem convertida em evento
    (ADR-010, Secao 20)."""
    if arquivo.tipo != TIPO_TENTATIVA_RECUSADA:
        raise ValueError("entrada de tentativa recusada exige arquivo desse tipo")
    return {
        "caminho_relativo": arquivo.caminho_relativo,
        "tamanho_bytes": arquivo.tamanho_bytes,
        "sha256": arquivo.sha256,
        "tipo": TIPO_TENTATIVA_RECUSADA,
        "geracao": None,
        "destino": DESTINO_SOMENTE_MANIFESTO,
        "motivo": None,
        "lote_id_legado": None,
        "lote_id_promovido": None,
    }


def montar_manifesto(importacao_id, fuso_declarado, entradas) -> bytes:
    """Bytes canonicos do manifesto (item 7): um documento JSON por
    execucao, com chaves ordenadas, separadores sem espaco e UTF-8 sem
    escape de caracteres; 'arquivos' ordenado por caminho_relativo.
    importacao_id em texto canonico minusculo."""
    documento = {
        "formato": FORMATO_MANIFESTO,
        "importacao_id": str(importacao_id).lower(),
        "fuso_declarado": fuso_declarado,
        "arquivos": sorted(entradas, key=lambda e: e["caminho_relativo"]),
    }
    return json.dumps(documento, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def conferir_origem(origem, arquivos, entradas) -> dict:
    """Parte do executor na paridade (item 14): o SHA-256 atual de cada
    arquivo de origem contra o registrado no manifesto, e a presenca de
    todo arquivo enumerado no manifesto com destino explicito. Devolve
    somente booleanos, contagens e caminhos relativos."""
    por_caminho = {}
    duplicadas = set()
    for entrada in entradas:
        caminho = entrada["caminho_relativo"]
        if caminho in por_caminho:
            duplicadas.add(caminho)
        por_caminho[caminho] = entrada

    alterados, sem_destino = [], []
    for arquivo in arquivos:
        entrada = por_caminho.get(arquivo.caminho_relativo)
        if entrada is None or not entrada.get("destino") or arquivo.caminho_relativo in duplicadas:
            sem_destino.append(arquivo.caminho_relativo)
            continue
        caminho = Path(origem) / arquivo.caminho_relativo
        sha256_atual = sha256_bytes(caminho.read_bytes()) if caminho.is_file() else None
        if sha256_atual != entrada.get("sha256"):
            alterados.append(arquivo.caminho_relativo)

    enumerados = {a.caminho_relativo for a in arquivos}
    fora_da_enumeracao = sorted(c for c in por_caminho if c not in enumerados)
    return {
        "origem_confere": not alterados,
        "manifesto_completo": not sem_destino and not fora_da_enumeracao,
        "arquivos_conferidos": len(arquivos),
        "arquivos_alterados": sorted(alterados),
        "arquivos_sem_destino": sorted(sem_destino),
        "entradas_fora_da_enumeracao": fora_da_enumeracao,
    }


def montar_relatorio(importacao_id, fuso_declarado, entradas, retornos, manifesto: bytes,
                     paridade_do_banco: dict, conferencia_da_origem: dict) -> dict:
    """Relatorio da execucao (item 5, passo 9), sem valor pessoal: contagens
    por geracao e destino, motivos de nao promocao e de recusa, e resultado
    da paridade. 'retornos' sao os de fn_importar_lote_legado, na ordem das
    entradas de lote.

    Paridade aprovada exige execucao concluida e todos os itens aplicaveis
    verdadeiros: a do banco, a conferencia dos arquivos de origem e o
    manifesto completo (item 14)."""
    por_geracao_e_destino = Counter()
    motivos_de_nao_promocao = Counter()
    motivos_de_recusa = Counter()
    constraints_violadas = Counter()
    for retorno in retornos:
        por_geracao_e_destino[(retorno.get("geracao") or "nao_classificado", retorno["destino"])] += 1
        if retorno["destino"] == "preservado":
            motivos_de_nao_promocao[retorno.get("motivo") or "sem_motivo"] += 1
        elif retorno["destino"] == "recusado":
            motivos_de_recusa[retorno.get("motivo") or "sem_motivo"] += 1
        if retorno.get("constraint_violada"):
            constraints_violadas[retorno["constraint_violada"]] += 1

    agrupado = {}
    for (geracao, destino), quantidade in sorted(por_geracao_e_destino.items()):
        agrupado.setdefault(geracao, {})[destino] = quantidade

    tentativas = sum(1 for e in entradas if e["tipo"] == TIPO_TENTATIVA_RECUSADA)
    banco_aprovada = paridade_do_banco.get("aprovada") is True
    return {
        "importacao_id": str(importacao_id).lower(),
        "fuso_declarado": fuso_declarado,
        "arquivos_no_manifesto": len(entradas),
        "lotes": len(retornos),
        "tentativas_recusadas_somente_manifesto": tentativas,
        "por_geracao_e_destino": agrupado,
        "motivos_de_nao_promocao": dict(sorted(motivos_de_nao_promocao.items())),
        "motivos_de_recusa": dict(sorted(motivos_de_recusa.items())),
        "constraints_violadas": dict(sorted(constraints_violadas.items())),
        "manifesto_sha256": sha256_bytes(manifesto),
        "paridade": {
            "aprovada": (banco_aprovada and conferencia_da_origem["origem_confere"]
                         and conferencia_da_origem["manifesto_completo"]),
            "concluida": paridade_do_banco.get("concluida") is True,
            "banco_aprovada": banco_aprovada,
            "registro_tecnico": paridade_do_banco.get("registro_tecnico"),
            "contagens": paridade_do_banco.get("contagens"),
            "origem_confere": conferencia_da_origem["origem_confere"],
            "manifesto_completo": conferencia_da_origem["manifesto_completo"],
            "arquivos_alterados": conferencia_da_origem["arquivos_alterados"],
            "arquivos_sem_destino": conferencia_da_origem["arquivos_sem_destino"],
            "entradas_fora_da_enumeracao": conferencia_da_origem["entradas_fora_da_enumeracao"],
        },
    }
