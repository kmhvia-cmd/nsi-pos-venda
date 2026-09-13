# -*- coding: utf-8 -*-
"""
NSI - tests/integration/test_provisionamento_b3_roles.py (Sprint B, B3.1 -
ADR-008, Parte 1 da B3 e correcoes de seguranca da PARTE 2A).

Testes de integracao REAIS contra PostgreSQL, mas EXCLUSIVAMENTE DE
LEITURA - nenhum destes testes executa CREATE, ALTER, GRANT, REVOKE ou
DROP, e nenhum deles chama provisionar_b3_roles.sql ou
desprovisionar_b3_roles.sql. O provisionamento em si (primeira execucao
OU segunda execucao para comprovar idempotencia) e sempre um
PROCEDIMENTO MANUAL, autorizado separadamente - nunca disparado por este
arquivo nem por nenhum outro teste automatizado. Os cenarios destrutivos
do script administrativo (role incompativel, desprovisionamento completo,
bloqueio por revisao diferente de 0001, prova de privilegio efetivo) sao
exclusivamente estaticos (tests/unit/test_scripts_b3_roles.py) ou manuais
(docs/implementation/PROCEDIMENTO-MANUAL-B3-DESTRUTIVO.md) - nunca
executados aqui contra o cluster local compartilhado.

Marcados 'pg_integration' (pytestmark, abaixo) - pulados em execucao
comum de desenvolvimento quando TEST_DATABASE_URL esta ausente (ver
tests/conftest.py); falham explicitamente (nunca pulam) quando
NSI_REQUIRE_PG_TESTS=1. Mesmo com TEST_DATABASE_URL definida, se B3.1
ainda nao foi provisionada manualmente neste cluster, as asserções deste
arquivo falham de forma controlada (mensagem clara identificando o que
esta ausente) - nunca com um erro cru de "role does not exist" sem
contexto.

Conexao usada: EXCLUSIVAMENTE a fixture 'url_banco_teste' (credencial do
migrator nsi_test_migrator, ja estabelecida desde B2 - ver
tests/conftest.py) - nunca as seis credenciais funcionais
(DATABASE_URL_NSI_*/TEST_DATABASE_URL_NSI_*), que normalmente ainda nao
estao configuradas no ambiente automatizado nesta fase (senha definida
manualmente, fora deste repositorio). Ler pg_roles/pg_auth_members/
pg_namespace/pg_database/pg_tables nao exige autenticar COMO a role
verificada - qualquer role autenticada pode consultar esses catalogos.
Nenhum teste solicita ou armazena credencial de postgres/superusuario.

ESCOPO: pg_roles, pg_auth_members e pg_database sao catalogos
COMPARTILHADOS do cluster (visiveis identicamente a partir de qualquer
banco) - por isso os testes de atributos de role, membership e CONNECT
cobrem nsi_dev E nsi_test, mesmo conectando apenas a nsi_test. Ja
pg_namespace, pg_tables e has_schema_privilege() sao especificos de CADA
banco - esses testes cobrem apenas nsi_test (unico banco ao qual a
infraestrutura de teste automatizada esta autorizada a conectar, mesma
restricao ja estabelecida pela B2 via BancoDeTesteNaoPermitido). O estado
de nsi_dev nesses aspectos especificos e verificado manualmente, pelo
operador, seguindo o mesmo padrao de consulta usado aqui.
"""
import pytest

from config import mascarar_dsn

pytestmark = pytest.mark.pg_integration

QUATRO_ROLES_FUNCIONAIS = ["nsi_eventos_owner", "nsi_aplicacao", "nsi_expiracao", "nsi_operador_restrito"]
TRES_ROLES_LOGIN = ["nsi_aplicacao", "nsi_expiracao", "nsi_operador_restrito"]


def _consultar_atributos_role(cur, nome_role):
    cur.execute(
        "SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, "
        "rolreplication, rolbypassrls, rolinherit "
        "FROM pg_roles WHERE rolname = %s",
        (nome_role,),
    )
    return cur.fetchone()


