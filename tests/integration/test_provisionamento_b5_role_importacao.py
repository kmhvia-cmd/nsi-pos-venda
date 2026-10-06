# -*- coding: utf-8 -*-
"""
NSI - tests/integration/test_provisionamento_b5_role_importacao.py
(Sprint B, B5.3 - ADR-010, Secao 16; Especificacao Tecnica, B5.2, itens 4
e 17)

Testes de integracao REAIS contra PostgreSQL, mas EXCLUSIVAMENTE DE
LEITURA - nenhum destes testes executa CREATE, ALTER, GRANT, REVOKE ou
DROP, e nenhum deles chama provisionar_b5_role_importacao.sql ou
desprovisionar_b5_role_importacao.sql. O provisionamento e sempre um
PROCEDIMENTO MANUAL, autorizado separadamente; os cenarios destrutivos dos
scripts sao exclusivamente estaticos
(tests/unit/test_scripts_b5_role_importacao.py) ou manuais.

Comprova o estado final provisionado da role nsi_importacao: atributos
(LOGIN, sem os cinco privilegios elevados), ausencia de qualquer
membership, CONNECT somente em nsi_test, USAGE no schema somente em
nsi_test, nenhum privilegio em tabela, e EXECUTE conforme a revisao -
nenhum em 0005; somente nas quatro funcoes de importacao em 0006
(concedido pela migration, nunca pelo script). A revisao e lida do proprio
banco: os mesmos testes valem antes e depois da migration 0006.

Conexao usada: EXCLUSIVAMENTE a fixture 'url_banco_teste' (migrator de
nsi_test). Ler pg_roles/pg_auth_members/pg_database/pg_shdepend nao exige
autenticar COMO a role verificada - por isso estes testes nao dependem da
senha de nsi_importacao nem da URL TEST_DATABASE_URL_NSI_IMPORTACAO.

ESCOPO (mesmo de test_provisionamento_b4_role_congelamento.py): pg_roles,
pg_auth_members, pg_database e pg_shdepend sao catalogos COMPARTILHADOS do
cluster - os testes de atributos, membership, CONNECT e dependencias cobrem
o cluster inteiro (nsi_dev E nsi_test), mesmo conectando apenas a
nsi_test. Ja USAGE no schema e privilegios em tabelas e funcoes sao
especificos de CADA banco - cobrem apenas nsi_test (unico banco ao qual a
infraestrutura de teste automatizada esta autorizada a conectar). Em
nsi_dev, esses aspectos sao comprovados pela Fase 3 do proprio script de
provisionamento.
"""
import psycopg
import pytest

from config import mascarar_dsn

pytestmark = pytest.mark.pg_integration

QUATRO_FUNCOES_DE_IMPORTACAO = [
    "fn_concluir_importacao_legado", "fn_importar_lote_legado",
    "fn_iniciar_importacao_legado", "fn_verificar_paridade_legado",
]

# Roles cuja relacao com nsi_importacao precisa ser nula nos dois sentidos.
DEMAIS_ROLES_DO_PROJETO = [
    "nsi_eventos_owner", "nsi_aplicacao", "nsi_expiracao", "nsi_operador_restrito",
    "nsi_congelamento", "nsi_dev_migrator", "nsi_test_migrator",
]


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


def _revisao(cur) -> str:
    cur.execute("SELECT version_num FROM nsi_operacional.alembic_version")
    return cur.fetchone()[0]


def test_role_existe_com_atributos_de_seguranca_corretos(cur):
    cur.execute(
        "SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls, rolinherit "
        "FROM pg_catalog.pg_roles WHERE rolname = 'nsi_importacao'"
    )
    atributos = cur.fetchone()
    assert atributos is not None, (
        "Role nsi_importacao nao existe neste cluster - execute o provisionamento administrativo "
        "(procedimento manual) antes desta suite."
    )
    assert atributos == (True, False, False, False, False, False, True), (
        f"Atributos de nsi_importacao divergentes do aprovado: {atributos}"
    )


def test_role_nao_pertence_a_nenhuma_outra_role(cur):
    """ADR-010, Secao 16.2: nenhuma membership - nenhuma segunda excecao a
    regra da B3.1."""
    cur.execute(
        "SELECT g.rolname FROM pg_catalog.pg_auth_members m "
        "JOIN pg_catalog.pg_roles r ON r.oid = m.member JOIN pg_catalog.pg_roles g ON g.oid = m.roleid "
        "WHERE r.rolname = 'nsi_importacao'"
    )
    assert cur.fetchall() == []


