# -*- coding: utf-8 -*-
"""
NSI - tests/integration/test_fn_revisao_e_reatribuicao.py (Sprint B, B3.3 - ADR-008)

Testes de integracao REAIS contra PostgreSQL, exclusivamente contra
nsi_test, de nsi_operacional.fn_registrar_revisao_abandono e
nsi_operacional.fn_reatribuir_claim (migration 0003).

DIVULGACAO DE RESIDUO INTENCIONAL: o teste de concorrencia real de duas
reatribuicoes (test_duas_reatribuicoes_concorrentes_uma_vencedora) exige
um cenario ja COMMITADO e visivel as duas conexoes (UPDATE, ao contrario
de INSERT, nao espera por uma linha ainda nao commitada por outra
transacao - so enxerga o que ja e visivel). Para satisfazer
claims_revisao_atual_fk, isso exige um evento real de
'revisao_de_abandono_registrada' - e eventos_claim e imutavel mesmo para
o owner (trigger eventos_claim_bloqueia_alteracao bloqueia UPDATE/DELETE
incondicionalmente). Inventario exato do residuo permanente deixado por
esse teste em nsi_test: **1 linha em claims + 1 linha em eventos_claim**
- a linha de claims tambem NAO pode ser removida (eventos_claim.
aggregate_id referencia claims.registro_coleta_id por FK nao diferivel;
enquanto o evento existir - e ele e permanente - a linha de claims fica
presa). A limpeza deste teste verifica essa condicao antes de tentar
qualquer DELETE - nunca tenta remover a linha de claims quando um evento
ainda a referencia, reconhecendo o residuo como intencional em vez de
falhar por violacao de chave estrangeira.

Nenhum teste chama pytest nem executa a suite completa internamente.
"""
import hashlib
import json
import uuid

import psycopg
import pytest

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


def _criar_claim(cur, registro_coleta_id, token_hash, chave="chave-criar") -> dict:
    payload = _payload_hash(registro_coleta_id=registro_coleta_id, token_hash=token_hash)
    cur.execute(
        "SELECT nsi_operacional.fn_criar_claim(%s, %s, %s, %s)",
        (registro_coleta_id, token_hash, chave, payload),
    )
    return cur.fetchone()[0]


def _expirar(cur, registro_coleta_id) -> None:
    # Claim expirado (regra aprovada): criado_em e expira_em atualizados
    # juntos, ambos no passado, preservando expira_em > criado_em. Se ja
    # havia um heartbeat real registrado (ultimo_heartbeat_em NOT NULL -
    # caso de test_reatribuicao_com_sucesso_zera_heartbeat_e_gera_novo_claim),
    # ele e reposicionado para dentro da nova janela [criado_em, expira_em)
    # na MESMA instrucao, preservando criado_em <= ultimo_heartbeat_em <
    # expira_em (ck_claims_heartbeat_dentro_da_janela) - nunca zerado aqui,
    # pois o teste de reatribuicao precisa provar que e a PROPRIA funcao
    # fn_reatribuir_claim que limpa um heartbeat preexistente, nao este
    # helper de setup. Se ja era NULL, permanece NULL.
    cur.execute(
        "UPDATE nsi_operacional.claims "
        "SET criado_em = now() - interval '2 minutes', "
        "    expira_em = now() - interval '1 minute', "
        "    ultimo_heartbeat_em = CASE WHEN ultimo_heartbeat_em IS NOT NULL "
        "                               THEN now() - interval '90 seconds' "
        "                               ELSE NULL END "
        "WHERE registro_coleta_id = %s",
        (registro_coleta_id,),
    )
    cur.execute("SELECT nsi_operacional.fn_materializar_expiracao(%s)", (registro_coleta_id,))
    assert cur.fetchone()[0]["materializado"] is True


def _revisar(cur, registro_coleta_id, decisao, justificativa, chave) -> dict:
    payload = _payload_hash(registro_coleta_id=registro_coleta_id, decisao=decisao, justificativa=justificativa)
    cur.execute(
        "SELECT nsi_operacional.fn_registrar_revisao_abandono(%s, %s, %s, %s, %s)",
        (registro_coleta_id, decisao, justificativa, chave, payload),
    )
    return cur.fetchone()[0]


