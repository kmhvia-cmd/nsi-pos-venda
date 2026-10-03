# -*- coding: utf-8 -*-
"""
NSI — core/payload_hash.py
Responsabilidade: calculo canonico do payload_hash de idempotencia dos
cinco comandos do catalogo de eventos operacionais (ADR-009, Secoes 6, 9
e 12; Especificacao Tecnica da Sprint B, Secao 18, B4.3, "payload_hash").

Modulo de producao PURO: sem acesso a banco, sem I/O, sem estado. E a
implementacao UNICA do calculo em Python - usada pelo chamador real e
pelos testes. O hash que nsi_operacional.fn_registrar_congelamento
calcula internamente e identico ao de hash_registrar_congelamento() para
o mesmo lote_id.

Formato (aprovado, D3): SHA-256 em hexadecimal minusculo (64 caracteres)
sobre a serializacao canonica da entrada semantica do chamador - JSON com
chaves ordenadas, sem espacos, UTF-8 (sem escape ASCII), com o
discriminador "comando". Identificadores UUID em texto canonico
minusculo.

O que entra: os valores exatamente como passados a funcao SQL, ja
normalizados pela validacao existente (Sprint A2) - nenhum valor pessoal e
alterado aqui. Nunca entra valor gerado pelo servidor e nunca a chave de
idempotencia (que nem e parametro destas funcoes).

Correlacao (ADR-009, Secao 9): os hashes de registrar_lote e
registrar_correcao cobrem conteudo pessoal e sao potencialmente
correlacionaveis - vivem somente em comandos_idempotentes, nunca em
evento, log ou mensagem. Por isso nenhuma excecao deste modulo interpola
valor recebido.
"""
from __future__ import annotations

import hashlib
import json
import uuid

CAMPOS_REGISTRO = ("registro_coleta_id", "nome", "whatsapp", "produto", "valido", "motivos_invalidez")


def _uuid_canonico(valor) -> str:
    """UUID em texto canonico minusculo. Mensagem fixa - nunca o valor."""
    try:
        return str(uuid.UUID(str(valor)))
    except (ValueError, TypeError, AttributeError):
        raise ValueError("identificador UUID invalido") from None


def _motivos_ordenados(motivos):
    return None if motivos is None else sorted(motivos)


def _hash(comando: str, campos: dict) -> str:
    texto = json.dumps({"comando": comando, **campos}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def hash_registrar_lote(lote_id, lote_id_legado, registros) -> str:
    """registrar_lote: lote_id, lote_id_legado e os registros ordenados por
    registro_coleta_id, cada um com seus seis campos e os motivos
    ordenados."""
    normalizados = []
    for registro in registros:
        if set(registro) != set(CAMPOS_REGISTRO):
            raise ValueError("registro fora do formato de seis campos")
        normalizados.append({
            **registro,
            "registro_coleta_id": _uuid_canonico(registro["registro_coleta_id"]),
            "motivos_invalidez": _motivos_ordenados(registro["motivos_invalidez"]),
        })
    normalizados.sort(key=lambda r: r["registro_coleta_id"])
    return _hash("registrar_lote", {
        "lote_id": _uuid_canonico(lote_id),
        "lote_id_legado": lote_id_legado,
        "registros": normalizados,
    })


def hash_registrar_congelamento(lote_id) -> str:
    """registrar_congelamento: somente lote_id (ADR-009, Secao 12)."""
    return _hash("registrar_congelamento", {"lote_id": _uuid_canonico(lote_id)})


def hash_confirmar_disparo(lote_id, total_esperado) -> str:
    """confirmar_disparo: lote_id e a precondicao total_esperado."""
    return _hash("confirmar_disparo", {"lote_id": _uuid_canonico(lote_id), "total_esperado": total_esperado})


def hash_registrar_correcao(lote_id, registro_coleta_id, nome, whatsapp, produto, valido, motivos_invalidez) -> str:
    """registrar_correcao: lote_id, registro_coleta_id, os valores corrigidos
    e os motivos ordenados."""
    return _hash("registrar_correcao", {
        "lote_id": _uuid_canonico(lote_id),
        "registro_coleta_id": _uuid_canonico(registro_coleta_id),
        "nome": nome,
        "whatsapp": whatsapp,
        "produto": produto,
        "valido": valido,
        "motivos_invalidez": _motivos_ordenados(motivos_invalidez),
    })


def hash_registrar_tentativa_nao_resolvida(lote_id, motivo, codigo_tecnico_normalizado) -> str:
    """registrar_tentativa_nao_resolvida: lote_id, motivo e o codigo tecnico
    normalizado (ou nulo)."""
    return _hash("registrar_tentativa_nao_resolvida", {
        "lote_id": _uuid_canonico(lote_id),
        "motivo": motivo,
        "codigo_tecnico_normalizado": (
            None if codigo_tecnico_normalizado is None else _uuid_canonico(codigo_tecnico_normalizado)
        ),
    })
