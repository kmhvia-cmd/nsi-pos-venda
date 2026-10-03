# -*- coding: utf-8 -*-
"""
NSI - tests/integration/test_fn_registrar_lote.py (Sprint B, B4.3 - ADR-009)

Testes de integracao REAIS contra PostgreSQL, exclusivamente contra
nsi_test, de nsi_operacional.fn_registrar_lote (migration 0005) - evento
'lote_criado'.

Conexao primaria: migrator ('SET LOCAL ROLE nsi_eventos_owner') - o
owner tem EXECUTE implicito nas proprias funcoes e SELECT direto nas
tabelas, necessario para inspecionar o efeito das chamadas. Cada teste
roda numa transacao propria (SAVEPOINT), revertida no teardown - nenhum
residuo em nsi_test.

Concorrencia real (dois uploads com o mesmo lote_id; e dois lotes
diferentes com o mesmo registro_coleta_id): duas conexoes reais como
nsi_aplicacao; exige COMMIT real. DIVULGACAO DE RESIDUO INTENCIONAL
(Especificacao Tecnica, Secao 18, "Criterios de rollback"): o lote
vencedor, seus registros e o evento 'lote_criado' permanecem como residuo
sintetico em nsi_test (eventos sao imutaveis e referenciam o lote por
FK); os recibos criados pelos testes sao removidos explicitamente, pelas
proprias chaves - nunca por remocao em massa -, para nao bloquear o
preflight do downgrade da 0004.

Nenhum valor pessoal e interpolado em mensagem de falha. Nenhum teste
chama pytest nem executa a suite completa internamente.
"""
import threading
import uuid

import psycopg
import pytest
from psycopg.types.json import Jsonb

from config import resolver_url_banco_papel
from core.payload_hash import hash_registrar_lote
from tests.apoio_b4_3 import aguardar_bloqueio, registro_invalido, registro_valido, uuid_texto

pytestmark = pytest.mark.pg_integration

CHAVES_RETORNO_SUCESSO = {
    "sucesso", "lote_id", "recebido_em", "horario_conceitual_congelamento",
    "total_recebido", "total_valido", "total_invalido", "status", "versao_eventos",
}


def _chamar(cur, lote_id, registros, chave, payload_hash=None, lote_id_legado=None) -> dict:
    if payload_hash is None:
        # Implementacao unica do calculo canonico (core/payload_hash.py).
        payload_hash = hash_registrar_lote(lote_id, lote_id_legado, registros)
    cur.execute(
        "SELECT nsi_operacional.fn_registrar_lote(%s, %s, %s, %s, %s)",
        (lote_id, lote_id_legado, Jsonb(registros), chave, payload_hash),
    )
    return cur.fetchone()[0]


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


def _contar(cur, sql, params) -> int:
    cur.execute(sql, params)
    return cur.fetchone()[0]


def _assert_erro(exc, sqlstate: str, mensagem: str, constraint: str | None = None) -> None:
    """SQLSTATE e mensagem exatos, DETAIL nulo e o nome da constraint
    esperado - nulo quando o erro e levantado pela propria funcao, sem
    nenhuma constraint envolvida."""
    assert exc.sqlstate == sqlstate
    assert exc.diag.message_primary == mensagem
    assert exc.diag.message_detail is None
    assert exc.diag.constraint_name == constraint


# ============================================================
# Sucesso
# ============================================================

