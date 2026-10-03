# -*- coding: utf-8 -*-
"""
NSI - tests/integration/test_fn_registrar_correcao.py
(Sprint B, B4.3 - ADR-009, Secao 6.4)

Testes de integracao REAIS contra PostgreSQL, exclusivamente contra
nsi_test, de nsi_operacional.fn_registrar_correcao (migration 0005) -
evento 'correcao_registrada'.

Ordem de decisao da Sprint A3 (core/scheduler.py::processar_uma_correcao):
registro ja valido -> recusada_ja_valido; now() >= horario conceitual ou
lote fora de 'aguardando_d8' -> recusada_tardia; senao aplicada_valida /
aplicada_ainda_invalida. Fronteira sem espera real: deslocamento temporal
do lote na mesma transacao da chamada (ver test_fn_registrar_congelamento).

Conexao primaria: migrator ('SET LOCAL ROLE nsi_eventos_owner'), em
transacao revertida no teardown - nenhum residuo.

Concorrencia real (duas conexoes nsi_aplicacao, COMMIT real):
  - duas correcoes simultaneas ao mesmo registro - sem perda de
    atualizacao e com versoes sem lacuna;
  - correcao contra congelamento na fronteira - a correcao que comecou
    antes da fronteira mas esperou o bloqueio do lote enquanto o
    congelamento terminava e tardia pela regra do status. E o unico teste
    deste arquivo que depende de relogio real (cerca de 3 s, folga ampla
    para maquina carregada): a transacao da correcao precisa de fato
    comecar antes da fronteira - premissa afirmada pelo proprio teste.
DIVULGACAO DE RESIDUO INTENCIONAL: lotes, registros e eventos desses dois
testes permanecem como residuo sintetico em nsi_test; cada recibo criado
e removido explicitamente pela propria chave.

Nenhum valor pessoal e interpolado em mensagem de falha. Nenhum teste
chama pytest nem executa a suite completa internamente.
"""
import threading
import time

import psycopg
import pytest

from config import resolver_url_banco_papel
from core.payload_hash import hash_registrar_correcao, hash_registrar_tentativa_nao_resolvida
from tests.apoio_b4_3 import (
    aguardar_bloqueio,
    criar_lote,
    posicionar_fronteira,
    registro_invalido,
    registro_valido,
    uuid_texto,
)

pytestmark = pytest.mark.pg_integration

CORRECAO_VALIDA = ("Pessoa Corrigida", "5511977776666", "Produto Teste", True, None)
CORRECAO_AINDA_INVALIDA = (None, "5511966665555", "Produto Teste", False, ["nome_ausente"])


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


def _corrigir(cur, lote_id, registro_id, correcao, chave, payload_hash=None) -> dict:
    nome, whatsapp, produto, valido, motivos = correcao
    if payload_hash is None:
        payload_hash = hash_registrar_correcao(lote_id, registro_id, nome, whatsapp, produto, valido, motivos)
    cur.execute(
        "SELECT nsi_operacional.fn_registrar_correcao(%s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (lote_id, registro_id, nome, whatsapp, produto, valido, motivos, chave, payload_hash),
    )
    return cur.fetchone()[0]


def _registro(cur, registro_id):
    cur.execute(
        "SELECT nome, whatsapp, produto, valido, motivos_invalidez, numero_versao_dados, versao_eventos_atual "
        "FROM nsi_operacional.registros_coleta WHERE registro_coleta_id = %s",
        (registro_id,),
    )
    return cur.fetchone()


def _lote(cur, lote_id):
    cur.execute("SELECT total_valido, total_invalido, status, versao_eventos_atual "
                "FROM nsi_operacional.lotes WHERE lote_id = %s", (lote_id,))
    return cur.fetchone()


def _eventos_correcao(cur, registro_id):
    cur.execute(
        "SELECT aggregate_type, aggregate_version, resultado, numero_versao_dados, executado_por_login, "
        "occurred_at = now() FROM nsi_operacional.eventos_registro_coleta "
        "WHERE aggregate_id = %s ORDER BY aggregate_version",
        (registro_id,),
    )
    return cur.fetchall()


