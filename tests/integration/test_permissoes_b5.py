# -*- coding: utf-8 -*-
"""
NSI - tests/integration/test_permissoes_b5.py
(Sprint B, B5.4 - ADR-010, Secoes 9.2 e 16; Especificacao Tecnica, B5.2,
itens 4, 5.1, 8, 16 e 17)

Testes de integracao REAIS contra PostgreSQL, exclusivamente contra
nsi_test, do que atravessa a migration 0006 em materia de privilegio:

  - forma das quatro funcoes de importacao (owner, SECURITY DEFINER,
    search_path fixo, retorno JSONB) e da nova fn_criar_claim;
  - matriz de EXECUTE: as quatro funcoes somente para nsi_importacao;
    nsi_importacao em nenhuma das onze funcoes das ADRs 008 e 009; PUBLIC
    em nenhuma; fn_criar_claim inalterada (nsi_aplicacao);
  - nenhuma leitura nem DML direto, por nenhuma role funcional - inclusive
    nsi_importacao -, nas cinco tabelas novas;
  - por SQLSTATE real (42501), conectando como cada role funcional;
  - triggers de imutabilidade do registro tecnico; snapshot sem trigger.

Os testes de catalogo usam o migrator de teste, somente leitura. Os testes
que conectam COMO nsi_importacao dependem da credencial da role
(TEST_DATABASE_URL_NSI_IMPORTACAO - dependencia operacional da B5.2, item
19.6): sem ela, sao pulados em desenvolvimento comum e FALHAM no comando de
aceite (NSI_REQUIRE_PG_TESTS=1).

DIVULGACAO DE RESIDUO INTENCIONAL: test_identidade_tecnica_gravada_e_nsi_
importacao exige COMMIT real e usa somente um lote NAO promovivel (geracao
a1); a execucao concluida, o snapshot e o registro tecnico ficam como
residuo sintetico em nsi_test, ate o downgrade da 0006.
"""
import psycopg
import pytest

from config import resolver_url_banco_papel
from tests.apoio_b5 import (
    ASSINATURAS_DE_IMPORTACAO,
    FUNCOES_DE_IMPORTACAO,
    FUNCOES_DE_TRIGGER_0006,
    TABELAS_0006,
    TABELAS_REGISTRO_TECNICO,
    caminho_do_lote,
    concluir,
    doc_a1,
    doc_a2,
    entrada_de_lote,
    importar_bytes,
    iniciar,
    manifesto_canonico,
    paridade,
    serializar,
    url_nsi_importacao,
    uuid_texto,
)

pytestmark = pytest.mark.pg_integration

ONZE_FUNCOES_DAS_ADRS_008_E_009 = (
    "fn_criar_claim", "fn_registrar_heartbeat", "fn_liberar_claim", "fn_materializar_expiracao",
    "fn_registrar_revisao_abandono", "fn_reatribuir_claim",
    "fn_registrar_lote", "fn_registrar_congelamento", "fn_confirmar_disparo",
    "fn_registrar_correcao", "fn_registrar_tentativa_nao_resolvida",
)
ROLES_SEM_ACESSO_A_IMPORTACAO = (
    "nsi_aplicacao", "nsi_expiracao", "nsi_operador_restrito", "nsi_congelamento",
    "nsi_test_migrator", "nsi_dev_migrator",
)
ROLES_FUNCIONAIS = ("nsi_aplicacao", "nsi_expiracao", "nsi_operador_restrito", "nsi_congelamento", "nsi_importacao")
PAPEIS_DE_CONEXAO = ("nsi_aplicacao", "nsi_expiracao", "nsi_operador_restrito", "nsi_congelamento")
SEARCH_PATH_FIXO = ["search_path=pg_catalog, nsi_operacional, pg_temp"]


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


def _conectar_como(papel: str):
    """Os tres LOGIN da B3.1; nsi_congelamento por SET ROLE a partir de
    nsi_aplicacao (unico caminho possivel); nsi_importacao pela propria
    credencial."""
    if papel == "nsi_importacao":
        return psycopg.connect(url_nsi_importacao())
    if papel == "nsi_congelamento":
        conn = psycopg.connect(resolver_url_banco_papel("nsi_aplicacao", "test"))
        conn.cursor().execute("SET LOCAL ROLE nsi_congelamento")
        return conn
    return psycopg.connect(resolver_url_banco_papel(papel, "test"))