def _reatribuir(cur, registro_coleta_id, evento_id_revisao, token_hash_novo, chave) -> dict:
    payload = _payload_hash(registro_coleta_id=registro_coleta_id, evento_id_revisao=evento_id_revisao,
                             token_hash_novo=token_hash_novo)
    cur.execute(
        "SELECT nsi_operacional.fn_reatribuir_claim(%s, %s, %s, %s, %s)",
        (registro_coleta_id, evento_id_revisao, token_hash_novo, chave, payload),
    )
    return cur.fetchone()[0]


# ============================================================
# Revisao - sempre gera evento, inclusive decidindo nao reatribuir
# ============================================================

def test_revisao_negativa_gera_evento_mantem_estado_avanca_versao(cur):
    cur.execute("SAVEPOINT sp")
    try:
        registro_coleta_id = _uuid()
        criado = _criar_claim(cur, registro_coleta_id, _hash_valido())
        _expirar(cur, registro_coleta_id)

        cur.execute("SELECT versao_atual FROM nsi_operacional.claims WHERE registro_coleta_id = %s", (registro_coleta_id,))
        versao_antes = cur.fetchone()[0]

        resultado = _revisar(cur, registro_coleta_id, "nao_reatribuir", "sem contato do cliente", "chave-rev-neg")
        assert resultado["sucesso"] is True
        assert resultado["decisao"] == "nao_reatribuir"

        cur.execute(
            "SELECT estado, claim_id, token_hash, versao_atual, revisao_decisao, revisao_atual_id "
            "FROM nsi_operacional.claims WHERE registro_coleta_id = %s",
            (registro_coleta_id,),
        )
        estado, claim_id, token_hash, versao_depois, decisao, rev_id = cur.fetchone()
        assert estado == "expirado_pendente_revisao"          # projecao inalterada
        assert claim_id == uuid.UUID(criado["claim_id"])       # claim_id inalterado
        assert versao_depois == versao_antes + 1                # so a versao avanca
        assert decisao == "nao_reatribuir"
        assert rev_id == uuid.UUID(resultado["evento_id"])

        cur.execute(
            "SELECT count(*) FROM nsi_operacional.eventos_claim "
            "WHERE aggregate_id = %s AND tipo = 'revisao_de_abandono_registrada'",
            (registro_coleta_id,),
        )
        assert cur.fetchone()[0] == 1
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_revisao_posterior_com_chave_distinta_substitui_a_atual(cur):
    cur.execute("SAVEPOINT sp")
    try:
        registro_coleta_id = _uuid()
        _criar_claim(cur, registro_coleta_id, _hash_valido())
        _expirar(cur, registro_coleta_id)

        r1 = _revisar(cur, registro_coleta_id, "nao_reatribuir", "primeira analise", "chave-rev-1")
        r2 = _revisar(cur, registro_coleta_id, "reatribuir", "segunda analise, autoriza", "chave-rev-2")

        assert r1["evento_id"] != r2["evento_id"]

        cur.execute(
            "SELECT revisao_atual_id, revisao_decisao FROM nsi_operacional.claims WHERE registro_coleta_id = %s",
            (registro_coleta_id,),
        )
        rev_id, decisao = cur.fetchone()
        assert str(rev_id) == r2["evento_id"]
        assert decisao == "reatribuir"

        cur.execute(
            "SELECT count(*) FROM nsi_operacional.eventos_claim "
            "WHERE aggregate_id = %s AND tipo = 'revisao_de_abandono_registrada'",
            (registro_coleta_id,),
        )
        assert cur.fetchone()[0] == 2  # ambas as revisoes permanecem no log, so a mais recente e 'atual'
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_revisao_recusada_quando_claim_nao_esta_pendente(cur):
    cur.execute("SAVEPOINT sp")
    try:
        registro_coleta_id = _uuid()
        _criar_claim(cur, registro_coleta_id, _hash_valido())  # ainda 'ativo', nunca expirado

        resultado = _revisar(cur, registro_coleta_id, "nao_reatribuir", "tentativa precoce", "chave-rev-precoce")
        assert resultado["sucesso"] is False
        assert resultado["motivo"] == "claim_nao_esta_pendente_de_revisao"
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