# ============================================================
# Aplicacao
# ============================================================

def test_aplicada_valida_ajusta_registro_totais_e_grava_evento(cur):
    cur.execute("SAVEPOINT sp")
    try:
        invalido = registro_invalido()
        lote_id = criar_lote(cur, [registro_valido(1), invalido])
        resultado = _corrigir(cur, lote_id, invalido["registro_coleta_id"], CORRECAO_VALIDA, "chave-aplicada-valida")

        assert resultado == {"sucesso": True, "resultado": "aplicada_valida", "numero_versao_dados": 2,
                             "versao_eventos": 1}
        registro = _registro(cur, invalido["registro_coleta_id"])
        if registro[:5] != CORRECAO_VALIDA:
            pytest.fail("Valores do registro nao foram sobrescritos pela correcao - mensagem fixa, sem valores.")
        assert registro[5:] == (2, 1)
        # totais ajustados, sem evento de lote e sem mudanca de status
        assert _lote(cur, lote_id) == (2, 0, "aguardando_d8", 1)
        assert _eventos_correcao(cur, invalido["registro_coleta_id"]) == [
            ("registro_coleta", 1, "aplicada_valida", 2, "nsi_test_migrator", True)]
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_aplicada_ainda_invalida_nao_mexe_nos_totais(cur):
    cur.execute("SAVEPOINT sp")
    try:
        invalido = registro_invalido()
        lote_id = criar_lote(cur, [invalido])
        resultado = _corrigir(cur, lote_id, invalido["registro_coleta_id"], CORRECAO_AINDA_INVALIDA, "chave-ainda-invalida")
        assert resultado == {"sucesso": True, "resultado": "aplicada_ainda_invalida", "numero_versao_dados": 2,
                             "versao_eventos": 1}
        registro = _registro(cur, invalido["registro_coleta_id"])
        if registro[:5] != CORRECAO_AINDA_INVALIDA:
            pytest.fail("Valores do registro nao foram sobrescritos pela correcao - mensagem fixa, sem valores.")
        assert _lote(cur, lote_id) == (0, 1, "aguardando_d8", 1)
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_um_microssegundo_antes_da_fronteira_ainda_e_aplicada(cur):
    cur.execute("SAVEPOINT sp")
    try:
        invalido = registro_invalido()
        lote_id = criar_lote(cur, [invalido])
        posicionar_fronteira(cur, lote_id, "1 microsecond")
        resultado = _corrigir(cur, lote_id, invalido["registro_coleta_id"], CORRECAO_VALIDA, "chave-antes-fronteira")
        assert resultado["resultado"] == "aplicada_valida"
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


# ============================================================
# Recusas com evento
# ============================================================

def test_registro_ja_valido_e_recusada_ja_valido(cur):
    cur.execute("SAVEPOINT sp")
    try:
        valido = registro_valido(1)
        lote_id = criar_lote(cur, [valido])
        antes = _registro(cur, valido["registro_coleta_id"])
        resultado = _corrigir(cur, lote_id, valido["registro_coleta_id"], CORRECAO_VALIDA, "chave-ja-valido")
        assert resultado == {"sucesso": False, "motivo": "recusada_ja_valido", "resultado": "recusada_ja_valido",
                             "versao_eventos": 1}
        depois = _registro(cur, valido["registro_coleta_id"])
        assert depois[:6] == antes[:6]  # nenhum valor, validade ou numero_versao_dados muda
        assert depois[6] == antes[6] + 1  # so a versao de eventos avanca
        assert _eventos_correcao(cur, valido["registro_coleta_id"]) == [
            ("registro_coleta", 1, "recusada_ja_valido", None, "nsi_test_migrator", True)]
        assert _lote(cur, lote_id) == (1, 0, "aguardando_d8", 1)
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


