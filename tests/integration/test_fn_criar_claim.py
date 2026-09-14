# -*- coding: utf-8 -*-
"""
NSI - tests/integration/test_fn_criar_claim.py (Sprint B, B3.3 - ADR-008)

Testes de integracao REAIS contra PostgreSQL, exclusivamente contra
nsi_test, de nsi_operacional.fn_criar_claim (migration 0003).

Conexao primaria: migrator ('SET LOCAL ROLE nsi_eventos_owner') - o
owner tem EXECUTE implicito nas proprias funcoes (nao precisa constar na
matriz de GRANT) e SELECT direto nas tabelas, necessario para inspecionar
o efeito das chamadas sem exigir um segundo round-trip via outra role.
Cada teste roda numa transacao propria, revertida no teardown da
fixture - nenhum residuo em nsi_test.

Concorrencia real ("dois workers"): duas conexoes reais como
nsi_aplicacao (a role que de fato possui EXECUTE nesta funcao), a
segunda com 'lock_timeout' curto - a chamada da segunda BLOQUEIA no
proprio lock de unicidade do PostgreSQL sobre 'registro_coleta_id'
(mesma protecao usada por qualquer INSERT/UNIQUE concorrente) e
encerra deterministicamente por timeout, nunca por espera indefinida.
Ambas as conexoes sao revertidas ao final - nenhum commit real ocorre
neste arquivo.

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
    """Serializacao canonica (JSON, chaves ordenadas) - mesma convencao
    que um chamador Python real usaria antes de invocar a funcao SQL."""
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


def _chamar_fn_criar_claim(cur, registro_coleta_id, token_hash, chave, payload_hash) -> dict:
    cur.execute(
        "SELECT nsi_operacional.fn_criar_claim(%s, %s, %s, %s)",
        (registro_coleta_id, token_hash, chave, payload_hash),
    )
    return cur.fetchone()[0]


# ============================================================
# Sucesso: primeira vez
# ============================================================

def test_criar_pela_primeira_vez(cur):
    cur.execute("SAVEPOINT sp")
    try:
        registro_coleta_id = _uuid()
        token_hash = _hash_valido()
        chave = "chave-001"
        payload_hash = _payload_hash(registro_coleta_id=registro_coleta_id, token_hash=token_hash)

        resultado = _chamar_fn_criar_claim(cur, registro_coleta_id, token_hash, chave, payload_hash)

        assert resultado["sucesso"] is True
        assert uuid.UUID(resultado["claim_id"])
        assert "expira_em" in resultado
        assert resultado["versao_atual"] == 1
        assert "token_hash" not in resultado
        assert "token" not in resultado
        assert "payload_hash" not in resultado
        assert "chave" not in resultado and "chave_idempotencia" not in resultado

        cur.execute(
            "SELECT estado, versao_atual, token_hash FROM nsi_operacional.claims WHERE registro_coleta_id = %s",
            (registro_coleta_id,),
        )
        estado, versao, token_hash_persistido = cur.fetchone()
        assert estado == "ativo"
        assert versao == 1
        if token_hash_persistido != token_hash:
            pytest.fail(
                "token_hash persistido nao corresponde ao esperado - "
                "mensagem fixa, valores nunca interpolados no traceback."
            )
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


# ============================================================
# Sucesso: reutilizacao apos 'liberado' - zera heartbeat e trio de revisao
# ============================================================

def test_criar_apos_liberado_zera_heartbeat_e_revisao(cur):
    cur.execute("SAVEPOINT sp")
    try:
        registro_coleta_id = _uuid()
        token_hash_1 = _hash_valido("primeiro")
        payload_1 = _payload_hash(registro_coleta_id=registro_coleta_id, token_hash=token_hash_1)
        resultado_1 = _chamar_fn_criar_claim(cur, registro_coleta_id, token_hash_1, "chave-a", payload_1)
        assert resultado_1["sucesso"] is True

        cur.execute(
            "SELECT nsi_operacional.fn_liberar_claim(%s, %s, %s, %s, %s)",
            (registro_coleta_id, resultado_1["claim_id"], token_hash_1, "chave-liberar",
             _payload_hash(registro_coleta_id=registro_coleta_id, claim_id=resultado_1["claim_id"], token_hash=token_hash_1)),
        )
        assert cur.fetchone()[0]["sucesso"] is True

        token_hash_2 = _hash_valido("segundo")
        payload_2 = _payload_hash(registro_coleta_id=registro_coleta_id, token_hash=token_hash_2)
        resultado_2 = _chamar_fn_criar_claim(cur, registro_coleta_id, token_hash_2, "chave-b", payload_2)
        assert resultado_2["sucesso"] is True
        assert resultado_2["claim_id"] != resultado_1["claim_id"]

        cur.execute(
            "SELECT token_hash, ultimo_heartbeat_em, revisao_atual_id, revisao_decisao, revisao_registrada_em, versao_atual "
            "FROM nsi_operacional.claims WHERE registro_coleta_id = %s",
            (registro_coleta_id,),
        )
        token_atual, heartbeat, rev_id, rev_decisao, rev_registrada, versao = cur.fetchone()
        if token_atual != token_hash_2:
            pytest.fail(
                "token_hash atual nao corresponde ao esperado apos recriacao - "
                "mensagem fixa, valores nunca interpolados no traceback."
            )
        assert heartbeat is None
        assert rev_id is None
        assert rev_decisao is None
        assert rev_registrada is None
        assert versao == 3  # 1 (criacao) + 1 (liberacao) + 1 (recriacao)

        # o token anterior nao autentica mais - heartbeat com o token antigo falha.
        cur.execute(
            "SELECT nsi_operacional.fn_registrar_heartbeat(%s, %s, %s, %s, %s)",
            (registro_coleta_id, resultado_2["claim_id"], token_hash_1, "chave-hb-token-antigo",
             _payload_hash(registro_coleta_id=registro_coleta_id, claim_id=resultado_2["claim_id"], token_hash=token_hash_1)),
        )
        assert cur.fetchone()[0]["sucesso"] is False
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


# ============================================================
# Recusa: registro ocupado
# ============================================================

@pytest.mark.parametrize("estado_ocupado", ["ativo", "expirado_pendente_revisao"])
def test_criar_recusa_quando_ocupado(cur, estado_ocupado):
    cur.execute("SAVEPOINT sp")
    try:
        registro_coleta_id = _uuid()
        token_hash_1 = _hash_valido()
        payload_1 = _payload_hash(registro_coleta_id=registro_coleta_id, token_hash=token_hash_1)
        resultado_1 = _chamar_fn_criar_claim(cur, registro_coleta_id, token_hash_1, "chave-1", payload_1)
        assert resultado_1["sucesso"] is True

        if estado_ocupado == "expirado_pendente_revisao":
            # Claim expirado (regra aprovada): criado_em e expira_em
            # atualizados juntos, ambos no passado, preservando
            # expira_em > criado_em - nunca deixar expira_em igual a
            # criado_em (violaria ck_claims_expira_apos_criado).
            cur.execute(
                "UPDATE nsi_operacional.claims "
                "SET estado = 'expirado_pendente_revisao', "
                "    criado_em = now() - interval '2 minutes', expira_em = now() - interval '1 minute' "
                "WHERE registro_coleta_id = %s",
                (registro_coleta_id,),
            )

        token_hash_2 = _hash_valido("outro")
        payload_2 = _payload_hash(registro_coleta_id=registro_coleta_id, token_hash=token_hash_2)
        resultado_2 = _chamar_fn_criar_claim(cur, registro_coleta_id, token_hash_2, "chave-2", payload_2)

        assert resultado_2["sucesso"] is False
        assert resultado_2["motivo"] == "registro_ocupado"
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


# ============================================================
# Idempotencia: replay puro e conflito (token novo -> SQLSTATE 22023)
# ============================================================

def test_criar_replay_com_mesma_chave_e_mesmo_token_nao_gera_novo_evento(cur):
    cur.execute("SAVEPOINT sp")
    try:
        registro_coleta_id = _uuid()
        token_hash = _hash_valido()
        chave = "chave-repeticao"
        payload_hash = _payload_hash(registro_coleta_id=registro_coleta_id, token_hash=token_hash)

        resultado_1 = _chamar_fn_criar_claim(cur, registro_coleta_id, token_hash, chave, payload_hash)
        resultado_2 = _chamar_fn_criar_claim(cur, registro_coleta_id, token_hash, chave, payload_hash)

        assert resultado_1 == resultado_2

        cur.execute(
            "SELECT count(*) FROM nsi_operacional.eventos_claim WHERE aggregate_id = %s AND tipo = 'claim_criado'",
            (registro_coleta_id,),
        )
        assert cur.fetchone()[0] == 1
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_criar_com_token_novo_mesma_chave_produz_conflito_22023_e_preserva_original(cur):
    registro_coleta_id = _uuid()
    token_hash_original = _hash_valido("original")
    chave = "chave-conflito"
    payload_original = _payload_hash(registro_coleta_id=registro_coleta_id, token_hash=token_hash_original)

    cur.execute("SAVEPOINT sp_fora")
    try:
        resultado_original = _chamar_fn_criar_claim(cur, registro_coleta_id, token_hash_original, chave, payload_original)
        assert resultado_original["sucesso"] is True

        token_hash_novo = _hash_valido("perdido-e-gerado-de-novo")
        payload_novo = _payload_hash(registro_coleta_id=registro_coleta_id, token_hash=token_hash_novo)

        cur.execute("SAVEPOINT sp_conflito")
        with pytest.raises(psycopg.errors.InvalidParameterValue) as exc_info:
            _chamar_fn_criar_claim(cur, registro_coleta_id, token_hash_novo, chave, payload_novo)
        assert exc_info.value.sqlstate == "22023"
        assert str(exc_info.value).strip().startswith("conflito_de_idempotencia")
        # a mensagem fixa nunca inclui chave, hash, token ou payload - checado
        # em str() e repr(), nunca so um dos dois.
        for rotulo, valor in (("chave", chave), ("token_hash_novo", token_hash_novo), ("payload_novo", payload_novo)):
            if valor in str(exc_info.value) or valor in repr(exc_info.value):
                pytest.fail(
                    f"Vazamento de segredo detectado na excecao de conflito ({rotulo}) - "
                    "mensagem fixa, o valor em si nunca e exibido aqui."
                )
        cur.execute("ROLLBACK TO SAVEPOINT sp_conflito")

        # recibo, claim e evento originais inalterados: replay com os
        # parametros ORIGINAIS ainda devolve exatamente o resultado original.
        resultado_replay = _chamar_fn_criar_claim(cur, registro_coleta_id, token_hash_original, chave, payload_original)
        assert resultado_replay == resultado_original

        cur.execute(
            "SELECT token_hash, versao_atual FROM nsi_operacional.claims WHERE registro_coleta_id = %s",
            (registro_coleta_id,),
        )
        token_persistido, versao = cur.fetchone()
        if token_persistido != token_hash_original:
            pytest.fail(
                "token_hash persistido divergiu do original apos tentativa de conflito - "
                "mensagem fixa, valores nunca interpolados no traceback."
            )
        assert versao == 1

        cur.execute(
            "SELECT count(*) FROM nsi_operacional.eventos_claim WHERE aggregate_id = %s",
            (registro_coleta_id,),
        )
        assert cur.fetchone()[0] == 1
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp_fora")


# ============================================================
# Concorrencia real: dois workers, mesmo registro_coleta_id
# ============================================================

def test_dois_workers_reais_disputando_criacao(request):
    url_aplicacao = resolver_url_banco_papel("nsi_aplicacao", "test")
    registro_coleta_id = _uuid()

    # conn_b so e aberta DENTRO do try de conn_a - se a conexao de conn_b
    # falhar (rede, limite de conexoes), conn_a ainda assim e sempre
    # revertida e fechada no finally externo, nunca deixando um lock
    # pendurado em nsi_test.
    conn_a = psycopg.connect(url_aplicacao)
    try:
        cur_a = conn_a.cursor()

        token_a = _hash_valido("worker-a")
        payload_a = _payload_hash(registro_coleta_id=registro_coleta_id, token_hash=token_a)
        cur_a.execute(
            "SELECT nsi_operacional.fn_criar_claim(%s, %s, %s, %s)",
            (registro_coleta_id, token_a, "chave-worker-a", payload_a),
        )
        resultado_a = cur_a.fetchone()[0]
        assert resultado_a["sucesso"] is True
        # transacao de A permanece ABERTA (sem commit) - segura o lock.

        conn_b = psycopg.connect(url_aplicacao)
        try:
            cur_b = conn_b.cursor()
            cur_b.execute("SET lock_timeout = '2000ms'")

            token_b = _hash_valido("worker-b")
            payload_b = _payload_hash(registro_coleta_id=registro_coleta_id, token_hash=token_b)
            with pytest.raises(psycopg.errors.LockNotAvailable):
                cur_b.execute(
                    "SELECT nsi_operacional.fn_criar_claim(%s, %s, %s, %s)",
                    (registro_coleta_id, token_b, "chave-worker-b", payload_b),
                )
        finally:
            conn_b.rollback()
            conn_b.close()
    finally:
        conn_a.rollback()
        conn_a.close()
