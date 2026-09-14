# -*- coding: utf-8 -*-
"""
NSI - tests/integration/test_idempotencia_e_permissoes_b3_3.py
(Sprint B, B3.3 - ADR-008)

Testes de integracao REAIS contra PostgreSQL, exclusivamente contra
nsi_test, cobrindo o que atravessa as seis funcoes SECURITY DEFINER da
migration 0003: idempotencia sobrevivendo a reinicio de processo,
session_user vs. current_user, app.worker_id como rotulo nao
autorizante, e a matriz completa de GRANT/REVOKE EXECUTE (positiva e
negativa), por SQLSTATE real - nunca apenas inspecao de ACL.

DIVULGACAO DE RESIDUO INTENCIONAL: test_idempotencia_sobrevive_a_
reinicio_de_processo exige um COMMIT real - e a propria garantia sendo
provada (persistencia sobrevivendo a reinicio de processo/reconexao) so
existe se os dados estiverem genuinamente commitados; uma segunda
conexao so pode ver o que a primeira realmente persistiu. Inventario
exato do residuo permanente deixado por esse teste em nsi_test:
**1 linha em claims + 1 linha em eventos_claim ('claim_criado') + 1
linha em comandos_idempotentes (o recibo de 'criar_claim')** - a linha
de claims tambem NAO pode ser removida (eventos_claim.aggregate_id
referencia claims.registro_coleta_id por FK nao diferivel; enquanto o
evento existir - e ele e permanente - a linha de claims fica presa).
Unica excecao deliberada, junto com o equivalente em
test_fn_revisao_e_reatribuicao.py, a disciplina de 'sem residuos' deste
conjunto de arquivos. A limpeza deste teste verifica essa condicao antes
de tentar qualquer DELETE - nunca tenta remover a linha de claims quando
um evento ainda a referencia, reconhecendo o residuo como intencional em
vez de falhar por violacao de chave estrangeira.

Nenhum teste chama pytest nem executa a suite completa internamente.
"""
import hashlib
import json
import uuid

import psycopg
import pytest

from config import resolver_url_banco_papel

pytestmark = pytest.mark.pg_integration


def _uuid() -> str:
    return str(uuid.uuid4())


def _hash_valido(rotulo: str = "token-de-teste") -> str:
    return hashlib.sha256(rotulo.encode()).hexdigest()


def _payload_hash(**campos) -> str:
    return hashlib.sha256(json.dumps(campos, sort_keys=True).encode()).hexdigest()


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


# ============================================================
# Idempotencia sobrevivendo a reinicio de processo (nova conexao)
# ============================================================

def test_idempotencia_sobrevive_a_reinicio_de_processo(request):
    url_aplicacao = resolver_url_banco_papel("nsi_aplicacao", "test")
    registro_coleta_id = _uuid()
    token_hash = _hash_valido()
    chave = "chave-reinicio-processo"
    payload = _payload_hash(registro_coleta_id=registro_coleta_id, token_hash=token_hash)

    conn_1 = psycopg.connect(url_aplicacao)
    try:
        cur_1 = conn_1.cursor()
        cur_1.execute(
            "SELECT nsi_operacional.fn_criar_claim(%s, %s, %s, %s)",
            (registro_coleta_id, token_hash, chave, payload),
        )
        resultado_1 = cur_1.fetchone()[0]
        assert resultado_1["sucesso"] is True
        conn_1.commit()
    finally:
        conn_1.close()

    try:
        # nova conexao - simula reinicio de processo; nenhum estado Python
        # sobrevive entre conn_1 e conn_2, so o que esta persistido no banco.
        conn_2 = psycopg.connect(url_aplicacao)
        try:
            cur_2 = conn_2.cursor()
            cur_2.execute(
                "SELECT nsi_operacional.fn_criar_claim(%s, %s, %s, %s)",
                (registro_coleta_id, token_hash, chave, payload),
            )
            resultado_2 = cur_2.fetchone()[0]
            assert resultado_2 == resultado_1
            conn_2.rollback()  # replay puro - nao escreve nada, nada a commitar
        finally:
            conn_2.close()

        url_owner = request.getfixturevalue("url_banco_teste")
        conn_owner = psycopg.connect(url_owner)
        try:
            cur_owner = conn_owner.cursor()
            cur_owner.execute("SET LOCAL ROLE nsi_eventos_owner")
            cur_owner.execute(
                "SELECT count(*) FROM nsi_operacional.eventos_claim WHERE aggregate_id = %s",
                (registro_coleta_id,),
            )
            assert cur_owner.fetchone()[0] == 1  # so o evento da primeira chamada
        finally:
            conn_owner.rollback()
            conn_owner.close()
    finally:
        conn_cleanup = psycopg.connect(request.getfixturevalue("url_banco_teste"))
        try:
            cur_cleanup = conn_cleanup.cursor()
            cur_cleanup.execute("SET LOCAL ROLE nsi_eventos_owner")
            cur_cleanup.execute(
                "SELECT EXISTS (SELECT 1 FROM nsi_operacional.eventos_claim WHERE aggregate_id = %s)",
                (registro_coleta_id,),
            )
            tem_evento_referenciando = cur_cleanup.fetchone()[0]
            if not tem_evento_referenciando:
                cur_cleanup.execute(
                    "DELETE FROM nsi_operacional.claims WHERE registro_coleta_id = %s", (registro_coleta_id,)
                )
                conn_cleanup.commit()
            else:
                # RESIDUO PERMANENTE E INEVITAVEL, por desenho: eventos_claim
                # e imutavel (mesmo para o owner) e referencia esta linha de
                # claims via FK nao diferivel - nunca tratado como falha
                # deste teste (ver docstring do modulo).
                conn_cleanup.rollback()
        finally:
            conn_cleanup.close()


