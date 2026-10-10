# -*- coding: utf-8 -*-
"""
NSI - tests/integration/test_invariante_claim_legado.py
(Sprint B, B5.4 - ADR-010, Secao 15; Especificacao Tecnica, B5.2, itens
10.5, 12 e 17)

Testes de integracao REAIS contra PostgreSQL, exclusivamente contra
nsi_test, da invariante de claim: nenhum registro legado nao promovido
recebe claim, em qualquer ordem e sob concorrencia.

  - fn_criar_claim (nova definicao da 0006) recusa
    'registro_legado_nao_promovido', depois da reserva do recibo;
  - fn_importar_lote_legado recusa 'claim_preexistente' quando algum
    registro do documento ja tem claim;
  - as duas serializam-se pelo bloqueio SHARE ROW EXCLUSIVE de claims.

VALIDACAO DA HIPOTESE DE IMPLEMENTACAO (B5.2, item 10.5): os dois testes de
concorrencia real comprovam, por execucao, que um fn_criar_claim que
aguarda o bloqueio da importacao so le registros_legado depois de a
importacao concorrente ter terminado - e o inverso.

SOMENTE DADOS SINTETICOS. Os demais testes terminam em ROLLBACK.

DIVULGACAO DE RESIDUO INTENCIONAL: os dois testes de concorrencia e
test_lote_ja_importado_nao_bloqueia_claims exigem COMMIT real e usam
somente lotes NAO promoviveis (geracao a1). Ficam como
residuo sintetico em nsi_test, nunca em nsi_dev: o snapshot e o registro
tecnico desses lotes (ate o downgrade da 0006) e, no segundo teste, uma
linha de claims com o seu evento 'claim_criado' (imutavel - mesmo residuo
ja aceito na B3.3). Os recibos de 'criar_claim' criados pelos testes sao
removidos explicitamente, pelas proprias chaves.
"""
import hashlib
import threading

import psycopg
import pytest

from tests.apoio_b4_3 import aguardar_bloqueio
from tests.apoio_b5 import (
    conectar_como_owner,
    contar,
    doc_a1,
    doc_a2,
    doc_a3,
    doc_anterior_a1,
    ids_do_documento,
    importar,
    iniciar,
    uuid_texto,
)

pytestmark = pytest.mark.pg_integration

TOKEN_HASH = hashlib.sha256(b"token-sintetico-b5").hexdigest()


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


def _payload_hash(registro_id: str, token_hash: str = TOKEN_HASH) -> str:
    return hashlib.sha256(f"criar_claim|{registro_id}|{token_hash}".encode()).hexdigest()


def _criar_claim(cur, registro_id: str, chave: str = "chave-b5", token_hash: str = TOKEN_HASH) -> dict:
    cur.execute("SELECT nsi_operacional.fn_criar_claim(%s, %s, %s, %s)",
                (registro_id, token_hash, chave, _payload_hash(registro_id, token_hash)))
    return cur.fetchone()[0]


def _remover_recibo(url: str, registro_id: str, chave: str) -> None:
    with psycopg.connect(url) as conn:
        cur = conn.cursor()
        cur.execute("SET LOCAL ROLE nsi_eventos_owner")
        cur.execute("DELETE FROM nsi_operacional.comandos_idempotentes "
                    "WHERE comando = 'criar_claim' AND aggregate_id = %s AND chave_idempotencia = %s",
                    (registro_id, chave))
        conn.commit()


RECUSA_LEGADO = {"sucesso": False, "motivo": "registro_legado_nao_promovido"}


# ============================================================
# fn_criar_claim - claim pedido DEPOIS da importacao
# ============================================================

def test_registro_identificado_nao_promovido_nunca_recebe_claim(cur):
    documento = doc_a1()
    assert importar(cur, iniciar(cur), documento)["destino"] == "preservado"

    for registro_id in ids_do_documento(documento):
        assert _criar_claim(cur, registro_id) == RECUSA_LEGADO
        assert contar(cur, "claims", "registro_coleta_id = %s", (registro_id,)) == 0
        assert contar(cur, "eventos_claim", "aggregate_id = %s", (registro_id,)) == 0


