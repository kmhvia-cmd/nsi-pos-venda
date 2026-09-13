# -*- coding: utf-8 -*-
"""
NSI - tests/integration/test_trigger_imutabilidade_eventos_claim.py
(Sprint B, B3.2 - ADR-008, Parte 1 da B3 e correcoes de seguranca)

Testes de integracao REAIS contra PostgreSQL, exclusivamente contra
nsi_test, em duas frentes:

1. A trigger defensiva 'eventos_claim_bloqueia_alteracao' (funcao
   'fn_bloquear_alteracao_eventos_claim'): INSERT legitimo nunca
   bloqueado; UPDATE/DELETE sempre bloqueados, inclusive para
   nsi_eventos_owner (o proprio dono das tabelas); REVOKE ALL FROM PUBLIC
   na funcao da trigger, confirmado por catalogo.

2. Ausencia de DML direto - por OPERACAO REAL, nunca apenas inspecao de
   ACL - para as tres roles funcionais (nsi_aplicacao, nsi_expiracao,
   nsi_operador_restrito) nas tres tabelas (claims, eventos_claim,
   comandos_idempotentes), nas tres operacoes (INSERT, UPDATE, DELETE):
   27 combinacoes, cada uma conectando de fato como a role (via
   config.resolver_url_banco_papel), com dados sintatica e
   estruturalmente validos, confirmando especificamente SQLSTATE 42501
   (insufficient_privilege) e terminando sempre com ROLLBACK - nunca
   COMMIT. PUBLIC e verificado exclusivamente por inspecao de ACL
   (aclexplode/information_schema) - nunca por conexao real, ja que
   PUBLIC nao e uma role conectavel.

Mesma disciplina dos demais arquivos desta subetapa: pressupoe a
migration 0002 ja aplicada em nsi_test; nenhuma acao deste arquivo commita
dado algum; nenhum teste chama pytest nem executa a suite completa
internamente; nenhuma credencial aparece em nenhuma saida ou excecao
capturada.
"""
import hashlib
import uuid

import psycopg
import pytest

from config import mascarar_dsn, resolver_url_banco_papel

pytestmark = pytest.mark.pg_integration

PAPEIS_FUNCIONAIS = ["nsi_aplicacao", "nsi_expiracao", "nsi_operador_restrito"]
TABELAS_DE_NEGOCIO = ["claims", "eventos_claim", "comandos_idempotentes"]
OPERACOES_DML = ["INSERT", "UPDATE", "DELETE"]


def _hash_valido(rotulo: str = "valor-de-teste") -> str:
    return hashlib.sha256(rotulo.encode()).hexdigest()


def _uuid() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def cur_owner(request):
    """Conexao do migrator com 'SET LOCAL ROLE nsi_eventos_owner' ativo -
    usada exclusivamente para os testes da trigger em si (INSERT
    legitimo; UPDATE/DELETE bloqueados mesmo para o owner). A transacao
    externa e sempre revertida no teardown.

    A URL e obtida internamente via request.getfixturevalue(), nunca como
    parametro nomeado desta fixture - protege contra a DSN aparecer no
    cabecalho de um eventual erro de setup do pytest."""
    url = request.getfixturevalue("url_banco_teste")
    conn = psycopg.connect(url)
    try:
        cursor = conn.cursor()
        cursor.execute("SET LOCAL ROLE nsi_eventos_owner")
        yield cursor
    finally:
        conn.rollback()
        conn.close()


_EXECUTADO_POR = psycopg.types.json.Jsonb({"role": "nsi_test_migrator"})
_PAYLOAD_VAZIO = psycopg.types.json.Jsonb({})

_SQL_INSERT_CLAIM = """
    INSERT INTO nsi_operacional.claims
        (registro_coleta_id, claim_id, token_hash, estado, criado_em, expira_em, versao_atual)
    VALUES (%(registro_coleta_id)s, %(claim_id)s, %(token_hash)s, 'ativo', now(), now() + interval '5 minutes', 1)
"""

