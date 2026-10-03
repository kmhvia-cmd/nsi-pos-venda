# -*- coding: utf-8 -*-
"""
NSI - tests/integration/test_fn_registrar_congelamento.py
(Sprint B, B4.3 - ADR-009, Secoes 6.2 e 12)

Testes de integracao REAIS contra PostgreSQL, exclusivamente contra
nsi_test, de nsi_operacional.fn_registrar_congelamento (migration 0005) -
evento 'lote_congelado_d8'.

Fronteira temporal SEM ESPERA REAL (Especificacao Tecnica, Secao 18):
o lote e criado pela propria fn_registrar_lote e, na MESMA transacao,
deslocado no tempo (recebido_em e horario_conceitual_congelamento movidos
juntos, preservando as 192h exatas) - now() e o instante de inicio da
transacao, identico para o deslocamento e para a funcao; 'um microssegundo
antes / exatamente em / um microssegundo depois' e, portanto, exato.

Conexao primaria: migrator ('SET LOCAL ROLE nsi_eventos_owner'), em
transacao revertida no teardown - nenhum residuo.

Concorrencia real (dois workers congelando o mesmo lote): duas conexoes
nsi_aplicacao com 'SET LOCAL ROLE nsi_congelamento' - o caminho real de
autorizacao (ADR-009, Secao 11). Exige COMMIT real. DIVULGACAO DE RESIDUO
INTENCIONAL: o lote, seu registro e o evento 'lote_congelado_d8'
permanecem como residuo sintetico em nsi_test (eventos imutaveis); o
recibo de 'registrar_congelamento' criado pelo teste e removido
explicitamente pela propria chave, para nao bloquear o preflight do
downgrade da 0004. O lote e criado diretamente pelo owner (sem recibo de
registrar_lote).

Nenhum teste chama pytest nem executa a suite completa internamente.
"""
import threading

import psycopg
import pytest

from config import resolver_url_banco_papel
from core.payload_hash import hash_registrar_congelamento, hash_registrar_correcao
from tests.apoio_b4_3 import (
    aguardar_bloqueio,
    criar_lote,
    posicionar_fronteira,
    registro_invalido,
    registro_valido,
    uuid_texto,
)

pytestmark = pytest.mark.pg_integration

CHAVES_RETORNO_SUCESSO = {
    "sucesso", "status", "total_valido_congelado", "horario_conceitual",
    "horario_real_execucao", "atrasado", "versao_eventos",
}


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


def _congelar(cur, lote_id) -> dict:
    cur.execute("SELECT nsi_operacional.fn_registrar_congelamento(%s)", (lote_id,))
    return cur.fetchone()[0]


def _contar(cur, sql, params) -> int:
    cur.execute(sql, params)
    return cur.fetchone()[0]


def _recibos_congelamento(cur, lote_id) -> int:
    return _contar(cur, "SELECT count(*) FROM nsi_operacional.comandos_idempotentes "
                        "WHERE comando = 'registrar_congelamento' AND aggregate_id = %s", (lote_id,))


def _eventos(cur, lote_id, tipo) -> int:
    return _contar(cur, "SELECT count(*) FROM nsi_operacional.eventos_lote WHERE aggregate_id = %s AND tipo = %s",
                   (lote_id, tipo))


# ============================================================
# Sucesso e fronteira temporal
# ============================================================