@pytest.mark.parametrize("deslocamento", ["0 seconds", "-1 microsecond"])
def test_exatamente_na_fronteira_ou_depois_e_recusada_tardia(cur, deslocamento):
    """Correcao exatamente na fronteira e tardia, mesmo que o congelamento
    tecnico ainda nao tenha sido executado."""
    cur.execute("SAVEPOINT sp")
    try:
        invalido = registro_invalido()
        lote_id = criar_lote(cur, [invalido])
        posicionar_fronteira(cur, lote_id, deslocamento)
        antes = _registro(cur, invalido["registro_coleta_id"])
        resultado = _corrigir(cur, lote_id, invalido["registro_coleta_id"], CORRECAO_VALIDA, "chave-tardia")
        assert resultado == {"sucesso": False, "motivo": "recusada_tardia", "resultado": "recusada_tardia",
                             "versao_eventos": 1}
        depois = _registro(cur, invalido["registro_coleta_id"])
        assert depois[:6] == antes[:6] and depois[6] == antes[6] + 1
        assert _lote(cur, lote_id) == (0, 1, "aguardando_d8", 1)
        assert _eventos_correcao(cur, invalido["registro_coleta_id"])[0][2] == "recusada_tardia"
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_lote_fora_de_aguardando_d8_e_recusada_tardia_pelo_status(cur):
    """Regra do status, isolada da regra do relogio: o horario conceitual
    volta ao futuro depois do congelamento, e a correcao continua tardia."""
    cur.execute("SAVEPOINT sp")
    try:
        invalido = registro_invalido()
        lote_id = criar_lote(cur, [registro_valido(1), invalido])
        posicionar_fronteira(cur, lote_id, "-1 second")
        cur.execute("SELECT nsi_operacional.fn_registrar_congelamento(%s)", (lote_id,))
        assert cur.fetchone()[0]["sucesso"] is True
        # Mantem ck_lotes_congelamento_nunca_antecipado e ck_lotes_atrasado_correto.
        cur.execute(
            "UPDATE nsi_operacional.lotes SET horario_conceitual_congelamento = now() + interval '1 hour', "
            "recebido_em = now() + interval '1 hour' - interval '192 hours', "
            "horario_real_congelamento = now() + interval '1 hour', congelamento_atrasado = false "
            "WHERE lote_id = %s",
            (lote_id,),
        )
        resultado = _corrigir(cur, lote_id, invalido["registro_coleta_id"], CORRECAO_VALIDA, "chave-tardia-status")
        assert resultado["resultado"] == "recusada_tardia"
        assert _lote(cur, lote_id)[:3] == (1, 1, "aguardando_confirmacao_disparo")
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


# ============================================================
# Registro nao resolvido neste lote - sem evento, com diagnostico
# ============================================================

