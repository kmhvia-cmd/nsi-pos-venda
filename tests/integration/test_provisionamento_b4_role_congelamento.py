# -*- coding: utf-8 -*-
"""
NSI - tests/integration/test_provisionamento_b4_role_congelamento.py
(Sprint B, B4.3 - ADR-009, Secoes 11 e 21)

Testes de integracao REAIS contra PostgreSQL, mas EXCLUSIVAMENTE DE
LEITURA - nenhum destes testes executa CREATE, ALTER, GRANT, REVOKE ou
DROP, e nenhum deles chama provisionar_b4_role_congelamento.sql ou
desprovisionar_b4_role_congelamento.sql. O provisionamento e sempre um
PROCEDIMENTO MANUAL, autorizado separadamente; os cenarios destrutivos dos
scripts sao exclusivamente estaticos
(tests/unit/test_scripts_b4_role_congelamento.py) ou manuais.

Comprova o estado final provisionado da role nsi_congelamento, ja com a
migration 0005 aplicada: atributos, ausencia de membership inesperada,
a membership formalizada de nsi_aplicacao (INHERIT FALSE, SET TRUE,
ADMIN FALSE), USAGE no schema e EXECUTE somente na funcao de
congelamento.

Conexao usada: EXCLUSIVAMENTE a fixture 'url_banco_teste' (migrator de
nsi_test). Ler pg_roles/pg_auth_members/pg_database/pg_shdepend nao exige
autenticar COMO a role verificada.

ESCOPO (mesmo de test_provisionamento_b3_roles.py): pg_roles,
pg_auth_members, pg_database e pg_shdepend sao catalogos COMPARTILHADOS do
cluster - os testes de atributos, membership, CONNECT e dependencias cobrem
o cluster inteiro (nsi_dev E nsi_test), mesmo conectando apenas a
nsi_test. Ja USAGE no schema e privilegios em tabelas e funcoes sao
especificos de CADA banco - cobrem apenas nsi_test (unico banco ao qual a
infraestrutura de teste automatizada esta autorizada a conectar). Em
nsi_dev, esses aspectos sao comprovados pela Fase 3 do proprio script de
provisionamento. A ausencia de senha (pg_authid, leitura exclusiva de
superusuario) tambem e comprovada pela Fase 3 do script, nunca aqui.
"""
import psycopg
import pytest

from config import mascarar_dsn

pytestmark = pytest.mark.pg_integration


@pytest.fixture
def cur(request):
    url = request.getfixturevalue("url_banco_teste")
    conn = psycopg.connect(url)
    try:
        conn.read_only = True
        yield conn.cursor()
    finally:
        conn.rollback()
        conn.close()


def test_role_existe_com_atributos_de_seguranca_corretos(cur):
    cur.execute(
        "SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls, rolinherit "
        "FROM pg_catalog.pg_roles WHERE rolname = 'nsi_congelamento'"
    )
    atributos = cur.fetchone()
    assert atributos is not None, (
        "Role nsi_congelamento nao existe neste cluster - execute o provisionamento administrativo "
        "(procedimento manual) antes desta suite."
    )
    assert atributos == (False, False, False, False, False, False, True), (
        f"Atributos de nsi_congelamento divergentes do aprovado: {atributos}"
    )


def test_role_nao_pertence_a_nenhuma_outra_role(cur):
    cur.execute(
        "SELECT g.rolname FROM pg_catalog.pg_auth_members m "
        "JOIN pg_catalog.pg_roles r ON r.oid = m.member JOIN pg_catalog.pg_roles g ON g.oid = m.roleid "
        "WHERE r.rolname = 'nsi_congelamento'"
    )
    assert cur.fetchall() == []


def test_unico_membro_e_nsi_aplicacao_com_as_opcoes_formalizadas(cur):
    """Lista COMPLETA de membros (sem agrupar): exatamente uma linha."""
    cur.execute(
        "SELECT r.rolname, m.inherit_option, m.set_option, m.admin_option FROM pg_catalog.pg_auth_members m "
        "JOIN pg_catalog.pg_roles r ON r.oid = m.member JOIN pg_catalog.pg_roles g ON g.oid = m.roleid "
        "WHERE g.rolname = 'nsi_congelamento'"
    )
    assert cur.fetchall() == [("nsi_aplicacao", False, True, False)]


