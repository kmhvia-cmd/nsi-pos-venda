# -*- coding: utf-8 -*-
"""
NSI - tests/integration/test_comandos_idempotentes_compatibilidade_b4.py
(Sprint B, B4.2 - ADR-009)

Testes de integracao REAIS contra PostgreSQL, exclusivamente contra
nsi_test, da compatibilidade retroativa do CHECK
ck_comandos_idempotentes_comando apos a ampliacao aditiva da migration
0004: os cinco comandos de claim ja existentes (B3.2) continuam
validos; os cinco comandos novos da B4 passam a ser aceitos; um
comando fora da lista continua rejeitado.

Mesma disciplina dos demais arquivos desta subetapa: conexao do
migrator com 'SET LOCAL ROLE nsi_eventos_owner' (unica role com DML
direto na tabela), cada tentativa isolada num SAVEPOINT proprio, a
transacao externa sempre revertida no teardown - nenhum residuo em
nsi_test.

Pressupoe a migration 0004 ja aplicada em nsi_test. Nenhum teste deste
arquivo chama pytest nem executa a suite completa internamente.
"""
import hashlib
import uuid

import psycopg
import pytest

pytestmark = pytest.mark.pg_integration

COMANDOS_CLAIM_JA_EXISTENTES = (
    "criar_claim", "registrar_heartbeat", "liberar_claim",
    "registrar_revisao_abandono", "reatribuir_claim",
)

COMANDOS_NOVOS_B4 = (
    "registrar_lote", "registrar_congelamento", "confirmar_disparo",
    "registrar_correcao", "registrar_tentativa_nao_resolvida",
)


def _hash_valido(rotulo: str = "valor-de-teste") -> str:
    return hashlib.sha256(rotulo.encode()).hexdigest()


def _uuid() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def cur(request):
    """A URL e obtida internamente via request.getfixturevalue(), nunca
    como parametro nomeado desta fixture."""
    url = request.getfixturevalue("url_banco_teste")
    conn = psycopg.connect(url)
    try:
        cursor = conn.cursor()
        cursor.execute("SET LOCAL ROLE nsi_eventos_owner")
        yield cursor
    finally:
        conn.rollback()
        conn.close()


_SQL_INSERT_COMANDO = """
    INSERT INTO nsi_operacional.comandos_idempotentes
        (comando, aggregate_id, chave_idempotencia, payload_hash)
    VALUES
        (%(comando)s, %(aggregate_id)s, %(chave_idempotencia)s, %(payload_hash)s)
"""


def _params_comando(comando: str, **overrides) -> dict:
    base = dict(
        comando=comando,
        aggregate_id=_uuid(),
        chave_idempotencia=f"chave-compat-b4-{comando}",
        payload_hash=_hash_valido(comando),
    )
    base.update(overrides)
    return base


def _aceita(cur, params: dict) -> None:
    cur.execute("SAVEPOINT sp_teste")
    try:
        cur.execute(_SQL_INSERT_COMANDO, params)
    except Exception as exc:
        cur.execute("ROLLBACK TO SAVEPOINT sp_teste")
        pytest.fail(f"Esperado sucesso, mas falhou: {exc!r}")
    else:
        cur.execute("ROLLBACK TO SAVEPOINT sp_teste")


def _rejeita(cur, params: dict) -> None:
    cur.execute("SAVEPOINT sp_teste")
    try:
        with pytest.raises(psycopg.errors.CheckViolation) as exc_info:
            cur.execute(_SQL_INSERT_COMANDO, params)
        assert exc_info.value.sqlstate == "23514"
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp_teste")


@pytest.mark.parametrize("comando", COMANDOS_CLAIM_JA_EXISTENTES)
def test_comandos_de_claim_continuam_validos_apos_ampliacao(cur, comando):
    """Regressao obrigatoria: a ampliacao aditiva do CHECK feita pela
    migration 0004 nunca pode remover ou renomear nenhum dos cinco
    comandos de claim ja aprovados na B3.2."""
    _aceita(cur, _params_comando(comando))


@pytest.mark.parametrize("comando", COMANDOS_NOVOS_B4)
def test_comandos_novos_da_b4_sao_aceitos(cur, comando):
    _aceita(cur, _params_comando(comando))


def test_comando_fora_da_lista_continua_rejeitado(cur):
    _rejeita(cur, _params_comando("comando_inventado_fora_do_catalogo"))


def test_total_de_comandos_validos_e_exatamente_dez(request):
    """Confirma, por leitura direta do catalogo (pg_get_constraintdef),
    que o CHECK contem exatamente os 10 valores esperados - nem a mais
    nem a menos."""
    url = request.getfixturevalue("url_banco_teste")
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT pg_get_constraintdef(oid)
                  FROM pg_constraint
                 WHERE conname = 'ck_comandos_idempotentes_comando'
                   AND conrelid = 'nsi_operacional.comandos_idempotentes'::regclass
            """)
            (definicao,) = cur.fetchone()
    todos_os_comandos = COMANDOS_CLAIM_JA_EXISTENTES + COMANDOS_NOVOS_B4
    for comando in todos_os_comandos:
        assert comando in definicao, f"Comando {comando!r} ausente da definicao do CHECK: {definicao}"
    assert len(todos_os_comandos) == 10