def test_congela_exatamente_na_fronteira_sem_atraso(cur):
    cur.execute("SAVEPOINT sp")
    try:
        lote_id = criar_lote(cur, [registro_valido(1), registro_valido(2), registro_invalido()])
        posicionar_fronteira(cur, lote_id, "0 seconds")
        resultado = _congelar(cur, lote_id)

        assert set(resultado.keys()) == CHAVES_RETORNO_SUCESSO
        assert resultado["sucesso"] is True
        assert resultado["status"] == "aguardando_confirmacao_disparo"
        assert resultado["total_valido_congelado"] == 2
        assert resultado["atrasado"] is False
        assert resultado["versao_eventos"] == 2

        cur.execute("""
            SELECT status, total_valido_congelado, horario_real_congelamento = now(),
                   horario_real_congelamento = horario_conceitual_congelamento,
                   congelamento_atrasado, versao_eventos_atual, total_valido, total_invalido
              FROM nsi_operacional.lotes WHERE lote_id = %s
        """, (lote_id,))
        assert cur.fetchone() == ("aguardando_confirmacao_disparo", 2, True, True, False, 2, 2, 1)
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_um_microssegundo_depois_congela_com_atraso(cur):
    cur.execute("SAVEPOINT sp")
    try:
        lote_id = criar_lote(cur, [registro_valido(1)])
        posicionar_fronteira(cur, lote_id, "-1 microsecond")
        resultado = _congelar(cur, lote_id)
        assert resultado["sucesso"] is True
        assert resultado["atrasado"] is True
        cur.execute("SELECT congelamento_atrasado FROM nsi_operacional.lotes WHERE lote_id = %s", (lote_id,))
        assert cur.fetchone()[0] is True
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_um_microssegundo_antes_e_recusa_sem_evento_e_sem_recibo(cur):
    cur.execute("SAVEPOINT sp")
    try:
        lote_id = criar_lote(cur, [registro_valido(1)])
        posicionar_fronteira(cur, lote_id, "1 microsecond")
        assert _congelar(cur, lote_id) == {"sucesso": False, "motivo": "instante_nao_atingido"}
        assert _eventos(cur, lote_id, "lote_congelado_d8") == 0
        assert _recibos_congelamento(cur, lote_id) == 0
        cur.execute("SELECT status, versao_eventos_atual FROM nsi_operacional.lotes WHERE lote_id = %s", (lote_id,))
        assert cur.fetchone() == ("aguardando_d8", 1)
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_chamada_prematura_seguida_de_chamada_legitima(cur):
    """A recusa prematura nao deixa recibo - por isso nao se torna
    permanente e nao impede o congelamento legitimo posterior."""
    cur.execute("SAVEPOINT sp")
    try:
        lote_id = criar_lote(cur, [registro_valido(1)])
        assert _congelar(cur, lote_id)["motivo"] == "instante_nao_atingido"
        posicionar_fronteira(cur, lote_id, "-1 second")
        resultado = _congelar(cur, lote_id)
        assert resultado["sucesso"] is True
        assert _recibos_congelamento(cur, lote_id) == 1
        assert _eventos(cur, lote_id, "lote_congelado_d8") == 1
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_lote_sem_registros_validos_vai_para_sem_registros_validos(cur):
    cur.execute("SAVEPOINT sp")
    try:
        lote_id = criar_lote(cur, [registro_invalido(), registro_invalido()])
        posicionar_fronteira(cur, lote_id, "-1 second")
        resultado = _congelar(cur, lote_id)
        assert resultado["status"] == "sem_registros_validos"
        assert resultado["total_valido_congelado"] == 0
        cur.execute("SELECT status, total_valido_congelado FROM nsi_operacional.lotes WHERE lote_id = %s", (lote_id,))
        assert cur.fetchone() == ("sem_registros_validos", 0)
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_contagem_real_do_instante_diverge_da_contagem_do_upload(cur):
    """Correcao aplicada antes da fronteira muda a contagem: o congelamento
    usa a contagem real do instante, nunca a do upload."""
    cur.execute("SAVEPOINT sp")
    try:
        invalido = registro_invalido()
        lote_id = criar_lote(cur, [registro_valido(1), invalido])
        cur.execute(
            "SELECT nsi_operacional.fn_registrar_correcao(%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (lote_id, invalido["registro_coleta_id"], "Pessoa Corrigida", "5511977776666", "Produto Teste",
             True, None, "chave-correcao-contagem",
             hash_registrar_correcao(lote_id, invalido["registro_coleta_id"], "Pessoa Corrigida", "5511977776666",
                                     "Produto Teste", True, None)),
        )
        assert cur.fetchone()[0]["resultado"] == "aplicada_valida"

        posicionar_fronteira(cur, lote_id, "-1 second")
        resultado = _congelar(cur, lote_id)
        assert resultado["total_valido_congelado"] == 2  # o upload trazia 1 valido
        cur.execute("SELECT total_valido FROM nsi_operacional.eventos_lote WHERE aggregate_id = %s AND tipo = 'lote_criado'",
                    (lote_id,))
        assert cur.fetchone()[0] == 1
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_grava_evento_lote_congelado_d8_exato(cur):
    cur.execute("SAVEPOINT sp")
    try:
        lote_id = criar_lote(cur, [registro_valido(1)])
        posicionar_fronteira(cur, lote_id, "-5 seconds")
        _congelar(cur, lote_id)
        cur.execute("""
            SELECT aggregate_type, aggregate_version, occurred_at = now(), executado_por_login,
                   horario_conceitual = now() - interval '5 seconds', horario_real_execucao = now(), atrasado,
                   recebido_em, total_recebido, total_valido, total_invalido, operador_humano_id,
                   total_confirmado, motivo, codigo_tecnico_normalizado
              FROM nsi_operacional.eventos_lote WHERE aggregate_id = %s AND tipo = 'lote_congelado_d8'
        """, (lote_id,))
        eventos = cur.fetchall()
        assert len(eventos) == 1
        assert eventos[0][:7] == ("lote", 2, True, "nsi_test_migrator", True, True, True)
        assert eventos[0][7:] == (None,) * 8
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