def test_nsi_aplicacao_tem_exatamente_a_membership_formalizada(cur):
    """ADR-009, Secao 21: a excecao e unica e fechada - nsi_aplicacao nao
    pertence a nenhuma outra role."""
    cur.execute(
        "SELECT g.rolname, m.inherit_option, m.set_option, m.admin_option FROM pg_catalog.pg_auth_members m "
        "JOIN pg_catalog.pg_roles r ON r.oid = m.member JOIN pg_catalog.pg_roles g ON g.oid = m.roleid "
        "WHERE r.rolname = 'nsi_aplicacao'"
    )
    assert cur.fetchall() == [("nsi_congelamento", False, True, False)]


@pytest.mark.parametrize("banco", ["nsi_dev", "nsi_test"])
def test_role_sem_connect_proprio(cur, banco):
    cur.execute(
        "SELECT count(*) FROM pg_catalog.pg_database d CROSS JOIN LATERAL aclexplode(d.datacl) a "
        "JOIN pg_catalog.pg_roles g ON g.oid = a.grantee WHERE d.datname = %s AND g.rolname = 'nsi_congelamento'",
        (banco,),
    )
    assert cur.fetchone()[0] == 0


def test_role_nao_e_dona_de_nenhum_objeto_no_cluster(cur):
    cur.execute(
        "SELECT count(*) FROM pg_catalog.pg_shdepend s JOIN pg_catalog.pg_roles r ON r.oid = s.refobjid "
        "WHERE s.refclassid = 'pg_authid'::regclass AND r.rolname = 'nsi_congelamento' AND s.deptype = 'o'"
    )
    assert cur.fetchone()[0] == 0


def test_dependencias_no_cluster_somente_acl_de_schema_e_funcao_nos_bancos_locais(cur):
    cur.execute("""
        SELECT count(*) FROM pg_catalog.pg_shdepend s JOIN pg_catalog.pg_roles r ON r.oid = s.refobjid
         WHERE s.refclassid = 'pg_authid'::regclass AND r.rolname = 'nsi_congelamento'
           AND NOT (s.deptype = 'a'
                    AND s.classid IN ('pg_namespace'::regclass, 'pg_proc'::regclass)
                    AND s.dbid IN (SELECT oid FROM pg_catalog.pg_database WHERE datname IN ('nsi_dev', 'nsi_test')))
    """)
    assert cur.fetchone()[0] == 0


def test_usage_no_schema_sem_create_nem_grant_option(cur):
    cur.execute("""
        SELECT a.privilege_type, a.is_grantable FROM pg_catalog.pg_namespace n
         CROSS JOIN LATERAL aclexplode(n.nspacl) a JOIN pg_catalog.pg_roles g ON g.oid = a.grantee
         WHERE g.rolname = 'nsi_congelamento'
    """)
    assert cur.fetchall() == [("USAGE", False)]
    cur.execute("SELECT has_schema_privilege('nsi_congelamento', 'nsi_operacional', 'CREATE')")
    assert cur.fetchone()[0] is False


def test_nenhum_privilegio_efetivo_em_tabela(cur):
    cur.execute("""
        SELECT count(*) FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = 'nsi_operacional' AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
           AND (has_table_privilege('nsi_congelamento', c.oid, 'SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER')
                OR has_any_column_privilege('nsi_congelamento', c.oid, 'SELECT, INSERT, UPDATE, REFERENCES'))
    """)
    assert cur.fetchone()[0] == 0


def test_execute_efetivo_somente_na_funcao_de_congelamento(cur):
    """Matriz final, com a 0005 aplicada: a role nao tem EXECUTE em
    nenhuma outra funcao do schema, inclusive as seis de claim."""
    cur.execute("""
        SELECT p.proname FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
         WHERE n.nspname = 'nsi_operacional' AND has_function_privilege('nsi_congelamento', p.oid, 'EXECUTE')
    """)
    assert [r[0] for r in cur.fetchall()] == ["fn_registrar_congelamento"]


def test_nsi_aplicacao_nao_herda_execute_de_congelamento(cur):
    """INHERIT FALSE: sem SET ROLE, nsi_aplicacao nao tem o privilegio."""
    cur.execute("""
        SELECT has_function_privilege('nsi_aplicacao', p.oid, 'EXECUTE')
          FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
         WHERE n.nspname = 'nsi_operacional' AND p.proname = 'fn_registrar_congelamento'
    """)
    assert cur.fetchone()[0] is False


def test_dsn_mascarada_nunca_contem_usuario_ou_senha(request):
    url = request.getfixturevalue("url_banco_teste")
    representacao_segura = mascarar_dsn(url)
    assert "@" not in representacao_segura
    assert "://" not in representacao_segura