@pytest.mark.parametrize("construtor", [doc_a2, doc_a3])
def test_registro_de_lote_a2_ou_a3_preservado_e_nao_promovido_nunca_recebe_claim(cur, construtor):
    """Lote promovivel pela geracao, mas nao promovido (execucao sem fuso):
    valido ou invalido, o registro continua legado_identificado_nao_
    promovido."""
    documento = construtor()
    resultado = importar(cur, iniciar(cur, None), documento)
    assert (resultado["destino"], resultado["motivo"]) == ("preservado", "fuso_nao_declarado")
    for registro_id in ids_do_documento(documento):
        assert _criar_claim(cur, registro_id) == RECUSA_LEGADO
    assert contar(cur, "claims", "registro_coleta_id = ANY(%s::uuid[])", (ids_do_documento(documento),)) == 0


def test_recusa_e_gravada_no_recibo_depois_da_reserva_e_repetida_no_replay(cur):
    """Posicao da recusa (item 10.5): depois da reserva do recibo, exatamente
    como 'registro_ocupado'."""
    documento = doc_a1()
    importar(cur, iniciar(cur), documento)
    registro_id = documento["clientes"][0]["registro_coleta_id"]

    assert _criar_claim(cur, registro_id, "chave-recusa") == RECUSA_LEGADO
    cur.execute(
        "SELECT estado_processamento, resultado FROM nsi_operacional.comandos_idempotentes "
        " WHERE comando = 'criar_claim' AND aggregate_id = %s AND chave_idempotencia = 'chave-recusa'",
        (registro_id,))
    assert cur.fetchone() == ("concluido", RECUSA_LEGADO)

    assert _criar_claim(cur, registro_id, "chave-recusa") == RECUSA_LEGADO, "Replay devolve a mesma recusa."
    assert contar(cur, "comandos_idempotentes", "aggregate_id = %s", (registro_id,)) == 1


def test_recusa_e_permanente_para_qualquer_chave(cur):
    documento = doc_a1()
    importar(cur, iniciar(cur), documento)
    registro_id = documento["clientes"][0]["registro_coleta_id"]
    for chave in ("chave-1", "chave-2", "chave-3"):
        assert _criar_claim(cur, registro_id, chave) == RECUSA_LEGADO
    assert contar(cur, "claims", "registro_coleta_id = %s", (registro_id,)) == 0


def test_conflito_de_idempotencia_preservado_na_recusa(cur):
    documento = doc_a1()
    importar(cur, iniciar(cur), documento)
    registro_id = documento["clientes"][0]["registro_coleta_id"]
    _criar_claim(cur, registro_id, "chave-conflito")
    with pytest.raises(psycopg.errors.InvalidParameterValue) as exc_info:
        _criar_claim(cur, registro_id, "chave-conflito", hashlib.sha256(b"outro-token").hexdigest())
    assert exc_info.value.sqlstate == "22023"
    assert exc_info.value.diag.message_primary == "conflito_de_idempotencia"


@pytest.mark.parametrize("construtor", [doc_a2, doc_a3])
def test_registro_promovido_segue_as_regras_nativas_de_claim(cur, construtor):
    """ADR-010, Secao 15: registros legado_promovido tem identidade nascida
    em M0 e seguem as regras nativas a partir da promocao."""
    documento = construtor()
    assert importar(cur, iniciar(cur), documento)["destino"] == "promovido"

    for registro_id in ids_do_documento(documento):
        resultado = _criar_claim(cur, registro_id)
        assert resultado["sucesso"] is True
        assert resultado["versao_atual"] == 1
        cur.execute("SELECT estado, claim_id::text FROM nsi_operacional.claims WHERE registro_coleta_id = %s",
                    (registro_id,))
        assert cur.fetchone() == ("ativo", resultado["claim_id"])
        cur.execute("SELECT tipo, aggregate_version FROM nsi_operacional.eventos_claim WHERE aggregate_id = %s",
                    (registro_id,))
        assert cur.fetchall() == [("claim_criado", 1)]


def test_uuid_sem_relacao_com_o_legado_recebe_claim(cur):
    """A verificacao e deliberadamente estreita: nao exige a existencia do
    registro em registros_coleta (desenho da B3 preservado)."""
    importar(cur, iniciar(cur), doc_a1())
    registro_id = uuid_texto()
    assert _criar_claim(cur, registro_id)["sucesso"] is True