def _chamada_com_nulos(cur, nome_funcao: str) -> str:
    """SELECT da funcao com um NULL tipado por parametro: a checagem de
    EXECUTE ocorre antes de o corpo rodar."""
    cur.execute("""
        SELECT pg_catalog.pg_get_function_identity_arguments(p.oid)
          FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
         WHERE n.nspname = 'nsi_operacional' AND p.proname = %s
    """, (nome_funcao,))
    argumentos = cur.fetchone()[0]
    tipos = [a.strip().split(" ", 1)[1] for a in argumentos.split(",")] if argumentos else []
    return f"SELECT nsi_operacional.{nome_funcao}({', '.join(f'NULL::{t}' for t in tipos)})"


# ============================================================
# Forma das funcoes (item 5.1; criterio de aceite 3)
# ============================================================

def test_quatro_funcoes_de_importacao_com_a_forma_aprovada(cur):
    cur.execute("""
        SELECT p.proname, pg_get_userbyid(p.proowner), p.prosecdef, p.proconfig, l.lanname,
               pg_catalog.format_type(p.prorettype, NULL),
               '(' || pg_catalog.pg_get_function_identity_arguments(p.oid) || ')'
          FROM pg_catalog.pg_proc p
          JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
          JOIN pg_catalog.pg_language l ON l.oid = p.prolang
         WHERE n.nspname = 'nsi_operacional' AND p.proname = ANY(%s)
    """, (list(FUNCOES_DE_IMPORTACAO),))
    linhas = cur.fetchall()
    assert sorted(l[0] for l in linhas) == sorted(FUNCOES_DE_IMPORTACAO), "Exatamente quatro, uma assinatura cada."
    for nome, dono, secdef, config, linguagem, retorno, assinatura in linhas:
        assert dono == "nsi_eventos_owner", nome
        assert secdef is True, nome
        assert config == SEARCH_PATH_FIXO, nome
        assert linguagem == "plpgsql", nome
        assert retorno == "jsonb", nome
        tipos = [a.strip().split(" ", 1)[1] for a in assinatura.strip("()").split(",")]
        assert "(" + ", ".join(tipos) + ")" == ASSINATURAS_DE_IMPORTACAO[nome], nome


def test_fn_criar_claim_mantem_assinatura_owner_security_definer_e_matriz(cur):
    """Item 10.5: mesma assinatura (UUID, TEXT, TEXT, TEXT), mesmo owner,
    SECURITY DEFINER, search_path e matriz de EXECUTE."""
    cur.execute("""
        SELECT pg_get_userbyid(p.proowner), p.prosecdef, p.proconfig,
               pg_catalog.pg_get_function_identity_arguments(p.oid),
               ARRAY(SELECT pg_get_userbyid(a.grantee) FROM aclexplode(p.proacl) a
                      WHERE a.privilege_type = 'EXECUTE' AND a.grantee <> p.proowner ORDER BY 1),
               EXISTS (SELECT 1 FROM aclexplode(p.proacl) a WHERE a.grantee = 0),
               p.prosrc LIKE '%%registro_legado_nao_promovido%%'
          FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
         WHERE n.nspname = 'nsi_operacional' AND p.proname = 'fn_criar_claim'
    """)
    linhas = cur.fetchall()
    assert len(linhas) == 1
    dono, secdef, config, argumentos, grantees, public_tem, nova_definicao = linhas[0]
    assert (dono, secdef, config) == ("nsi_eventos_owner", True, SEARCH_PATH_FIXO)
    assert argumentos == ("p_registro_coleta_id uuid, p_token_hash text, "
                          "p_chave_idempotencia text, p_payload_hash text")
    assert grantees == ["nsi_aplicacao"]
    assert public_tem is False
    assert nova_definicao is True


# ============================================================
# Matriz de EXECUTE - catalogo (item 4)
# ============================================================

