# -*- coding: utf-8 -*-
"""
NSI - tests/unit/test_payload_hash.py (Sprint B, B4.3 - ADR-009)

Testes unitarios, em Python puro, do modulo de producao
core/payload_hash.py - calculo canonico do payload_hash dos cinco
comandos do catalogo de eventos operacionais (Especificacao Tecnica da
Sprint B, Secao 18, B4.3, "payload_hash"; formato aprovado D3).

Determinismo, ordenacao, insensibilidade a ordem dos registros e dos
motivos, discriminador por comando, ausencia da chave de idempotencia,
UTF-8 sem escape, mensagens de erro sem valor recebido e pureza do modulo.
A igualdade com o hash calculado DENTRO de fn_registrar_congelamento e
provada em integracao (tests/integration/test_fn_registrar_congelamento.py);
aqui se prova o mesmo vetor literal que a funcao SQL concatena.

Nenhum destes testes acessa banco.
"""
import ast
import hashlib
import inspect
import re
import uuid
from pathlib import Path

import pytest

from core import payload_hash as ph

LOTE_ID = "3f2c1b9a-7d4e-4c8b-9a1f-0e2d3c4b5a69"
OUTRO_ID = "a1b2c3d4-e5f6-4789-8abc-def012345678"


def _registro(rid, nome="Pessoa", whatsapp="5511900000001", produto="Produto", valido=True, motivos=None) -> dict:
    return {"registro_coleta_id": rid, "nome": nome, "whatsapp": whatsapp, "produto": produto,
            "valido": valido, "motivos_invalidez": motivos}


TODOS_OS_HASHES = [
    lambda: ph.hash_registrar_lote(LOTE_ID, None, [_registro(OUTRO_ID)]),
    lambda: ph.hash_registrar_congelamento(LOTE_ID),
    lambda: ph.hash_confirmar_disparo(LOTE_ID, 3),
    lambda: ph.hash_registrar_correcao(LOTE_ID, OUTRO_ID, "Nome", "5511900000001", "Produto", True, None),
    lambda: ph.hash_registrar_tentativa_nao_resolvida(LOTE_ID, "codigo_ausente", None),
]


# ============================================================
# Formato e determinismo
# ============================================================

@pytest.mark.parametrize("calcular", TODOS_OS_HASHES)
def test_sha256_hexadecimal_minusculo_de_64_caracteres(calcular):
    # mesmo formato exigido por ck_comandos_idempotentes_payload_hash_sha256
    assert re.fullmatch(r"[0-9a-f]{64}", calcular())


@pytest.mark.parametrize("calcular", TODOS_OS_HASHES)
def test_deterministico(calcular):
    assert calcular() == calcular()


def test_hashes_dos_cinco_comandos_sao_distintos():
    assert len({calcular() for calcular in TODOS_OS_HASHES}) == 5


# ============================================================
# Congelamento: vetor identico ao calculado pela funcao SQL
# ============================================================

def test_congelamento_e_o_vetor_literal_da_funcao_sql():
    """fn_registrar_congelamento faz sha256 de
    '{"comando":"registrar_congelamento","lote_id":"' || lote_id::text || '"}'."""
    literal = '{"comando":"registrar_congelamento","lote_id":"' + LOTE_ID + '"}'
    assert ph.hash_registrar_congelamento(LOTE_ID) == hashlib.sha256(literal.encode("utf-8")).hexdigest()


def test_uuid_e_normalizado_para_texto_canonico_minusculo():
    assert ph.hash_registrar_congelamento(LOTE_ID.upper()) == ph.hash_registrar_congelamento(LOTE_ID)
    assert ph.hash_registrar_congelamento(uuid.UUID(LOTE_ID)) == ph.hash_registrar_congelamento(LOTE_ID)


# ============================================================
# Ordenacao canonica
# ============================================================

def test_ordem_dos_registros_nao_altera_o_hash():
    a, b, c = _registro(str(uuid.uuid4())), _registro(str(uuid.uuid4())), _registro(str(uuid.uuid4()))
    assert ph.hash_registrar_lote(LOTE_ID, None, [a, b, c]) == ph.hash_registrar_lote(LOTE_ID, None, [c, a, b])


def test_ordem_dos_motivos_nao_altera_o_hash():
    motivos = ["nome_ausente", "produto_ausente"]
    r1 = _registro(OUTRO_ID, nome=None, produto=None, valido=False, motivos=motivos)
    r2 = _registro(OUTRO_ID, nome=None, produto=None, valido=False, motivos=list(reversed(motivos)))
    assert ph.hash_registrar_lote(LOTE_ID, None, [r1]) == ph.hash_registrar_lote(LOTE_ID, None, [r2])
    assert (ph.hash_registrar_correcao(LOTE_ID, OUTRO_ID, None, "5511900000001", None, False, motivos)
            == ph.hash_registrar_correcao(LOTE_ID, OUTRO_ID, None, "5511900000001", None, False, motivos[::-1]))


def test_ordem_dos_campos_do_registro_nao_altera_o_hash():
    r = _registro(OUTRO_ID)
    invertido = dict(reversed(list(r.items())))
    assert ph.hash_registrar_lote(LOTE_ID, None, [r]) == ph.hash_registrar_lote(LOTE_ID, None, [invertido])


# ============================================================
# Sensibilidade ao conteudo semantico
# ============================================================