def test_comportamento_da_0003_preservado_nos_demais_casos(cur):
    registro_id = uuid_texto()
    primeiro = _criar_claim(cur, registro_id, "chave-a")
    assert set(primeiro) == {"sucesso", "claim_id", "expira_em", "versao_atual"}
    assert _criar_claim(cur, registro_id, "chave-a") == primeiro, "Replay."
    assert _criar_claim(cur, registro_id, "chave-b") == {"sucesso": False, "motivo": "registro_ocupado"}

    cur.execute("UPDATE nsi_operacional.claims SET estado = 'liberado' WHERE registro_coleta_id = %s", (registro_id,))
    novo = _criar_claim(cur, registro_id, "chave-c")
    assert novo["sucesso"] is True
    assert novo["versao_atual"] == 2
    assert novo["claim_id"] != primeiro["claim_id"]
    cur.execute("SELECT executado_por ->> 'role' = session_user FROM nsi_operacional.eventos_claim "
                "WHERE aggregate_id = %s AND aggregate_version = 2", (registro_id,))
    assert cur.fetchone()[0] is True


def test_registro_sem_identidade_tecnica_nao_tem_uuid_no_snapshot(cur):
    """Registros legado_sem_identidade_tecnica nao podem ser alvo de claim:
    nao tem UUID."""
    documento = doc_anterior_a1()
    importar(cur, iniciar(cur), documento)
    assert contar(
        cur, "registros_legado r JOIN nsi_operacional.lotes_legado g USING (snapshot_lote_id)",
        "g.lote_id_legado = %s AND r.registro_coleta_id IS NULL "
        "AND r.classificacao = 'legado_sem_identidade_tecnica'", (documento["lote_id"],)) == 2


# ============================================================
# fn_importar_lote_legado - claim ANTERIOR a importacao
# ============================================================

@pytest.mark.parametrize("construtor,lista", [
    (doc_a1, "clientes"), (doc_a2, "clientes"), (doc_a2, "clientes_invalidos"), (doc_a3, "clientes_invalidos"),
])
def test_lote_com_registro_que_ja_tem_claim_e_recusado_sem_escrita(cur, construtor, lista):
    documento = construtor()
    registro_id = documento[lista][-1]["registro_coleta_id"]
    assert _criar_claim(cur, registro_id)["sucesso"] is True

    importacao_id = iniciar(cur)
    antes = tuple(contar(cur, t) for t in ("lotes_legado", "registros_legado", "lotes", "registros_coleta"))
    resultado = importar(cur, importacao_id, documento)
    depois = tuple(contar(cur, t) for t in ("lotes_legado", "registros_legado", "lotes", "registros_coleta"))

    assert resultado["destino"] == "recusado"
    assert resultado["motivo"] == "claim_preexistente"
    assert resultado["lote_id_promovido"] is None
    assert depois == antes, "Nada vai para o snapshot nem para a projecao."
    cur.execute("SELECT destino, motivo, geracao FROM nsi_operacional.importacoes_legado_arquivos "
                "WHERE importacao_id = %s", (importacao_id,))
    assert cur.fetchone() == ("recusado", "claim_preexistente", resultado["geracao"])


@pytest.mark.parametrize("estado", ["liberado", "expirado_pendente_revisao"])
def test_claim_em_qualquer_estado_e_claim_preexistente(cur, estado):
    """A regra e 'ja tiver linha em claims' - nao apenas claim ativo."""
    documento = doc_a1()
    registro_id = documento["clientes"][0]["registro_coleta_id"]
    _criar_claim(cur, registro_id)
    cur.execute("UPDATE nsi_operacional.claims SET estado = %s WHERE registro_coleta_id = %s", (estado, registro_id))
    assert importar(cur, iniciar(cur), documento)["motivo"] == "claim_preexistente"


def test_claim_preexistente_e_decidido_antes_dos_criterios_de_promocao(cur):
    """Ordem fixa: o passo 8 decide antes do passo 10."""
    documento = doc_a2()
    documento["status"] = "disparado"
    _criar_claim(cur, documento["clientes"][0]["registro_coleta_id"])
    resultado = importar(cur, iniciar(cur, None), documento)
    assert (resultado["destino"], resultado["motivo"]) == ("recusado", "claim_preexistente")