def test_registra_lote_com_validos_e_invalidos(cur):
    cur.execute("SAVEPOINT sp")
    try:
        lote_id = uuid_texto()
        registros = [registro_valido(1), registro_valido(2), registro_invalido()]
        resultado = _chamar(cur, lote_id, registros, "chave-lote-001")

        assert set(resultado.keys()) == CHAVES_RETORNO_SUCESSO
        assert resultado["sucesso"] is True
        assert resultado["lote_id"] == lote_id
        assert resultado["total_recebido"] == 3
        assert resultado["total_valido"] == 2
        assert resultado["total_invalido"] == 1
        assert resultado["status"] == "aguardando_d8"
        assert resultado["versao_eventos"] == 1

        cur.execute("""
            SELECT status, total_recebido, total_valido, total_invalido, versao_eventos_atual,
                   total_valido_congelado, horario_real_congelamento, congelamento_atrasado,
                   disparo_confirmado_em, disparo_confirmado_por_login, total_confirmado_para_disparo,
                   recebido_em = now(),
                   EXTRACT(EPOCH FROM (horario_conceitual_congelamento - recebido_em))
              FROM nsi_operacional.lotes WHERE lote_id = %s
        """, (lote_id,))
        linha = cur.fetchone()
        assert linha[:5] == ("aguardando_d8", 3, 2, 1, 1)
        assert linha[5:11] == (None,) * 6
        assert linha[11] is True  # PostgreSQL e a autoridade temporal
        assert linha[12] == 691200  # M0 + 192h exatas

        cur.execute(
            "SELECT registro_coleta_id::text, valido, motivos_invalidez, numero_versao_dados, versao_eventos_atual "
            "FROM nsi_operacional.registros_coleta WHERE lote_id = %s",
            (lote_id,),
        )
        persistidos = {r[0]: r[1:] for r in cur.fetchall()}
        assert set(persistidos) == {r["registro_coleta_id"] for r in registros}
        for r in registros:
            valido, motivos, versao_dados, versao_eventos = persistidos[r["registro_coleta_id"]]
            assert valido is r["valido"]
            assert motivos == r["motivos_invalidez"]
            assert (versao_dados, versao_eventos) == (1, 0)
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_valores_pessoais_vao_somente_para_a_projecao(cur):
    cur.execute("SAVEPOINT sp")
    try:
        lote_id = uuid_texto()
        registro = registro_valido(7)
        _chamar(cur, lote_id, [registro], "chave-lote-projecao")
        cur.execute(
            "SELECT nome, whatsapp, produto FROM nsi_operacional.registros_coleta WHERE registro_coleta_id = %s",
            (registro["registro_coleta_id"],),
        )
        if cur.fetchone() != (registro["nome"], registro["whatsapp"], registro["produto"]):
            pytest.fail("Valores pessoais da projecao divergem do enviado - mensagem fixa, sem valores.")
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_grava_evento_lote_criado_exato(cur):
    cur.execute("SAVEPOINT sp")
    try:
        lote_id = uuid_texto()
        _chamar(cur, lote_id, [registro_valido(1), registro_invalido()], "chave-lote-evento")
        cur.execute("""
            SELECT aggregate_type, aggregate_version, tipo, occurred_at = now(), executado_por_login,
                   recebido_em = now(), total_recebido, total_valido, total_invalido,
                   horario_conceitual, horario_real_execucao, atrasado, operador_humano_id,
                   total_confirmado, motivo, codigo_tecnico_normalizado
              FROM nsi_operacional.eventos_lote WHERE aggregate_id = %s
        """, (lote_id,))
        eventos = cur.fetchall()
        assert len(eventos) == 1
        assert eventos[0][:9] == ("lote", 1, "lote_criado", True, "nsi_test_migrator", True, 2, 1, 1)
        assert eventos[0][9:] == (None,) * 7
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_recibo_concluido_com_o_resultado_retornado(cur):
    cur.execute("SAVEPOINT sp")
    try:
        lote_id = uuid_texto()
        registros = [registro_valido(1)]
        payload_hash = hash_registrar_lote(lote_id, None, registros)
        resultado = _chamar(cur, lote_id, registros, "chave-lote-recibo", payload_hash)
        cur.execute(
            "SELECT estado_processamento, payload_hash, resultado, concluido_em IS NOT NULL "
            "FROM nsi_operacional.comandos_idempotentes "
            "WHERE comando = 'registrar_lote' AND aggregate_id = %s AND chave_idempotencia = %s",
            (lote_id, "chave-lote-recibo"),
        )
        estado, hash_persistido, resultado_persistido, concluido = cur.fetchone()
        assert estado == "concluido" and concluido is True
        assert hash_persistido == payload_hash
        assert resultado_persistido == resultado
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_lote_sem_nenhum_valido_e_criado_normalmente(cur):
    cur.execute("SAVEPOINT sp")
    try:
        lote_id = uuid_texto()
        resultado = _chamar(cur, lote_id, [registro_invalido(), registro_invalido()], "chave-lote-sem-validos")
        assert resultado["sucesso"] is True
        assert (resultado["total_valido"], resultado["total_invalido"], resultado["status"]) == (0, 2, "aguardando_d8")
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_lote_id_legado_valido_e_persistido(cur):
    cur.execute("SAVEPOINT sp")
    try:
        lote_id = uuid_texto()
        legado = "NSI-20260101-" + uuid.uuid4().hex[:6].upper()
        _chamar(cur, lote_id, [registro_valido(1)], "chave-lote-legado", lote_id_legado=legado)
        cur.execute("SELECT lote_id_legado FROM nsi_operacional.lotes WHERE lote_id = %s", (lote_id,))
        assert cur.fetchone()[0] == legado
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