@pytest.mark.parametrize("campo,valor", [
    ("nome", "Outra Pessoa"), ("whatsapp", "5511900000002"), ("produto", "Outro Produto"),
    ("valido", False), ("motivos_invalidez", ["nome_ausente"]),
])
def test_cada_campo_do_registro_altera_o_hash(campo, valor):
    base = _registro(OUTRO_ID)
    assert ph.hash_registrar_lote(LOTE_ID, None, [base]) != ph.hash_registrar_lote(LOTE_ID, None, [{**base, campo: valor}])


def test_lote_id_legado_e_lote_id_alteram_o_hash():
    registros = [_registro(OUTRO_ID)]
    base = ph.hash_registrar_lote(LOTE_ID, None, registros)
    assert ph.hash_registrar_lote(LOTE_ID, "NSI-20260101-ABCDEF", registros) != base
    assert ph.hash_registrar_lote(OUTRO_ID, None, [_registro(LOTE_ID)]) != base


def test_total_esperado_altera_o_hash_do_disparo():
    assert ph.hash_confirmar_disparo(LOTE_ID, 1) != ph.hash_confirmar_disparo(LOTE_ID, 2)


def test_motivo_e_codigo_alteram_o_hash_da_tentativa():
    base = ph.hash_registrar_tentativa_nao_resolvida(LOTE_ID, "codigo_inexistente", OUTRO_ID)
    assert ph.hash_registrar_tentativa_nao_resolvida(LOTE_ID, "registro_de_outra_operacao", OUTRO_ID) != base
    assert ph.hash_registrar_tentativa_nao_resolvida(LOTE_ID, "codigo_inexistente", str(uuid.uuid4())) != base


def test_motivos_nulos_e_lista_vazia_sao_entradas_distintas():
    assert (ph.hash_registrar_lote(LOTE_ID, None, [_registro(OUTRO_ID, motivos=None)])
            != ph.hash_registrar_lote(LOTE_ID, None, [_registro(OUTRO_ID, motivos=[])]))


def test_discriminador_separa_comandos_com_os_mesmos_campos():
    """registrar_congelamento e confirmar_disparo compartilham lote_id - o
    discriminador 'comando' impede colisao de entrada semantica."""
    sem_discriminador = hashlib.sha256(('{"lote_id":"' + LOTE_ID + '"}').encode("utf-8")).hexdigest()
    assert ph.hash_registrar_congelamento(LOTE_ID) != sem_discriminador


def test_utf8_sem_escape_ascii():
    nome = "José Ação"
    esperado_texto = ('{"comando":"registrar_correcao","lote_id":"' + LOTE_ID + '","motivos_invalidez":null,'
                      '"nome":"' + nome + '","produto":"Produto","registro_coleta_id":"' + OUTRO_ID + '",'
                      '"valido":true,"whatsapp":"5511900000001"}')
    assert (ph.hash_registrar_correcao(LOTE_ID, OUTRO_ID, nome, "5511900000001", "Produto", True, None)
            == hashlib.sha256(esperado_texto.encode("utf-8")).hexdigest())


# ============================================================
# Chave de idempotencia nunca entra; valor nunca vaza
# ============================================================

@pytest.mark.parametrize("funcao", [
    ph.hash_registrar_lote, ph.hash_registrar_congelamento, ph.hash_confirmar_disparo,
    ph.hash_registrar_correcao, ph.hash_registrar_tentativa_nao_resolvida,
])
def test_chave_de_idempotencia_nao_e_parametro(funcao):
    parametros = set(inspect.signature(funcao).parameters)
    assert not any("chave" in p or "idempot" in p for p in parametros)


@pytest.mark.parametrize("invalido", ["nao-e-uuid", "", None, 123])
def test_uuid_invalido_levanta_erro_sem_o_valor(invalido):
    with pytest.raises(ValueError) as exc_info:
        ph.hash_registrar_congelamento(invalido)
    assert str(exc_info.value) == "identificador UUID invalido"


def test_registro_fora_do_formato_levanta_erro_sem_o_valor():
    sem_campo = {k: v for k, v in _registro(OUTRO_ID, nome="NOME-PRIVADO").items() if k != "produto"}
    with pytest.raises(ValueError) as exc_info:
        ph.hash_registrar_lote(LOTE_ID, None, [sem_campo])
    assert "NOME-PRIVADO" not in str(exc_info.value)
    with pytest.raises(ValueError):
        ph.hash_registrar_lote(LOTE_ID, None, [{**_registro(OUTRO_ID), "extra": 1}])


def test_entrada_do_chamador_nao_e_alterada():
    motivos = ["produto_ausente", "nome_ausente"]
    registro = _registro(OUTRO_ID.upper(), nome=None, produto=None, valido=False, motivos=motivos)
    copia = dict(registro)
    ph.hash_registrar_lote(LOTE_ID, None, [registro])
    assert registro == copia and motivos == ["produto_ausente", "nome_ausente"]


# ============================================================
# Pureza: sem banco, sem I/O
# ============================================================

def test_modulo_e_puro_sem_dependencia_de_banco_ou_io():
    fonte = Path(ph.__file__).read_text(encoding="utf-8")
    importados = set()
    for no in ast.walk(ast.parse(fonte)):
        if isinstance(no, ast.Import):
            importados |= {a.name.split(".")[0] for a in no.names}
        elif isinstance(no, ast.ImportFrom) and no.module:
            importados.add(no.module.split(".")[0])
    assert importados <= {"__future__", "hashlib", "json", "uuid"}, importados
    assert not re.search(r"\bopen\(|\bprint\(", fonte)