def test_execute_das_quatro_funcoes_concedido_somente_a_nsi_importacao(cur):
    cur.execute("""
        SELECT p.proname,
               ARRAY(SELECT pg_get_userbyid(a.grantee) FROM aclexplode(p.proacl) a
                      WHERE a.privilege_type = 'EXECUTE' AND a.grantee <> p.proowner AND a.grantee <> 0 ORDER BY 1),
               EXISTS (SELECT 1 FROM aclexplode(p.proacl) a WHERE a.grantee = 0),
               EXISTS (SELECT 1 FROM aclexplode(p.proacl) a WHERE a.is_grantable AND a.grantee <> p.proowner)
          FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
         WHERE n.nspname = 'nsi_operacional' AND p.proname = ANY(%s)
    """, (list(FUNCOES_DE_IMPORTACAO),))
    linhas = cur.fetchall()
    assert len(linhas) == 4
    for nome, grantees, public_tem, com_grant_option in linhas:
        assert grantees == ["nsi_importacao"], nome
        assert public_tem is False, f"PUBLIC nao pode ter EXECUTE em {nome}"
        assert com_grant_option is False, nome


@pytest.mark.parametrize("role", ROLES_SEM_ACESSO_A_IMPORTACAO)
@pytest.mark.parametrize("funcao", FUNCOES_DE_IMPORTACAO)
def test_nenhuma_outra_role_tem_execute_efetivo_nas_funcoes_de_importacao(cur, role, funcao):
    """Inclusive os migrators: aplicam a 0006, nunca executam importacao."""
    cur.execute("SELECT has_function_privilege(%s, %s, 'EXECUTE')",
                (role, f"nsi_operacional.{funcao}{ASSINATURAS_DE_IMPORTACAO[funcao]}"))
    assert cur.fetchone()[0] is False


def test_nsi_importacao_tem_execute_somente_nas_quatro_funcoes(cur):
    """ADR-010, Secao 16.2: nenhum EXECUTE nas onze funcoes das ADRs 008 e
    009, nem nas funcoes de trigger."""
    cur.execute("""
        SELECT p.proname FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
         WHERE n.nspname = 'nsi_operacional' AND has_function_privilege('nsi_importacao', p.oid, 'EXECUTE')
    """)
    assert sorted(r[0] for r in cur.fetchall()) == sorted(FUNCOES_DE_IMPORTACAO)

    cur.execute("""
        SELECT count(*) FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
         WHERE n.nspname = 'nsi_operacional' AND p.proname = ANY(%s)
    """, (list(ONZE_FUNCOES_DAS_ADRS_008_E_009),))
    assert cur.fetchone()[0] == 11, "As onze funcoes existentes continuam la."


def test_funcoes_de_trigger_sem_execute_para_public_e_sem_security_definer(cur):
    cur.execute("""
        SELECT p.proname, pg_get_userbyid(p.proowner), p.prosecdef, p.proconfig,
               EXISTS (SELECT 1 FROM aclexplode(p.proacl) a WHERE a.grantee <> p.proowner)
          FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
         WHERE n.nspname = 'nsi_operacional' AND p.proname = ANY(%s)
    """, (list(FUNCOES_DE_TRIGGER_0006),))
    linhas = cur.fetchall()
    assert len(linhas) == 3
    for nome, dono, secdef, config, alguem_alem_do_owner in linhas:
        assert dono == "nsi_eventos_owner", nome
        assert secdef is False, nome
        assert config == SEARCH_PATH_FIXO, nome
        assert alguem_alem_do_owner is False, nome


# ============================================================
# Tabelas - catalogo (itens 8 e 16)
# ============================================================

def test_cinco_tabelas_pertencem_ao_owner_e_nao_tem_nenhuma_concessao(cur):
    cur.execute("""
        SELECT c.relname, pg_get_userbyid(c.relowner),
               (SELECT count(*) FROM aclexplode(c.relacl) a WHERE a.grantee <> c.relowner)
          FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = 'nsi_operacional' AND c.relkind = 'r' AND c.relname = ANY(%s)
    """, (list(TABELAS_0006),))
    linhas = cur.fetchall()
    assert sorted(l[0] for l in linhas) == sorted(TABELAS_0006)
    for tabela, dono, concessoes in linhas:
        assert dono == "nsi_eventos_owner", tabela
        assert concessoes == 0, f"{tabela}: nenhuma role alem do owner, nem PUBLIC, pode ter concessao."