@pytest.mark.parametrize("nome_role", QUATRO_ROLES_FUNCIONAIS)
def test_role_existe_com_atributos_de_seguranca_corretos(url_banco_teste, nome_role):
    import psycopg

    with psycopg.connect(url_banco_teste) as conn:
        with conn.cursor() as cur:
            atributos = _consultar_atributos_role(cur, nome_role)

    assert atributos is not None, (
        f"Role {nome_role!r} nao existe neste cluster - B3.1 ainda nao foi "
        "provisionada (provisionar_b3_roles.sql), ou foi provisionada em "
        "outro cluster. Execucao manual e pre-requisito deste teste."
    )
    canlogin, super_, createdb, createrole, replication, bypassrls, inherit = atributos
    esperado_canlogin = nome_role != "nsi_eventos_owner"
    assert canlogin == esperado_canlogin, f"{nome_role}: rolcanlogin={canlogin}, esperado {esperado_canlogin}"
    assert super_ is False, f"{nome_role}: rolsuper={super_}, esperado False"
    assert createdb is False, f"{nome_role}: rolcreatedb={createdb}, esperado False"
    assert createrole is False, f"{nome_role}: rolcreaterole={createrole}, esperado False"
    assert replication is False, f"{nome_role}: rolreplication={replication}, esperado False"
    assert bypassrls is False, f"{nome_role}: rolbypassrls={bypassrls}, esperado False"
    assert inherit is True, f"{nome_role}: rolinherit={inherit}, esperado True"


@pytest.mark.parametrize("nome_role", QUATRO_ROLES_FUNCIONAIS)
def test_role_nao_pertence_a_nenhuma_membership_inesperada(url_banco_teste, nome_role):
    import psycopg

    with psycopg.connect(url_banco_teste) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM pg_auth_members m "
                "JOIN pg_roles r ON r.oid = m.member WHERE r.rolname = %s",
                (nome_role,),
            )
            (total,) = cur.fetchone()

    assert total == 0, f"{nome_role} pertence a {total} role(s) inesperada(s) - esperado zero."


@pytest.mark.parametrize("nome_migrator,nome_banco", [
    ("nsi_dev_migrator", "nsi_dev"),
    ("nsi_test_migrator", "nsi_test"),
])
def test_membership_do_migrator_em_nsi_eventos_owner(url_banco_teste, nome_migrator, nome_banco):
    import psycopg

    with psycopg.connect(url_banco_teste) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT m.inherit_option, m.set_option, m.admin_option "
                "FROM pg_auth_members m "
                "JOIN pg_roles r_role ON r_role.oid = m.roleid "
                "JOIN pg_roles r_member ON r_member.oid = m.member "
                "WHERE r_role.rolname = 'nsi_eventos_owner' AND r_member.rolname = %s",
                (nome_migrator,),
            )
            linha = cur.fetchone()

    assert linha is not None, (
        f"Membership de {nome_migrator} em nsi_eventos_owner nao encontrada - "
        "B3.1 ainda nao foi provisionada."
    )
    inherit_opt, set_opt, admin_opt = linha
    assert inherit_opt is False, f"{nome_migrator}: inherit_option={inherit_opt}, esperado False"
    assert set_opt is True, f"{nome_migrator}: set_option={set_opt}, esperado True"
    assert admin_opt is False, f"{nome_migrator}: admin_option={admin_opt}, esperado False"


def test_public_sem_connect_em_nsi_dev_e_nsi_test(url_banco_teste):
    """NUNCA usa has_database_privilege('public', ...) - 'public' seria
    interpretado como nome de role real (inexistente). aclexplode() com
    grantee = 0 e a forma correta de identificar o pseudo-role PUBLIC."""
    import psycopg

    with psycopg.connect(url_banco_teste) as conn:
        with conn.cursor() as cur:
            for nome_banco in ("nsi_dev", "nsi_test"):
                cur.execute(
                    "SELECT EXISTS ("
                    "  SELECT 1 FROM pg_database d, "
                    "  aclexplode(coalesce(d.datacl, acldefault('d', d.datdba))) AS acl "
                    "  WHERE d.datname = %s AND acl.grantee = 0 AND acl.privilege_type = 'CONNECT'"
                    ")",
                    (nome_banco,),
                )
                (public_tem_connect,) = cur.fetchone()
                assert public_tem_connect is False, f"PUBLIC ainda tem CONNECT em {nome_banco}."


