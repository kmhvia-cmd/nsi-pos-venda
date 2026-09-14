# -*- coding: utf-8 -*-
"""
NSI - tests/integration/test_fn_registrar_heartbeat.py (Sprint B, B3.3 - ADR-008)

Testes de integracao REAIS contra PostgreSQL, exclusivamente contra
nsi_test, de nsi_operacional.fn_registrar_heartbeat (migration 0003).

Fronteira temporal exata testada pela tecnica ja aprovada (Especificacao
Tecnica, Secao 7): 'now()' e estavel durante toda a transacao
('transaction_timestamp()') - fixar 'expira_em' via UPDATE e chamar a
funcao na MESMA transacao produz precisao total, sem sleep e sem
dependencia de relogio de parede.

Mesma disciplina dos demais arquivos desta subetapa: conexao primaria
como migrator ('SET LOCAL ROLE nsi_eventos_owner'), SAVEPOINT por
cenario, rollback total no teardown - nenhum residuo em nsi_test. Nenhum
teste chama pytest nem executa a suite completa internamente.
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


def _heartbeat(cur, registro_coleta_id, claim_id, token_hash, chave) -> dict:
    payload = _payload_hash(registro_coleta_id=registro_coleta_id, claim_id=claim_id, token_hash=token_hash)
    cur.execute(
        "SELECT nsi_operacional.fn_registrar_heartbeat(%s, %s, %s, %s, %s)",
        (registro_coleta_id, claim_id, token_hash, chave, payload),
    )
    return cur.fetchone()[0]


# ============================================================
# Fronteira temporal exata
# ============================================================

@pytest.mark.parametrize("deslocamento_expira, deve_suceder", [
    ("1 microsecond", True),    # 1us apos a fronteira do lado valido - ainda ativo (Cenario ainda valido)
    ("0 seconds", False),       # exatamente na fronteira - ja expirado (Fronteira exata)
    ("-1 microsecond", False),  # 1us antes da fronteira - ja expirado
])
def test_heartbeat_fronteira_temporal_exata(cur, deslocamento_expira, deve_suceder):
    cur.execute("SAVEPOINT sp")
    try:
        registro_coleta_id = _uuid()
        token_hash = _hash_valido()
        criado = _criar_claim(cur, registro_coleta_id, token_hash)
        claim_id = criado["claim_id"]

        # criado_em e expira_em SEMPRE atualizados na mesma instrucao -
        # criado_em fixo em now()-1min garante ck_claims_expira_apos_criado
        # (expira_em > criado_em) para qualquer um dos tres deslocamentos
        # de expira_em testados (todos >> -1 minuto).
        cur.execute(
            "UPDATE nsi_operacional.claims "
            "SET criado_em = now() - interval '1 minute', expira_em = now() + %s::interval "
            "WHERE registro_coleta_id = %s",
            (deslocamento_expira, registro_coleta_id),
        )

        resultado = _heartbeat(cur, registro_coleta_id, claim_id, token_hash, "chave-hb")

        assert resultado["sucesso"] is deve_suceder
        if deve_suceder:
            assert "expira_em" in resultado
        else:
            assert resultado["motivo"] == "expirado_materializado_nesta_chamada"
            cur.execute(
                "SELECT estado FROM nsi_operacional.claims WHERE registro_coleta_id = %s",
                (registro_coleta_id,),
            )
            assert cur.fetchone()[0] == "expirado_pendente_revisao"
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


# ============================================================
# Token/claim_id errados - nunca materializa por credencial invalida
# ============================================================

def test_heartbeat_token_errado_recusado_sem_materializar(cur):
    cur.execute("SAVEPOINT sp")
    try:
        registro_coleta_id = _uuid()
        token_hash = _hash_valido()
        criado = _criar_claim(cur, registro_coleta_id, token_hash)

        resultado = _heartbeat(cur, registro_coleta_id, criado["claim_id"], _hash_valido("errado"), "chave-hb")
        assert resultado["sucesso"] is False
        assert resultado["motivo"] == "token_claim_ou_estado_invalido"

        cur.execute("SELECT estado FROM nsi_operacional.claims WHERE registro_coleta_id = %s", (registro_coleta_id,))
        assert cur.fetchone()[0] == "ativo"
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_heartbeat_claim_id_errado_recusado_sem_materializar(cur):
    cur.execute("SAVEPOINT sp")
    try:
        registro_coleta_id = _uuid()
        token_hash = _hash_valido()
        _criar_claim(cur, registro_coleta_id, token_hash)

        resultado = _heartbeat(cur, registro_coleta_id, _uuid(), token_hash, "chave-hb")
        assert resultado["sucesso"] is False
        assert resultado["motivo"] == "token_claim_ou_estado_invalido"

        cur.execute("SELECT estado FROM nsi_operacional.claims WHERE registro_coleta_id = %s", (registro_coleta_id,))
        assert cur.fetchone()[0] == "ativo"
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_heartbeat_credencial_errada_apos_expiracao_nao_materializa(cur):
    """Mesmo com o claim tecnicamente expirado, uma tentativa com
    credencial ERRADA nunca aciona a materializacao - o efeito colateral
    so ocorre quando claim_id/token_hash estao corretos."""
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

        resultado = _heartbeat(cur, registro_coleta_id, criado["claim_id"], _hash_valido("errado"), "chave-hb")
        assert resultado["sucesso"] is False
        assert resultado["motivo"] == "token_claim_ou_estado_invalido"

        cur.execute("SELECT estado FROM nsi_operacional.claims WHERE registro_coleta_id = %s", (registro_coleta_id,))
        assert cur.fetchone()[0] == "ativo"  # nao materializado
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


# ============================================================
# Idempotencia
# ============================================================

def test_heartbeat_replay_mesma_chave_mesmo_token_sem_novo_evento(cur):
    cur.execute("SAVEPOINT sp")
    try:
        registro_coleta_id = _uuid()
        token_hash = _hash_valido()
        criado = _criar_claim(cur, registro_coleta_id, token_hash)

        r1 = _heartbeat(cur, registro_coleta_id, criado["claim_id"], token_hash, "chave-hb-repete")
        r2 = _heartbeat(cur, registro_coleta_id, criado["claim_id"], token_hash, "chave-hb-repete")
        assert r1 == r2

        cur.execute(
            "SELECT count(*) FROM nsi_operacional.eventos_claim WHERE aggregate_id = %s AND tipo = 'heartbeat_registrado'",
            (registro_coleta_id,),
        )
        assert cur.fetchone()[0] == 1
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_heartbeat_token_novo_mesma_chave_produz_conflito_22023(cur):
    cur.execute("SAVEPOINT sp")
    try:
        registro_coleta_id = _uuid()
        token_hash = _hash_valido()
        criado = _criar_claim(cur, registro_coleta_id, token_hash)
        claim_id = criado["claim_id"]

        r1 = _heartbeat(cur, registro_coleta_id, claim_id, token_hash, "chave-hb-conf")
        assert r1["sucesso"] is True

        token_hash_novo = _hash_valido("novo")
        chave = "chave-hb-conf"
        payload_novo = _payload_hash(registro_coleta_id=registro_coleta_id, claim_id=claim_id, token_hash=token_hash_novo)

        cur.execute("SAVEPOINT sp_conflito")
        with pytest.raises(psycopg.errors.InvalidParameterValue) as exc_info:
            _heartbeat(cur, registro_coleta_id, claim_id, token_hash_novo, chave)
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

        r_replay = _heartbeat(cur, registro_coleta_id, claim_id, token_hash, "chave-hb-conf")
        assert r_replay == r1
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_heartbeat_nunca_expoe_token_ou_payload_hash(cur):
    cur.execute("SAVEPOINT sp")
    try:
        registro_coleta_id = _uuid()
        token_hash = _hash_valido()
        criado = _criar_claim(cur, registro_coleta_id, token_hash)
        resultado = _heartbeat(cur, registro_coleta_id, criado["claim_id"], token_hash, "chave-hb")
        assert "token" not in resultado and "token_hash" not in resultado and "payload_hash" not in resultado
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")
