# -*- coding: utf-8 -*-
"""
NSI - tests/integration/test_idempotencia_e_permissoes_b4_3.py
(Sprint B, B4.3 - ADR-009, Secoes 7, 10 e 11)

Testes de integracao REAIS contra PostgreSQL, exclusivamente contra
nsi_test, cobrindo o que atravessa as cinco funcoes SECURITY DEFINER da
migration 0005:

  - matriz completa de GRANT/REVOKE EXECUTE (positiva e negativa), por
    SQLSTATE real - nunca apenas inspecao de ACL -, incluindo o caminho de
    autorizacao de nsi_congelamento (NOLOGIN, alcancada exclusivamente por
    SET ROLE a partir de nsi_aplicacao, com INHERIT FALSE);
  - PUBLIC sem EXECUTE; nenhuma DML ou leitura direta por role funcional;
  - SECURITY DEFINER, owner, search_path fixo e retorno JSONB;
  - executado_por_login = session_user da conexao real, de ponta a ponta;
  - replay sobrevivendo a reinicio de processo (nova conexao);
  - nenhum valor pessoal em evento ou recibo; nenhum segredo no recibo;
  - configuracao de log do servidor sem registro de comandos/parametros;
  - imutabilidade preservada (triggers da 0004 ativas).

DIVULGACAO DE RESIDUO INTENCIONAL: test_fluxo_completo_por_papel_e_
replay_em_nova_conexao exige COMMIT real (identidade por papel e replay
em nova conexao so existem sobre dados genuinamente persistidos). O lote,
seu registro e os eventos 'lote_criado', 'lote_congelado_d8' e
'disparo_confirmado' permanecem como residuo sintetico em nsi_test; os
TRES recibos criados pelo teste sao removidos explicitamente, pelas
proprias chaves, para nao bloquear o preflight do downgrade da 0004.
Todos os demais testes deste arquivo sao revertidos.

Nenhum teste chama pytest nem executa a suite completa internamente.
"""

import psycopg
import pytest
from psycopg.types.json import Jsonb

from config import resolver_url_banco_papel
from core.payload_hash import (
    hash_confirmar_disparo,
    hash_registrar_congelamento,
    hash_registrar_correcao,
    hash_registrar_lote,
    hash_registrar_tentativa_nao_resolvida,
)
from tests.apoio_b4_3 import posicionar_fronteira, registro_valido, uuid_texto

pytestmark = pytest.mark.pg_integration

FUNCOES_0005 = (
    "fn_registrar_lote", "fn_registrar_congelamento", "fn_confirmar_disparo",
    "fn_registrar_correcao", "fn_registrar_tentativa_nao_resolvida",
)
TABELAS_B4 = ("lotes", "registros_coleta", "eventos_lote", "eventos_registro_coleta", "comandos_idempotentes")


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


