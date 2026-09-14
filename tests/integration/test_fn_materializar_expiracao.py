# -*- coding: utf-8 -*-
"""
NSI - tests/integration/test_fn_materializar_expiracao.py (Sprint B, B3.3 - ADR-008)

Testes de integracao REAIS contra PostgreSQL, exclusivamente contra
nsi_test, de nsi_operacional.fn_materializar_expiracao (migration 0003) -
a unica das seis SEM chave de idempotencia externa, idempotente por
desenho via UPDATE condicional.

Idempotencia sob concorrencia real: uma conexao mantem a transacao
ABERTA apos chamar a funcao (segura o lock de linha sobre 'claims'); uma
segunda conexao real, com 'lock_timeout' curto, tenta a mesma chamada -
bloqueia e encerra deterministicamente por timeout, nunca por espera
indefinida. Ambas revertidas ao final - nenhum residuo.

Nenhum teste chama pytest nem executa a suite completa internamente.
"""
import hashlib
import json
import uuid

import psycopg
import pytest

from config import resolver_url_banco_papel

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


def _materializar(cur, registro_coleta_id) -> dict:
    cur.execute("SELECT nsi_operacional.fn_materializar_expiracao(%s)", (registro_coleta_id,))
    return cur.fetchone()[0]


# ============================================================
# Comportamento basico
# ============================================================

def test_materializa_quando_expirado(cur):
    cur.execute("SAVEPOINT sp")
    try:
        registro_coleta_id = _uuid()
        criado = _criar_claim(cur, registro_coleta_id, _hash_valido())
        # Claim expirado (regra aprovada): criado_em e expira_em atualizados
        # juntos, ambos no passado, preservando expira_em > criado_em.
        cur.execute(
            "UPDATE nsi_operacional.claims "
            "SET criado_em = now() - interval '2 minutes', expira_em = now() - interval '1 minute' "
            "WHERE registro_coleta_id = %s",
            (registro_coleta_id,),
        )

        resultado = _materializar(cur, registro_coleta_id)
        assert resultado["materializado"] is True
        assert resultado["claim_id"] == criado["claim_id"]

        cur.execute("SELECT estado FROM nsi_operacional.claims WHERE registro_coleta_id = %s", (registro_coleta_id,))
        assert cur.fetchone()[0] == "expirado_pendente_revisao"

        cur.execute(
            "SELECT count(*) FROM nsi_operacional.eventos_claim WHERE aggregate_id = %s AND tipo = 'claim_expirado'",
            (registro_coleta_id,),
        )
        assert cur.fetchone()[0] == 1
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_no_op_quando_ainda_ativo(cur):
    cur.execute("SAVEPOINT sp")
    try:
        registro_coleta_id = _uuid()
        _criar_claim(cur, registro_coleta_id, _hash_valido())

        resultado = _materializar(cur, registro_coleta_id)
        assert resultado == {"materializado": False}

        cur.execute("SELECT estado FROM nsi_operacional.claims WHERE registro_coleta_id = %s", (registro_coleta_id,))
        assert cur.fetchone()[0] == "ativo"
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_no_op_quando_registro_inexistente(cur):
    cur.execute("SAVEPOINT sp")
    try:
        resultado = _materializar(cur, _uuid())
        assert resultado == {"materializado": False}
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_idempotente_repetido_na_mesma_transacao(cur):
    """Chamado duas vezes seguidas apos materializar - a segunda e no-op,
    nunca um segundo evento (rede de seguranca: eventos_claim_expirado_unico)."""
    cur.execute("SAVEPOINT sp")
    try:
        registro_coleta_id = _uuid()
        _criar_claim(cur, registro_coleta_id, _hash_valido())
        # Claim expirado (regra aprovada): criado_em e expira_em atualizados
        # juntos, ambos no passado, preservando expira_em > criado_em.
        cur.execute(
            "UPDATE nsi_operacional.claims "
            "SET criado_em = now() - interval '2 minutes', expira_em = now() - interval '1 minute' "
            "WHERE registro_coleta_id = %s",
            (registro_coleta_id,),
        )

        r1 = _materializar(cur, registro_coleta_id)
        r2 = _materializar(cur, registro_coleta_id)
        assert r1["materializado"] is True
        assert r2 == {"materializado": False}

        cur.execute(
            "SELECT count(*) FROM nsi_operacional.eventos_claim WHERE aggregate_id = %s AND tipo = 'claim_expirado'",
            (registro_coleta_id,),
        )
        assert cur.fetchone()[0] == 1
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