def test_role_nao_tem_nenhum_membro(cur):
    cur.execute(
        "SELECT r.rolname FROM pg_catalog.pg_auth_members m "
        "JOIN pg_catalog.pg_roles r ON r.oid = m.member JOIN pg_catalog.pg_roles g ON g.oid = m.roleid "
        "WHERE g.rolname = 'nsi_importacao'"
    )
    assert cur.fetchall() == []


@pytest.mark.parametrize("outra_role", DEMAIS_ROLES_DO_PROJETO)
def test_nenhuma_role_do_projeto_alcanca_nsi_importacao_por_set_role(cur, outra_role):
    """Nenhuma outra identidade do projeto consegue assumir a role de
    importacao, e ela nao consegue assumir nenhuma outra."""
    cur.execute("SELECT pg_has_role(%s, 'nsi_importacao', 'MEMBER'), pg_has_role('nsi_importacao', %s, 'MEMBER')",
                (outra_role, outra_role))
    assert cur.fetchone() == (False, False)


def test_connect_concedido_somente_em_nsi_test(cur):
    """Lista COMPLETA das concessoes de banco a role, em todo o cluster."""
    cur.execute("""
        SELECT d.datname, a.privilege_type, a.is_grantable
          FROM pg_catalog.pg_database d
         CROSS JOIN LATERAL aclexplode(d.datacl) a
          JOIN pg_catalog.pg_roles g ON g.oid = a.grantee
         WHERE g.rolname = 'nsi_importacao'
    """)
    assert cur.fetchall() == [("nsi_test", "CONNECT", False)]


def test_connect_efetivo_somente_em_nsi_test(cur):
    """A importacao nunca ocorre em nsi_dev (ADR-010, Secao 21): sem
    CONNECT nominal e sem CONNECT herdado de PUBLIC."""
    cur.execute("SELECT has_database_privilege('nsi_importacao', 'nsi_test', 'CONNECT'), "
                "has_database_privilege('nsi_importacao', 'nsi_dev', 'CONNECT')")
    assert cur.fetchone() == (True, False)


@pytest.mark.parametrize("banco", ["nsi_dev", "nsi_test"])
def test_role_sem_create_em_banco(cur, banco):
    cur.execute("SELECT has_database_privilege('nsi_importacao', %s, 'CREATE')", (banco,))
    assert cur.fetchone()[0] is False


def test_role_nao_e_dona_de_nenhum_objeto_no_cluster(cur):
    cur.execute(
        "SELECT count(*) FROM pg_catalog.pg_shdepend s JOIN pg_catalog.pg_roles r ON r.oid = s.refobjid "
        "WHERE s.refclassid = 'pg_authid'::regclass AND r.rolname = 'nsi_importacao' AND s.deptype = 'o'"
    )
    assert cur.fetchone()[0] == 0


def test_dependencias_no_cluster_somente_as_previstas(cur):
    """So lista de permissao: CONNECT em nsi_test, schema de nsi_test e
    funcao de nsi_dev/nsi_test (EXECUTE concedido pela 0006)."""
    cur.execute("""
        SELECT count(*) FROM pg_catalog.pg_shdepend s JOIN pg_catalog.pg_roles r ON r.oid = s.refobjid
         WHERE s.refclassid = 'pg_authid'::regclass AND r.rolname = 'nsi_importacao'
           AND NOT (s.deptype = 'a' AND (
                    (s.classid = 'pg_database'::regclass AND s.dbid = 0
                     AND s.objid = (SELECT oid FROM pg_catalog.pg_database WHERE datname = 'nsi_test'))
                 OR (s.classid = 'pg_namespace'::regclass
                     AND s.dbid = (SELECT oid FROM pg_catalog.pg_database WHERE datname = 'nsi_test'))
                 OR (s.classid = 'pg_proc'::regclass
                     AND s.dbid IN (SELECT oid FROM pg_catalog.pg_database WHERE datname IN ('nsi_dev', 'nsi_test')))))
    """)
    assert cur.fetchone()[0] == 0


def test_nenhuma_dependencia_de_schema_em_nsi_dev(cur):
    """USAGE somente em nsi_test: em nsi_dev, a role nao aparece em
    nenhuma lista de permissao de schema (visivel pelo catalogo
    compartilhado, sem conectar a nsi_dev)."""
    cur.execute("""
        SELECT count(*) FROM pg_catalog.pg_shdepend s JOIN pg_catalog.pg_roles r ON r.oid = s.refobjid
         WHERE s.refclassid = 'pg_authid'::regclass AND r.rolname = 'nsi_importacao'
           AND s.classid = 'pg_namespace'::regclass
           AND s.dbid = (SELECT oid FROM pg_catalog.pg_database WHERE datname = 'nsi_dev')
    """)
    assert cur.fetchone()[0] == 0


