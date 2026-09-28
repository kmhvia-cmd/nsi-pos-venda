# -*- coding: utf-8 -*-
"""
NSI - tests/integration/test_trigger_imutabilidade_eventos_lote.py
(Sprint B, B4.2 - ADR-009)

Testes de integracao REAIS contra PostgreSQL, exclusivamente contra
nsi_test, em duas frentes, mesmo padrao de
test_trigger_imutabilidade_eventos_claim.py:

1. A trigger defensiva 'eventos_lote_bloqueia_alteracao' (funcao
   'fn_bloquear_alteracao_eventos_lote'): INSERT legitimo nunca
   bloqueado; UPDATE/DELETE sempre bloqueados, inclusive para
   nsi_eventos_owner; REVOKE ALL FROM PUBLIC na funcao da trigger,
   confirmado por catalogo.

2. Ausencia de DML direto - por OPERACAO REAL, nunca so inspecao de ACL
   - para as tres roles funcionais (nsi_aplicacao, nsi_expiracao,
   nsi_operador_restrito) nas quatro tabelas da B4.2 (lotes,
   registros_coleta, eventos_lote, eventos_registro_coleta), nas tres
   operacoes (INSERT, UPDATE, DELETE): 36 combinacoes, cada uma
   conectando de fato como a role (via config.resolver_url_banco_papel),
   confirmando especificamente SQLSTATE 42501 (insufficient_privilege).
   PUBLIC e verificado exclusivamente por inspecao de ACL - nunca por
   conexao real.

nsi_congelamento nao existe ainda neste ponto (provisionamento
administrativo, posterior a esta migration - B4.3) - este arquivo nunca
a referencia.

Nenhuma acao deste arquivo commita dado algum. Pressupoe a migration
0004 ja aplicada em nsi_test. Nenhum teste chama pytest nem executa a
suite completa internamente.
"""
import uuid
from datetime import datetime, timedelta, timezone

import psycopg
import pytest

from config import mascarar_dsn, resolver_url_banco_papel

pytestmark = pytest.mark.pg_integration

PAPEIS_FUNCIONAIS = ["nsi_aplicacao", "nsi_expiracao", "nsi_operador_restrito"]
TABELAS_DE_NEGOCIO_B4 = ["lotes", "registros_coleta", "eventos_lote", "eventos_registro_coleta"]
OPERACOES_DML = ["INSERT", "UPDATE", "DELETE"]

_RECEBIDO_EM_BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)
_HORARIO_CONCEITUAL_BASE = _RECEBIDO_EM_BASE + timedelta(hours=192)


def _uuid() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def cur_owner(request):
    """Conexao do migrator com 'SET LOCAL ROLE nsi_eventos_owner' ativo -
    usada exclusivamente para os testes da trigger em si. A transacao
    externa e sempre revertida no teardown."""
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

_SQL_INSERT_EVENTO_LOTE = """
    INSERT INTO nsi_operacional.eventos_lote
        (evento_id, aggregate_type, aggregate_id, aggregate_version, tipo, executado_por_login,
         recebido_em, total_recebido, total_valido, total_invalido)
    VALUES (%(evento_id)s, 'lote', %(aggregate_id)s, 1, 'lote_criado', 'nsi_aplicacao',
            %(recebido_em)s, 0, 0, 0)
"""


def _inserir_lote_e_evento(cur) -> tuple:
    lote_id = _uuid()
    evento_id = _uuid()
    cur.execute(_SQL_INSERT_LOTE, dict(
        lote_id=lote_id, recebido_em=_RECEBIDO_EM_BASE, horario_conceitual=_HORARIO_CONCEITUAL_BASE,
    ))
    cur.execute(_SQL_INSERT_EVENTO_LOTE, dict(
        evento_id=evento_id, aggregate_id=lote_id, recebido_em=_RECEBIDO_EM_BASE,
    ))
    return lote_id, evento_id


# ============================================================
# 1. Trigger 'eventos_lote_bloqueia_alteracao'
# ============================================================

