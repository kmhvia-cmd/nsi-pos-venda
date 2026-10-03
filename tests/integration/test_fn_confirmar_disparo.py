# -*- coding: utf-8 -*-
"""
NSI - tests/integration/test_fn_confirmar_disparo.py
(Sprint B, B4.3 - ADR-009, Secao 6.3)

Testes de integracao REAIS contra PostgreSQL, exclusivamente contra
nsi_test, de nsi_operacional.fn_confirmar_disparo (migration 0005) -
evento 'disparo_confirmado'.

Os lotes ja congelados sao produzidos pelas proprias funcoes da 0005
(fn_registrar_lote -> deslocamento temporal na mesma transacao ->
fn_registrar_congelamento), nunca por estado montado a mao, exceto no
teste de concorrencia, que precisa de COMMIT real.

Conexao primaria: migrator ('SET LOCAL ROLE nsi_eventos_owner'), em
transacao revertida no teardown - nenhum residuo.

Concorrencia real (duas confirmacoes do mesmo lote): duas conexoes
nsi_operador_restrito (a role com EXECUTE). Exige COMMIT real.
DIVULGACAO DE RESIDUO INTENCIONAL: o lote congelado, seu registro e o
evento 'disparo_confirmado' permanecem como residuo sintetico em
nsi_test; os DOIS recibos de 'confirmar_disparo' sao removidos
explicitamente, pelas proprias chaves.

Nenhum teste chama pytest nem executa a suite completa internamente.
"""
import threading

import psycopg
import pytest

from config import resolver_url_banco_papel
from core.payload_hash import hash_confirmar_disparo
from tests.apoio_b4_3 import (
    aguardar_bloqueio,
    criar_lote,
    posicionar_fronteira,
    registro_invalido,
    registro_valido,
    uuid_texto,
)

pytestmark = pytest.mark.pg_integration


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


def _criar_lote_congelado(cur, registros) -> str:
    lote_id = criar_lote(cur, registros)
    posicionar_fronteira(cur, lote_id, "-1 second")
    cur.execute("SELECT nsi_operacional.fn_registrar_congelamento(%s)", (lote_id,))
    assert cur.fetchone()[0]["sucesso"] is True
    return lote_id


def _confirmar(cur, lote_id, total_esperado, chave, payload_hash=None) -> dict:
    if payload_hash is None:
        payload_hash = hash_confirmar_disparo(lote_id, total_esperado)
    cur.execute(
        "SELECT nsi_operacional.fn_confirmar_disparo(%s, %s, %s, %s)",
        (lote_id, total_esperado, chave, payload_hash),
    )
    return cur.fetchone()[0]


def _contar(cur, sql, params) -> int:
    cur.execute(sql, params)
    return cur.fetchone()[0]


# ============================================================
# Sucesso
# ============================================================

def test_confirma_disparo_do_lote_congelado(cur):
    cur.execute("SAVEPOINT sp")
    try:
        lote_id = _criar_lote_congelado(cur, [registro_valido(1), registro_valido(2), registro_invalido()])
        resultado = _confirmar(cur, lote_id, 2, "chave-confirmar-001")

        assert set(resultado.keys()) == {"sucesso", "lote_id", "disparo_confirmado_em", "total_confirmado", "versao_eventos"}
        assert resultado["sucesso"] is True
        assert resultado["lote_id"] == lote_id
        assert resultado["total_confirmado"] == 2
        assert resultado["versao_eventos"] == 3

        cur.execute("""
            SELECT status, disparo_confirmado_em = now(), disparo_confirmado_por_login,
                   total_confirmado_para_disparo, versao_eventos_atual
              FROM nsi_operacional.lotes WHERE lote_id = %s
        """, (lote_id,))
        assert cur.fetchone() == ("disparo_confirmado", True, "nsi_test_migrator", 2, 3)
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_grava_evento_disparo_confirmado_exato(cur):
    cur.execute("SAVEPOINT sp")
    try:
        lote_id = _criar_lote_congelado(cur, [registro_valido(1)])
        _confirmar(cur, lote_id, 1, "chave-confirmar-evento")
        cur.execute("""
            SELECT aggregate_type, aggregate_version, occurred_at = now(), executado_por_login,
                   operador_humano_id, total_confirmado, recebido_em, total_recebido, total_valido,
                   total_invalido, horario_conceitual, horario_real_execucao, atrasado, motivo,
                   codigo_tecnico_normalizado
              FROM nsi_operacional.eventos_lote WHERE aggregate_id = %s AND tipo = 'disparo_confirmado'
        """, (lote_id,))
        eventos = cur.fetchall()
        assert len(eventos) == 1
        # operador_humano_id nulo ate a Sprint D (ADR-009, Secao 10).
        assert eventos[0][:6] == ("lote", 3, True, "nsi_test_migrator", None, 1)
        assert eventos[0][6:] == (None,) * 9
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