# ============================================================
# Reatribuicao - sucesso, zera heartbeat, predicado atomico completo
# ============================================================

def test_reatribuicao_com_sucesso_zera_heartbeat_e_gera_novo_claim(cur):
    cur.execute("SAVEPOINT sp")
    try:
        registro_coleta_id = _uuid()
        token_original = _hash_valido("original")
        criado = _criar_claim(cur, registro_coleta_id, token_original)

        hb_payload = _payload_hash(registro_coleta_id=registro_coleta_id, claim_id=criado["claim_id"], token_hash=token_original)
        cur.execute(
            "SELECT nsi_operacional.fn_registrar_heartbeat(%s, %s, %s, %s, %s)",
            (registro_coleta_id, criado["claim_id"], token_original, "chave-hb-antes", hb_payload),
        )
        assert cur.fetchone()[0]["sucesso"] is True

        _expirar(cur, registro_coleta_id)
        revisao = _revisar(cur, registro_coleta_id, "reatribuir", "cliente retomou contato", "chave-rev-ok")

        token_novo = _hash_valido("novo")
        resultado = _reatribuir(cur, registro_coleta_id, revisao["evento_id"], token_novo, "chave-reatrib-ok")

        assert resultado["sucesso"] is True
        assert resultado["claim_id"] != criado["claim_id"]

        cur.execute(
            "SELECT estado, token_hash, ultimo_heartbeat_em, revisao_atual_id, revisao_decisao, revisao_registrada_em "
            "FROM nsi_operacional.claims WHERE registro_coleta_id = %s",
            (registro_coleta_id,),
        )
        estado, token_persistido, heartbeat, rev_id, rev_decisao, rev_registrada = cur.fetchone()
        assert estado == "ativo"
        if token_persistido != token_novo:
            pytest.fail(
                "token_hash persistido nao corresponde ao novo token apos reatribuicao - "
                "mensagem fixa, valores nunca interpolados no traceback."
            )
        assert heartbeat is None       # [correcao] zerado na reatribuicao
        assert rev_id is None
        assert rev_decisao is None
        assert rev_registrada is None

        cur.execute(
            "SELECT count(*) FROM nsi_operacional.eventos_claim WHERE aggregate_id = %s AND tipo = 'claim_reatribuido'",
            (registro_coleta_id,),
        )
        assert cur.fetchone()[0] == 1
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_reatribuicao_recusada_sem_revisao_valida(cur):
    cur.execute("SAVEPOINT sp")
    try:
        registro_coleta_id = _uuid()
        _criar_claim(cur, registro_coleta_id, _hash_valido())
        _expirar(cur, registro_coleta_id)
        # nenhuma revisao registrada - revisao_atual_id ainda NULL.

        resultado = _reatribuir(cur, registro_coleta_id, _uuid(), _hash_valido("novo"), "chave-reatrib-sem-rev")
        assert resultado["sucesso"] is False
        assert resultado["motivo"] == "revisao_invalida_ou_ja_consumida"
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_reatribuicao_recusada_quando_revisao_decidiu_nao_reatribuir(cur):
    cur.execute("SAVEPOINT sp")
    try:
        registro_coleta_id = _uuid()
        _criar_claim(cur, registro_coleta_id, _hash_valido())
        _expirar(cur, registro_coleta_id)
        revisao = _revisar(cur, registro_coleta_id, "nao_reatribuir", "negado", "chave-rev-negada")

        resultado = _reatribuir(cur, registro_coleta_id, revisao["evento_id"], _hash_valido("novo"), "chave-reatrib-negada")
        assert resultado["sucesso"] is False
        assert resultado["motivo"] == "revisao_invalida_ou_ja_consumida"
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_reatribuicao_recusada_com_revisao_de_geracao_antiga_ja_consumida(cur):
    cur.execute("SAVEPOINT sp")
    try:
        registro_coleta_id = _uuid()
        _criar_claim(cur, registro_coleta_id, _hash_valido())
        _expirar(cur, registro_coleta_id)
        revisao_1 = _revisar(cur, registro_coleta_id, "reatribuir", "primeira autorizacao", "chave-rev-1a")

        resultado_1 = _reatribuir(cur, registro_coleta_id, revisao_1["evento_id"], _hash_valido("novo-1"), "chave-reatrib-1a")
        assert resultado_1["sucesso"] is True

        # revisao_1 ja foi consumida (revisao_atual_id voltou a NULL) -
        # reusa-la agora, mesmo referenciando um evento real do log,
        # precisa falhar.
        resultado_2 = _reatribuir(cur, registro_coleta_id, revisao_1["evento_id"], _hash_valido("novo-2"), "chave-reatrib-1b")
        assert resultado_2["sucesso"] is False
        assert resultado_2["motivo"] == "revisao_invalida_ou_ja_consumida"
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_reatribuicao_bloqueada_quando_claim_id_diverge_do_evento(cur):
    """Defesa em profundidade do predicado EXISTS: corrompe claims.claim_id
    diretamente (fora de qualquer funcao, simulando uma divergencia que as
    seis funcoes nunca produziriam sozinhas) e confirma que o EXISTS
    correlacionado bloqueia a reatribuicao mesmo com os quatro outros
    predicados satisfeitos."""
    cur.execute("SAVEPOINT sp")
    try:
        registro_coleta_id = _uuid()
        _criar_claim(cur, registro_coleta_id, _hash_valido())
        _expirar(cur, registro_coleta_id)
        revisao = _revisar(cur, registro_coleta_id, "reatribuir", "autorizado", "chave-rev-divergente")

        cur.execute(
            "UPDATE nsi_operacional.claims SET claim_id = %s WHERE registro_coleta_id = %s",
            (_uuid(), registro_coleta_id),
        )

        resultado = _reatribuir(cur, registro_coleta_id, revisao["evento_id"], _hash_valido("novo"), "chave-reatrib-divergente")
        assert resultado["sucesso"] is False
        assert resultado["motivo"] == "revisao_invalida_ou_ja_consumida"
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


