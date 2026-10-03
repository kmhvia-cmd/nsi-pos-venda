# -*- coding: utf-8 -*-
"""
NSI - tests/integration/test_fn_registrar_tentativa_nao_resolvida.py
(Sprint B, B4.3 - ADR-009, Secoes 6.5 e 8)

Testes de integracao REAIS contra PostgreSQL, exclusivamente contra
nsi_test, de nsi_operacional.fn_registrar_tentativa_nao_resolvida
(migration 0005) - evento 'tentativa_correcao_nao_resolvida', com payload
seguro (ADR-009, Secao 8): lote_id, motivo de vocabulario fechado e
codigo tecnico normalizado (ou nulo) - nunca codigo bruto, nunca texto
livre, nunca valor pessoal.

Conexao primaria: migrator ('SET LOCAL ROLE nsi_eventos_owner'), em
transacao revertida no teardown - nenhum residuo.

Nenhum teste chama pytest nem executa a suite completa internamente.
"""

import psycopg
import pytest

from config import mascarar_dsn
from core.payload_hash import hash_registrar_tentativa_nao_resolvida
from tests.apoio_b4_3 import criar_lote, posicionar_fronteira, registro_invalido, uuid_texto

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


def _registrar(cur, lote_id, motivo, codigo, chave, payload_hash=None) -> dict:
    if payload_hash is None:
        payload_hash = hash_registrar_tentativa_nao_resolvida(lote_id, motivo, codigo)
    cur.execute(
        "SELECT nsi_operacional.fn_registrar_tentativa_nao_resolvida(%s, %s, %s, %s, %s)",
        (lote_id, motivo, codigo, chave, payload_hash),
    )
    return cur.fetchone()[0]


def _versao_lote(cur, lote_id) -> int:
    cur.execute("SELECT versao_eventos_atual FROM nsi_operacional.lotes WHERE lote_id = %s", (lote_id,))
    return cur.fetchone()[0]


def _eventos_tentativa(cur, lote_id):
    cur.execute(
        "SELECT evento_id::text, aggregate_version, motivo, codigo_tecnico_normalizado::text, executado_por_login, "
        "occurred_at = now(), recebido_em, total_recebido, total_valido, total_invalido, horario_conceitual, "
        "horario_real_execucao, atrasado, operador_humano_id, total_confirmado "
        "FROM nsi_operacional.eventos_lote WHERE aggregate_id = %s AND tipo = 'tentativa_correcao_nao_resolvida' "
        "ORDER BY aggregate_version",
        (lote_id,),
    )
    return cur.fetchall()


# ============================================================
# Sucesso - os quatro motivos, cada um com o codigo coerente
# ============================================================

@pytest.mark.parametrize("motivo", ["codigo_ausente", "codigo_invalido"])
def test_motivo_sem_codigo_sintaticamente_valido_grava_codigo_nulo(cur, motivo):
    cur.execute("SAVEPOINT sp")
    try:
        lote_id = criar_lote(cur, [registro_invalido()])
        resultado = _registrar(cur, lote_id, motivo, None, "chave-" + motivo)
        assert set(resultado.keys()) == {"sucesso", "evento_id", "versao_eventos"}
        assert resultado["sucesso"] is True and resultado["versao_eventos"] == 2

        eventos = _eventos_tentativa(cur, lote_id)
        assert len(eventos) == 1
        assert eventos[0][0] == resultado["evento_id"]
        assert eventos[0][1:6] == (2, motivo, None, "nsi_test_migrator", True)
        assert eventos[0][6:] == (None,) * 9
        assert _versao_lote(cur, lote_id) == 2  # nenhum outro efeito na projecao
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_codigo_inexistente_em_qualquer_lote(cur):
    cur.execute("SAVEPOINT sp")
    try:
        lote_id = criar_lote(cur, [registro_invalido()])
        codigo = uuid_texto()
        assert _registrar(cur, lote_id, "codigo_inexistente", codigo, "chave-inexistente")["sucesso"] is True
        assert _eventos_tentativa(cur, lote_id)[0][2:4] == ("codigo_inexistente", codigo)
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_registro_de_outra_operacao(cur):
    cur.execute("SAVEPOINT sp")
    try:
        de_outro_lote = registro_invalido()
        criar_lote(cur, [de_outro_lote])
        lote_id = criar_lote(cur, [registro_invalido()])
        codigo = de_outro_lote["registro_coleta_id"]
        assert _registrar(cur, lote_id, "registro_de_outra_operacao", codigo, "chave-outra-operacao")["sucesso"] is True
        assert _eventos_tentativa(cur, lote_id)[0][2:4] == ("registro_de_outra_operacao", codigo)
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_aceita_em_qualquer_status_inclusive_apos_congelamento(cur):
    cur.execute("SAVEPOINT sp")
    try:
        lote_id = criar_lote(cur, [registro_invalido()])
        posicionar_fronteira(cur, lote_id, "-1 second")
        cur.execute("SELECT nsi_operacional.fn_registrar_congelamento(%s)", (lote_id,))
        assert cur.fetchone()[0]["status"] == "sem_registros_validos"
        resultado = _registrar(cur, lote_id, "codigo_ausente", None, "chave-apos-congelamento")
        assert resultado["sucesso"] is True and resultado["versao_eventos"] == 3
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_versoes_de_evento_do_lote_sem_lacuna(cur):
    cur.execute("SAVEPOINT sp")
    try:
        lote_id = criar_lote(cur, [registro_invalido()])
        for i in range(3):
            _registrar(cur, lote_id, "codigo_ausente", None, f"chave-sequencia-{i}")
        cur.execute("SELECT aggregate_version FROM nsi_operacional.eventos_lote WHERE aggregate_id = %s "
                    "ORDER BY aggregate_version", (lote_id,))
        assert [r[0] for r in cur.fetchall()] == [1, 2, 3, 4]
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


