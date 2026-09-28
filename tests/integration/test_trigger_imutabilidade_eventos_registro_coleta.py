# -*- coding: utf-8 -*-
"""
NSI - tests/integration/test_trigger_imutabilidade_eventos_registro_coleta.py
(Sprint B, B4.2 - ADR-009)

Testes de integracao REAIS contra PostgreSQL, exclusivamente contra
nsi_test, da trigger defensiva
'eventos_registro_coleta_bloqueia_alteracao' (funcao
'fn_bloquear_alteracao_eventos_registro_coleta'): INSERT legitimo nunca
bloqueado; UPDATE/DELETE sempre bloqueados, inclusive para
nsi_eventos_owner (o proprio dono das tabelas); REVOKE ALL FROM PUBLIC
na funcao da trigger, confirmado por catalogo.

A matriz completa de "ausencia de DML direto por operacao real" para as
tres roles funcionais, nas quatro tabelas da B4.2 (incluindo esta),
esta em test_trigger_imutabilidade_eventos_lote.py - nao repetida aqui
para nao duplicar as mesmas 36 combinacoes.

Nenhuma acao deste arquivo commita dado algum. Pressupoe a migration
0004 ja aplicada em nsi_test. Nenhum teste chama pytest nem executa a
suite completa internamente.
"""
import uuid
from datetime import datetime, timedelta, timezone

import psycopg
import pytest

pytestmark = pytest.mark.pg_integration

_RECEBIDO_EM_BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)
_HORARIO_CONCEITUAL_BASE = _RECEBIDO_EM_BASE + timedelta(hours=192)


def _uuid() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def cur_owner(request):
    """Conexao do migrator com 'SET LOCAL ROLE nsi_eventos_owner' ativo.
    A transacao externa e sempre revertida no teardown."""
    url = request.getfixturevalue("url_banco_teste")
    conn = psycopg.connect(url)
    try:
        cursor = conn.cursor()
        cursor.execute("SET LOCAL ROLE nsi_eventos_owner")
        yield cursor
    finally:
        conn.rollback()
        conn.close()


_SQL_INSERT_LOTE = """
    INSERT INTO nsi_operacional.lotes
        (lote_id, recebido_em, total_recebido, total_valido, total_invalido, status,
         horario_conceitual_congelamento, versao_eventos_atual)
    VALUES (%(lote_id)s, %(recebido_em)s, 0, 0, 0, 'aguardando_d8', %(horario_conceitual)s, 1)
"""

_SQL_INSERT_REGISTRO = """
    INSERT INTO nsi_operacional.registros_coleta
        (registro_coleta_id, lote_id, nome, produto, whatsapp, valido)
    VALUES (%(registro_coleta_id)s, %(lote_id)s, 'Cliente de Teste', 'Produto de Teste',
            '5511987654321', TRUE)
"""

_SQL_INSERT_EVENTO_REGISTRO = """
    INSERT INTO nsi_operacional.eventos_registro_coleta
        (evento_id, aggregate_type, aggregate_id, aggregate_version, tipo, executado_por_login,
         resultado, numero_versao_dados)
    VALUES (%(evento_id)s, 'registro_coleta', %(aggregate_id)s, 1, 'correcao_registrada',
            'nsi_aplicacao', 'aplicada_valida', 2)
"""


def _inserir_lote_registro_e_evento(cur) -> tuple:
    lote_id = _uuid()
    registro_id = _uuid()
    evento_id = _uuid()
    cur.execute(_SQL_INSERT_LOTE, dict(
        lote_id=lote_id, recebido_em=_RECEBIDO_EM_BASE, horario_conceitual=_HORARIO_CONCEITUAL_BASE,
    ))
    cur.execute(_SQL_INSERT_REGISTRO, dict(registro_coleta_id=registro_id, lote_id=lote_id))
    cur.execute(_SQL_INSERT_EVENTO_REGISTRO, dict(evento_id=evento_id, aggregate_id=registro_id))
    return registro_id, evento_id


def test_insert_legitimo_nunca_bloqueado_pela_trigger(cur_owner):
    cur_owner.execute("SAVEPOINT sp_insert")
    try:
        _inserir_lote_registro_e_evento(cur_owner)
    except Exception as exc:
        cur_owner.execute("ROLLBACK TO SAVEPOINT sp_insert")
        pytest.fail(f"INSERT legitimo nao deveria ser bloqueado pela trigger: {exc!r}")
    else:
        cur_owner.execute("ROLLBACK TO SAVEPOINT sp_insert")


def test_update_bloqueado_mesmo_para_owner(cur_owner):
    cur_owner.execute("SAVEPOINT sp_update")
    try:
        _registro_id, evento_id = _inserir_lote_registro_e_evento(cur_owner)
        with pytest.raises(psycopg.errors.RaiseException) as exc_info:
            cur_owner.execute(
                "UPDATE nsi_operacional.eventos_registro_coleta SET resultado = 'recusada_tardia' "
                "WHERE evento_id = %(id)s",
                {"id": evento_id},
            )
        assert exc_info.value.sqlstate == "P0001"
        assert "imutavel" in str(exc_info.value)
    finally:
        cur_owner.execute("ROLLBACK TO SAVEPOINT sp_update")


def test_delete_bloqueado_mesmo_para_owner(cur_owner):
    cur_owner.execute("SAVEPOINT sp_delete")
    try:
        _registro_id, evento_id = _inserir_lote_registro_e_evento(cur_owner)
        with pytest.raises(psycopg.errors.RaiseException) as exc_info:
            cur_owner.execute(
                "DELETE FROM nsi_operacional.eventos_registro_coleta WHERE evento_id = %(id)s",
                {"id": evento_id},
            )
        assert exc_info.value.sqlstate == "P0001"
        assert "imutavel" in str(exc_info.value)
    finally:
        cur_owner.execute("ROLLBACK TO SAVEPOINT sp_delete")


def test_funcao_da_trigger_revogada_de_public(request):
    url = request.getfixturevalue("url_banco_teste")
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM information_schema.routine_privileges "
                "WHERE routine_schema = 'nsi_operacional' "
                "AND routine_name = 'fn_bloquear_alteracao_eventos_registro_coleta' "
                "AND grantee = 'PUBLIC' AND privilege_type = 'EXECUTE'"
            )
            linhas = cur.fetchall()
    assert linhas == [], "fn_bloquear_alteracao_eventos_registro_coleta ainda concede EXECUTE a PUBLIC."
