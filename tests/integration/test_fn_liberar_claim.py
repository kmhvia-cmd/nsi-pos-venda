# -*- coding: utf-8 -*-
"""
NSI - tests/integration/test_fn_liberar_claim.py (Sprint B, B3.3 - ADR-008)

Testes de integracao REAIS contra PostgreSQL, exclusivamente contra
nsi_test, de nsi_operacional.fn_liberar_claim (migration 0003).

Mesma disciplina dos demais arquivos: conexao primaria como migrator
('SET LOCAL ROLE nsi_eventos_owner'), SAVEPOINT por cenario, rollback
total no teardown - nenhum residuo em nsi_test. Nenhum teste chama
pytest nem executa a suite completa internamente.
"""
import hashlib
import json
import uuid

import psycopg
import pytest

pytestmark = pytest.mark.pg_integration


def _uuid() -> str:
    return str(uuid.uuid4())


def _hash_valido(rotulo: str = "token-de-teste") -> str:
    return hashlib.sha256(rotulo.encode()).hexdigest()


def _payload_hash(**campos) -> str:
    return hashlib.sha256(json.dumps(campos, sort_keys=True).encode()).hexdigest()


@pytest.fixture
def cur(request):
    url = request.getfixturevalue("url_banco_teste")
    conn = psycopg.connect(url)
    try:
        cursor = conn.cursor()
        cursor.execute("SET LOCAL ROLE nsi_eventos_owner")
        yield cursor
    finally:
        conn.rollback()
        conn.close()


def _criar_claim(cur, registro_coleta_id, token_hash, chave="chave-criar") -> dict:
    payload = _payload_hash(registro_coleta_id=registro_coleta_id, token_hash=token_hash)
    cur.execute(
        "SELECT nsi_operacional.fn_criar_claim(%s, %s, %s, %s)",
        (registro_coleta_id, token_hash, chave, payload),
    )
    return cur.fetchone()[0]


def _liberar(cur, registro_coleta_id, claim_id, token_hash, chave) -> dict:
    payload = _payload_hash(registro_coleta_id=registro_coleta_id, claim_id=claim_id, token_hash=token_hash)
    cur.execute(
        "SELECT nsi_operacional.fn_liberar_claim(%s, %s, %s, %s, %s)",
        (registro_coleta_id, claim_id, token_hash, chave, payload),
    )
    return cur.fetchone()[0]


# ============================================================
# Sucesso
# ============================================================

def test_liberar_com_sucesso(cur):
    cur.execute("SAVEPOINT sp")
    try:
        registro_coleta_id = _uuid()
        token_hash = _hash_valido()
        criado = _criar_claim(cur, registro_coleta_id, token_hash)

        resultado = _liberar(cur, registro_coleta_id, criado["claim_id"], token_hash, "chave-lib")
        assert resultado["sucesso"] is True

        cur.execute("SELECT estado FROM nsi_operacional.claims WHERE registro_coleta_id = %s", (registro_coleta_id,))
        assert cur.fetchone()[0] == "liberado"

        cur.execute(
            "SELECT count(*) FROM nsi_operacional.eventos_claim WHERE aggregate_id = %s AND tipo = 'claim_liberado'",
            (registro_coleta_id,),
        )
        assert cur.fetchone()[0] == 1
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


# ============================================================
# Fronteira temporal exata - liberar na expiracao materializa, nunca libera
# ============================================================