@pytest.mark.parametrize("role", ROLES_FUNCIONAIS + ("nsi_test_migrator",))
@pytest.mark.parametrize("tabela", TABELAS_0006)
def test_nenhuma_role_tem_privilegio_efetivo_nas_tabelas_novas(cur, role, tabela):
    cur.execute(
        "SELECT has_table_privilege(%s, %s, 'SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER'), "
        "       has_any_column_privilege(%s, %s, 'SELECT, INSERT, UPDATE, REFERENCES')",
        (role, f"nsi_operacional.{tabela}", role, f"nsi_operacional.{tabela}"))
    assert cur.fetchone() == (False, False)


def test_triggers_de_imutabilidade_somente_no_registro_tecnico(cur):
    """Item 16: uma trigger BEFORE UPDATE OR DELETE por tabela do registro
    tecnico. Item 8 / ADR-010, Secao 9.3: nenhuma no snapshot."""
    cur.execute("""
        SELECT c.relname, t.tgname, p.proname, t.tgenabled, t.tgtype
          FROM pg_catalog.pg_trigger t
          JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
          JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
          JOIN pg_catalog.pg_proc p ON p.oid = t.tgfoid
         WHERE n.nspname = 'nsi_operacional' AND c.relname = ANY(%s) AND NOT t.tgisinternal
         ORDER BY c.relname
    """, (list(TABELAS_0006),))
    # tgtype: ROW (1) + BEFORE (2) + DELETE (8) + UPDATE (16) = 27.
    assert cur.fetchall() == [
        (tabela, f"{tabela}_bloqueia_alteracao", f"fn_bloquear_alteracao_{tabela}", "O", 27)
        for tabela in sorted(TABELAS_REGISTRO_TECNICO)
    ]


# ============================================================
# Por SQLSTATE real - roles funcionais existentes
# ============================================================

@pytest.mark.parametrize("papel", PAPEIS_DE_CONEXAO)
@pytest.mark.parametrize("funcao", FUNCOES_DE_IMPORTACAO)
def test_role_funcional_sem_execute_nas_funcoes_de_importacao(request, papel, funcao):
    url = request.getfixturevalue("url_banco_teste")
    with psycopg.connect(url) as conn_catalogo:
        sql = _chamada_com_nulos(conn_catalogo.cursor(), funcao)

    conn = _conectar_como(papel)
    try:
        with pytest.raises(psycopg.errors.InsufficientPrivilege) as exc_info:
            conn.cursor().execute(sql)
        assert exc_info.value.sqlstate == "42501"
    finally:
        conn.rollback()
        conn.close()


@pytest.mark.parametrize("papel", PAPEIS_DE_CONEXAO)
@pytest.mark.parametrize("tabela", TABELAS_0006)
def test_role_funcional_nao_le_nem_escreve_nas_tabelas_novas(papel, tabela):
    conn = _conectar_como(papel)
    try:
        cur = conn.cursor()
        for comando in (f"SELECT 1 FROM nsi_operacional.{tabela} LIMIT 1", f"DELETE FROM nsi_operacional.{tabela}"):
            cur.execute("SAVEPOINT sp")
            with pytest.raises(psycopg.errors.InsufficientPrivilege) as exc_info:
                cur.execute(comando)
            assert exc_info.value.sqlstate == "42501"
            cur.execute("ROLLBACK TO SAVEPOINT sp")
    finally:
        conn.rollback()
        conn.close()


def test_nsi_aplicacao_continua_executando_fn_criar_claim():
    """A nova definicao mantem a matriz: nsi_aplicacao cria claim; a
    identidade gravada continua sendo a role da conexao."""
    conn = _conectar_como("nsi_aplicacao")
    try:
        cur = conn.cursor()
        cur.execute("SELECT nsi_operacional.fn_criar_claim(%s, %s, %s, %s)",
                    (uuid_texto(), "a" * 64, "chave-permissao-b5", "b" * 64))
        assert cur.fetchone()[0]["sucesso"] is True
    finally:
        conn.rollback()
        conn.close()


# ============================================================
# Conectando como nsi_importacao (depende da credencial - item 19.6)
# ============================================================