def test_registro_inexistente_diagnostico_codigo_inexistente(cur):
    cur.execute("SAVEPOINT sp")
    try:
        lote_id = criar_lote(cur, [registro_invalido()])
        registro_id = uuid_texto()
        resultado = _corrigir(cur, lote_id, registro_id, CORRECAO_VALIDA, "chave-inexistente")
        assert resultado == {"sucesso": False, "motivo": "registro_nao_resolvido_neste_lote",
                             "diagnostico": "codigo_inexistente"}
        assert _eventos_correcao(cur, registro_id) == []
        cur.execute("SELECT resultado FROM nsi_operacional.comandos_idempotentes "
                    "WHERE comando = 'registrar_correcao' AND aggregate_id = %s", (registro_id,))
        assert cur.fetchone()[0] == resultado  # a recusa grava recibo
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_registro_de_outro_lote_diagnostico_registro_de_outra_operacao(cur):
    cur.execute("SAVEPOINT sp")
    try:
        invalido_outro = registro_invalido()
        criar_lote(cur, [invalido_outro])
        lote_id = criar_lote(cur, [registro_invalido()])
        antes = _registro(cur, invalido_outro["registro_coleta_id"])
        resultado = _corrigir(cur, lote_id, invalido_outro["registro_coleta_id"], CORRECAO_VALIDA, "chave-outro-lote")
        assert resultado == {"sucesso": False, "motivo": "registro_nao_resolvido_neste_lote",
                             "diagnostico": "registro_de_outra_operacao"}
        assert _eventos_correcao(cur, invalido_outro["registro_coleta_id"]) == []
        assert _registro(cur, invalido_outro["registro_coleta_id"]) == antes  # outro lote intocado
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_lote_inexistente_nao_resolve_registro(cur):
    cur.execute("SAVEPOINT sp")
    try:
        invalido = registro_invalido()
        criar_lote(cur, [invalido])
        resultado = _corrigir(cur, uuid_texto(), invalido["registro_coleta_id"], CORRECAO_VALIDA, "chave-lote-inexistente")
        assert resultado["motivo"] == "registro_nao_resolvido_neste_lote"
        assert resultado["diagnostico"] == "registro_de_outra_operacao"
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_diagnostico_leva_a_tentativa_coerente(cur):
    """O diagnostico devolvido pela correcao permite ao chamador registrar a
    tentativa nao resolvida com o motivo coerente; o motivo divergente e
    recusado."""
    cur.execute("SAVEPOINT sp")
    try:
        lote_id = criar_lote(cur, [registro_invalido()])
        codigo = uuid_texto()
        diagnostico = _corrigir(cur, lote_id, codigo, CORRECAO_VALIDA, "chave-diag")["diagnostico"]
        cur.execute(
            "SELECT nsi_operacional.fn_registrar_tentativa_nao_resolvida(%s, %s, %s, %s, %s)",
            (lote_id, diagnostico, codigo, "chave-tentativa-coerente",
             hash_registrar_tentativa_nao_resolvida(lote_id, diagnostico, codigo)),
        )
        assert cur.fetchone()[0]["sucesso"] is True
        cur.execute(
            "SELECT nsi_operacional.fn_registrar_tentativa_nao_resolvida(%s, %s, %s, %s, %s)",
            (lote_id, "registro_de_outra_operacao", codigo, "chave-tentativa-divergente",
             hash_registrar_tentativa_nao_resolvida(lote_id, "registro_de_outra_operacao", codigo)),
        )
        assert cur.fetchone()[0] == {"sucesso": False, "motivo": "motivo_diverge_do_estado"}
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


# ============================================================
# Idempotencia, entradas invalidas e privacidade
# ============================================================

def test_replay_mesma_chave_sem_novo_evento(cur):
    cur.execute("SAVEPOINT sp")
    try:
        invalido = registro_invalido()
        lote_id = criar_lote(cur, [invalido])
        primeiro = _corrigir(cur, lote_id, invalido["registro_coleta_id"], CORRECAO_VALIDA, "chave-replay")
        assert _corrigir(cur, lote_id, invalido["registro_coleta_id"], CORRECAO_VALIDA, "chave-replay") == primeiro
        assert len(_eventos_correcao(cur, invalido["registro_coleta_id"])) == 1
        assert _lote(cur, lote_id)[:2] == (1, 0)  # totais ajustados uma unica vez
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_chave_e_por_tentativa_nunca_o_registro(cur):
    """Duas tentativas distintas (chaves distintas) sobre o mesmo registro
    produzem dois eventos - a chave identifica a tentativa."""
    cur.execute("SAVEPOINT sp")
    try:
        invalido = registro_invalido()
        lote_id = criar_lote(cur, [invalido])
        _corrigir(cur, lote_id, invalido["registro_coleta_id"], CORRECAO_AINDA_INVALIDA, "tentativa-1")
        _corrigir(cur, lote_id, invalido["registro_coleta_id"], CORRECAO_VALIDA, "tentativa-2")
        eventos = _eventos_correcao(cur, invalido["registro_coleta_id"])
        assert [(e[1], e[2], e[3]) for e in eventos] == [(1, "aplicada_ainda_invalida", 2), (2, "aplicada_valida", 3)]
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_conflito_de_idempotencia_22023(cur):
    cur.execute("SAVEPOINT sp")
    try:
        invalido = registro_invalido()
        lote_id = criar_lote(cur, [invalido])
        hash_original = hash_registrar_correcao(lote_id, invalido["registro_coleta_id"], *CORRECAO_VALIDA)
        primeiro = _corrigir(cur, lote_id, invalido["registro_coleta_id"], CORRECAO_VALIDA, "chave-conflito")
        # Mesma chave, valores corrigidos diferentes: o hash canonico real diverge.
        cur.execute("SAVEPOINT antes")
        with pytest.raises(psycopg.Error) as exc_info:
            _corrigir(cur, lote_id, invalido["registro_coleta_id"], CORRECAO_AINDA_INVALIDA, "chave-conflito")
        assert exc_info.value.sqlstate == "22023"
        assert exc_info.value.diag.message_primary == "conflito_de_idempotencia"
        assert exc_info.value.diag.message_detail is None
        cur.execute("ROLLBACK TO SAVEPOINT antes")
        cur.execute("SELECT payload_hash, resultado FROM nsi_operacional.comandos_idempotentes "
                    "WHERE comando = 'registrar_correcao' AND aggregate_id = %s", (invalido["registro_coleta_id"],))
        assert cur.fetchone() == (hash_original, primeiro)
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