def test_insert_legitimo_nunca_bloqueado_pela_trigger(cur_owner):
    cur_owner.execute("SAVEPOINT sp_insert")
    try:
        _inserir_lote_e_evento(cur_owner)
    except Exception as exc:
        cur_owner.execute("ROLLBACK TO SAVEPOINT sp_insert")
        pytest.fail(f"INSERT legitimo nao deveria ser bloqueado pela trigger: {exc!r}")
    else:
        cur_owner.execute("ROLLBACK TO SAVEPOINT sp_insert")


def test_update_bloqueado_mesmo_para_owner(cur_owner):
    cur_owner.execute("SAVEPOINT sp_update")
    try:
        _lote_id, evento_id = _inserir_lote_e_evento(cur_owner)
        with pytest.raises(psycopg.errors.RaiseException) as exc_info:
            cur_owner.execute(
                "UPDATE nsi_operacional.eventos_lote SET executado_por_login = 'outro' WHERE evento_id = %(id)s",
                {"id": evento_id},
            )
        assert exc_info.value.sqlstate == "P0001"
        assert "imutavel" in str(exc_info.value)
    finally:
        cur_owner.execute("ROLLBACK TO SAVEPOINT sp_update")


def test_delete_bloqueado_mesmo_para_owner(cur_owner):
    cur_owner.execute("SAVEPOINT sp_delete")
    try:
        _lote_id, evento_id = _inserir_lote_e_evento(cur_owner)
        with pytest.raises(psycopg.errors.RaiseException) as exc_info:
            cur_owner.execute(
                "DELETE FROM nsi_operacional.eventos_lote WHERE evento_id = %(id)s",
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
                "AND routine_name = 'fn_bloquear_alteracao_eventos_lote' "
                "AND grantee = 'PUBLIC' AND privilege_type = 'EXECUTE'"
            )
            linhas = cur.fetchall()
    assert linhas == [], "fn_bloquear_alteracao_eventos_lote ainda concede EXECUTE a PUBLIC."


# ============================================================
# 2. PUBLIC sem DML direto - exclusivamente por ACL, nunca conexao real
# ============================================================

def test_public_sem_dml_direto_nas_quatro_tabelas_via_acl(request):
    url = request.getfixturevalue("url_banco_teste")
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT table_name, privilege_type FROM information_schema.table_privileges "
                "WHERE table_schema = 'nsi_operacional' AND table_name = ANY(%s) "
                "AND grantee = 'PUBLIC' AND privilege_type IN ('INSERT', 'UPDATE', 'DELETE', 'SELECT')",
                (TABELAS_DE_NEGOCIO_B4,),
            )
            linhas = cur.fetchall()
    assert linhas == [], f"PUBLIC tem privilegio(s) inesperado(s) nas tabelas da B4.2: {linhas}"


# ============================================================
# 3. As tres roles funcionais - permission denied REAL, 36 combinacoes
# ============================================================