# ============================================================
# Recusa de negocio e idempotencia
# ============================================================

def test_segundo_upload_com_chave_nova_e_recusa_lote_ja_existe(cur):
    cur.execute("SAVEPOINT sp")
    try:
        lote_id = uuid_texto()
        registros = [registro_valido(1)]
        assert _chamar(cur, lote_id, registros, "chave-upload-1")["sucesso"] is True

        recusa = _chamar(cur, lote_id, registros, "chave-upload-2")
        assert recusa == {"sucesso": False, "motivo": "lote_ja_existe"}

        assert _contar(cur, "SELECT count(*) FROM nsi_operacional.eventos_lote WHERE aggregate_id = %s", (lote_id,)) == 1
        assert _contar(cur, "SELECT count(*) FROM nsi_operacional.registros_coleta WHERE lote_id = %s", (lote_id,)) == 1
        # A recusa tambem grava recibo: repetir a chave devolve a mesma recusa.
        assert _chamar(cur, lote_id, registros, "chave-upload-2") == recusa
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_replay_mesma_chave_mesmo_hash_sem_novo_evento(cur):
    cur.execute("SAVEPOINT sp")
    try:
        lote_id = uuid_texto()
        registros = [registro_valido(1), registro_invalido()]
        primeiro = _chamar(cur, lote_id, registros, "chave-replay")
        segundo = _chamar(cur, lote_id, registros, "chave-replay")
        assert segundo == primeiro
        assert _contar(cur, "SELECT count(*) FROM nsi_operacional.eventos_lote WHERE aggregate_id = %s", (lote_id,)) == 1
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_mesma_chave_hash_divergente_e_conflito_22023_recibo_intacto(cur):
    cur.execute("SAVEPOINT sp")
    try:
        lote_id = uuid_texto()
        registros = [registro_valido(1)]
        hash_original = hash_registrar_lote(lote_id, None, registros)
        resultado = _chamar(cur, lote_id, registros, "chave-conflito", hash_original)

        # Mesma chave, entrada semantica diferente (outro registro): o hash
        # canonico real diverge do persistido.
        registros_divergentes = [registro_valido(2)]
        cur.execute("SAVEPOINT antes_conflito")
        with pytest.raises(psycopg.Error) as exc_info:
            _chamar(cur, lote_id, registros_divergentes, "chave-conflito")
        _assert_erro(exc_info.value, "22023", "conflito_de_idempotencia")
        cur.execute("ROLLBACK TO SAVEPOINT antes_conflito")

        cur.execute(
            "SELECT payload_hash, resultado FROM nsi_operacional.comandos_idempotentes "
            "WHERE comando = 'registrar_lote' AND aggregate_id = %s AND chave_idempotencia = 'chave-conflito'",
            (lote_id,),
        )
        assert cur.fetchone() == (hash_original, resultado)
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