# ============================================================
# Recusas de negocio - sem evento, com recibo
# ============================================================

def _assert_recusa(cur, lote_id, motivo, codigo, chave, motivo_recusa):
    versao_antes = _versao_lote(cur, lote_id) if motivo_recusa != "lote_inexistente" else None
    recusa = _registrar(cur, lote_id, motivo, codigo, chave)
    assert recusa == {"sucesso": False, "motivo": motivo_recusa}
    assert _eventos_tentativa(cur, lote_id) == []
    if versao_antes is not None:
        assert _versao_lote(cur, lote_id) == versao_antes
    cur.execute("SELECT resultado FROM nsi_operacional.comandos_idempotentes "
                "WHERE comando = 'registrar_tentativa_nao_resolvida' AND aggregate_id = %s "
                "AND chave_idempotencia = %s", (lote_id, chave))
    assert cur.fetchone()[0] == recusa
    assert _registrar(cur, lote_id, motivo, codigo, chave) == recusa  # replay da recusa


def test_lote_inexistente(cur):
    cur.execute("SAVEPOINT sp")
    try:
        _assert_recusa(cur, uuid_texto(), "codigo_ausente", None, "chave-lote-inexistente", "lote_inexistente")
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


@pytest.mark.parametrize("motivo", ["motivo_livre", "", "CODIGO_AUSENTE", None])
def test_motivo_fora_do_vocabulario(cur, motivo):
    cur.execute("SAVEPOINT sp")
    try:
        lote_id = criar_lote(cur, [registro_invalido()])
        _assert_recusa(cur, lote_id, motivo, None, "chave-motivo-invalido", "motivo_invalido")
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


@pytest.mark.parametrize("motivo,codigo_presente", [
    ("codigo_ausente", True), ("codigo_invalido", True),
    ("codigo_inexistente", False), ("registro_de_outra_operacao", False),
])
def test_motivo_incoerente_com_codigo(cur, motivo, codigo_presente):
    cur.execute("SAVEPOINT sp")
    try:
        lote_id = criar_lote(cur, [registro_invalido()])
        codigo = uuid_texto() if codigo_presente else None
        _assert_recusa(cur, lote_id, motivo, codigo, "chave-incoerente", "motivo_incoerente_com_codigo")
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


@pytest.mark.parametrize("motivo", ["codigo_inexistente", "registro_de_outra_operacao"])
def test_codigo_que_resolve_neste_lote(cur, motivo):
    cur.execute("SAVEPOINT sp")
    try:
        registro = registro_invalido()
        lote_id = criar_lote(cur, [registro])
        _assert_recusa(cur, lote_id, motivo, registro["registro_coleta_id"], "chave-resolve", "codigo_resolve_neste_lote")
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_codigo_inexistente_mas_que_existe_em_outro_lote_diverge_do_estado(cur):
    cur.execute("SAVEPOINT sp")
    try:
        de_outro_lote = registro_invalido()
        criar_lote(cur, [de_outro_lote])
        lote_id = criar_lote(cur, [registro_invalido()])
        _assert_recusa(cur, lote_id, "codigo_inexistente", de_outro_lote["registro_coleta_id"],
                       "chave-diverge-1", "motivo_diverge_do_estado")
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_outra_operacao_mas_codigo_inexistente_diverge_do_estado(cur):
    cur.execute("SAVEPOINT sp")
    try:
        lote_id = criar_lote(cur, [registro_invalido()])
        _assert_recusa(cur, lote_id, "registro_de_outra_operacao", uuid_texto(), "chave-diverge-2", "motivo_diverge_do_estado")
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