@pytest.mark.parametrize("nome_migrator,banco_correto,banco_errado", [
    ("nsi_dev_migrator", "nsi_dev", "nsi_test"),
    ("nsi_test_migrator", "nsi_test", "nsi_dev"),
])
def test_migrator_tem_connect_somente_no_proprio_banco(url_banco_teste, nome_migrator, banco_correto, banco_errado):
    import psycopg

    with psycopg.connect(url_banco_teste) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT EXISTS ("
                "  SELECT 1 FROM pg_database d, "
                "  aclexplode(coalesce(d.datacl, acldefault('d', d.datdba))) AS acl, pg_roles r "
                "  WHERE d.datname = %s AND r.oid = acl.grantee AND r.rolname = %s AND acl.privilege_type = 'CONNECT'"
                ")",
                (banco_correto, nome_migrator),
            )
            (tem_connect_correto,) = cur.fetchone()

            cur.execute(
                "SELECT EXISTS ("
                "  SELECT 1 FROM pg_database d, "
                "  aclexplode(coalesce(d.datacl, acldefault('d', d.datdba))) AS acl, pg_roles r "
                "  WHERE d.datname = %s AND r.oid = acl.grantee AND r.rolname = %s AND acl.privilege_type = 'CONNECT'"
                ")",
                (banco_errado, nome_migrator),
            )
            (tem_connect_errado,) = cur.fetchone()

    assert tem_connect_correto is True, f"{nome_migrator} sem CONNECT em {banco_correto}."
    assert tem_connect_errado is False, f"{nome_migrator} com CONNECT indevido em {banco_errado}."


@pytest.mark.parametrize("nome_role", TRES_ROLES_LOGIN)
def test_role_funcional_tem_connect_nos_dois_bancos(url_banco_teste, nome_role):
    import psycopg

    with psycopg.connect(url_banco_teste) as conn:
        with conn.cursor() as cur:
            for nome_banco in ("nsi_dev", "nsi_test"):
                cur.execute(
                    "SELECT EXISTS ("
                    "  SELECT 1 FROM pg_database d, "
                    "  aclexplode(coalesce(d.datacl, acldefault('d', d.datdba))) AS acl, pg_roles r "
                    "  WHERE d.datname = %s AND r.oid = acl.grantee AND r.rolname = %s AND acl.privilege_type = 'CONNECT'"
                    ")",
                    (nome_banco, nome_role),
                )
                (tem_connect,) = cur.fetchone()
                assert tem_connect is True, f"{nome_role} sem CONNECT em {nome_banco}."


def test_schema_nsi_operacional_pertence_a_nsi_eventos_owner_em_nsi_test(url_banco_teste):
    import psycopg

    with psycopg.connect(url_banco_teste) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT r.rolname FROM pg_namespace n "
                "JOIN pg_roles r ON r.oid = n.nspowner WHERE n.nspname = 'nsi_operacional'"
            )
            linha = cur.fetchone()

    assert linha is not None, "Schema nsi_operacional nao existe em nsi_test."
    assert linha[0] == "nsi_eventos_owner", f"Schema nsi_operacional em nsi_test pertence a {linha[0]!r}, esperado 'nsi_eventos_owner'."


def test_usage_no_schema_em_nsi_test(url_banco_teste):
    import psycopg

    with psycopg.connect(url_banco_teste) as conn:
        with conn.cursor() as cur:
            for nome_role in ["nsi_test_migrator"] + TRES_ROLES_LOGIN:
                cur.execute(
                    "SELECT has_schema_privilege(%s, 'nsi_operacional', 'USAGE')",
                    (nome_role,),
                )
                (tem_usage,) = cur.fetchone()
                assert tem_usage is True, f"{nome_role} sem USAGE em nsi_operacional (nsi_test)."


def test_alembic_version_continua_pertencendo_ao_migrator_em_nsi_test(url_banco_teste):
    import psycopg

    with psycopg.connect(url_banco_teste) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT tableowner FROM pg_tables "
                "WHERE schemaname = 'nsi_operacional' AND tablename = 'alembic_version'"
            )
            linha = cur.fetchone()

    assert linha is not None, "alembic_version nao existe em nsi_operacional (nsi_test)."
    assert linha[0] == "nsi_test_migrator", (
        f"alembic_version em nsi_test pertence a {linha[0]!r}, esperado 'nsi_test_migrator' - "
        "nunca deve passar a pertencer a nsi_eventos_owner."
    )


def test_dsn_mascarada_nunca_contem_usuario_ou_senha(url_banco_teste):
    """Mesmo padrao ja usado em test_alembic_postgres.py (B2) - nenhuma
    credencial em texto puro em nenhuma representacao usada por este
    arquivo."""
    representacao_segura = mascarar_dsn(url_banco_teste)
    assert "@" not in representacao_segura
    assert "://" not in representacao_segura
