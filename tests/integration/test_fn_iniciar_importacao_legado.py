# -*- coding: utf-8 -*-
"""
NSI - tests/integration/test_fn_iniciar_importacao_legado.py
(Sprint B, B5.4 - ADR-010, Secoes 5 e 13; Especificacao Tecnica, B5.2,
itens 5.1, 12, 15 e 16)

Testes de integracao REAIS contra PostgreSQL, exclusivamente contra
nsi_test, de fn_iniciar_importacao_legado: abertura da execucao, declaracao
de fuso, replay, conflito de idempotencia e imutabilidade do registro
tecnico.

Todos os testes rodam numa transacao do migrator de teste sob SET LOCAL
ROLE nsi_eventos_owner e terminam em ROLLBACK - nenhum residuo.
"""
import psycopg
import pytest

from tests.apoio_b5 import contar, iniciar, uuid_texto

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


def _iniciar(cur, importacao_id, fuso):
    cur.execute("SELECT nsi_operacional.fn_iniciar_importacao_legado(%s, %s)", (importacao_id, fuso))
    return cur.fetchone()[0]


def _assert_erro_fixo(exc_info, sqlstate: str, mensagem: str) -> None:
    assert exc_info.value.sqlstate == sqlstate
    assert exc_info.value.diag.message_primary == mensagem
    assert exc_info.value.diag.message_detail is None


# ============================================================
# Abertura
# ============================================================

@pytest.mark.parametrize("fuso", ["America/Sao_Paulo", "UTC", "America/Argentina/Buenos_Aires", "Europe/Lisbon"])
def test_abre_execucao_com_fuso_iana_valido(cur, fuso):
    importacao_id = uuid_texto()
    resultado = _iniciar(cur, importacao_id, fuso)

    assert set(resultado) == {"importacao_id", "iniciada_em", "fuso_declarado"}
    assert resultado["importacao_id"] == importacao_id
    assert resultado["fuso_declarado"] == fuso

    cur.execute(
        "SELECT executado_por_login, fuso_declarado, iniciada_em = now(), session_user "
        "FROM nsi_operacional.importacoes_legado WHERE importacao_id = %s", (importacao_id,))
    login, fuso_gravado, iniciada_agora, usuario_da_sessao = cur.fetchone()
    assert login == usuario_da_sessao, "A identidade tecnica gravada e session_user, nunca current_user."
    assert login != "nsi_eventos_owner"
    assert fuso_gravado == fuso
    assert iniciada_agora is True


def test_fuso_nulo_e_aceito(cur):
    """A ausencia de declaracao de fuso nao impede a execucao (item 5)."""
    importacao_id = uuid_texto()
    resultado = _iniciar(cur, importacao_id, None)
    assert resultado["fuso_declarado"] is None
    assert contar(cur, "importacoes_legado", "importacao_id = %s AND fuso_declarado IS NULL", (importacao_id,)) == 1


# ============================================================
# Entrada estruturalmente invalida (22000)
# ============================================================

@pytest.mark.parametrize("fuso", [
    "America/Nao_Existe",            # fora de pg_timezone_names
    "Etc/GMT+3", "Etc/GMT-3", "Etc/UTC",   # prefixo Etc/ (deslocamento fixo)
    "posix/America/Sao_Paulo", "right/America/Sao_Paulo",
    "GMT+0", "GMT", "EST", "EST5EDT", "BRT", "Brazil",   # sem a forma Regiao/Local
    "-03:00", "UTC-3", "<-03>3",     # deslocamentos e especificacoes POSIX
    "america/sao_paulo", "utc",      # grafia diferente da registrada
    "", " ", "America/Sao_Paulo ",
])
def test_fuso_invalido_e_recusado(cur, fuso):
    importacao_id = uuid_texto()
    with pytest.raises(psycopg.errors.DataException) as exc_info:
        _iniciar(cur, importacao_id, fuso)
    _assert_erro_fixo(exc_info, "22000", "entrada_estrutural_invalida")


def test_importacao_id_nulo_e_recusado(cur):
    with pytest.raises(psycopg.errors.DataException) as exc_info:
        _iniciar(cur, None, "America/Sao_Paulo")
    _assert_erro_fixo(exc_info, "22000", "entrada_estrutural_invalida")


def test_fuso_invalido_nao_grava_nada(cur):
    importacao_id = uuid_texto()
    cur.execute("SAVEPOINT sp")
    with pytest.raises(psycopg.errors.DataException):
        _iniciar(cur, importacao_id, "Etc/GMT+3")
    cur.execute("ROLLBACK TO SAVEPOINT sp")
    assert contar(cur, "importacoes_legado", "importacao_id = %s", (importacao_id,)) == 0