# ============================================================
# Entrada estruturalmente invalida - 22000, sem recibo
# ============================================================

def _registros_invalidos():
    base = registro_valido(1)
    sem_campo = {k: v for k, v in base.items() if k != "produto"}
    campo_extra = {**base, "campo_extra": "x"}
    return [
        ("nao_e_lista", {"registro_coleta_id": uuid_texto()}),
        ("item_nao_objeto", ["texto"]),
        ("objeto_vazio", [{}]),
        ("campo_ausente", [sem_campo]),
        ("campo_extra", [campo_extra]),
        ("id_nao_uuid", [{**base, "registro_coleta_id": "nao-e-uuid"}]),
        ("id_numerico", [{**base, "registro_coleta_id": 123}]),
        ("valido_texto", [{**base, "valido": "true"}]),
        ("nome_numerico", [{**base, "nome": 10}]),
        ("motivos_texto", [{**base, "motivos_invalidez": "nome_ausente"}]),
        ("motivo_nao_texto", [{**base, "valido": False, "motivos_invalidez": [1]}]),
        ("id_repetido", [base, {**registro_valido(2), "registro_coleta_id": base["registro_coleta_id"].upper()}]),
        ("lista_vazia", []),  # decisao da B4.3: lote sem nenhum registro e recusado
    ]


@pytest.mark.parametrize("rotulo,registros", _registros_invalidos(), ids=[c[0] for c in _registros_invalidos()])
def test_entrada_estrutural_invalida_aborta_sem_recibo(cur, rotulo, registros):
    lote_id = uuid_texto()
    # Entrada malformada nao tem hash canonico (core.payload_hash recusa
    # registros fora do formato de seis campos): usa-se um hash bem formado
    # qualquer - a funcao aborta antes de usa-lo para qualquer coisa alem
    # da reserva, que e desfeita junto.
    hash_qualquer_bem_formado = hash_registrar_lote(lote_id, None, [registro_valido(9)])
    cur.execute("SAVEPOINT sp")
    with pytest.raises(psycopg.Error) as exc_info:
        _chamar(cur, lote_id, registros, "chave-estrutural", hash_qualquer_bem_formado)
    _assert_erro(exc_info.value, "22000", "entrada_estrutural_invalida")
    cur.execute("ROLLBACK TO SAVEPOINT sp")
    assert _contar(cur, "SELECT count(*) FROM nsi_operacional.comandos_idempotentes WHERE aggregate_id = %s", (lote_id,)) == 0
    assert _contar(cur, "SELECT count(*) FROM nsi_operacional.lotes WHERE lote_id = %s", (lote_id,)) == 0


