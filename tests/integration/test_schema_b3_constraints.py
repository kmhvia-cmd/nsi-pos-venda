# -*- coding: utf-8 -*-
"""
NSI - tests/integration/test_schema_b3_constraints.py
(Sprint B, B3.2 - ADR-008, Parte 1 da B3)

Testes de integracao REAIS contra PostgreSQL, exclusivamente contra
nsi_test, das CHECK constraints das tres tabelas criadas pela migration
0002 (nsi_operacional.claims, nsi_operacional.eventos_claim,
nsi_operacional.comandos_idempotentes) - cada uma testada nos dois
sentidos (valor valido aceito, valor invalido rejeitado com
CheckViolation / SQLSTATE 23514).

Como nenhuma role funcional tem qualquer privilegio DML direto nas tres
tabelas (REVOKE ALL explicito na propria migration 0002) e as seis
funcoes SECURITY DEFINER ainda nao existem (B3.3), todo INSERT deste
arquivo roda com a conexao do migrator apos 'SET LOCAL ROLE
nsi_eventos_owner' (a mesma role que a migration usa para criar os
objetos) - nunca commitado: cada tentativa roda dentro de um SAVEPOINT
proprio, revertido logo em seguida (ROLLBACK TO SAVEPOINT), e a
transacao externa e sempre revertida ao final do teste (fixture). nsi_test
nunca fica com residuo de dados de teste.

Este arquivo pressupoe a migration 0002 ja aplicada em nsi_test (upgrade
0002) - roda como parte do ciclo de testes descrito em
test_migration_0002_upgrade_downgrade.py, nunca isoladamente contra um
banco ainda em 0001.

Nenhum teste deste arquivo chama pytest nem executa a suite completa
internamente.
"""
import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import psycopg
import pytest

pytestmark = pytest.mark.pg_integration


def _hash_valido(rotulo: str = "valor-de-teste") -> str:
    return hashlib.sha256(rotulo.encode()).hexdigest()


def _uuid() -> str:
    return str(uuid.uuid4())