_SQL_INSERT_EVENTO = """
    INSERT INTO nsi_operacional.eventos_claim
        (evento_id, aggregate_type, aggregate_id, aggregate_version, tipo, claim_id, executado_por, payload)
    VALUES (%(evento_id)s, 'claim', %(aggregate_id)s, 1, 'claim_criado', %(claim_id)s, %(executado_por)s, %(payload)s)
"""


def _inserir_claim_e_evento(cur) -> tuple:
    registro_coleta_id = _uuid()
    evento_id = _uuid()
    cur.execute(_SQL_INSERT_CLAIM, dict(
        registro_coleta_id=registro_coleta_id, claim_id=_uuid(), token_hash=_hash_valido(),
    ))
    cur.execute(_SQL_INSERT_EVENTO, dict(
        evento_id=evento_id, aggregate_id=registro_coleta_id, claim_id=_uuid(),
        executado_por=_EXECUTADO_POR, payload=_PAYLOAD_VAZIO,
    ))
    return registro_coleta_id, evento_id


# ============================================================
# 1. Trigger 'eventos_claim_bloqueia_alteracao'
# ============================================================

def test_insert_legitimo_nunca_bloqueado_pela_trigger(cur_owner):
    cur_owner.execute("SAVEPOINT sp_insert")
    try:
        _inserir_claim_e_evento(cur_owner)
    except Exception as exc:
        cur_owner.execute("ROLLBACK TO SAVEPOINT sp_insert")
        pytest.fail(f"INSERT legitimo nao deveria ser bloqueado pela trigger: {exc!r}")
    else:
        cur_owner.execute("ROLLBACK TO SAVEPOINT sp_insert")


def test_update_bloqueado_mesmo_para_owner(cur_owner):
    cur_owner.execute("SAVEPOINT sp_update")
    try:
        _registro_coleta_id, evento_id = _inserir_claim_e_evento(cur_owner)
        with pytest.raises(psycopg.errors.RaiseException) as exc_info:
            cur_owner.execute(
                "UPDATE nsi_operacional.eventos_claim SET payload = %(payload)s WHERE evento_id = %(id)s",
                {"payload": _PAYLOAD_VAZIO, "id": evento_id},
            )
        assert exc_info.value.sqlstate == "P0001"
        assert "imutavel" in str(exc_info.value)
    finally:
        cur_owner.execute("ROLLBACK TO SAVEPOINT sp_update")


def test_delete_bloqueado_mesmo_para_owner(cur_owner):
    cur_owner.execute("SAVEPOINT sp_delete")
    try:
        _registro_coleta_id, evento_id = _inserir_claim_e_evento(cur_owner)
        with pytest.raises(psycopg.errors.RaiseException) as exc_info:
            cur_owner.execute(
                "DELETE FROM nsi_operacional.eventos_claim WHERE evento_id = %(id)s",
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
                "AND routine_name = 'fn_bloquear_alteracao_eventos_claim' "
                "AND grantee = 'PUBLIC' AND privilege_type = 'EXECUTE'"
            )
            linhas = cur.fetchall()
    assert linhas == [], "fn_bloquear_alteracao_eventos_claim ainda concede EXECUTE a PUBLIC."


# ============================================================
# 2. PUBLIC sem DML direto - exclusivamente por ACL, nunca conexao real
# ============================================================

def test_public_sem_dml_direto_nas_tres_tabelas_via_acl(request):
    url = request.getfixturevalue("url_banco_teste")
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT table_name, privilege_type FROM information_schema.table_privileges "
                "WHERE table_schema = 'nsi_operacional' AND table_name = ANY(%s) "
                "AND grantee = 'PUBLIC' AND privilege_type IN ('INSERT', 'UPDATE', 'DELETE', 'SELECT')",
                (TABELAS_DE_NEGOCIO,),
            )
            linhas = cur.fetchall()
    assert linhas == [], f"PUBLIC tem privilegio(s) inesperado(s) nas tabelas de negocio: {linhas}"


# ============================================================
# 3. As tres roles funcionais - permission denied REAL, 27 combinacoes
# ============================================================