@pytest.mark.parametrize("campo", ["lote_id", "chave", "payload_hash", "registros"])
def test_parametro_obrigatorio_nulo_e_violacao_estrutural(cur, campo):
    lote_id, registros = uuid_texto(), [registro_valido(1)]
    params = {"lote_id": lote_id, "chave": "chave-nulo", "payload_hash": hash_registrar_lote(lote_id, None, registros),
              "registros": Jsonb(registros)}
    params[campo] = None
    cur.execute("SAVEPOINT sp")
    with pytest.raises(psycopg.Error) as exc_info:
        cur.execute(
            "SELECT nsi_operacional.fn_registrar_lote(%s, NULL, %s, %s, %s)",
            (params["lote_id"], params["registros"], params["chave"], params["payload_hash"]),
        )
    _assert_erro(exc_info.value, "22000", "entrada_estrutural_invalida")
    cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_registro_coleta_id_ja_existente_em_outro_lote_e_violacao_estrutural(cur):
    cur.execute("SAVEPOINT sp")
    try:
        registro = registro_valido(1)
        _chamar(cur, uuid_texto(), [registro], "chave-primeiro-lote")

        outro_lote = uuid_texto()
        cur.execute("SAVEPOINT antes")
        with pytest.raises(psycopg.Error) as exc_info:
            _chamar(cur, outro_lote, [registro], "chave-segundo-lote")
        _assert_erro(exc_info.value, "22000", "entrada_estrutural_invalida")
        cur.execute("ROLLBACK TO SAVEPOINT antes")
        assert _contar(cur, "SELECT count(*) FROM nsi_operacional.lotes WHERE lote_id = %s", (outro_lote,)) == 0
        assert _contar(cur, "SELECT count(*) FROM nsi_operacional.comandos_idempotentes WHERE aggregate_id = %s",
                       (outro_lote,)) == 0
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_json_sintaticamente_invalido_e_recusado_antes_da_funcao(cur):
    lote_id = uuid_texto()
    # JSON quebrado nao tem hash canonico; o PostgreSQL recusa a conversao
    # antes de a funcao executar - o hash bem formado nunca e usado.
    hash_qualquer_bem_formado = hash_registrar_lote(lote_id, None, [registro_valido(9)])
    cur.execute("SAVEPOINT sp")
    with pytest.raises(psycopg.errors.InvalidTextRepresentation) as exc_info:
        cur.execute(
            "SELECT nsi_operacional.fn_registrar_lote(%s, NULL, %s::jsonb, %s, %s)",
            (lote_id, '[{"registro_coleta_id": ', "chave-json", hash_qualquer_bem_formado),
        )
    assert exc_info.value.sqlstate == "22P02"
    cur.execute("ROLLBACK TO SAVEPOINT sp")
    assert _contar(cur, "SELECT count(*) FROM nsi_operacional.comandos_idempotentes WHERE aggregate_id = %s", (lote_id,)) == 0


# ============================================================
# Violacao de constraint - mensagem fixa, sem DETAIL, sem valor pessoal
# ============================================================