@pytest.mark.parametrize("deslocamento_expira, deve_liberar", [
    ("1 microsecond", True),    # Cenario ainda valido
    ("0 seconds", False),       # Fronteira exata
    ("-1 microsecond", False),  # ja expirado
])
def test_liberar_na_fronteira_materializa_nunca_libera(cur, deslocamento_expira, deve_liberar):
    cur.execute("SAVEPOINT sp")
    try:
        registro_coleta_id = _uuid()
        token_hash = _hash_valido()
        criado = _criar_claim(cur, registro_coleta_id, token_hash)

        # criado_em e expira_em SEMPRE atualizados na mesma instrucao -
        # criado_em fixo em now()-1min preserva ck_claims_expira_apos_criado
        # para qualquer um dos tres deslocamentos de expira_em testados.
        cur.execute(
            "UPDATE nsi_operacional.claims "
            "SET criado_em = now() - interval '1 minute', expira_em = now() + %s::interval "
            "WHERE registro_coleta_id = %s",
            (deslocamento_expira, registro_coleta_id),
        )

        resultado = _liberar(cur, registro_coleta_id, criado["claim_id"], token_hash, "chave-lib-fronteira")

        cur.execute("SELECT estado FROM nsi_operacional.claims WHERE registro_coleta_id = %s", (registro_coleta_id,))
        estado_final = cur.fetchone()[0]

        if deve_liberar:
            assert resultado["sucesso"] is True
            assert estado_final == "liberado"
        else:
            assert resultado["sucesso"] is False
            assert resultado["motivo"] == "expirado_materializado_nesta_chamada"
            assert estado_final == "expirado_pendente_revisao"  # nunca 'liberado'
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_liberar_credencial_errada_apos_expiracao_nao_materializa(cur):
    cur.execute("SAVEPOINT sp")
    try:
        registro_coleta_id = _uuid()
        token_hash = _hash_valido()
        criado = _criar_claim(cur, registro_coleta_id, token_hash)
        # Claim expirado (regra aprovada): criado_em e expira_em atualizados
        # juntos, ambos no passado, preservando expira_em > criado_em.
        cur.execute(
            "UPDATE nsi_operacional.claims "
            "SET criado_em = now() - interval '2 minutes', expira_em = now() - interval '1 minute' "
            "WHERE registro_coleta_id = %s",
            (registro_coleta_id,),
        )

        resultado = _liberar(cur, registro_coleta_id, criado["claim_id"], _hash_valido("errado"), "chave-lib-cred")
        assert resultado["sucesso"] is False
        assert resultado["motivo"] == "token_claim_ou_estado_invalido"

        cur.execute("SELECT estado FROM nsi_operacional.claims WHERE registro_coleta_id = %s", (registro_coleta_id,))
        assert cur.fetchone()[0] == "ativo"
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


# ============================================================
# Idempotencia
# ============================================================

def test_liberar_replay_mesma_chave_sem_novo_evento(cur):
    cur.execute("SAVEPOINT sp")
    try:
        registro_coleta_id = _uuid()
        token_hash = _hash_valido()
        criado = _criar_claim(cur, registro_coleta_id, token_hash)

        r1 = _liberar(cur, registro_coleta_id, criado["claim_id"], token_hash, "chave-lib-repete")
        r2 = _liberar(cur, registro_coleta_id, criado["claim_id"], token_hash, "chave-lib-repete")
        assert r1 == r2

        cur.execute(
            "SELECT count(*) FROM nsi_operacional.eventos_claim WHERE aggregate_id = %s AND tipo = 'claim_liberado'",
            (registro_coleta_id,),
        )
        assert cur.fetchone()[0] == 1
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_liberar_token_novo_mesma_chave_produz_conflito_22023(cur):
    cur.execute("SAVEPOINT sp")
    try:
        registro_coleta_id = _uuid()
        token_hash = _hash_valido()
        criado = _criar_claim(cur, registro_coleta_id, token_hash)
        claim_id = criado["claim_id"]

        r1 = _liberar(cur, registro_coleta_id, claim_id, token_hash, "chave-lib-conf")
        assert r1["sucesso"] is True

        token_hash_novo = _hash_valido("novo")
        chave = "chave-lib-conf"
        payload_novo = _payload_hash(registro_coleta_id=registro_coleta_id, claim_id=claim_id, token_hash=token_hash_novo)

        cur.execute("SAVEPOINT sp_conflito")
        with pytest.raises(psycopg.errors.InvalidParameterValue) as exc_info:
            _liberar(cur, registro_coleta_id, claim_id, token_hash_novo, chave)
        assert exc_info.value.sqlstate == "22023"
        assert str(exc_info.value).strip().startswith("conflito_de_idempotencia")
        # mensagem fixa - nunca inclui chave, token ou payload, checado em str() e repr().
        for rotulo, valor in (("chave", chave), ("token_hash_novo", token_hash_novo), ("payload_novo", payload_novo)):
            if valor in str(exc_info.value) or valor in repr(exc_info.value):
                pytest.fail(
                    f"Vazamento de segredo detectado na excecao de conflito ({rotulo}) - "
                    "mensagem fixa, o valor em si nunca e exibido aqui."
                )
        cur.execute("ROLLBACK TO SAVEPOINT sp_conflito")

        r_replay = _liberar(cur, registro_coleta_id, claim_id, token_hash, "chave-lib-conf")
        assert r_replay == r1
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")