@pytest.mark.parametrize("indice_nulo", [0, 1, 5, 7, 8])
def test_parametro_obrigatorio_nulo_e_violacao_estrutural(cur, indice_nulo):
    """p_lote_id e obrigatorio (Sprint A3) - assim como registro, validade,
    chave e hash. Valores pessoais e motivos podem ser nulos."""
    lote_id, registro_id = uuid_texto(), uuid_texto()
    valores = ("Nome", "5511900000000", "Produto", True, None)
    params = [lote_id, registro_id, *valores, "chave-nulo",
              hash_registrar_correcao(lote_id, registro_id, *valores)]
    params[indice_nulo] = None
    cur.execute("SAVEPOINT sp")
    with pytest.raises(psycopg.Error) as exc_info:
        cur.execute(
            "SELECT nsi_operacional.fn_registrar_correcao(%s::uuid, %s::uuid, %s, %s, %s, %s::boolean, %s::text[], %s, %s)",
            params,
        )
    assert exc_info.value.sqlstate == "22000"
    assert exc_info.value.diag.message_primary == "entrada_estrutural_invalida"
    cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_violacao_de_constraint_nunca_expoe_valor_pessoal(cur):
    invalido = registro_invalido()
    cur.execute("SAVEPOINT setup")
    lote_id = criar_lote(cur, [invalido])
    nome, whatsapp, produto = "NOME-PRIVADO-CORRECAO", "WHATS-PRIVADO-CORRECAO", "PRODUTO-PRIVADO-CORRECAO"
    cur.execute("SAVEPOINT sp")
    with pytest.raises(psycopg.Error) as exc_info:
        _corrigir(cur, lote_id, invalido["registro_coleta_id"], (nome, whatsapp, produto, True, None), "chave-constraint")
    exc = exc_info.value
    assert exc.sqlstate == "23514"
    assert exc.diag.message_primary == "violacao_de_constraint"
    assert exc.diag.message_detail is None
    assert exc.diag.constraint_name == "ck_registros_coleta_coerencia"  # so o nome, nunca a linha
    texto_erro = " ".join(str(x) for x in (exc, exc.diag.message_primary, exc.diag.message_detail,
                                          exc.diag.message_hint, exc.diag.context) if x)
    for valor in (nome, whatsapp, produto):
        if valor in texto_erro:
            pytest.fail("Valor pessoal apareceu no erro de constraint - mensagem fixa, sem o valor.")
    cur.execute("ROLLBACK TO SAVEPOINT sp")
    # Nada persistido pela tentativa: nem valor, nem total, nem evento, nem recibo.
    assert _registro(cur, invalido["registro_coleta_id"])[5:] == (1, 0)
    assert _lote(cur, lote_id) == (0, 1, "aguardando_d8", 1)
    cur.execute("SELECT count(*) FROM nsi_operacional.comandos_idempotentes "
                "WHERE comando = 'registrar_correcao' AND aggregate_id = %s", (invalido["registro_coleta_id"],))
    assert cur.fetchone()[0] == 0
    cur.execute("ROLLBACK TO SAVEPOINT setup")


# ============================================================
# Concorrencia real
# ============================================================