def test_violacao_de_constraint_nunca_expoe_valor_pessoal(cur):
    lote_id = uuid_texto()
    nome, whatsapp, produto = "NOME-PRIVADO-LOTE", "WHATS-PRIVADO-LOTE", "PRODUTO-PRIVADO-LOTE"
    registro = {"registro_coleta_id": uuid_texto(), "nome": nome, "whatsapp": whatsapp, "produto": produto,
                "valido": True, "motivos_invalidez": None}
    cur.execute("SAVEPOINT sp")
    with pytest.raises(psycopg.Error) as exc_info:
        _chamar(cur, lote_id, [registro], "chave-constraint")
    exc = exc_info.value
    _assert_erro(exc, "23514", "violacao_de_constraint", "ck_registros_coleta_coerencia")
    texto_erro = " ".join(str(x) for x in (exc, exc.diag.message_primary, exc.diag.message_detail,
                                          exc.diag.message_hint, exc.diag.context) if x)
    for valor in (nome, whatsapp, produto):
        if valor in texto_erro:
            pytest.fail("Valor pessoal apareceu no erro de constraint - mensagem fixa, sem o valor.")
    cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_lote_id_legado_fora_do_formato_e_violacao_de_constraint(cur):
    cur.execute("SAVEPOINT sp")
    with pytest.raises(psycopg.Error) as exc_info:
        _chamar(cur, uuid_texto(), [registro_valido(1)], "chave-legado-invalido", lote_id_legado="formato-invalido")
    _assert_erro(exc_info.value, "23514", "violacao_de_constraint", "ck_lotes_lote_id_legado_formato")
    cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_checks_de_lotes_sao_avaliadas_antes_do_conflito(cur):
    """Comportamento documentado no cabecalho da 0005: o PostgreSQL avalia
    as CHECKs de lotes ANTES do teste de conflito do ON CONFLICT. Um
    segundo upload do MESMO lote_id com lote_id_legado fora do formato e,
    por isso, violacao de constraint - nao a recusa 'lote_ja_existe'."""
    cur.execute("SAVEPOINT sp")
    try:
        lote_id = uuid_texto()
        assert _chamar(cur, lote_id, [registro_valido(1)], "chave-primeiro-upload")["sucesso"] is True
        cur.execute("SAVEPOINT antes")
        with pytest.raises(psycopg.Error) as exc_info:
            _chamar(cur, lote_id, [registro_valido(2)], "chave-segundo-upload", lote_id_legado="formato-invalido")
        _assert_erro(exc_info.value, "23514", "violacao_de_constraint", "ck_lotes_lote_id_legado_formato")
        cur.execute("ROLLBACK TO SAVEPOINT antes")
        assert _contar(cur, "SELECT count(*) FROM nsi_operacional.comandos_idempotentes "
                            "WHERE aggregate_id = %s AND chave_idempotencia = 'chave-segundo-upload'", (lote_id,)) == 0
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_falha_no_meio_desfaz_lote_registros_e_recibo(cur):
    """Atomicidade: os registros falham DEPOIS que a linha do lote ja foi
    inserida - nada sobrevive, nem lote, nem recibo."""
    lote_id = uuid_texto()
    invalido_incoerente = {**registro_invalido(), "motivos_invalidez": ["produto_ausente"]}
    cur.execute("SAVEPOINT sp")
    with pytest.raises(psycopg.Error) as exc_info:
        _chamar(cur, lote_id, [registro_valido(1), invalido_incoerente], "chave-atomicidade")
    _assert_erro(exc_info.value, "23514", "violacao_de_constraint", "ck_registros_coleta_coerencia")
    cur.execute("ROLLBACK TO SAVEPOINT sp")
    for tabela, coluna in (("lotes", "lote_id"), ("registros_coleta", "lote_id"),
                           ("eventos_lote", "aggregate_id"), ("comandos_idempotentes", "aggregate_id")):
        assert _contar(cur, f"SELECT count(*) FROM nsi_operacional.{tabela} WHERE {coluna} = %s", (lote_id,)) == 0


# ============================================================
# Concorrencia real: dois uploads com o mesmo lote_id
# ============================================================

def test_dois_uploads_concorrentes_do_mesmo_lote(request):
    url_aplicacao = resolver_url_banco_papel("nsi_aplicacao", "test")
    url_owner = request.getfixturevalue("url_banco_teste")
    lote_id = uuid_texto()
    registros_a, registros_b = [registro_valido(1)], [registro_valido(2)]
    chaves = ("chave-concorrente-a", "chave-concorrente-b")
    resultado_b = {}

    conn_a = psycopg.connect(url_aplicacao)
    conn_b = psycopg.connect(url_aplicacao)
    conn_obs = psycopg.connect(url_owner)
    try:
        resultado_a = _chamar(conn_a.cursor(), lote_id, registros_a, chaves[0])
        assert resultado_a["sucesso"] is True

        def segundo_upload():
            try:
                resultado_b["valor"] = _chamar(conn_b.cursor(), lote_id, registros_b, chaves[1])
                conn_b.commit()
            except Exception as exc:  # reportado no fluxo principal
                resultado_b["erro"] = exc

        t = threading.Thread(target=segundo_upload)
        t.start()
        aguardar_bloqueio(conn_obs, conn_b.info.backend_pid)
        conn_a.commit()
        t.join(timeout=15)
        assert not t.is_alive()
        assert "erro" not in resultado_b, type(resultado_b.get("erro")).__name__
        assert resultado_b["valor"] == {"sucesso": False, "motivo": "lote_ja_existe"}

        with conn_obs.cursor() as c:
            c.execute("SET LOCAL ROLE nsi_eventos_owner")
            c.execute("SELECT count(*) FROM nsi_operacional.eventos_lote WHERE aggregate_id = %s", (lote_id,))
            assert c.fetchone()[0] == 1
            c.execute("SELECT count(*) FROM nsi_operacional.registros_coleta WHERE lote_id = %s", (lote_id,))
            assert c.fetchone()[0] == 1
        conn_obs.rollback()
    finally:
        for conn in (conn_a, conn_b):
            conn.rollback()
            conn.close()
        with conn_obs.cursor() as c:
            c.execute("SET LOCAL ROLE nsi_eventos_owner")
            c.execute(
                "DELETE FROM nsi_operacional.comandos_idempotentes "
                "WHERE comando = 'registrar_lote' AND aggregate_id = %s AND chave_idempotencia = ANY(%s)",
                (lote_id, list(chaves)),
            )
        conn_obs.commit()
        conn_obs.close()