# ============================================================
# session_user (nunca current_user) e app.worker_id como rotulo
# ============================================================

def test_session_user_correto_nunca_current_user(cur):
    cur.execute("SAVEPOINT sp")
    try:
        registro_coleta_id = _uuid()
        token_hash = _hash_valido()
        payload = _payload_hash(registro_coleta_id=registro_coleta_id, token_hash=token_hash)
        cur.execute(
            "SELECT nsi_operacional.fn_criar_claim(%s, %s, %s, %s)",
            (registro_coleta_id, token_hash, "chave-su", payload),
        )
        assert cur.fetchone()[0]["sucesso"] is True

        cur.execute(
            "SELECT executado_por FROM nsi_operacional.eventos_claim "
            "WHERE aggregate_id = %s AND tipo = 'claim_criado'",
            (registro_coleta_id,),
        )
        executado_por = cur.fetchone()[0]
        assert executado_por["role"] == "nsi_test_migrator"  # session_user - identidade REAL do chamador
        assert executado_por["role"] != "nsi_eventos_owner"  # nunca current_user (owner durante SECURITY DEFINER)
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_worker_id_forjado_nao_concede_privilegio():
    """nsi_expiracao NAO tem EXECUTE em fn_criar_claim - declarar
    app.worker_id='nsi_aplicacao' (mentiroso) nunca contorna o GRANT
    real, que depende exclusivamente de session_user/pertencimento de
    role."""
    url = resolver_url_banco_papel("nsi_expiracao", "test")
    conn = psycopg.connect(url)
    try:
        cur = conn.cursor()
        cur.execute("SET LOCAL app.worker_id = 'nsi_aplicacao'")
        registro_coleta_id = _uuid()
        token_hash = _hash_valido()
        payload = _payload_hash(registro_coleta_id=registro_coleta_id, token_hash=token_hash)
        with pytest.raises(psycopg.errors.InsufficientPrivilege) as exc_info:
            cur.execute(
                "SELECT nsi_operacional.fn_criar_claim(%s, %s, %s, %s)",
                (registro_coleta_id, token_hash, "chave-forjado", payload),
            )
        assert exc_info.value.sqlstate == "42501"
    finally:
        conn.rollback()
        conn.close()


def test_worker_id_e_apenas_rotulo_informativo_para_quem_tem_privilegio():
    url = resolver_url_banco_papel("nsi_aplicacao", "test")
    conn = psycopg.connect(url)
    try:
        cur = conn.cursor()
        cur.execute("SET LOCAL app.worker_id = 'qualquer-rotulo-nao-verificado'")
        registro_coleta_id = _uuid()
        token_hash = _hash_valido()
        payload = _payload_hash(registro_coleta_id=registro_coleta_id, token_hash=token_hash)
        cur.execute(
            "SELECT nsi_operacional.fn_criar_claim(%s, %s, %s, %s)",
            (registro_coleta_id, token_hash, "chave-rotulo", payload),
        )
        resultado = cur.fetchone()[0]
        assert resultado["sucesso"] is True  # o rotulo e so informativo - nunca bloqueia nem altera autorizacao real
    finally:
        conn.rollback()
        conn.close()


# ============================================================
# Matriz completa de GRANT/REVOKE EXECUTE - por SQLSTATE real
# ============================================================