def test_lote_promovido_e_reapresentado_continua_ja_importado_mesmo_com_claim(cur):
    """A reimportacao (passo 7) vem antes da verificacao de claim (passo 8)
    de proposito: os registros de um lote promovido podem ter claims
    legitimos do fluxo novo."""
    documento = doc_a2()
    original = importar(cur, iniciar(cur), documento)
    assert original["destino"] == "promovido"
    for registro_id in ids_do_documento(documento):
        assert _criar_claim(cur, registro_id)["sucesso"] is True

    resultado = importar(cur, iniciar(cur), documento)
    assert resultado["destino"] == "ja_importado"
    assert resultado["destino_original"] == "promovido"
    assert resultado["lote_id_promovido"] == original["lote_id_promovido"]


def test_claim_de_uuid_alheio_nao_afeta_a_importacao(cur):
    _criar_claim(cur, uuid_texto())
    assert importar(cur, iniciar(cur), doc_a2())["destino"] == "promovido"


def test_importacao_bloqueia_claims_em_share_row_exclusive_ate_o_fim_da_transacao(cur):
    importar(cur, iniciar(cur), doc_a1())
    cur.execute("""
        SELECT l.mode FROM pg_catalog.pg_locks l
         WHERE l.pid = pg_backend_pid() AND l.locktype = 'relation' AND l.granted
           AND l.relation = 'nsi_operacional.claims'::regclass
    """)
    assert "ShareRowExclusiveLock" in {linha[0] for linha in cur.fetchall()}


def test_lote_ja_importado_nao_bloqueia_claims(request):
    """A reimportacao e decidida antes do bloqueio: reapresentar um lote ja
    importado nao faz a criacao de claims esperar. Exige um lote ja
    CONFIRMADO (COMMIT real, lote nao promovivel - residuo sintetico em
    nsi_test, como nos testes de concorrencia abaixo); a reapresentacao roda
    em outra transacao, revertida."""
    url = request.getfixturevalue("url_banco_teste")
    consulta_do_bloqueio = """
        SELECT count(*) FROM pg_catalog.pg_locks l
         WHERE l.pid = pg_backend_pid() AND l.mode = 'ShareRowExclusiveLock'
           AND l.relation = 'nsi_operacional.claims'::regclass
    """
    conn = conectar_como_owner(url)
    try:
        cur = conn.cursor()
        documento = doc_a1()
        importar(cur, iniciar(cur), documento)
        cur.execute(consulta_do_bloqueio)
        assert cur.fetchone()[0] == 1, "A importacao de um lote novo bloqueia claims."
        conn.commit()

        cur.execute("SET LOCAL ROLE nsi_eventos_owner")
        assert importar(cur, iniciar(cur), documento)["destino"] == "ja_importado"
        cur.execute(consulta_do_bloqueio)
        assert cur.fetchone()[0] == 0, "O lote ja importado e decidido antes do bloqueio de claims."
    finally:
        conn.rollback()
        conn.close()


# ============================================================
# Concorrencia real nos dois sentidos (item 10.5) - COMMIT real
# ============================================================