# ============================================================
# Idempotencia e entradas invalidas
# ============================================================

def test_replay_sem_novo_evento(cur):
    cur.execute("SAVEPOINT sp")
    try:
        lote_id = criar_lote(cur, [registro_invalido()])
        primeiro = _registrar(cur, lote_id, "codigo_ausente", None, "chave-replay")
        assert _registrar(cur, lote_id, "codigo_ausente", None, "chave-replay") == primeiro
        assert len(_eventos_tentativa(cur, lote_id)) == 1
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_conflito_de_idempotencia_22023(cur):
    cur.execute("SAVEPOINT sp")
    try:
        lote_id = criar_lote(cur, [registro_invalido()])
        hash_original = hash_registrar_tentativa_nao_resolvida(lote_id, "codigo_ausente", None)
        primeiro = _registrar(cur, lote_id, "codigo_ausente", None, "chave-conflito")
        # Mesma chave, motivo diferente: o hash canonico real diverge.
        cur.execute("SAVEPOINT antes")
        with pytest.raises(psycopg.Error) as exc_info:
            _registrar(cur, lote_id, "codigo_invalido", None, "chave-conflito")
        assert exc_info.value.sqlstate == "22023"
        assert exc_info.value.diag.message_primary == "conflito_de_idempotencia"
        assert exc_info.value.diag.message_detail is None
        cur.execute("ROLLBACK TO SAVEPOINT antes")
        cur.execute("SELECT payload_hash, resultado FROM nsi_operacional.comandos_idempotentes "
                    "WHERE comando = 'registrar_tentativa_nao_resolvida' AND aggregate_id = %s", (lote_id,))
        assert cur.fetchone() == (hash_original, primeiro)
        assert len(_eventos_tentativa(cur, lote_id)) == 1
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


@pytest.mark.parametrize("indice_nulo", [0, 3, 4])
def test_parametro_obrigatorio_nulo_e_violacao_estrutural(cur, indice_nulo):
    lote_id = uuid_texto()
    params = [lote_id, "codigo_ausente", None, "chave-nulo",
              hash_registrar_tentativa_nao_resolvida(lote_id, "codigo_ausente", None)]
    params[indice_nulo] = None
    cur.execute("SAVEPOINT sp")
    with pytest.raises(psycopg.Error) as exc_info:
        cur.execute("SELECT nsi_operacional.fn_registrar_tentativa_nao_resolvida(%s::uuid, %s, %s::uuid, %s, %s)", params)
    assert exc_info.value.sqlstate == "22000"
    assert exc_info.value.diag.message_primary == "entrada_estrutural_invalida"
    cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_codigo_bruto_invalido_nunca_chega_a_funcao(cur):
    """O parametro UUID torna impossivel gravar um codigo bruto
    sintaticamente invalido (ADR-009, Secao 8): o PostgreSQL recusa a
    conversao antes de a funcao executar - nada e gravado."""
    cur.execute("SAVEPOINT setup")
    lote_id = criar_lote(cur, [registro_invalido()])
    # Um codigo bruto nao-UUID nao tem hash canonico (core.payload_hash
    # recusa-o, como a propria funcao): usa-se o hash do motivo com codigo
    # nulo - nunca usado, porque o PostgreSQL recusa a conversao antes.
    hash_qualquer_bem_formado = hash_registrar_tentativa_nao_resolvida(lote_id, "codigo_invalido", None)
    cur.execute("SAVEPOINT sp")
    with pytest.raises(psycopg.errors.InvalidTextRepresentation) as exc_info:
        cur.execute("SELECT nsi_operacional.fn_registrar_tentativa_nao_resolvida(%s, %s, %s::uuid, %s, %s)",
                    (lote_id, "codigo_invalido", "CODIGO-BRUTO-XYZ", "chave-bruto", hash_qualquer_bem_formado))
    assert exc_info.value.sqlstate == "22P02"
    cur.execute("ROLLBACK TO SAVEPOINT sp")
    assert _eventos_tentativa(cur, lote_id) == []
    cur.execute("ROLLBACK TO SAVEPOINT setup")


def test_dsn_mascarada_nunca_contem_usuario_ou_senha(request):
    url = request.getfixturevalue("url_banco_teste")
    representacao_segura = mascarar_dsn(url)
    assert "@" not in representacao_segura
    assert "://" not in representacao_segura