def test_nsi_importacao_executa_o_fluxo_completo_e_nada_mais():
    conn = _conectar_como("nsi_importacao")
    try:
        cur = conn.cursor()
        cur.execute("SELECT session_user, current_user, current_database()")
        assert cur.fetchone() == ("nsi_importacao", "nsi_importacao", "nsi_test")

        importacao_id = iniciar(cur)
        entradas = []
        for documento in (doc_a1(), doc_a2()):
            conteudo = serializar(documento)
            resultado = importar_bytes(cur, importacao_id, caminho_do_lote(documento["lote_id"]), conteudo)
            entradas.append(entrada_de_lote(caminho_do_lote(documento["lote_id"]), conteudo, resultado))
        assert [e["destino"] for e in entradas] == ["preservado", "promovido"]
        concluir(cur, importacao_id, manifesto_canonico(importacao_id, "America/Sao_Paulo", entradas), 2)
        assert paridade(cur, importacao_id)["aprovada"] is True
    finally:
        conn.rollback()  # promocao nunca e confirmada em teste
        conn.close()


@pytest.mark.parametrize("funcao", ONZE_FUNCOES_DAS_ADRS_008_E_009)
def test_nsi_importacao_sem_execute_nas_onze_funcoes_existentes(request, funcao):
    url = request.getfixturevalue("url_banco_teste")
    with psycopg.connect(url) as conn_catalogo:
        sql = _chamada_com_nulos(conn_catalogo.cursor(), funcao)

    conn = _conectar_como("nsi_importacao")
    try:
        with pytest.raises(psycopg.errors.InsufficientPrivilege) as exc_info:
            conn.cursor().execute(sql)
        assert exc_info.value.sqlstate == "42501"
    finally:
        conn.rollback()
        conn.close()


@pytest.mark.parametrize("tabela", TABELAS_0006 + ("lotes", "registros_coleta", "claims", "comandos_idempotentes",
                                                   "eventos_lote", "eventos_registro_coleta", "eventos_claim"))
def test_nsi_importacao_sem_acesso_direto_a_nenhuma_tabela(tabela):
    conn = _conectar_como("nsi_importacao")
    try:
        cur = conn.cursor()
        for comando in (f"SELECT 1 FROM nsi_operacional.{tabela} LIMIT 1", f"DELETE FROM nsi_operacional.{tabela}"):
            cur.execute("SAVEPOINT sp")
            with pytest.raises(psycopg.errors.InsufficientPrivilege) as exc_info:
                cur.execute(comando)
            assert exc_info.value.sqlstate == "42501"
            cur.execute("ROLLBACK TO SAVEPOINT sp")
    finally:
        conn.rollback()
        conn.close()


@pytest.mark.parametrize("outra_role", ["nsi_eventos_owner", "nsi_aplicacao", "nsi_congelamento", "nsi_test_migrator"])
def test_nsi_importacao_nao_assume_nenhuma_outra_role(outra_role):
    conn = _conectar_como("nsi_importacao")
    try:
        with pytest.raises(psycopg.errors.InsufficientPrivilege) as exc_info:
            conn.cursor().execute(f"SET LOCAL ROLE {outra_role}")
        assert exc_info.value.sqlstate == "42501"
    finally:
        conn.rollback()
        conn.close()


def test_identidade_tecnica_gravada_e_nsi_importacao(request):
    """ADR-010, Secao 16.4: session_user = nsi_importacao, de ponta a ponta.
    A role nao le tabela nenhuma; por isso a execucao e confirmada (COMMIT
    real, lote nao promovivel) e lida depois pelo owner."""
    url = request.getfixturevalue("url_banco_teste")
    documento = doc_a1()
    conteudo = serializar(documento)

    conn = _conectar_como("nsi_importacao")
    try:
        cur = conn.cursor()
        importacao_id = iniciar(cur)
        resultado = importar_bytes(cur, importacao_id, caminho_do_lote(documento["lote_id"]), conteudo)
        assert resultado["destino"] == "preservado"
        concluir(cur, importacao_id, manifesto_canonico(
            importacao_id, "America/Sao_Paulo",
            [entrada_de_lote(caminho_do_lote(documento["lote_id"]), conteudo, resultado)]), 1)
        conn.commit()
        assert paridade(cur, importacao_id)["aprovada"] is True
    finally:
        conn.rollback()
        conn.close()

    with psycopg.connect(url) as conn:
        cur = conn.cursor()
        cur.execute("SET LOCAL ROLE nsi_eventos_owner")
        cur.execute("SELECT executado_por_login FROM nsi_operacional.importacoes_legado WHERE importacao_id = %s",
                    (importacao_id,))
        assert cur.fetchone()[0] == "nsi_importacao"
        conn.rollback()