def _chamada_minima(nome_funcao: str):
    lote_id = uuid_texto()
    if nome_funcao == "fn_registrar_lote":
        registros = [registro_valido(1)]
        return ("SELECT nsi_operacional.fn_registrar_lote(%s, NULL, %s, %s, %s)",
                (lote_id, Jsonb(registros), "chave-matriz", hash_registrar_lote(lote_id, None, registros)))
    if nome_funcao == "fn_registrar_congelamento":
        return ("SELECT nsi_operacional.fn_registrar_congelamento(%s)", (lote_id,))
    if nome_funcao == "fn_confirmar_disparo":
        return ("SELECT nsi_operacional.fn_confirmar_disparo(%s, %s, %s, %s)",
                (lote_id, 1, "chave-matriz", hash_confirmar_disparo(lote_id, 1)))
    if nome_funcao == "fn_registrar_correcao":
        registro_id, valores = uuid_texto(), ("Nome", "5511900000000", "Produto", True, None)
        return ("SELECT nsi_operacional.fn_registrar_correcao(%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (lote_id, registro_id, *valores, "chave-matriz", hash_registrar_correcao(lote_id, registro_id, *valores)))
    if nome_funcao == "fn_registrar_tentativa_nao_resolvida":
        return ("SELECT nsi_operacional.fn_registrar_tentativa_nao_resolvida(%s, %s, %s, %s, %s)",
                (lote_id, "codigo_ausente", None, "chave-matriz",
                 hash_registrar_tentativa_nao_resolvida(lote_id, "codigo_ausente", None)))
    raise ValueError(nome_funcao)


# Papeis de conexao: os tres LOGIN da B3.1, e nsi_congelamento alcancada
# por SET ROLE a partir de nsi_aplicacao (unico caminho possivel).
PAPEIS = ("nsi_aplicacao", "nsi_expiracao", "nsi_operador_restrito", "nsi_congelamento")

_MATRIZ_PERMITIDA = {
    ("nsi_aplicacao", "fn_registrar_lote"),
    ("nsi_aplicacao", "fn_registrar_correcao"),
    ("nsi_aplicacao", "fn_registrar_tentativa_nao_resolvida"),
    ("nsi_congelamento", "fn_registrar_congelamento"),
    ("nsi_operador_restrito", "fn_confirmar_disparo"),
}
_MATRIZ_NEGADA = sorted({(p, f) for p in PAPEIS for f in FUNCOES_0005} - _MATRIZ_PERMITIDA)


def _conectar_como(papel: str):
    if papel == "nsi_congelamento":
        conn = psycopg.connect(resolver_url_banco_papel("nsi_aplicacao", "test"))
        conn.cursor().execute("SET LOCAL ROLE nsi_congelamento")
        return conn
    return psycopg.connect(resolver_url_banco_papel(papel, "test"))


# ============================================================
# Matriz de EXECUTE - por SQLSTATE real
# ============================================================

@pytest.mark.parametrize("papel,funcao", sorted(_MATRIZ_PERMITIDA))
def test_execute_permitido_conforme_matriz(papel, funcao):
    sql, params = _chamada_minima(funcao)
    conn = _conectar_como(papel)
    try:
        cur = conn.cursor()
        cur.execute(sql, params)  # nunca deve levantar InsufficientPrivilege
        resultado = cur.fetchone()[0]
        assert isinstance(resultado, dict)
        for chave_proibida in ("payload_hash", "chave", "chave_idempotencia", "dsn", "nome", "whatsapp", "produto"):
            assert chave_proibida not in resultado
    finally:
        conn.rollback()
        conn.close()


@pytest.mark.parametrize("papel,funcao", _MATRIZ_NEGADA)
def test_execute_negado_fora_da_matriz(papel, funcao):
    sql, params = _chamada_minima(funcao)
    conn = _conectar_como(papel)
    try:
        with pytest.raises(psycopg.errors.InsufficientPrivilege) as exc_info:
            conn.cursor().execute(sql, params)
        assert exc_info.value.sqlstate == "42501"
    finally:
        conn.rollback()
        conn.close()


def test_nsi_aplicacao_sem_set_role_nao_congela():
    """A membership e INHERIT FALSE: sem SET ROLE explicito, nsi_aplicacao
    nao exerce o privilegio de nsi_congelamento."""
    sql, params = _chamada_minima("fn_registrar_congelamento")
    conn = psycopg.connect(resolver_url_banco_papel("nsi_aplicacao", "test"))
    try:
        with pytest.raises(psycopg.errors.InsufficientPrivilege) as exc_info:
            conn.cursor().execute(sql, params)
        assert exc_info.value.sqlstate == "42501"
    finally:
        conn.rollback()
        conn.close()


@pytest.mark.parametrize("papel", ["nsi_expiracao", "nsi_operador_restrito"])
def test_somente_nsi_aplicacao_pode_assumir_nsi_congelamento(papel):
    conn = psycopg.connect(resolver_url_banco_papel(papel, "test"))
    try:
        with pytest.raises(psycopg.errors.InsufficientPrivilege) as exc_info:
            conn.cursor().execute("SET LOCAL ROLE nsi_congelamento")
        assert exc_info.value.sqlstate == "42501"
    finally:
        conn.rollback()
        conn.close()


def test_set_role_tem_escopo_de_transacao():
    """SET LOCAL ROLE se desfaz no fim da transacao: a transacao seguinte
    volta a ser nsi_aplicacao e perde o privilegio de congelar."""
    sql, params = _chamada_minima("fn_registrar_congelamento")
    conn = _conectar_como("nsi_congelamento")
    try:
        conn.cursor().execute(sql, params)
        conn.rollback()
        cur = conn.cursor()
        cur.execute("SELECT current_user, session_user")
        assert cur.fetchone() == ("nsi_aplicacao", "nsi_aplicacao")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(sql, params)
    finally:
        conn.rollback()
        conn.close()


def test_public_e_nsi_expiracao_sem_execute_em_nenhuma(cur):
    cur.execute("""
        SELECT p.proname,
               EXISTS (SELECT 1 FROM aclexplode(p.proacl) a WHERE a.grantee = 0 AND a.privilege_type = 'EXECUTE'),
               has_function_privilege('nsi_expiracao', p.oid, 'EXECUTE')
          FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
         WHERE n.nspname = 'nsi_operacional' AND p.proname = ANY(%s)
    """, (list(FUNCOES_0005),))
    linhas = cur.fetchall()
    assert len(linhas) == 5
    for proname, public_tem, expiracao_tem in linhas:
        assert public_tem is False, proname
        assert expiracao_tem is False, proname


@pytest.mark.parametrize("papel", PAPEIS)
@pytest.mark.parametrize("tabela", TABELAS_B4)
def test_nenhuma_role_funcional_le_ou_escreve_diretamente(papel, tabela):
    conn = _conectar_como(papel)
    try:
        cur = conn.cursor()
        cur.execute("SAVEPOINT sp")
        with pytest.raises(psycopg.errors.InsufficientPrivilege) as exc_info:
            cur.execute(f"SELECT 1 FROM nsi_operacional.{tabela} LIMIT 1")
        assert exc_info.value.sqlstate == "42501"
        cur.execute("ROLLBACK TO SAVEPOINT sp")
        with pytest.raises(psycopg.errors.InsufficientPrivilege) as exc_info:
            cur.execute(f"DELETE FROM nsi_operacional.{tabela}")
        assert exc_info.value.sqlstate == "42501"
    finally:
        conn.rollback()
        conn.close()


# ============================================================
# SECURITY DEFINER, owner, search_path, retorno
# ============================================================

def test_cinco_funcoes_security_definer_com_search_path_fixo(cur):
    cur.execute("""
        SELECT p.proname, pg_get_userbyid(p.proowner), p.prosecdef, p.proconfig,
               l.lanname, format_type(p.prorettype, NULL)
          FROM pg_catalog.pg_proc p
          JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
          JOIN pg_catalog.pg_language l ON l.oid = p.prolang
         WHERE n.nspname = 'nsi_operacional' AND p.proname = ANY(%s)
    """, (list(FUNCOES_0005),))
    linhas = {r[0]: r[1:] for r in cur.fetchall()}
    assert set(linhas) == set(FUNCOES_0005)
    for proname, (dono, secdef, config, linguagem, retorno) in linhas.items():
        assert dono == "nsi_eventos_owner", proname
        assert secdef is True, proname
        assert config == ["search_path=pg_catalog, nsi_operacional, pg_temp"], proname
        assert linguagem == "plpgsql", proname
        assert retorno == "jsonb", proname


def test_security_definer_escreve_por_quem_nao_tem_privilegio_de_tabela():
    """nsi_aplicacao nao tem nenhum privilegio nas tabelas, mas a funcao
    (executada com os direitos do owner) cria o lote."""
    conn = psycopg.connect(resolver_url_banco_papel("nsi_aplicacao", "test"))
    try:
        cur = conn.cursor()
        sql, params = _chamada_minima("fn_registrar_lote")
        cur.execute(sql, params)
        assert cur.fetchone()[0]["sucesso"] is True
    finally:
        conn.rollback()
        conn.close()


def test_triggers_de_imutabilidade_continuam_ativas(cur):
    cur.execute("""
        SELECT tgname, tgenabled FROM pg_catalog.pg_trigger
         WHERE tgname IN ('eventos_lote_bloqueia_alteracao', 'eventos_registro_coleta_bloqueia_alteracao')
    """)
    assert dict(cur.fetchall()) == {
        "eventos_lote_bloqueia_alteracao": "O", "eventos_registro_coleta_bloqueia_alteracao": "O"}


# ============================================================
# Fluxo completo por papel: session_user e replay em nova conexao
# ============================================================

def test_fluxo_completo_por_papel_e_replay_em_nova_conexao(request):
    url_owner = request.getfixturevalue("url_banco_teste")
    url_aplicacao = resolver_url_banco_papel("nsi_aplicacao", "test")
    url_operador = resolver_url_banco_papel("nsi_operador_restrito", "test")
    lote_id = uuid_texto()
    registros = [registro_valido(1)]
    chave_lote, chave_disparo = "chave-fluxo-lote", "chave-fluxo-disparo"
    hash_lote = hash_registrar_lote(lote_id, None, registros)

    try:
        conn = psycopg.connect(url_aplicacao)
        try:
            cur = conn.cursor()
            cur.execute("SELECT nsi_operacional.fn_registrar_lote(%s, NULL, %s, %s, %s)",
                        (lote_id, Jsonb(registros), chave_lote, hash_lote))
            resultado_lote = cur.fetchone()[0]
            assert resultado_lote["sucesso"] is True
            conn.commit()
        finally:
            conn.close()

        # Nova conexao - simula reinicio de processo: so o persistido sobrevive.
        conn = psycopg.connect(url_aplicacao)
        try:
            cur = conn.cursor()
            cur.execute("SELECT nsi_operacional.fn_registrar_lote(%s, NULL, %s, %s, %s)",
                        (lote_id, Jsonb(registros), chave_lote, hash_lote))
            assert cur.fetchone()[0] == resultado_lote
            conn.rollback()
        finally:
            conn.close()

        conn = psycopg.connect(url_owner)
        try:
            cur = conn.cursor()
            cur.execute("SET LOCAL ROLE nsi_eventos_owner")
            posicionar_fronteira(cur, lote_id, "-1 second")
            conn.commit()
        finally:
            conn.close()

        conn = _conectar_como("nsi_congelamento")
        try:
            cur = conn.cursor()
            cur.execute("SELECT nsi_operacional.fn_registrar_congelamento(%s)", (lote_id,))
            assert cur.fetchone()[0]["sucesso"] is True
            conn.commit()
        finally:
            conn.close()

        conn = psycopg.connect(url_operador)
        try:
            cur = conn.cursor()
            cur.execute("SELECT nsi_operacional.fn_confirmar_disparo(%s, %s, %s, %s)",
                        (lote_id, 1, chave_disparo, hash_confirmar_disparo(lote_id, 1)))
            assert cur.fetchone()[0]["sucesso"] is True
            conn.commit()
        finally:
            conn.close()

        conn = psycopg.connect(url_owner)
        try:
            cur = conn.cursor()
            cur.execute("SET LOCAL ROLE nsi_eventos_owner")
            cur.execute("SELECT tipo, executado_por_login FROM nsi_operacional.eventos_lote "
                        "WHERE aggregate_id = %s ORDER BY aggregate_version", (lote_id,))
            assert cur.fetchall() == [
                ("lote_criado", "nsi_aplicacao"),
                ("lote_congelado_d8", "nsi_aplicacao"),  # SET ROLE nao altera session_user
                ("disparo_confirmado", "nsi_operador_restrito"),
            ]
            cur.execute("SELECT disparo_confirmado_por_login, status FROM nsi_operacional.lotes WHERE lote_id = %s",
                        (lote_id,))
            assert cur.fetchone() == ("nsi_operador_restrito", "disparo_confirmado")
            cur.execute("SELECT count(*) FROM nsi_operacional.eventos_lote "
                        "WHERE aggregate_id = %s AND executado_por_login = 'nsi_eventos_owner'", (lote_id,))
            assert cur.fetchone()[0] == 0  # nunca current_user
            # Os tres recibos persistidos carregam exatamente o hash canonico
            # do modulo de producao - inclusive o do congelamento, calculado
            # dentro da funcao SQL.
            cur.execute("SELECT comando, payload_hash FROM nsi_operacional.comandos_idempotentes "
                        "WHERE aggregate_id = %s ORDER BY comando", (lote_id,))
            assert cur.fetchall() == [
                ("confirmar_disparo", hash_confirmar_disparo(lote_id, 1)),
                ("registrar_congelamento", hash_registrar_congelamento(lote_id)),
                ("registrar_lote", hash_lote),
            ]
            conn.rollback()
        finally:
            conn.close()
    finally:
        conn = psycopg.connect(url_owner)
        try:
            cur = conn.cursor()
            cur.execute("SET LOCAL ROLE nsi_eventos_owner")
            for comando, chave in (("registrar_lote", chave_lote), ("registrar_congelamento", lote_id),
                                   ("confirmar_disparo", chave_disparo)):
                cur.execute(
                    "DELETE FROM nsi_operacional.comandos_idempotentes "
                    "WHERE comando = %s AND aggregate_id = %s AND chave_idempotencia = %s",
                    (comando, lote_id, chave),
                )
            conn.commit()
        finally:
            conn.close()


# ============================================================
# Privacidade: nenhum valor pessoal em evento ou recibo
# ============================================================

def test_nenhum_valor_pessoal_em_evento_ou_recibo(cur):
    cur.execute("SAVEPOINT sp")
    try:
        lote_id = uuid_texto()
        pessoal = {"nome": "NOME-PRIVADO-VARREDURA", "whatsapp": "5511912345678", "produto": "PRODUTO-PRIVADO-VARREDURA"}
        valido = {"registro_coleta_id": uuid_texto(), **pessoal, "valido": True, "motivos_invalidez": None}
        invalido = {"registro_coleta_id": uuid_texto(), "nome": None, "whatsapp": "5511987654321",
                    "produto": "PRODUTO-PRIVADO-VARREDURA", "valido": False, "motivos_invalidez": ["nome_ausente"]}
        retornos = []
        cur.execute("SELECT nsi_operacional.fn_registrar_lote(%s, NULL, %s, %s, %s)",
                    (lote_id, Jsonb([valido, invalido]), "chave-privacidade",
                     hash_registrar_lote(lote_id, None, [valido, invalido])))
        retornos.append(cur.fetchone()[0])
        correcao = ("NOME-CORRIGIDO-PRIVADO", "5511955554444", "PRODUTO-CORRIGIDO-PRIVADO")
        cur.execute("SELECT nsi_operacional.fn_registrar_correcao(%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (lote_id, invalido["registro_coleta_id"], *correcao, True, None, "chave-privacidade-c",
                     hash_registrar_correcao(lote_id, invalido["registro_coleta_id"], *correcao, True, None)))
        retornos.append(cur.fetchone()[0])
        cur.execute("SELECT nsi_operacional.fn_registrar_tentativa_nao_resolvida(%s, %s, %s, %s, %s)",
                    (lote_id, "codigo_ausente", None, "chave-privacidade-t",
                     hash_registrar_tentativa_nao_resolvida(lote_id, "codigo_ausente", None)))
        retornos.append(cur.fetchone()[0])
        posicionar_fronteira(cur, lote_id, "-1 second")
        cur.execute("SELECT nsi_operacional.fn_registrar_congelamento(%s)", (lote_id,))
        retornos.append(cur.fetchone()[0])
        cur.execute("SELECT nsi_operacional.fn_confirmar_disparo(%s, %s, %s, %s)",
                    (lote_id, 2, "chave-privacidade-d", hash_confirmar_disparo(lote_id, 2)))
        retornos.append(cur.fetchone()[0])
        assert all(r["sucesso"] for r in retornos)

        ids_registros = [valido["registro_coleta_id"], invalido["registro_coleta_id"]]
        cur.execute("""
            SELECT (SELECT string_agg(e::text, ' ') FROM nsi_operacional.eventos_lote e WHERE e.aggregate_id = %s),
                   (SELECT string_agg(e::text, ' ') FROM nsi_operacional.eventos_registro_coleta e
                     WHERE e.aggregate_id = ANY(%s::uuid[])),
                   (SELECT string_agg(c.resultado::text, ' ') FROM nsi_operacional.comandos_idempotentes c
                     WHERE c.aggregate_id = %s OR c.aggregate_id = ANY(%s::uuid[]))
        """, (lote_id, ids_registros, lote_id, ids_registros))
        textos = [t or "" for t in cur.fetchone()] + [str(r) for r in retornos]
        valores = list(pessoal.values()) + [invalido["whatsapp"], *correcao]
        for texto in textos:
            for valor in valores:
                if valor in texto:
                    pytest.fail("Valor pessoal encontrado em evento, recibo ou retorno - mensagem fixa, sem o valor.")
        # Sanidade: a varredura realmente cobriu os eventos e os recibos.
        assert textos[0] and textos[1] and textos[2]
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_log_do_servidor_nao_registra_comandos_nem_parametros(cur):
    """Verificacao de ambiente, fora das funcoes (Especificacao Tecnica,
    Secao 18, "Criterios de seguranca"): as chamadas carregam valores
    pessoais como parametros vinculados - a configuracao de log do
    servidor nao pode registra-los, nem no caminho normal, nem por
    duracao, nem por amostragem, nem em erro."""
    configuracao = {}
    for nome in ("log_statement", "log_min_duration_statement", "log_min_duration_sample",
                 "log_statement_sample_rate", "log_transaction_sample_rate", "log_parameter_max_length_on_error"):
        cur.execute("SELECT current_setting(%s)", (nome,))
        configuracao[nome] = cur.fetchone()[0]

    assert configuracao["log_statement"] in ("none", "ddl"), configuracao["log_statement"]
    assert configuracao["log_min_duration_statement"] == "-1", configuracao["log_min_duration_statement"]
    assert configuracao["log_min_duration_sample"] == "-1" or float(configuracao["log_statement_sample_rate"]) == 0
    assert float(configuracao["log_transaction_sample_rate"]) == 0
    assert configuracao["log_parameter_max_length_on_error"] == "0"