def _concluido_em_coerente() -> str:
    """
    'criado_em' de comandos_idempotentes nunca e passado explicitamente
    nestes testes - usa o DEFAULT now() da coluna, avaliado no instante
    real do INSERT. Um literal fixo no passado (ex.: um ano anterior ao
    de qualquer execucao real) violaria genuinamente
    ck_comandos_idempotentes_concluido_apos_criado (concluido_em >=
    criado_em) - nao seria um caso 'valido', seria dado de teste
    incoerente com a propria premissa do CHECK. Esta funcao devolve um
    instante sempre posterior ao 'now()' real, em qualquer data de
    execucao.
    """
    return (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat()


@pytest.fixture
def cur(request):
    """
    Conexao real contra nsi_test, com uma unica transacao externa aberta
    durante todo o teste e 'SET LOCAL ROLE nsi_eventos_owner' ja ativo -
    escopo da propria transacao, nunca persiste alem dela. A transacao
    externa e SEMPRE revertida no teardown, commitada nunca.

    A URL e obtida internamente via request.getfixturevalue(), nunca como
    parametro nomeado desta fixture - se a conexao falhar, o erro de setup
    do pytest nunca exibe a DSN no cabecalho (correcao de seguranca desta
    rodada).
    """
    url = request.getfixturevalue("url_banco_teste")
    conn = psycopg.connect(url)
    try:
        cursor = conn.cursor()
        cursor.execute("SET LOCAL ROLE nsi_eventos_owner")
        yield cursor
    finally:
        conn.rollback()
        conn.close()


def _aceita(cur, sql: str, params: dict) -> None:
    """Executa dentro de um SAVEPOINT - espera sucesso; sempre desfaz o
    efeito (ROLLBACK TO SAVEPOINT), nunca deixa a linha persistida além
    do próprio teste."""
    cur.execute("SAVEPOINT sp_teste")
    try:
        cur.execute(sql, params)
    except Exception as exc:
        cur.execute("ROLLBACK TO SAVEPOINT sp_teste")
        pytest.fail(f"Esperado sucesso, mas falhou: {exc!r}")
    else:
        cur.execute("ROLLBACK TO SAVEPOINT sp_teste")


def _rejeita(cur, sql: str, params: dict, sqlstate_esperado: str = "23514") -> None:
    """Executa dentro de um SAVEPOINT - espera CheckViolation (23514);
    sempre desfaz (ROLLBACK TO SAVEPOINT) mesmo em caso de falha
    inesperada do teste."""
    cur.execute("SAVEPOINT sp_teste")
    try:
        with pytest.raises(psycopg.errors.CheckViolation) as exc_info:
            cur.execute(sql, params)
        assert exc_info.value.sqlstate == sqlstate_esperado
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp_teste")


# ============================================================
# nsi_operacional.claims
# ============================================================

_SQL_INSERT_CLAIM = """
    INSERT INTO nsi_operacional.claims
        (registro_coleta_id, claim_id, token_hash, estado, criado_em, expira_em,
         ultimo_heartbeat_em, versao_atual, revisao_atual_id, revisao_decisao, revisao_registrada_em)
    VALUES
        (%(registro_coleta_id)s, %(claim_id)s, %(token_hash)s, %(estado)s,
         now() + %(deslocamento_criado)s::interval, now() + %(deslocamento_expira)s::interval,
         %(heartbeat)s, %(versao_atual)s, %(revisao_atual_id)s, %(revisao_decisao)s, %(revisao_registrada_em)s)
"""


def _params_claim_validos(**overrides) -> dict:
    base = dict(
        registro_coleta_id=_uuid(),
        claim_id=_uuid(),
        token_hash=_hash_valido(),
        estado="ativo",
        deslocamento_criado="-1 minute",
        deslocamento_expira="4 minutes",
        heartbeat=None,
        versao_atual=1,
        revisao_atual_id=None,
        revisao_decisao=None,
        revisao_registrada_em=None,
    )
    base.update(overrides)
    return base


def test_claims_token_hash_valido_aceito(cur):
    _aceita(cur, _SQL_INSERT_CLAIM, _params_claim_validos())


def test_claims_token_hash_maiusculo_rejeitado(cur):
    _rejeita(cur, _SQL_INSERT_CLAIM, _params_claim_validos(token_hash="A" * 64))


def test_claims_token_hash_tamanho_errado_rejeitado(cur):
    _rejeita(cur, _SQL_INSERT_CLAIM, _params_claim_validos(token_hash="abc123"))


@pytest.mark.parametrize("estado", ["ativo", "liberado", "expirado_pendente_revisao"])
def test_claims_estado_valido_aceito(cur, estado):
    extra = {}
    if estado == "expirado_pendente_revisao":
        pass  # sem revisao preenchida tambem e valido (revisao e opcional)
    _aceita(cur, _SQL_INSERT_CLAIM, _params_claim_validos(estado=estado, **extra))


def test_claims_estado_invalido_rejeitado(cur):
    _rejeita(cur, _SQL_INSERT_CLAIM, _params_claim_validos(estado="cancelado"))


def test_claims_versao_atual_positiva_aceita(cur):
    _aceita(cur, _SQL_INSERT_CLAIM, _params_claim_validos(versao_atual=1))


def test_claims_versao_atual_zero_rejeitada(cur):
    _rejeita(cur, _SQL_INSERT_CLAIM, _params_claim_validos(versao_atual=0))


def test_claims_versao_atual_negativa_rejeitada(cur):
    _rejeita(cur, _SQL_INSERT_CLAIM, _params_claim_validos(versao_atual=-1))


@pytest.mark.parametrize("decisao", ["reatribuir", "nao_reatribuir"])
def test_claims_revisao_decisao_valida_aceita(cur, decisao):
    _aceita(cur, _SQL_INSERT_CLAIM, _params_claim_validos(
        estado="expirado_pendente_revisao",
        revisao_atual_id=_uuid(), revisao_decisao=decisao,
        revisao_registrada_em="2026-01-01T00:00:00+00:00",
    ))


def test_claims_revisao_decisao_invalida_rejeitada(cur):
    _rejeita(cur, _SQL_INSERT_CLAIM, _params_claim_validos(
        estado="expirado_pendente_revisao",
        revisao_atual_id=_uuid(), revisao_decisao="talvez",
        revisao_registrada_em="2026-01-01T00:00:00+00:00",
    ))


def test_claims_expira_apos_criado_aceito(cur):
    _aceita(cur, _SQL_INSERT_CLAIM, _params_claim_validos(
        deslocamento_criado="0 seconds", deslocamento_expira="5 minutes",
    ))


def test_claims_expira_igual_criado_rejeitado(cur):
    _rejeita(cur, _SQL_INSERT_CLAIM, _params_claim_validos(
        deslocamento_criado="0 seconds", deslocamento_expira="0 seconds",
    ))


def test_claims_expira_antes_de_criado_rejeitado(cur):
    _rejeita(cur, _SQL_INSERT_CLAIM, _params_claim_validos(
        deslocamento_criado="0 seconds", deslocamento_expira="-1 minute",
    ))


def test_claims_heartbeat_nulo_aceito(cur):
    _aceita(cur, _SQL_INSERT_CLAIM, _params_claim_validos(heartbeat=None))


def test_claims_heartbeat_dentro_da_janela_aceito(cur):
    cur.execute("SAVEPOINT sp_hb")
    try:
        params = _params_claim_validos(deslocamento_criado="-2 minutes", deslocamento_expira="3 minutes")
        sql = _SQL_INSERT_CLAIM.replace("%(heartbeat)s", "now() - interval '1 minute'")
        cur.execute(sql, {k: v for k, v in params.items() if k != "heartbeat"})
    except Exception as exc:
        cur.execute("ROLLBACK TO SAVEPOINT sp_hb")
        pytest.fail(f"Esperado sucesso, mas falhou: {exc!r}")
    else:
        cur.execute("ROLLBACK TO SAVEPOINT sp_hb")


def test_claims_heartbeat_antes_de_criado_rejeitado(cur):
    cur.execute("SAVEPOINT sp_hb2")
    try:
        params = _params_claim_validos(deslocamento_criado="-1 minute", deslocamento_expira="4 minutes")
        sql = _SQL_INSERT_CLAIM.replace("%(heartbeat)s", "now() - interval '5 minutes'")
        with pytest.raises(psycopg.errors.CheckViolation) as exc_info:
            cur.execute(sql, {k: v for k, v in params.items() if k != "heartbeat"})
        assert exc_info.value.sqlstate == "23514"
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp_hb2")


def test_claims_heartbeat_na_ou_apos_expiracao_rejeitado(cur):
    cur.execute("SAVEPOINT sp_hb3")
    try:
        params = _params_claim_validos(deslocamento_criado="-1 minute", deslocamento_expira="1 minute")
        sql = _SQL_INSERT_CLAIM.replace("%(heartbeat)s", "now() + interval '1 minute'")
        with pytest.raises(psycopg.errors.CheckViolation) as exc_info:
            cur.execute(sql, {k: v for k, v in params.items() if k != "heartbeat"})
        assert exc_info.value.sqlstate == "23514"
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp_hb3")


def test_claims_revisao_totalmente_vazia_aceita(cur):
    _aceita(cur, _SQL_INSERT_CLAIM, _params_claim_validos(
        revisao_atual_id=None, revisao_decisao=None, revisao_registrada_em=None,
    ))


def test_claims_revisao_parcial_rejeitada(cur):
    _rejeita(cur, _SQL_INSERT_CLAIM, _params_claim_validos(
        estado="expirado_pendente_revisao",
        revisao_atual_id=_uuid(), revisao_decisao=None, revisao_registrada_em=None,
    ))


def test_claims_revisao_fora_de_pendente_revisao_rejeitada(cur):
    _rejeita(cur, _SQL_INSERT_CLAIM, _params_claim_validos(
        estado="ativo",
        revisao_atual_id=_uuid(), revisao_decisao="reatribuir",
        revisao_registrada_em="2026-01-01T00:00:00+00:00",
    ))


# ============================================================
# nsi_operacional.eventos_claim - depende de uma linha valida em claims
# (FK simples) inserida na mesma transacao/savepoint.
# ============================================================

_SQL_INSERT_CLAIM_SIMPLES = """
    INSERT INTO nsi_operacional.claims
        (registro_coleta_id, claim_id, token_hash, estado, criado_em, expira_em, versao_atual)
    VALUES (%(registro_coleta_id)s, %(claim_id)s, %(token_hash)s, 'ativo', now(), now() + interval '5 minutes', 1)
"""

_SQL_INSERT_EVENTO = """
    INSERT INTO nsi_operacional.eventos_claim
        (evento_id, aggregate_type, aggregate_id, aggregate_version, tipo, claim_id, executado_por, payload)
    VALUES
        (%(evento_id)s, %(aggregate_type)s, %(aggregate_id)s, %(aggregate_version)s, %(tipo)s,
         %(claim_id)s, %(executado_por)s, %(payload)s)
"""


def _params_evento_validos(aggregate_id: str, **overrides) -> dict:
    base = dict(
        evento_id=_uuid(),
        aggregate_type="claim",
        aggregate_id=aggregate_id,
        aggregate_version=1,
        tipo="claim_criado",
        claim_id=_uuid(),
        executado_por=psycopg.types.json.Jsonb({"role": "nsi_test_migrator"}),
        payload=psycopg.types.json.Jsonb({}),
    )
    base.update(overrides)
    return base


def _com_claim_e_evento(cur, params_evento_overrides=None, esperar_sucesso=True, sqlstate_esperado="23514"):
    registro_coleta_id = _uuid()
    cur.execute("SAVEPOINT sp_evt")
    try:
        cur.execute(_SQL_INSERT_CLAIM_SIMPLES, dict(
            registro_coleta_id=registro_coleta_id, claim_id=_uuid(), token_hash=_hash_valido(),
        ))
        params = _params_evento_validos(registro_coleta_id, **(params_evento_overrides or {}))
        if esperar_sucesso:
            cur.execute(_SQL_INSERT_EVENTO, params)
        else:
            with pytest.raises(psycopg.errors.CheckViolation) as exc_info:
                cur.execute(_SQL_INSERT_EVENTO, params)
            assert exc_info.value.sqlstate == sqlstate_esperado
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp_evt")


def test_eventos_claim_aggregate_type_correto_aceito(cur):
    _com_claim_e_evento(cur, {"aggregate_type": "claim"}, esperar_sucesso=True)


def test_eventos_claim_aggregate_type_incorreto_rejeitado(cur):
    _com_claim_e_evento(cur, {"aggregate_type": "outro"}, esperar_sucesso=False)


def test_eventos_claim_aggregate_version_positiva_aceita(cur):
    _com_claim_e_evento(cur, {"aggregate_version": 1}, esperar_sucesso=True)


def test_eventos_claim_aggregate_version_zero_rejeitada(cur):
    _com_claim_e_evento(cur, {"aggregate_version": 0}, esperar_sucesso=False)


@pytest.mark.parametrize("tipo", [
    "claim_criado", "heartbeat_registrado", "claim_liberado",
    "claim_expirado", "revisao_de_abandono_registrada", "claim_reatribuido",
])
def test_eventos_claim_tipo_valido_aceito(cur, tipo):
    _com_claim_e_evento(cur, {"tipo": tipo}, esperar_sucesso=True)


def test_eventos_claim_tipo_invalido_rejeitado(cur):
    _com_claim_e_evento(cur, {"tipo": "evento_inventado"}, esperar_sucesso=False)


# ============================================================
# nsi_operacional.comandos_idempotentes
# ============================================================

_SQL_INSERT_COMANDO = """
    INSERT INTO nsi_operacional.comandos_idempotentes
        (comando, aggregate_id, chave_idempotencia, payload_hash, estado_processamento, resultado, concluido_em)
    VALUES
        (%(comando)s, %(aggregate_id)s, %(chave_idempotencia)s, %(payload_hash)s,
         %(estado_processamento)s, %(resultado)s, %(concluido_em)s)
"""


def _params_comando_validos(**overrides) -> dict:
    base = dict(
        comando="criar_claim",
        aggregate_id=_uuid(),
        chave_idempotencia="chave-de-teste-001",
        payload_hash=_hash_valido("payload"),
        estado_processamento="processando",
        resultado=None,
        concluido_em=None,
    )
    base.update(overrides)
    return base


def _testar_comando(cur, params, esperar_sucesso, sqlstate_esperado="23514"):
    cur.execute("SAVEPOINT sp_cmd")
    try:
        if esperar_sucesso:
            cur.execute(_SQL_INSERT_COMANDO, params)
        else:
            with pytest.raises(psycopg.errors.CheckViolation) as exc_info:
                cur.execute(_SQL_INSERT_COMANDO, params)
            assert exc_info.value.sqlstate == sqlstate_esperado
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp_cmd")


@pytest.mark.parametrize("comando", [
    "criar_claim", "registrar_heartbeat", "liberar_claim",
    "registrar_revisao_abandono", "reatribuir_claim",
])
def test_comandos_idempotentes_comando_valido_aceito(cur, comando):
    _testar_comando(cur, _params_comando_validos(comando=comando), esperar_sucesso=True)


def test_comandos_idempotentes_comando_invalido_rejeitado(cur):
    _testar_comando(cur, _params_comando_validos(comando="comando_inventado"), esperar_sucesso=False)


def test_comandos_idempotentes_chave_tamanho_minimo_aceito(cur):
    _testar_comando(cur, _params_comando_validos(chave_idempotencia="x"), esperar_sucesso=True)


def test_comandos_idempotentes_chave_tamanho_maximo_aceito(cur):
    _testar_comando(cur, _params_comando_validos(chave_idempotencia="x" * 200), esperar_sucesso=True)


def test_comandos_idempotentes_chave_vazia_rejeitada(cur):
    _testar_comando(cur, _params_comando_validos(chave_idempotencia=""), esperar_sucesso=False)


def test_comandos_idempotentes_chave_muito_longa_rejeitada(cur):
    _testar_comando(cur, _params_comando_validos(chave_idempotencia="x" * 201), esperar_sucesso=False)


def test_comandos_idempotentes_payload_hash_valido_aceito(cur):
    _testar_comando(cur, _params_comando_validos(payload_hash=_hash_valido("outro")), esperar_sucesso=True)


def test_comandos_idempotentes_payload_hash_maiusculo_rejeitado(cur):
    _testar_comando(cur, _params_comando_validos(payload_hash="A" * 64), esperar_sucesso=False)


@pytest.mark.parametrize("estado", ["processando", "concluido"])
def test_comandos_idempotentes_estado_processamento_valido_aceito(cur, estado):
    if estado == "processando":
        params = _params_comando_validos(estado_processamento="processando", resultado=None, concluido_em=None)
    else:
        params = _params_comando_validos(
            estado_processamento="concluido",
            resultado=psycopg.types.json.Jsonb({"ok": True}),
            concluido_em=_concluido_em_coerente(),
        )
    _testar_comando(cur, params, esperar_sucesso=True)


def test_comandos_idempotentes_estado_processamento_invalido_rejeitado(cur):
    _testar_comando(cur, _params_comando_validos(estado_processamento="cancelado"), esperar_sucesso=False)


def test_comandos_idempotentes_processando_com_resultado_rejeitado(cur):
    _testar_comando(cur, _params_comando_validos(
        estado_processamento="processando",
        resultado=psycopg.types.json.Jsonb({"nao": "deveria"}),
        concluido_em=None,
    ), esperar_sucesso=False)


def test_comandos_idempotentes_concluido_sem_resultado_rejeitado(cur):
    """Isola exclusivamente a violacao de 'concluido sem resultado' -
    concluido_em coerente com criado_em, para nao se confundir com
    ck_comandos_idempotentes_concluido_apos_criado."""
    _testar_comando(cur, _params_comando_validos(
        estado_processamento="concluido", resultado=None, concluido_em=_concluido_em_coerente(),
    ), esperar_sucesso=False)


def test_comandos_idempotentes_concluido_antes_de_criado_rejeitado(cur):
    cur.execute("SAVEPOINT sp_data")
    try:
        params = _params_comando_validos(
            estado_processamento="concluido",
            resultado=psycopg.types.json.Jsonb({"ok": True}),
        )
        sql = _SQL_INSERT_COMANDO.replace("%(concluido_em)s", "now() - interval '1 day'")
        with pytest.raises(psycopg.errors.CheckViolation) as exc_info:
            cur.execute(sql, {k: v for k, v in params.items() if k != "concluido_em"})
        assert exc_info.value.sqlstate == "23514"
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp_data")