def _criar_lote_comitado(url_owner, horario_sql: str, registros_sql: list) -> tuple:
    """Cria, com COMMIT, um lote (horario conceitual dado por expressao SQL)
    com os registros informados como (valido, nome)."""
    lote_id = uuid_texto()
    ids = []
    conn = psycopg.connect(url_owner)
    with conn.cursor() as c:
        c.execute("SET LOCAL ROLE nsi_eventos_owner")
        total_valido = sum(1 for valido, _ in registros_sql if valido)
        c.execute(
            f"WITH h AS (SELECT {horario_sql} AS horario) "
            "INSERT INTO nsi_operacional.lotes (lote_id, recebido_em, total_recebido, total_valido, total_invalido, "
            "status, horario_conceitual_congelamento, versao_eventos_atual) "
            "SELECT %s, horario - interval '192 hours', %s, %s, %s, 'aguardando_d8', horario, 1 FROM h",
            (lote_id, len(registros_sql), total_valido, len(registros_sql) - total_valido),
        )
        for valido, nome in registros_sql:
            registro_id = uuid_texto()
            ids.append(registro_id)
            c.execute(
                "INSERT INTO nsi_operacional.registros_coleta "
                "(registro_coleta_id, lote_id, nome, produto, whatsapp, valido, motivos_invalidez) "
                "VALUES (%s, %s, %s, 'Produto Teste', '5511900000003', %s, %s)",
                (registro_id, lote_id, nome, valido, None if valido else ["nome_ausente"]),
            )
    conn.commit()
    conn.close()
    return lote_id, ids


def _remover_recibos(url_owner, recibos) -> None:
    conn = psycopg.connect(url_owner)
    with conn.cursor() as c:
        c.execute("SET LOCAL ROLE nsi_eventos_owner")
        for comando, aggregate_id, chave in recibos:
            c.execute(
                "DELETE FROM nsi_operacional.comandos_idempotentes "
                "WHERE comando = %s AND aggregate_id = %s AND chave_idempotencia = %s",
                (comando, aggregate_id, chave),
            )
    conn.commit()
    conn.close()


def test_duas_correcoes_simultaneas_sem_perda_e_sem_lacuna(request):
    url_aplicacao = resolver_url_banco_papel("nsi_aplicacao", "test")
    url_owner = request.getfixturevalue("url_banco_teste")
    lote_id, (registro_id,) = _criar_lote_comitado(url_owner, "now() + interval '1 hour'", [(False, None)])
    chaves = ("chave-simultanea-a", "chave-simultanea-b")

    conn_a = psycopg.connect(url_aplicacao)
    conn_b = psycopg.connect(url_aplicacao)
    conn_obs = psycopg.connect(url_owner)
    resultado_b = {}
    try:
        resultado_a = _corrigir(conn_a.cursor(), lote_id, registro_id, CORRECAO_AINDA_INVALIDA, chaves[0])
        assert resultado_a["resultado"] == "aplicada_ainda_invalida"

        def segunda_correcao():
            try:
                resultado_b["valor"] = _corrigir(conn_b.cursor(), lote_id, registro_id, CORRECAO_VALIDA, chaves[1])
                conn_b.commit()
            except Exception as exc:
                resultado_b["erro"] = exc

        t = threading.Thread(target=segunda_correcao)
        t.start()
        aguardar_bloqueio(conn_obs, conn_b.info.backend_pid)
        conn_a.commit()
        t.join(timeout=15)
        assert not t.is_alive()
        assert "erro" not in resultado_b, type(resultado_b.get("erro")).__name__
        assert resultado_b["valor"] == {"sucesso": True, "resultado": "aplicada_valida", "numero_versao_dados": 3,
                                        "versao_eventos": 2}

        with conn_obs.cursor() as c:
            c.execute("SET LOCAL ROLE nsi_eventos_owner")
            assert [(e[1], e[2], e[3], e[4]) for e in _eventos_correcao(c, registro_id)] == [
                (1, "aplicada_ainda_invalida", 2, "nsi_aplicacao"), (2, "aplicada_valida", 3, "nsi_aplicacao")]
            assert _registro(c, registro_id)[3:] == (True, None, 3, 2)
            assert _lote(c, lote_id) == (1, 0, "aguardando_d8", 1)
        conn_obs.rollback()
    finally:
        for conn in (conn_a, conn_b):
            conn.rollback()
            conn.close()
        conn_obs.close()
        _remover_recibos(url_owner, [("registrar_correcao", registro_id, chave) for chave in chaves])