def _chamada_com_chave_e_hash(nome_funcao: str, chave: str, payload_hash: str):
    """Chamada valida em tudo, exceto chave e payload_hash, que sao os
    informados. Devolve tambem o aggregate_id do recibo que seria reservado."""
    lote_id = uuid_texto()
    if nome_funcao == "fn_registrar_lote":
        return ("SELECT nsi_operacional.fn_registrar_lote(%s, NULL, %s, %s, %s)",
                (lote_id, Jsonb([registro_valido(1)]), chave, payload_hash), lote_id)
    if nome_funcao == "fn_confirmar_disparo":
        return ("SELECT nsi_operacional.fn_confirmar_disparo(%s, %s, %s, %s)",
                (lote_id, 1, chave, payload_hash), lote_id)
    if nome_funcao == "fn_registrar_correcao":
        registro_id = uuid_texto()
        return ("SELECT nsi_operacional.fn_registrar_correcao(%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (lote_id, registro_id, "Nome", "5511900000000", "Produto", True, None, chave, payload_hash), registro_id)
    if nome_funcao == "fn_registrar_tentativa_nao_resolvida":
        return ("SELECT nsi_operacional.fn_registrar_tentativa_nao_resolvida(%s, %s, %s, %s, %s)",
                (lote_id, "codigo_ausente", None, chave, payload_hash), lote_id)
    raise ValueError(nome_funcao)


FUNCOES_COM_CHAVE = ("fn_registrar_lote", "fn_confirmar_disparo", "fn_registrar_correcao",
                     "fn_registrar_tentativa_nao_resolvida")
HASH_VALIDO = hash_registrar_lote("00000000-0000-4000-8000-000000000000", None, [])
CHAVE_VALIDA = "CHAVE-DE-TESTE-NUNCA-EXPOSTA"
ENTRADAS_DE_RECIBO_INVALIDAS = [
    ("chave_vazia", "", HASH_VALIDO),
    ("chave_201_caracteres", "K" * 201, HASH_VALIDO),
    ("hash_maiusculo", CHAVE_VALIDA, HASH_VALIDO.upper()),
    ("hash_63_caracteres", CHAVE_VALIDA, HASH_VALIDO[:63]),
    ("hash_nao_hexadecimal", CHAVE_VALIDA, "g" * 64),
]


@pytest.mark.parametrize("funcao", FUNCOES_COM_CHAVE)
@pytest.mark.parametrize("rotulo,chave,payload_hash", ENTRADAS_DE_RECIBO_INVALIDAS,
                         ids=[e[0] for e in ENTRADAS_DE_RECIBO_INVALIDAS])
def test_chave_ou_hash_fora_do_formato_e_recusado_antes_da_reserva(cur, funcao, rotulo, chave, payload_hash):
    """Chave vazia, chave com mais de 200 caracteres ou payload_hash fora do
    formato SHA-256 hexadecimal minusculo sao violacao estrutural (22000),
    detectada ANTES do INSERT em comandos_idempotentes: o CHECK da tabela
    nunca e alcancado, e por isso o DETAIL nativo (que conteria a linha
    inteira, com o hash correlacionavel) nunca e produzido."""
    sql, params, aggregate_id = _chamada_com_chave_e_hash(funcao, chave, payload_hash)
    cur.execute("SAVEPOINT sp")
    with pytest.raises(psycopg.Error) as exc_info:
        cur.execute(sql, params)
    exc = exc_info.value
    assert exc.sqlstate == "22000"
    assert exc.diag.message_primary == "entrada_estrutural_invalida"
    assert exc.diag.message_detail is None
    assert exc.diag.message_hint is None
    # Nenhuma constraint envolvida: o INSERT do recibo nunca foi executado.
    assert exc.diag.constraint_name is None
    texto_erro = " ".join(str(x) for x in (exc, exc.diag.message_primary, exc.diag.message_detail,
                                          exc.diag.message_hint, exc.diag.context) if x)
    for valor in (chave, payload_hash, HASH_VALIDO, CHAVE_VALIDA):
        if valor and valor in texto_erro:
            pytest.fail("Chave ou payload_hash apareceu no erro - mensagem fixa, sem o valor.")
    cur.execute("ROLLBACK TO SAVEPOINT sp")
    cur.execute("SELECT count(*) FROM nsi_operacional.comandos_idempotentes WHERE aggregate_id = %s", (aggregate_id,))
    assert cur.fetchone()[0] == 0


@pytest.mark.parametrize("funcao", FUNCOES_COM_CHAVE)
def test_limites_validos_da_chave_sao_aceitos(cur, funcao):
    """Fronteira do CHECK de comandos_idempotentes: 1 e 200 caracteres sao
    aceitos - a validacao antecipada nao e mais restritiva que a tabela."""
    for chave in ("k", "K" * 200):
        sql, params, aggregate_id = _chamada_com_chave_e_hash(funcao, chave, HASH_VALIDO)
        cur.execute("SAVEPOINT sp")
        cur.execute(sql, params)
        assert isinstance(cur.fetchone()[0], dict)
        cur.execute("SELECT count(*) FROM nsi_operacional.comandos_idempotentes "
                    "WHERE aggregate_id = %s AND chave_idempotencia = %s", (aggregate_id, chave))
        assert cur.fetchone()[0] == 1
        cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_recibo_nunca_contem_chave_hash_ou_segredo(cur):
    cur.execute("SAVEPOINT sp")
    try:
        lote_id = uuid_texto()
        registros = [registro_valido(1)]
        payload_hash = hash_registrar_lote(lote_id, None, registros)
        cur.execute("SELECT nsi_operacional.fn_registrar_lote(%s, NULL, %s, %s, %s)",
                    (lote_id, Jsonb(registros), "chave-recibo-segredo", payload_hash))
        cur.execute("SELECT resultado FROM nsi_operacional.comandos_idempotentes "
                    "WHERE comando = 'registrar_lote' AND aggregate_id = %s", (lote_id,))
        resultado = cur.fetchone()[0]
        proibidas = {"payload_hash", "chave", "chave_idempotencia", "dsn", "nome", "whatsapp", "produto", "registros"}
        assert not (set(resultado.keys()) & proibidas)
        assert "chave-recibo-segredo" not in str(resultado) and payload_hash not in str(resultado)
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp")