# ============================================================
# Permissao: nsi_aplicacao e nsi_expiracao tem EXECUTE (chamada trivial,
# sem exigir estado pre-existente - materializado=false para um registro
# inexistente ja prova que o EXECUTE foi concedido, sem depender de
# visibilidade entre transacoes).
# ============================================================

@pytest.mark.parametrize("papel", ["nsi_aplicacao", "nsi_expiracao"])
def test_role_permitida_executa_sem_erro_de_privilegio(papel):
    url = resolver_url_banco_papel(papel, "test")
    conn = psycopg.connect(url)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT nsi_operacional.fn_materializar_expiracao(%s)", (_uuid(),))
        resultado = cursor.fetchone()[0]
        assert resultado == {"materializado": False}
    finally:
        conn.rollback()
        conn.close()


# ============================================================
# Idempotencia sob concorrencia real
# ============================================================

def test_concorrencia_real_apenas_um_materializa(request):
    """
    Diferente do INSERT de fn_criar_claim (que espera de verdade por uma
    chave duplicada ainda nao commitada), fn_materializar_expiracao faz
    UPDATE sobre uma linha PRE-EXISTENTE - o WHERE so encontra a linha se
    ela ja for visivel (MVCC) para a transacao que consulta. Por isso o
    setup precisa ser commitado de fato ANTES das duas conexoes
    concorrentes, para que ambas enxerguem a mesma linha. Para nao deixar
    nenhum evento imutavel commitado, o setup faz INSERT DIRETO em
    'claims' (nunca via fn_criar_claim, que geraria um 'claim_criado'
    commitado) - e a linha e removida ao final via DELETE direto
    ('claims' nao tem trigger de imutabilidade, ao contrario de
    'eventos_claim'). Como nem A nem B chegam a commitar sua chamada de
    fn_materializar_expiracao (ambas revertidas), nenhum evento
    'claim_expirado' chega a ser criado - nada imutavel e tocado, e o
    unico residuo transitorio (a linha de 'claims') e removido.
    """
    url_banco_teste = request.getfixturevalue("url_banco_teste")
    registro_coleta_id = _uuid()

    conn_setup = psycopg.connect(url_banco_teste)
    try:
        cur_setup = conn_setup.cursor()
        cur_setup.execute("SET LOCAL ROLE nsi_eventos_owner")
        cur_setup.execute(
            "INSERT INTO nsi_operacional.claims "
            "(registro_coleta_id, claim_id, token_hash, estado, criado_em, expira_em, versao_atual) "
            "VALUES (%s, %s, %s, 'ativo', now() - interval '10 minutes', now() - interval '1 minute', 1)",
            (registro_coleta_id, _uuid(), _hash_valido()),
        )
        conn_setup.commit()
    finally:
        conn_setup.close()

    try:
        # conn_b so e aberta DENTRO do try de conn_a - se a conexao de
        # conn_b falhar, conn_a ainda assim e sempre revertida e fechada,
        # nunca deixando um lock pendurado em nsi_test.
        conn_a = psycopg.connect(url_banco_teste)
        try:
            cur_a = conn_a.cursor()
            cur_a.execute("SET LOCAL ROLE nsi_eventos_owner")
            resultado_a = _materializar(cur_a, registro_coleta_id)
            assert resultado_a["materializado"] is True
            # transacao de A permanece ABERTA (sem commit) - segura o lock da linha.

            conn_b = psycopg.connect(url_banco_teste)
            try:
                cur_b = conn_b.cursor()
                cur_b.execute("SET LOCAL ROLE nsi_eventos_owner")
                cur_b.execute("SET lock_timeout = '2000ms'")
                with pytest.raises(psycopg.errors.LockNotAvailable):
                    _materializar(cur_b, registro_coleta_id)
            finally:
                conn_b.rollback()
                conn_b.close()
        finally:
            conn_a.rollback()
            conn_a.close()
    finally:
        conn_cleanup = psycopg.connect(url_banco_teste)
        try:
            cur_cleanup = conn_cleanup.cursor()
            cur_cleanup.execute("SET LOCAL ROLE nsi_eventos_owner")
            cur_cleanup.execute(
                "DELETE FROM nsi_operacional.claims WHERE registro_coleta_id = %s",
                (registro_coleta_id,),
            )
            conn_cleanup.commit()
        finally:
            conn_cleanup.close()