def test_criar_claim_que_espera_uma_importacao_em_andamento_recusa(request):
    """Sentido 1: a importacao de um lote nao promovivel esta em andamento
    (snapshot ainda nao confirmado). fn_criar_claim para um registro desse
    lote e observada em espera pelo bloqueio de claims; depois do commit da
    importacao, le registros_legado e recusa."""
    url = request.getfixturevalue("url_banco_teste")
    documento = doc_a1()
    registro_id = documento["clientes"][0]["registro_coleta_id"]
    chave = "chave-concorrencia-" + registro_id
    saida, pid_pronto = {}, threading.Event()

    def _criar_claim_em_thread():
        conn = conectar_como_owner(url)
        try:
            cur = conn.cursor()
            cur.execute("SELECT pg_backend_pid()")
            saida["pid"] = cur.fetchone()[0]
            pid_pronto.set()
            saida["resultado"] = _criar_claim(cur, registro_id, chave)
            conn.commit()
        except Exception as exc:  # reportada pelo teste, na thread principal
            saida["erro"] = exc
            conn.rollback()
        finally:
            pid_pronto.set()
            conn.close()

    conn_a = conectar_como_owner(url)
    try:
        cur_a = conn_a.cursor()
        importacao_id = iniciar(cur_a)
        conn_a.commit()

        cur_a.execute("SET LOCAL ROLE nsi_eventos_owner")
        assert importar(cur_a, importacao_id, documento)["destino"] == "preservado"

        thread = threading.Thread(target=_criar_claim_em_thread)
        thread.start()
        try:
            assert pid_pronto.wait(10), "A conexao concorrente nao chegou a iniciar."
            observador = psycopg.connect(url)
            try:
                aguardar_bloqueio(observador, saida["pid"])
            finally:
                observador.close()
            conn_a.commit()
        finally:
            conn_a.rollback()
            thread.join(30)
        assert not thread.is_alive(), "fn_criar_claim nao terminou depois do commit da importacao."
        if "erro" in saida:
            raise saida["erro"]

        assert saida["resultado"] == RECUSA_LEGADO, (
            "Hipotese do item 10.5 refutada: fn_criar_claim leu registros_legado antes do fim da importacao."
        )
        cur_a.execute("SET LOCAL ROLE nsi_eventos_owner")
        assert contar(cur_a, "claims", "registro_coleta_id = %s", (registro_id,)) == 0
        assert contar(cur_a, "registros_legado", "registro_coleta_id = %s", (registro_id,)) == 1
    finally:
        conn_a.rollback()
        conn_a.close()
        _remover_recibo(url, registro_id, chave)


def test_importacao_que_espera_um_criar_claim_em_andamento_recusa(request):
    """Sentido 2: fn_criar_claim esta em andamento (claim ainda nao
    confirmado). A importacao de um lote que contem esse registro e
    observada em espera pelo bloqueio de claims; depois do commit do claim,
    recusa 'claim_preexistente', sem snapshot."""
    url = request.getfixturevalue("url_banco_teste")
    documento = doc_a1()
    registro_id = documento["clientes"][0]["registro_coleta_id"]
    chave = "chave-concorrencia-" + registro_id
    saida, pid_pronto = {}, threading.Event()

    def _importar_em_thread(importacao_id):
        conn = conectar_como_owner(url)
        try:
            cur = conn.cursor()
            cur.execute("SELECT pg_backend_pid()")
            saida["pid"] = cur.fetchone()[0]
            pid_pronto.set()
            saida["resultado"] = importar(cur, importacao_id, documento)
            conn.commit()
        except Exception as exc:  # reportada pelo teste, na thread principal
            saida["erro"] = exc
            conn.rollback()
        finally:
            pid_pronto.set()
            conn.close()

    conn_a = conectar_como_owner(url)
    try:
        cur_a = conn_a.cursor()
        importacao_id = iniciar(cur_a)
        conn_a.commit()

        cur_a.execute("SET LOCAL ROLE nsi_eventos_owner")
        assert _criar_claim(cur_a, registro_id, chave)["sucesso"] is True

        thread = threading.Thread(target=_importar_em_thread, args=(importacao_id,))
        thread.start()
        try:
            assert pid_pronto.wait(10), "A conexao concorrente nao chegou a iniciar."
            observador = psycopg.connect(url)
            try:
                aguardar_bloqueio(observador, saida["pid"])
            finally:
                observador.close()
            conn_a.commit()
        finally:
            conn_a.rollback()
            thread.join(30)
        assert not thread.is_alive(), "A importacao nao terminou depois do commit do claim."
        if "erro" in saida:
            raise saida["erro"]

        assert saida["resultado"]["destino"] == "recusado"
        assert saida["resultado"]["motivo"] == "claim_preexistente"
        cur_a.execute("SET LOCAL ROLE nsi_eventos_owner")
        assert contar(cur_a, "lotes_legado", "lote_id_legado = %s", (documento["lote_id"],)) == 0
        assert contar(cur_a, "registros_legado", "registro_coleta_id = %s", (registro_id,)) == 0
        assert contar(cur_a, "claims", "registro_coleta_id = %s", (registro_id,)) == 1
    finally:
        conn_a.rollback()
        conn_a.close()
        _remover_recibo(url, registro_id, chave)