def test_usage_no_schema_sem_create_nem_grant_option(cur):
    cur.execute("""
        SELECT n.nspname, a.privilege_type, a.is_grantable FROM pg_catalog.pg_namespace n
         CROSS JOIN LATERAL aclexplode(n.nspacl) a JOIN pg_catalog.pg_roles g ON g.oid = a.grantee
         WHERE g.rolname = 'nsi_importacao'
    """)
    assert cur.fetchall() == [("nsi_operacional", "USAGE", False)]
    cur.execute("SELECT has_schema_privilege('nsi_importacao', 'nsi_operacional', 'CREATE')")
    assert cur.fetchone()[0] is False


def test_nenhum_privilegio_efetivo_em_tabela(cur):
    """Nenhuma leitura nem escrita direta - inclusive, depois da 0006, no
    snapshot legado e no registro tecnico (ADR-010, Secoes 9.2 e 16.2)."""
    cur.execute("""
        SELECT count(*) FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = 'nsi_operacional' AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
           AND (has_table_privilege('nsi_importacao', c.oid, 'SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER')
                OR has_any_column_privilege('nsi_importacao', c.oid, 'SELECT, INSERT, UPDATE, REFERENCES'))
    """)
    assert cur.fetchone()[0] == 0


def test_execute_efetivo_conforme_a_revisao(cur):
    """Em 0005, nenhuma funcao; em 0006, exatamente as quatro de
    importacao - nunca nenhuma das onze das ADRs 008 e 009."""
    revisao = _revisao(cur)
    cur.execute("""
        SELECT p.proname FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
         WHERE n.nspname = 'nsi_operacional' AND has_function_privilege('nsi_importacao', p.oid, 'EXECUTE')
         ORDER BY p.proname
    """)
    com_execute = [r[0] for r in cur.fetchall()]
    if revisao == "0005":
        assert com_execute == []
    elif revisao == "0006":
        assert com_execute == QUATRO_FUNCOES_DE_IMPORTACAO
    else:
        pytest.fail(f"Revisao {revisao!r} fora das aceitas pelo provisionamento da B5.3 (0005 ou 0006).")


def test_concessoes_nominais_em_funcao_conforme_a_revisao(cur):
    """Concessao nominal (ACL), nao so privilegio efetivo: sem GRANT
    OPTION, e somente nas quatro funcoes em 0006."""
    revisao = _revisao(cur)
    cur.execute("""
        SELECT p.proname, a.privilege_type, a.is_grantable
          FROM pg_catalog.pg_proc p
         CROSS JOIN LATERAL aclexplode(p.proacl) a
          JOIN pg_catalog.pg_roles g ON g.oid = a.grantee
         WHERE g.rolname = 'nsi_importacao'
         ORDER BY p.proname
    """)
    esperado = [] if revisao == "0005" else [(nome, "EXECUTE", False) for nome in QUATRO_FUNCOES_DE_IMPORTACAO]
    assert cur.fetchall() == esperado


def test_provisionamento_nao_alterou_a_excecao_unica_de_membership_da_adr_009(cur):
    """nsi_aplicacao continua com exatamente a membership formalizada."""
    cur.execute(
        "SELECT g.rolname, m.inherit_option, m.set_option, m.admin_option FROM pg_catalog.pg_auth_members m "
        "JOIN pg_catalog.pg_roles r ON r.oid = m.member JOIN pg_catalog.pg_roles g ON g.oid = m.roleid "
        "WHERE r.rolname = 'nsi_aplicacao'"
    )
    assert cur.fetchall() == [("nsi_congelamento", False, True, False)]


@pytest.mark.parametrize("banco", ["nsi_dev", "nsi_test"])
def test_public_continua_sem_connect(cur, banco):
    cur.execute(
        "SELECT count(*) FROM pg_catalog.pg_database d CROSS JOIN LATERAL aclexplode(d.datacl) a "
        "WHERE d.datname = %s AND a.grantee = 0 AND a.privilege_type = 'CONNECT'",
        (banco,),
    )
    assert cur.fetchone()[0] == 0


def test_dsn_mascarada_nunca_contem_usuario_ou_senha(request):
    url = request.getfixturevalue("url_banco_teste")
    representacao_segura = mascarar_dsn(url)
    assert "@" not in representacao_segura
    assert "://" not in representacao_segura