def _chamada_minima(nome_funcao: str):
    rid = _uuid()
    th = _hash_valido()
    if nome_funcao == "fn_criar_claim":
        return ("SELECT nsi_operacional.fn_criar_claim(%s, %s, %s, %s)",
                (rid, th, "chave-matriz", _hash_valido("p")))
    if nome_funcao == "fn_registrar_heartbeat":
        return ("SELECT nsi_operacional.fn_registrar_heartbeat(%s, %s, %s, %s, %s)",
                (rid, _uuid(), th, "chave-matriz", _hash_valido("p")))
    if nome_funcao == "fn_liberar_claim":
        return ("SELECT nsi_operacional.fn_liberar_claim(%s, %s, %s, %s, %s)",
                (rid, _uuid(), th, "chave-matriz", _hash_valido("p")))
    if nome_funcao == "fn_materializar_expiracao":
        return ("SELECT nsi_operacional.fn_materializar_expiracao(%s)", (rid,))
    if nome_funcao == "fn_registrar_revisao_abandono":
        return ("SELECT nsi_operacional.fn_registrar_revisao_abandono(%s, %s, %s, %s, %s)",
                (rid, "nao_reatribuir", "motivo", "chave-matriz", _hash_valido("p")))
    if nome_funcao == "fn_reatribuir_claim":
        return ("SELECT nsi_operacional.fn_reatribuir_claim(%s, %s, %s, %s, %s)",
                (rid, _uuid(), th, "chave-matriz", _hash_valido("p")))
    raise ValueError(nome_funcao)


_MATRIZ_PERMITIDA = [
    ("nsi_aplicacao", "fn_criar_claim"),
    ("nsi_aplicacao", "fn_registrar_heartbeat"),
    ("nsi_aplicacao", "fn_liberar_claim"),
    ("nsi_aplicacao", "fn_materializar_expiracao"),
    ("nsi_expiracao", "fn_materializar_expiracao"),
    ("nsi_operador_restrito", "fn_registrar_revisao_abandono"),
    ("nsi_operador_restrito", "fn_reatribuir_claim"),
]

_MATRIZ_NEGADA = [
    ("nsi_expiracao", "fn_criar_claim"),
    ("nsi_operador_restrito", "fn_criar_claim"),
    ("nsi_expiracao", "fn_registrar_heartbeat"),
    ("nsi_operador_restrito", "fn_registrar_heartbeat"),
    ("nsi_expiracao", "fn_liberar_claim"),
    ("nsi_operador_restrito", "fn_liberar_claim"),
    ("nsi_operador_restrito", "fn_materializar_expiracao"),
    ("nsi_aplicacao", "fn_registrar_revisao_abandono"),
    ("nsi_expiracao", "fn_registrar_revisao_abandono"),
    ("nsi_aplicacao", "fn_reatribuir_claim"),
    ("nsi_expiracao", "fn_reatribuir_claim"),
]


@pytest.mark.parametrize("papel,funcao", _MATRIZ_PERMITIDA)
def test_execute_permitido_conforme_matriz(papel, funcao):
    sql, params = _chamada_minima(funcao)
    url = resolver_url_banco_papel(papel, "test")
    conn = psycopg.connect(url)
    try:
        cur = conn.cursor()
        cur.execute(sql, params)  # nunca deve levantar InsufficientPrivilege
        resultado = cur.fetchone()[0]
        assert isinstance(resultado, dict)
        for chave_proibida in ("token", "token_bruto", "token_hash", "token_hash_novo", "payload_hash", "dsn"):
            assert chave_proibida not in resultado
    finally:
        conn.rollback()
        conn.close()


@pytest.mark.parametrize("papel,funcao", _MATRIZ_NEGADA)
def test_execute_negado_fora_da_matriz(papel, funcao):
    sql, params = _chamada_minima(funcao)
    url = resolver_url_banco_papel(papel, "test")
    conn = psycopg.connect(url)
    try:
        cur = conn.cursor()
        with pytest.raises(psycopg.errors.InsufficientPrivilege) as exc_info:
            cur.execute(sql, params)
        assert exc_info.value.sqlstate == "42501"
    finally:
        conn.rollback()
        conn.close()


# ============================================================
# Nenhum segredo no recibo persistido
# ============================================================

def test_recibo_persistido_nunca_contem_segredo(cur):
    cur.execute("SAVEPOINT sp")
    try:
        registro_coleta_id = _uuid()
        token_hash = _hash_valido()
        chave = "chave-recibo"
        payload = _payload_hash(registro_coleta_id=registro_coleta_id, token_hash=token_hash)
        cur.execute(
            "SELECT nsi_operacional.fn_criar_claim(%s, %s, %s, %s)",
            (registro_coleta_id, token_hash, chave, payload),
        )
        assert cur.fetchone()[0]["sucesso"] is True

        cur.execute(
            "SELECT resultado FROM nsi_operacional.comandos_idempotentes "
            "WHERE comando = 'criar_claim' AND aggregate_id = %s AND chave_idempotencia = %s",
            (registro_coleta_id, chave),
        )
        resultado_persistido = cur.fetchone()[0]

        proibidas = {"token", "token_bruto", "token_hash", "token_hash_novo", "payload_hash",
                     "chave", "chave_idempotencia", "dsn"}
        assert not (set(resultado_persistido.keys()) & proibidas)
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")