# ============================================================
# Idempotencia de fn_registrar_revisao_abandono e fn_reatribuir_claim
# ============================================================

def test_revisao_token_e_reatribuicao_replay_e_conflito(cur):
    cur.execute("SAVEPOINT sp")
    try:
        registro_coleta_id = _uuid()
        _criar_claim(cur, registro_coleta_id, _hash_valido())
        _expirar(cur, registro_coleta_id)

        r1 = _revisar(cur, registro_coleta_id, "reatribuir", "motivo", "chave-rev-replay")
        r2 = _revisar(cur, registro_coleta_id, "reatribuir", "motivo", "chave-rev-replay")
        assert r1 == r2

        token_novo = _hash_valido("reatrib-1")
        ra1 = _reatribuir(cur, registro_coleta_id, r1["evento_id"], token_novo, "chave-reatrib-replay")
        ra2 = _reatribuir(cur, registro_coleta_id, r1["evento_id"], token_novo, "chave-reatrib-replay")
        assert ra1 == ra2

        token_hash_conflitante = _hash_valido("outro-token")
        chave_reatrib = "chave-reatrib-replay"
        payload_conflitante = _payload_hash(
            registro_coleta_id=registro_coleta_id, evento_id_revisao=r1["evento_id"], token_hash_novo=token_hash_conflitante,
        )

        cur.execute("SAVEPOINT sp_conflito")
        with pytest.raises(psycopg.errors.InvalidParameterValue) as exc_info:
            _reatribuir(cur, registro_coleta_id, r1["evento_id"], token_hash_conflitante, chave_reatrib)
        assert exc_info.value.sqlstate == "22023"
        assert str(exc_info.value).strip().startswith("conflito_de_idempotencia")
        # mensagem fixa - nunca inclui chave, token ou payload, checado em str() e repr().
        for rotulo, valor in (
            ("chave", chave_reatrib), ("token_hash_novo", token_hash_conflitante), ("payload_hash", payload_conflitante),
        ):
            if valor in str(exc_info.value) or valor in repr(exc_info.value):
                pytest.fail(
                    f"Vazamento de segredo detectado na excecao de conflito ({rotulo}) - "
                    "mensagem fixa, o valor em si nunca e exibido aqui."
                )
        cur.execute("ROLLBACK TO SAVEPOINT sp_conflito")

        ra_final = _reatribuir(cur, registro_coleta_id, r1["evento_id"], token_novo, "chave-reatrib-replay")
        assert ra_final == ra1
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