# ============================================================
# Recusas de negocio - todas gravam recibo
# ============================================================

def _assert_recusa_com_recibo(cur, lote_id, total_esperado, chave, motivo, eventos_disparo_esperados=0):
    recusa = _confirmar(cur, lote_id, total_esperado, chave)
    assert recusa == {"sucesso": False, "motivo": motivo}
    # A recusa nunca grava evento: a contagem e a de antes da chamada.
    assert _contar(cur, "SELECT count(*) FROM nsi_operacional.eventos_lote "
                        "WHERE aggregate_id = %s AND tipo = 'disparo_confirmado'", (lote_id,)) == eventos_disparo_esperados
    cur.execute(
        "SELECT estado_processamento, resultado FROM nsi_operacional.comandos_idempotentes "
        "WHERE comando = 'confirmar_disparo' AND aggregate_id = %s AND chave_idempotencia = %s",
        (lote_id, chave),
    )
    assert cur.fetchone() == ("concluido", recusa)
    # repetir a chave devolve a mesma recusa
    assert _confirmar(cur, lote_id, total_esperado, chave) == recusa


def test_lote_inexistente(cur):
    cur.execute("SAVEPOINT sp")
    try:
        _assert_recusa_com_recibo(cur, uuid_texto(), 1, "chave-inexistente", "lote_inexistente")
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_lote_nao_congelado(cur):
    cur.execute("SAVEPOINT sp")
    try:
        lote_id = criar_lote(cur, [registro_valido(1)])
        _assert_recusa_com_recibo(cur, lote_id, 1, "chave-nao-congelado", "lote_nao_congelado")
        cur.execute("SELECT status FROM nsi_operacional.lotes WHERE lote_id = %s", (lote_id,))
        assert cur.fetchone()[0] == "aguardando_d8"
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_sem_registros_validos(cur):
    cur.execute("SAVEPOINT sp")
    try:
        lote_id = _criar_lote_congelado(cur, [registro_invalido()])
        _assert_recusa_com_recibo(cur, lote_id, 0, "chave-sem-validos", "sem_registros_validos")
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_disparo_ja_confirmado_com_chave_nova(cur):
    cur.execute("SAVEPOINT sp")
    try:
        lote_id = _criar_lote_congelado(cur, [registro_valido(1)])
        assert _confirmar(cur, lote_id, 1, "chave-primeira")["sucesso"] is True
        _assert_recusa_com_recibo(cur, lote_id, 1, "chave-segunda", "disparo_ja_confirmado", eventos_disparo_esperados=1)
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


@pytest.mark.parametrize("total_esperado", [1, 3])
def test_total_divergente(cur, total_esperado):
    cur.execute("SAVEPOINT sp")
    try:
        lote_id = _criar_lote_congelado(cur, [registro_valido(1), registro_valido(2)])
        _assert_recusa_com_recibo(cur, lote_id, total_esperado, "chave-divergente", "total_divergente")
        cur.execute("SELECT status FROM nsi_operacional.lotes WHERE lote_id = %s", (lote_id,))
        assert cur.fetchone()[0] == "aguardando_confirmacao_disparo"
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


# ============================================================
# Idempotencia e entradas invalidas
# ============================================================

def test_replay_sem_novo_evento(cur):
    cur.execute("SAVEPOINT sp")
    try:
        lote_id = _criar_lote_congelado(cur, [registro_valido(1)])
        primeiro = _confirmar(cur, lote_id, 1, "chave-replay")
        assert _confirmar(cur, lote_id, 1, "chave-replay") == primeiro
        assert _contar(cur, "SELECT count(*) FROM nsi_operacional.eventos_lote "
                            "WHERE aggregate_id = %s AND tipo = 'disparo_confirmado'", (lote_id,)) == 1
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_conflito_de_idempotencia_22023(cur):
    cur.execute("SAVEPOINT sp")
    try:
        lote_id = _criar_lote_congelado(cur, [registro_valido(1)])
        primeiro = _confirmar(cur, lote_id, 1, "chave-conflito")
        cur.execute("SAVEPOINT antes")
        with pytest.raises(psycopg.Error) as exc_info:
            # Mesma chave, precondicao diferente: o hash canonico real diverge.
            _confirmar(cur, lote_id, 2, "chave-conflito")
        assert exc_info.value.sqlstate == "22023"
        assert exc_info.value.diag.message_primary == "conflito_de_idempotencia"
        assert exc_info.value.diag.message_detail is None
        cur.execute("ROLLBACK TO SAVEPOINT antes")
        cur.execute("SELECT resultado FROM nsi_operacional.comandos_idempotentes "
                    "WHERE comando = 'confirmar_disparo' AND aggregate_id = %s AND chave_idempotencia = 'chave-conflito'",
                    (lote_id,))
        assert cur.fetchone()[0] == primeiro
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