def _construir_operacao(tabela: str, operacao: str):
    """Monta uma instrucao sintatica e estruturalmente valida para a
    tabela/operacao pedida - a checagem de privilegio do PostgreSQL
    ocorre antes de qualquer avaliacao de FK/linha, entao a tentativa
    falha por permissao mesmo contra dados inexistentes."""
    if tabela == "lotes":
        if operacao == "INSERT":
            return (
                "INSERT INTO nsi_operacional.lotes "
                "(lote_id, recebido_em, total_recebido, total_valido, total_invalido, status, "
                "horario_conceitual_congelamento, versao_eventos_atual) "
                "VALUES (%(id)s, now(), 0, 0, 0, 'aguardando_d8', now() + interval '192 hours', 1)",
                {"id": _uuid()},
            )
        if operacao == "UPDATE":
            return (
                "UPDATE nsi_operacional.lotes SET status = 'aguardando_d8' WHERE lote_id = %(id)s",
                {"id": _uuid()},
            )
        return ("DELETE FROM nsi_operacional.lotes WHERE lote_id = %(id)s", {"id": _uuid()})

    if tabela == "registros_coleta":
        if operacao == "INSERT":
            return (
                "INSERT INTO nsi_operacional.registros_coleta "
                "(registro_coleta_id, lote_id, nome, produto, whatsapp, valido) "
                "VALUES (%(id)s, %(lote_id)s, 'Nome', 'Produto', '5511987654321', TRUE)",
                {"id": _uuid(), "lote_id": _uuid()},
            )
        if operacao == "UPDATE":
            return (
                "UPDATE nsi_operacional.registros_coleta SET nome = 'Outro' WHERE registro_coleta_id = %(id)s",
                {"id": _uuid()},
            )
        return (
            "DELETE FROM nsi_operacional.registros_coleta WHERE registro_coleta_id = %(id)s",
            {"id": _uuid()},
        )

    if tabela == "eventos_lote":
        if operacao == "INSERT":
            return (
                "INSERT INTO nsi_operacional.eventos_lote "
                "(evento_id, aggregate_type, aggregate_id, aggregate_version, tipo, executado_por_login, "
                "recebido_em, total_recebido, total_valido, total_invalido) "
                "VALUES (%(evento_id)s, 'lote', %(aggregate_id)s, 1, 'lote_criado', 'nsi_aplicacao', "
                "now(), 0, 0, 0)",
                {"evento_id": _uuid(), "aggregate_id": _uuid()},
            )
        if operacao == "UPDATE":
            return (
                "UPDATE nsi_operacional.eventos_lote SET executado_por_login = 'outro' WHERE evento_id = %(id)s",
                {"id": _uuid()},
            )
        return ("DELETE FROM nsi_operacional.eventos_lote WHERE evento_id = %(id)s", {"id": _uuid()})

    # eventos_registro_coleta
    if operacao == "INSERT":
        return (
            "INSERT INTO nsi_operacional.eventos_registro_coleta "
            "(evento_id, aggregate_type, aggregate_id, aggregate_version, tipo, executado_por_login, resultado) "
            "VALUES (%(evento_id)s, 'registro_coleta', %(aggregate_id)s, 1, 'correcao_registrada', "
            "'nsi_aplicacao', 'recusada_tardia')",
            {"evento_id": _uuid(), "aggregate_id": _uuid()},
        )
    if operacao == "UPDATE":
        return (
            "UPDATE nsi_operacional.eventos_registro_coleta SET resultado = 'recusada_tardia' "
            "WHERE evento_id = %(id)s",
            {"id": _uuid()},
        )
    return (
        "DELETE FROM nsi_operacional.eventos_registro_coleta WHERE evento_id = %(id)s",
        {"id": _uuid()},
    )


@pytest.mark.parametrize("operacao", OPERACOES_DML)
@pytest.mark.parametrize("tabela", TABELAS_DE_NEGOCIO_B4)
@pytest.mark.parametrize("papel", PAPEIS_FUNCIONAIS)
def test_role_funcional_recebe_permission_denied_real(papel, tabela, operacao):
    """As 36 combinacoes (3 roles x 4 tabelas x 3 operacoes) desta
    subetapa - operacao real, nunca so inspecao de ACL."""
    url = resolver_url_banco_papel(papel, "test")
    sql, params = _construir_operacao(tabela, operacao)

    conn = psycopg.connect(url)
    try:
        cursor = conn.cursor()
        with pytest.raises(psycopg.errors.InsufficientPrivilege) as exc_info:
            cursor.execute(sql, params)
        assert exc_info.value.sqlstate == "42501", (
            f"Esperado SQLSTATE 42501 (insufficient_privilege) para {papel}/{tabela}/{operacao}, "
            f"obtido {exc_info.value.sqlstate!r}"
        )
        texto_excecao = str(exc_info.value)
        if "://" in texto_excecao or "@" in texto_excecao:
            pytest.fail(
                f"Padrao de DSN encontrado na mensagem de erro para {papel}/{tabela}/{operacao} - "
                "mensagem fixa: o texto da excecao nao e exibido aqui."
            )
    finally:
        conn.rollback()
        conn.close()


def test_dsn_mascarada_nunca_contem_usuario_ou_senha(request):
    url = request.getfixturevalue("url_banco_teste")
    representacao_segura = mascarar_dsn(url)
    assert "@" not in representacao_segura
    assert "://" not in representacao_segura