def test_mesmo_registro_em_dois_lotes_concorrentes_e_violacao_estrutural(request):
    """Corrida: dois lotes DIFERENTES com o mesmo registro_coleta_id. O
    segundo passa pela verificacao de existencia (o primeiro ainda nao
    commitou), espera no indice da PK e, quando o primeiro commita, recebe
    unique_violation - relancada como violacao estrutural (22000), mesma
    classificacao do registro ja existente detectado sem corrida. Nada do
    segundo lote persiste, nem o recibo."""
    url_aplicacao = resolver_url_banco_papel("nsi_aplicacao", "test")
    url_owner = request.getfixturevalue("url_banco_teste")
    lote_a, lote_b = uuid_texto(), uuid_texto()
    registro = registro_valido(1)
    chave_a, chave_b = "chave-corrida-registro-a", "chave-corrida-registro-b"
    resultado_b = {}

    conn_a = psycopg.connect(url_aplicacao)
    conn_b = psycopg.connect(url_aplicacao)
    conn_obs = psycopg.connect(url_owner)
    try:
        assert _chamar(conn_a.cursor(), lote_a, [registro], chave_a)["sucesso"] is True

        def segundo_lote():
            try:
                resultado_b["valor"] = _chamar(conn_b.cursor(), lote_b, [registro], chave_b)
                conn_b.commit()
            except psycopg.Error as exc:
                resultado_b["erro"] = exc
                conn_b.rollback()

        t = threading.Thread(target=segundo_lote)
        t.start()
        aguardar_bloqueio(conn_obs, conn_b.info.backend_pid)
        conn_a.commit()
        t.join(timeout=15)
        assert not t.is_alive()
        assert "erro" in resultado_b, "O segundo lote deveria ter sido recusado."
        _assert_erro(resultado_b["erro"], "22000", "entrada_estrutural_invalida")

        with conn_obs.cursor() as c:
            c.execute("SET LOCAL ROLE nsi_eventos_owner")
            c.execute("SELECT count(*) FROM nsi_operacional.lotes WHERE lote_id = %s", (lote_b,))
            assert c.fetchone()[0] == 0
            c.execute("SELECT count(*) FROM nsi_operacional.comandos_idempotentes WHERE aggregate_id = %s", (lote_b,))
            assert c.fetchone()[0] == 0
            c.execute("SELECT lote_id::text FROM nsi_operacional.registros_coleta WHERE registro_coleta_id = %s",
                      (registro["registro_coleta_id"],))
            assert c.fetchone()[0] == lote_a
        conn_obs.rollback()
    finally:
        for conn in (conn_a, conn_b):
            conn.rollback()
            conn.close()
        with conn_obs.cursor() as c:
            c.execute("SET LOCAL ROLE nsi_eventos_owner")
            c.execute(
                "DELETE FROM nsi_operacional.comandos_idempotentes "
                "WHERE comando = 'registrar_lote' AND aggregate_id = ANY(%s) AND chave_idempotencia = ANY(%s)",
                ([lote_a, lote_b], [chave_a, chave_b]),
            )
        conn_obs.commit()
        conn_obs.close()