# ============================================================
# Idempotencia deterministica (ADR-009, Secao 12)
# ============================================================

def test_recibo_usa_chave_deterministica_e_hash_canonico(cur):
    cur.execute("SAVEPOINT sp")
    try:
        lote_id = criar_lote(cur, [registro_valido(1)])
        posicionar_fronteira(cur, lote_id, "-1 second")
        resultado = _congelar(cur, lote_id)
        cur.execute(
            "SELECT chave_idempotencia, payload_hash, estado_processamento, resultado "
            "FROM nsi_operacional.comandos_idempotentes "
            "WHERE comando = 'registrar_congelamento' AND aggregate_id = %s",
            (lote_id,),
        )
        chave, payload_hash, estado, resultado_persistido = cur.fetchone()
        assert chave == lote_id
        # O hash calculado DENTRO da funcao e identico ao do modulo de
        # producao (core/payload_hash.py) para o mesmo lote_id.
        assert payload_hash == hash_registrar_congelamento(lote_id)
        assert estado == "concluido"
        assert resultado_persistido == resultado
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_lote_ja_congelado_devolve_replay_sem_novo_evento(cur):
    cur.execute("SAVEPOINT sp")
    try:
        lote_id = criar_lote(cur, [registro_valido(1)])
        posicionar_fronteira(cur, lote_id, "-1 second")
        primeiro = _congelar(cur, lote_id)
        segundo = _congelar(cur, lote_id)
        assert segundo == primeiro
        assert _eventos(cur, lote_id, "lote_congelado_d8") == 1
        cur.execute("SELECT versao_eventos_atual FROM nsi_operacional.lotes WHERE lote_id = %s", (lote_id,))
        assert cur.fetchone()[0] == 2
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


# ============================================================
# Recusas e entradas invalidas
# ============================================================

def test_lote_inexistente_e_recusa_sem_recibo(cur):
    lote_id = uuid_texto()
    assert _congelar(cur, lote_id) == {"sucesso": False, "motivo": "lote_inexistente"}
    assert _recibos_congelamento(cur, lote_id) == 0