# ============================================================
# Idempotencia (item 12)
# ============================================================

@pytest.mark.parametrize("fuso", ["America/Sao_Paulo", None])
def test_replay_com_o_mesmo_fuso_devolve_o_mesmo_resultado(cur, fuso):
    importacao_id = uuid_texto()
    primeiro = _iniciar(cur, importacao_id, fuso)
    segundo = _iniciar(cur, importacao_id, fuso)
    assert segundo == primeiro
    assert contar(cur, "importacoes_legado", "importacao_id = %s", (importacao_id,)) == 1


@pytest.mark.parametrize("original,repetido", [
    ("America/Sao_Paulo", "UTC"),
    ("America/Sao_Paulo", None),
    (None, "America/Sao_Paulo"),
])
def test_mesmo_importacao_id_com_fuso_diferente_e_conflito(cur, original, repetido):
    importacao_id = uuid_texto()
    _iniciar(cur, importacao_id, original)

    cur.execute("SAVEPOINT sp")
    with pytest.raises(psycopg.errors.InvalidParameterValue) as exc_info:
        _iniciar(cur, importacao_id, repetido)
    _assert_erro_fixo(exc_info, "22023", "conflito_de_idempotencia")
    for texto in (str(exc_info.value), repr(exc_info.value)):
        assert importacao_id not in texto
    cur.execute("ROLLBACK TO SAVEPOINT sp")

    cur.execute("SELECT fuso_declarado FROM nsi_operacional.importacoes_legado WHERE importacao_id = %s",
                (importacao_id,))
    assert cur.fetchone()[0] == original, "O registro original permanece intocado."


def test_replay_em_nova_conexao(request):
    """Replay sobre dado genuinamente persistido, em outra conexao. A
    execucao aberta e sem lotes fica como residuo sintetico em nsi_test: o
    registro tecnico e imutavel, e so o downgrade da 0006 o remove."""
    url = request.getfixturevalue("url_banco_teste")
    importacao_id = uuid_texto()

    with psycopg.connect(url) as conn:
        cur = conn.cursor()
        cur.execute("SET LOCAL ROLE nsi_eventos_owner")
        primeiro = _iniciar(cur, importacao_id, "America/Sao_Paulo")
        conn.commit()

    with psycopg.connect(url) as conn:
        cur = conn.cursor()
        cur.execute("SET LOCAL ROLE nsi_eventos_owner")
        assert _iniciar(cur, importacao_id, "America/Sao_Paulo") == primeiro
        with pytest.raises(psycopg.errors.InvalidParameterValue) as exc_info:
            _iniciar(cur, importacao_id, None)
        assert exc_info.value.sqlstate == "22023"
        conn.rollback()


# ============================================================
# Imutabilidade do registro da abertura (item 16)
# ============================================================

@pytest.mark.parametrize("comando", [
    "UPDATE nsi_operacional.importacoes_legado SET fuso_declarado = 'UTC' WHERE importacao_id = %s",
    "UPDATE nsi_operacional.importacoes_legado SET executado_por_login = 'outro' WHERE importacao_id = %s",
    "DELETE FROM nsi_operacional.importacoes_legado WHERE importacao_id = %s",
])
def test_registro_da_abertura_e_imutavel_inclusive_para_o_owner(cur, comando):
    importacao_id = iniciar(cur)
    cur.execute("SAVEPOINT sp")
    with pytest.raises(psycopg.errors.RaiseException) as exc_info:
        cur.execute(comando, (importacao_id,))
    assert "registro tecnico imutavel" in exc_info.value.diag.message_primary
    cur.execute("ROLLBACK TO SAVEPOINT sp")
    assert contar(cur, "importacoes_legado", "importacao_id = %s AND fuso_declarado = 'America/Sao_Paulo'",
                  (importacao_id,)) == 1


def test_check_de_fuso_e_a_rede_de_seguranca_da_tabela(cur):
    """A funcao valida o fuso contra pg_timezone_names; a CHECK da tabela
    barra, por formato, uma gravacao direta de deslocamento fixo."""
    with pytest.raises(psycopg.errors.CheckViolation) as exc_info:
        cur.execute(
            "INSERT INTO nsi_operacional.importacoes_legado (importacao_id, executado_por_login, fuso_declarado) "
            "VALUES (%s, 'teste', 'Etc/GMT+3')", (uuid_texto(),))
    assert exc_info.value.diag.constraint_name == "ck_importacoes_legado_fuso_formato"