def _construir_operacao(tabela: str, operacao: str):
    """Monta uma instrucao SQL sintatica e estruturalmente valida (nomes
    de coluna e tipos corretos) para a tabela/operacao pedida. Nao exige
    que a linha-alvo exista de fato: a checagem de privilegio do
    PostgreSQL ocorre antes de qualquer avaliacao de FK/linha, entao a
    tentativa falha por permissao mesmo contra dados inexistentes."""
    if tabela == "claims":
        if operacao == "INSERT":
            return (
                "INSERT INTO nsi_operacional.claims "
                "(registro_coleta_id, claim_id, token_hash, estado, criado_em, expira_em, versao_atual) "
                "VALUES (%(id)s, %(claim_id)s, %(hash)s, 'ativo', now(), now() + interval '5 minutes', 1)",
                {"id": _uuid(), "claim_id": _uuid(), "hash": _hash_valido()},
            )
        if operacao == "UPDATE":
            return (
                "UPDATE nsi_operacional.claims SET estado = 'liberado' WHERE registro_coleta_id = %(id)s",
                {"id": _uuid()},
            )
        return (
            "DELETE FROM nsi_operacional.claims WHERE registro_coleta_id = %(id)s",
            {"id": _uuid()},
        )

    if tabela == "eventos_claim":
        if operacao == "INSERT":
            return (
                "INSERT INTO nsi_operacional.eventos_claim "
                "(evento_id, aggregate_type, aggregate_id, aggregate_version, tipo, claim_id, executado_por, payload) "
                "VALUES (%(evento_id)s, 'claim', %(aggregate_id)s, 1, 'claim_criado', %(claim_id)s, %(executado_por)s, %(payload)s)",
                {
                    "evento_id": _uuid(), "aggregate_id": _uuid(), "claim_id": _uuid(),
                    "executado_por": _EXECUTADO_POR, "payload": _PAYLOAD_VAZIO,
                },
            )
        if operacao == "UPDATE":
            return (
                "UPDATE nsi_operacional.eventos_claim SET payload = %(payload)s WHERE evento_id = %(id)s",
                {"payload": _PAYLOAD_VAZIO, "id": _uuid()},
            )
        return (
            "DELETE FROM nsi_operacional.eventos_claim WHERE evento_id = %(id)s",
            {"id": _uuid()},
        )

    # comandos_idempotentes
    if operacao == "INSERT":
        return (
            "INSERT INTO nsi_operacional.comandos_idempotentes "
            "(comando, aggregate_id, chave_idempotencia, payload_hash) "
            "VALUES ('criar_claim', %(aggregate_id)s, %(chave)s, %(hash)s)",
            {"aggregate_id": _uuid(), "chave": "chave-permissao-teste", "hash": _hash_valido()},
        )
    if operacao == "UPDATE":
        return (
            "UPDATE nsi_operacional.comandos_idempotentes SET estado_processamento = 'processando' "
            "WHERE comando = 'criar_claim' AND aggregate_id = %(id)s AND chave_idempotencia = 'chave-permissao-teste'",
            {"id": _uuid()},
        )
    return (
        "DELETE FROM nsi_operacional.comandos_idempotentes "
        "WHERE comando = 'criar_claim' AND aggregate_id = %(id)s AND chave_idempotencia = 'chave-permissao-teste'",
        {"id": _uuid()},
    )


@pytest.mark.parametrize("operacao", OPERACOES_DML)
@pytest.mark.parametrize("tabela", TABELAS_DE_NEGOCIO)
@pytest.mark.parametrize("papel", PAPEIS_FUNCIONAIS)
def test_role_funcional_recebe_permission_denied_real(papel, tabela, operacao):
    """As 27 combinacoes (3 roles x 3 tabelas x 3 operacoes) exigidas
    nesta rodada - operacao real, nunca so inspecao de ACL."""
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
        # Confirma ausencia de padrao de DSN na mensagem de erro do
        # servidor, SEM jamais interpolar essa mensagem na falha do
        # proprio teste (mensagem fixa) - protege contra o teste de
        # seguranca se tornar ele mesmo o vazamento.
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
    """A URL e obtida internamente, nunca como parametro nomeado da
    funcao de teste; o assert compara apenas a representacao JA
    MASCARADA, nunca a DSN bruta."""
    url = request.getfixturevalue("url_banco_teste")
    representacao_segura = mascarar_dsn(url)
    assert "@" not in representacao_segura
    assert "://" not in representacao_segura