def test_lote_id_nulo_e_violacao_estrutural(cur):
    cur.execute("SAVEPOINT sp")
    with pytest.raises(psycopg.Error) as exc_info:
        cur.execute("SELECT nsi_operacional.fn_registrar_congelamento(NULL)")
    assert exc_info.value.sqlstate == "22000"
    assert exc_info.value.diag.message_primary == "entrada_estrutural_invalida"
    cur.execute("ROLLBACK TO SAVEPOINT sp")


# ============================================================
# Estado impossivel da arquitetura - NS001, nada persistido
# ============================================================

def _provocar_divergencia(cur, lote_id) -> None:
    """Altera lotes.total_valido fora das funcoes (o owner pode), mantendo
    ck_lotes_totais - a contagem real deixa de bater com o total."""
    cur.execute(
        "UPDATE nsi_operacional.lotes SET total_valido = total_valido + 1, total_invalido = total_invalido - 1 "
        "WHERE lote_id = %s",
        (lote_id,),
    )


def test_divergencia_entre_contagem_real_e_total_aborta_com_invariante(cur):
    cur.execute("SAVEPOINT sp")
    try:
        lote_id = criar_lote(cur, [registro_valido(1), registro_invalido()])
        posicionar_fronteira(cur, lote_id, "-1 second")
        _provocar_divergencia(cur, lote_id)
        cur.execute("SELECT status, versao_eventos_atual, total_valido FROM nsi_operacional.lotes WHERE lote_id = %s",
                    (lote_id,))
        antes = cur.fetchone()

        for _tentativa in range(2):  # nova tentativa aborta da mesma forma
            cur.execute("SAVEPOINT tentativa")
            with pytest.raises(psycopg.Error) as exc_info:
                _congelar(cur, lote_id)
            assert exc_info.value.sqlstate == "NS001"
            assert exc_info.value.diag.message_primary == "invariante_violada"
            assert exc_info.value.diag.message_detail is None
            cur.execute("ROLLBACK TO SAVEPOINT tentativa")

            assert _eventos(cur, lote_id, "lote_congelado_d8") == 0
            assert _recibos_congelamento(cur, lote_id) == 0
            cur.execute("SELECT status, versao_eventos_atual, total_valido FROM nsi_operacional.lotes WHERE lote_id = %s",
                        (lote_id,))
            assert cur.fetchone() == antes
        assert antes[0] == "aguardando_d8"
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_lote_congelado_sem_recibo_e_estado_impossivel(cur):
    cur.execute("SAVEPOINT sp")
    try:
        lote_id = criar_lote(cur, [registro_valido(1)])
        posicionar_fronteira(cur, lote_id, "-1 second")
        _congelar(cur, lote_id)
        cur.execute("DELETE FROM nsi_operacional.comandos_idempotentes "
                    "WHERE comando = 'registrar_congelamento' AND aggregate_id = %s", (lote_id,))
        cur.execute("SAVEPOINT tentativa")
        with pytest.raises(psycopg.Error) as exc_info:
            _congelar(cur, lote_id)
        assert exc_info.value.sqlstate == "NS001"
        assert exc_info.value.diag.message_primary == "invariante_violada"
        cur.execute("ROLLBACK TO SAVEPOINT tentativa")
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_recibo_existente_com_lote_ainda_aguardando_e_estado_impossivel(cur):
    cur.execute("SAVEPOINT sp")
    try:
        lote_id = criar_lote(cur, [registro_valido(1)])
        posicionar_fronteira(cur, lote_id, "-1 second")
        cur.execute(
            "INSERT INTO nsi_operacional.comandos_idempotentes "
            "(comando, aggregate_id, chave_idempotencia, payload_hash, estado_processamento) "
            "VALUES ('registrar_congelamento', %s, %s, %s, 'processando')",
            (lote_id, lote_id, hash_registrar_congelamento(lote_id)),
        )
        cur.execute("SAVEPOINT tentativa")
        with pytest.raises(psycopg.Error) as exc_info:
            _congelar(cur, lote_id)
        assert exc_info.value.sqlstate == "NS001"
        cur.execute("ROLLBACK TO SAVEPOINT tentativa")
        cur.execute("SELECT status FROM nsi_operacional.lotes WHERE lote_id = %s", (lote_id,))
        assert cur.fetchone()[0] == "aguardando_d8"
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