def test_correcao_contra_congelamento_na_fronteira(request):
    url_aplicacao = resolver_url_banco_papel("nsi_aplicacao", "test")
    url_owner = request.getfixturevalue("url_banco_teste")
    lote_id, (_, registro_id) = _criar_lote_comitado(
        url_owner, "clock_timestamp() + interval '3 seconds'", [(True, "Pessoa Teste"), (False, None)])
    chave = "chave-correcao-fronteira"

    conn_congelamento = psycopg.connect(url_aplicacao)
    conn_correcao = psycopg.connect(url_aplicacao)
    conn_obs = psycopg.connect(url_owner)
    resultado = {}
    try:
        # A transacao da correcao comeca ANTES da fronteira: seu now() fica
        # fixado nesse instante.
        cur_correcao = conn_correcao.cursor()
        cur_correcao.execute("SELECT now()")
        inicio_transacao_correcao = cur_correcao.fetchone()[0]

        with conn_obs.cursor() as c:
            c.execute("SET LOCAL ROLE nsi_eventos_owner")
            c.execute("SELECT horario_conceitual_congelamento FROM nsi_operacional.lotes WHERE lote_id = %s",
                      (lote_id,))
            horario_conceitual = c.fetchone()[0]
            # Premissa do cenario: sem ela, a recusa viria da regra do relogio,
            # e o teste passaria pelo motivo errado.
            assert inicio_transacao_correcao < horario_conceitual, (
                "A transacao da correcao precisa comecar antes da fronteira."
            )
            limite = time.monotonic() + 10
            while True:
                c.execute("SELECT clock_timestamp() > %s", (horario_conceitual,))
                if c.fetchone()[0]:
                    break
                if time.monotonic() > limite:
                    pytest.fail("O relogio do servidor nao ultrapassou a fronteira no tempo esperado.")
                time.sleep(0.05)
        conn_obs.rollback()

        cur_congelamento = conn_congelamento.cursor()
        cur_congelamento.execute("SET LOCAL ROLE nsi_congelamento")
        cur_congelamento.execute("SELECT nsi_operacional.fn_registrar_congelamento(%s)", (lote_id,))
        assert cur_congelamento.fetchone()[0]["sucesso"] is True

        def correcao():
            try:
                resultado["valor"] = _corrigir(cur_correcao, lote_id, registro_id, CORRECAO_VALIDA, chave)
                conn_correcao.commit()
            except Exception as exc:
                resultado["erro"] = exc

        t = threading.Thread(target=correcao)
        t.start()
        aguardar_bloqueio(conn_obs, conn_correcao.info.backend_pid)
        conn_congelamento.commit()
        t.join(timeout=15)
        assert not t.is_alive()
        assert "erro" not in resultado, type(resultado.get("erro")).__name__
        # Pelo relogio a correcao ainda seria valida; e tardia pela regra do status.
        assert resultado["valor"]["resultado"] == "recusada_tardia"

        with conn_obs.cursor() as c:
            c.execute("SET LOCAL ROLE nsi_eventos_owner")
            assert _registro(c, registro_id)[3:6] == (False, ["nome_ausente"], 1)
            assert _lote(c, lote_id)[:3] == (1, 1, "aguardando_confirmacao_disparo")
            c.execute("SELECT total_valido_congelado FROM nsi_operacional.lotes WHERE lote_id = %s", (lote_id,))
            assert c.fetchone()[0] == 1
        conn_obs.rollback()
    finally:
        for conn in (conn_congelamento, conn_correcao):
            conn.rollback()
            conn.close()
        conn_obs.close()
        _remover_recibos(url_owner, [("registrar_correcao", registro_id, chave),
                                     ("registrar_congelamento", lote_id, lote_id)])