# ============================================================
# Concorrencia real: duas reatribuicoes, mesma revisao - uma vencedora
# ============================================================

def test_duas_reatribuicoes_concorrentes_uma_vencedora(request):
    url_banco_teste = request.getfixturevalue("url_banco_teste")
    registro_coleta_id = _uuid()
    claim_id_original = _uuid()
    evento_id_revisao = _uuid()

    conn_setup = psycopg.connect(url_banco_teste)
    try:
        cur_setup = conn_setup.cursor()
        cur_setup.execute("SET LOCAL ROLE nsi_eventos_owner")
        # claim ja expirado, com revisao valida ('reatribuir') ja
        # registrada - construido diretamente (nunca via funcoes) para
        # nao gerar eventos extras alem do estritamente necessario para
        # satisfazer claims_revisao_atual_fk.
        cur_setup.execute(
            "INSERT INTO nsi_operacional.claims "
            "(registro_coleta_id, claim_id, token_hash, estado, criado_em, expira_em, versao_atual, "
            " revisao_atual_id, revisao_decisao, revisao_registrada_em) "
            "VALUES (%s, %s, %s, 'expirado_pendente_revisao', now() - interval '10 minutes', "
            "        now() - interval '5 minutes', 2, %s, 'reatribuir', now())",
            (registro_coleta_id, claim_id_original, _hash_valido("original"), evento_id_revisao),
        )
        cur_setup.execute(
            "INSERT INTO nsi_operacional.eventos_claim "
            "(evento_id, aggregate_type, aggregate_id, aggregate_version, tipo, claim_id, executado_por, payload) "
            "VALUES (%s, 'claim', %s, 2, 'revisao_de_abandono_registrada', %s, %s, %s)",
            (evento_id_revisao, registro_coleta_id, claim_id_original,
             psycopg.types.json.Jsonb({"role": "setup_de_teste"}),
             psycopg.types.json.Jsonb({"claim_id_revisado": claim_id_original, "decisao": "reatribuir"})),
        )
        conn_setup.commit()
    finally:
        conn_setup.close()

    try:
        # conn_b so e aberta DENTRO do try de conn_a - se a conexao de
        # conn_b falhar, conn_a ainda assim e sempre revertida e fechada,
        # nunca deixando um lock pendurado em nsi_test.
        conn_a = psycopg.connect(url_banco_teste)
        try:
            cur_a = conn_a.cursor()
            cur_a.execute("SET LOCAL ROLE nsi_eventos_owner")
            resultado_a = _reatribuir(cur_a, registro_coleta_id, evento_id_revisao, _hash_valido("worker-a"), "chave-a")
            assert resultado_a["sucesso"] is True
            # transacao de A permanece aberta - segura o lock da linha.

            conn_b = psycopg.connect(url_banco_teste)
            try:
                cur_b = conn_b.cursor()
                cur_b.execute("SET LOCAL ROLE nsi_eventos_owner")
                cur_b.execute("SET lock_timeout = '2000ms'")
                with pytest.raises(psycopg.errors.LockNotAvailable):
                    _reatribuir(cur_b, registro_coleta_id, evento_id_revisao, _hash_valido("worker-b"), "chave-b")
            finally:
                conn_b.rollback()
                conn_b.close()
        finally:
            conn_a.rollback()
            conn_a.close()
    finally:
        conn_cleanup = psycopg.connect(url_banco_teste)
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
                    "DELETE FROM nsi_operacional.claims WHERE registro_coleta_id = %s",
                    (registro_coleta_id,),
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