# ============================================================
# Concorrencia real: dois workers congelando o mesmo lote
# ============================================================

def test_dois_workers_concorrentes_um_evento_e_um_replay(request):
    url_aplicacao = resolver_url_banco_papel("nsi_aplicacao", "test")
    url_owner = request.getfixturevalue("url_banco_teste")
    lote_id, registro_id = uuid_texto(), uuid_texto()

    conn_setup = psycopg.connect(url_owner)
    with conn_setup.cursor() as c:
        c.execute("SET LOCAL ROLE nsi_eventos_owner")
        c.execute(
            "INSERT INTO nsi_operacional.lotes (lote_id, recebido_em, total_recebido, total_valido, total_invalido, "
            "status, horario_conceitual_congelamento, versao_eventos_atual) "
            "VALUES (%s, now() - interval '193 hours', 1, 1, 0, 'aguardando_d8', now() - interval '1 hour', 1)",
            (lote_id,),
        )
        c.execute(
            "INSERT INTO nsi_operacional.registros_coleta (registro_coleta_id, lote_id, nome, produto, whatsapp, valido) "
            "VALUES (%s, %s, 'Pessoa Teste', 'Produto Teste', '5511900000001', true)",
            (registro_id, lote_id),
        )
    conn_setup.commit()
    conn_setup.close()

    conn_a = psycopg.connect(url_aplicacao)
    conn_b = psycopg.connect(url_aplicacao)
    conn_obs = psycopg.connect(url_owner)
    resultado_b = {}
    try:
        cur_a = conn_a.cursor()
        cur_a.execute("SET LOCAL ROLE nsi_congelamento")
        resultado_a = _congelar(cur_a, lote_id)
        assert resultado_a["sucesso"] is True

        def segundo_worker():
            try:
                cur_b = conn_b.cursor()
                cur_b.execute("SET LOCAL ROLE nsi_congelamento")
                resultado_b["valor"] = _congelar(cur_b, lote_id)
                conn_b.commit()
            except Exception as exc:
                resultado_b["erro"] = exc

        t = threading.Thread(target=segundo_worker)
        t.start()
        aguardar_bloqueio(conn_obs, conn_b.info.backend_pid)
        conn_a.commit()
        t.join(timeout=15)
        assert not t.is_alive()
        assert "erro" not in resultado_b, type(resultado_b.get("erro")).__name__
        assert resultado_b["valor"] == resultado_a  # replay, nunca conflito

        with conn_obs.cursor() as c:
            c.execute("SET LOCAL ROLE nsi_eventos_owner")
            assert _eventos(c, lote_id, "lote_congelado_d8") == 1
            assert _recibos_congelamento(c, lote_id) == 1
            c.execute("SELECT executado_por_login FROM nsi_operacional.eventos_lote "
                      "WHERE aggregate_id = %s AND tipo = 'lote_congelado_d8'", (lote_id,))
            # session_user da conexao real - SET ROLE nao altera session_user.
            assert c.fetchone()[0] == "nsi_aplicacao"
        conn_obs.rollback()
    finally:
        for conn in (conn_a, conn_b):
            conn.rollback()
            conn.close()
        with conn_obs.cursor() as c:
            c.execute("SET LOCAL ROLE nsi_eventos_owner")
            c.execute(
                "DELETE FROM nsi_operacional.comandos_idempotentes "
                "WHERE comando = 'registrar_congelamento' AND aggregate_id = %s AND chave_idempotencia = %s",
                (lote_id, lote_id),
            )
        conn_obs.commit()
        conn_obs.close()