@pytest.mark.parametrize("indice_nulo", [0, 1, 2, 3])
def test_parametro_obrigatorio_nulo_e_violacao_estrutural(cur, indice_nulo):
    lote_id = uuid_texto()
    params = [lote_id, 1, "chave-nulo", hash_confirmar_disparo(lote_id, 1)]
    params[indice_nulo] = None
    cur.execute("SAVEPOINT sp")
    with pytest.raises(psycopg.Error) as exc_info:
        cur.execute("SELECT nsi_operacional.fn_confirmar_disparo(%s::uuid, %s::integer, %s, %s)", params)
    assert exc_info.value.sqlstate == "22000"
    assert exc_info.value.diag.message_primary == "entrada_estrutural_invalida"
    cur.execute("ROLLBACK TO SAVEPOINT sp")


# ============================================================
# Concorrencia real: duas confirmacoes do mesmo lote
# ============================================================

def test_duas_confirmacoes_concorrentes_do_mesmo_lote(request):
    url_operador = resolver_url_banco_papel("nsi_operador_restrito", "test")
    url_owner = request.getfixturevalue("url_banco_teste")
    lote_id = uuid_texto()
    chaves = ("chave-confirmacao-a", "chave-confirmacao-b")

    conn_setup = psycopg.connect(url_owner)
    with conn_setup.cursor() as c:
        c.execute("SET LOCAL ROLE nsi_eventos_owner")
        c.execute(
            "INSERT INTO nsi_operacional.lotes (lote_id, recebido_em, total_recebido, total_valido, total_invalido, "
            "total_valido_congelado, status, horario_conceitual_congelamento, horario_real_congelamento, "
            "congelamento_atrasado, versao_eventos_atual) "
            "VALUES (%s, now() - interval '193 hours', 1, 1, 0, 1, 'aguardando_confirmacao_disparo', "
            "now() - interval '1 hour', now() - interval '1 hour', false, 2)",
            (lote_id,),
        )
        c.execute(
            "INSERT INTO nsi_operacional.registros_coleta (registro_coleta_id, lote_id, nome, produto, whatsapp, valido) "
            "VALUES (%s, %s, 'Pessoa Teste', 'Produto Teste', '5511900000002', true)",
            (uuid_texto(), lote_id),
        )
    conn_setup.commit()
    conn_setup.close()

    conn_a = psycopg.connect(url_operador)
    conn_b = psycopg.connect(url_operador)
    conn_obs = psycopg.connect(url_owner)
    resultado_b = {}
    try:
        resultado_a = _confirmar(conn_a.cursor(), lote_id, 1, chaves[0])
        assert resultado_a["sucesso"] is True

        def segunda_confirmacao():
            try:
                resultado_b["valor"] = _confirmar(conn_b.cursor(), lote_id, 1, chaves[1])
                conn_b.commit()
            except Exception as exc:
                resultado_b["erro"] = exc

        t = threading.Thread(target=segunda_confirmacao)
        t.start()
        aguardar_bloqueio(conn_obs, conn_b.info.backend_pid)
        conn_a.commit()
        t.join(timeout=15)
        assert not t.is_alive()
        assert "erro" not in resultado_b, type(resultado_b.get("erro")).__name__
        assert resultado_b["valor"] == {"sucesso": False, "motivo": "disparo_ja_confirmado"}

        with conn_obs.cursor() as c:
            c.execute("SET LOCAL ROLE nsi_eventos_owner")
            c.execute("SELECT count(*) FROM nsi_operacional.eventos_lote "
                      "WHERE aggregate_id = %s AND tipo = 'disparo_confirmado'", (lote_id,))
            assert c.fetchone()[0] == 1
            c.execute("SELECT disparo_confirmado_por_login FROM nsi_operacional.lotes WHERE lote_id = %s", (lote_id,))
            assert c.fetchone()[0] == "nsi_operador_restrito"  # session_user real
        conn_obs.rollback()
    finally:
        for conn in (conn_a, conn_b):
            conn.rollback()
            conn.close()
        with conn_obs.cursor() as c:
            c.execute("SET LOCAL ROLE nsi_eventos_owner")
            c.execute(
                "DELETE FROM nsi_operacional.comandos_idempotentes "
                "WHERE comando = 'confirmar_disparo' AND aggregate_id = %s AND chave_idempotencia = ANY(%s)",
                (lote_id, list(chaves)),
            )
        conn_obs.commit()
        conn_obs.close()
