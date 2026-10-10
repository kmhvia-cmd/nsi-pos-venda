# -*- coding: utf-8 -*-
"""
NSI - tests/integration/test_migration_0005_upgrade_downgrade.py
(Sprint B, B4.3 - ADR-009)

Testes de integracao REAIS contra PostgreSQL - nunca SQLite, nunca mock -
do ciclo que atravessa o downgrade da 0005, exclusivamente contra nsi_test
(nunca nsi_dev - Especificacao Tecnica, Secao 18, "Criterios de rollback":
nenhum downgrade e executado em nsi_dev). Desde a B5.4 o head e 0006: o
ciclo parte de 0006 e volta a 0006 (0006 -> 0004 -> 0006), atravessando
tambem o downgrade da 0006, que restaura fn_criar_claim da 0003.

Revisoes EXPLICITAS em toda chamada ao Alembic (`downgrade 0004`,
`upgrade 0006`) - nunca `head`.

GATE DE IDENTIDADE OBRIGATORIO antes de qualquer downgrade: current_
database() = 'nsi_test', servidor local, porta 5432, current_user =
'nsi_test_migrator' - repetido antes de CADA acao destrutiva, inclusive
na recuperacao do 'finally'.

O que o ciclo comprova:
  - inventario somente leitura exato das cinco funcoes (owner,
    SECURITY DEFINER, search_path fixo, matriz de EXECUTE);
  - o downgrade remove exatamente as cinco funcoes e nada mais - nao toca
    tabelas, dados, eventos, recibos nem a role nsi_congelamento
    (membership e USAGE preservados);
  - o novo upgrade recria a mesma matriz, e as funcoes voltam a operar
    sobre os dados preservados.

DIVULGACAO DE RESIDUO INTENCIONAL: para provar que o downgrade nao toca
dados, o teste commita um lote sintetico (com um registro) e um recibo
sintetico de 'registrar_lote'. O lote e o registro permanecem como
residuo sintetico em nsi_test (sem eventos); o recibo e removido
explicitamente, pela propria chave, no 'finally' - nunca por remocao em
massa -, para nao bloquear o preflight do downgrade da 0004.

Nenhum teste chama pytest nem executa a suite completa internamente.
"""
import os
import subprocess
import sys

import psycopg
import pytest

from config import mascarar_dsn
from core.payload_hash import hash_registrar_lote
from tests.apoio_b4_3 import uuid_texto

pytestmark = pytest.mark.pg_integration

NOME_SCHEMA = "nsi_operacional"
USUARIO_MIGRATOR_ESPERADO = "nsi_test_migrator"

FUNCOES_0005 = (
    "fn_registrar_lote", "fn_registrar_congelamento", "fn_confirmar_disparo",
    "fn_registrar_correcao", "fn_registrar_tentativa_nao_resolvida",
)
FUNCOES_ATE_0004 = {
    "fn_criar_claim", "fn_registrar_heartbeat", "fn_liberar_claim", "fn_materializar_expiracao",
    "fn_registrar_revisao_abandono", "fn_reatribuir_claim",
    "fn_bloquear_alteracao_eventos_claim", "fn_bloquear_alteracao_eventos_lote",
    "fn_bloquear_alteracao_eventos_registro_coleta",
}
MATRIZ_EXECUTE = {
    "fn_registrar_lote": {"nsi_aplicacao"},
    "fn_registrar_congelamento": {"nsi_congelamento"},
    "fn_confirmar_disparo": {"nsi_operador_restrito"},
    "fn_registrar_correcao": {"nsi_aplicacao"},
    "fn_registrar_tentativa_nao_resolvida": {"nsi_aplicacao"},
}
TABELAS = {"alembic_version", "claims", "eventos_claim", "comandos_idempotentes",
           "lotes", "registros_coleta", "eventos_lote", "eventos_registro_coleta"}

# Head 0006 (B5.4): cinco tabelas, quatro funcoes de importacao e tres
# funcoes de trigger a mais - nenhuma delas existe em 0004.
REVISAO_HEAD = "0006"
TABELAS_0006 = {"importacoes_legado", "importacoes_legado_arquivos", "importacoes_legado_conclusoes",
                "lotes_legado", "registros_legado"}
FUNCOES_0006 = {
    "fn_iniciar_importacao_legado", "fn_importar_lote_legado", "fn_concluir_importacao_legado",
    "fn_verificar_paridade_legado", "fn_bloquear_alteracao_importacoes_legado",
    "fn_bloquear_alteracao_importacoes_legado_arquivos", "fn_bloquear_alteracao_importacoes_legado_conclusoes",
}

_CHAVE_SINTETICA = "chave-sintetica-teste-downgrade-0005"


def _executar_alembic(*args: str, env: dict) -> "subprocess.CompletedProcess[str]":
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        capture_output=True,
        text=True,
        env=env,
    )


def _consultar_estado(url: str) -> dict:
    """Le, numa unica conexao, revisao, tabelas, funcoes do schema, a matriz
    de EXECUTE das cinco funcoes da 0005 e o estado da role nsi_congelamento
    - sempre o estado real do banco, nunca presumido pela saida do Alembic."""
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT version_num FROM nsi_operacional.alembic_version")
            linha = cur.fetchone()
            versao = linha[0] if linha else None

            cur.execute("SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname = %s", (NOME_SCHEMA,))
            tabelas = {r[0] for r in cur.fetchall()}

            cur.execute("""
                SELECT p.proname, pg_get_userbyid(p.proowner), p.prosecdef, p.proconfig, p.oid
                  FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
                 WHERE n.nspname = %s
            """, (NOME_SCHEMA,))
            funcoes = {}
            for proname, dono, secdef, config, oid in cur.fetchall():
                cur.execute("""
                    SELECT COALESCE(array_agg(pg_get_userbyid(a.grantee) ORDER BY 1), ARRAY[]::text[])
                      FROM pg_catalog.pg_proc p CROSS JOIN LATERAL aclexplode(p.proacl) a
                     WHERE p.oid = %s AND a.privilege_type = 'EXECUTE' AND a.grantee <> p.proowner
                """, (oid,))
                grantees = set(cur.fetchone()[0])
                funcoes[proname] = {"dono": dono, "secdef": secdef, "config": config, "execute": grantees}

            cur.execute("""
                SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'nsi_congelamento'),
                       (SELECT count(*) FROM pg_catalog.pg_auth_members m
                          JOIN pg_catalog.pg_roles r ON r.oid = m.member JOIN pg_catalog.pg_roles g ON g.oid = m.roleid
                         WHERE g.rolname = 'nsi_congelamento' AND r.rolname = 'nsi_aplicacao'
                           AND NOT m.inherit_option AND m.set_option AND NOT m.admin_option),
                       has_schema_privilege('nsi_congelamento', 'nsi_operacional', 'USAGE')
            """)
            role_existe, membership_exata, usage = cur.fetchone()

    return {
        "versao": versao, "tabelas": tabelas, "funcoes": funcoes,
        "role_congelamento": (role_existe, membership_exata, usage),
    }


def _comprovar_identidade_antes_de_destrutivo(url: str) -> None:
    """GATE OBRIGATORIO antes de qualquer 'alembic downgrade' - mesmo
    mecanismo de test_migration_0002/0004_upgrade_downgrade.py."""
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database(), inet_server_addr(), inet_server_port(), current_user")
            banco_real, endereco_servidor, porta_real, usuario_real = cur.fetchone()

    assert banco_real == "nsi_test", (
        f"Identidade do banco nao comprovada: current_database()={banco_real!r}, "
        "esperado 'nsi_test'. Nenhuma acao adicional e executada."
    )
    assert endereco_servidor is None or str(endereco_servidor) in ("127.0.0.1", "::1"), (
        f"Servidor remoto detectado (inet_server_addr()={endereco_servidor!r}). "
        "Este teste e exclusivo de PostgreSQL LOCAL. Nenhuma acao adicional e executada."
    )
    assert porta_real == 5432, (
        f"Porta inesperada (inet_server_port()={porta_real!r}), esperado 5432. "
        "Nenhuma acao adicional e executada."
    )
    assert usuario_real == USUARIO_MIGRATOR_ESPERADO, (
        f"Usuario de conexao inesperado (current_user={usuario_real!r}), esperado "
        f"{USUARIO_MIGRATOR_ESPERADO!r}. Nenhuma acao adicional e executada."
    )


def _assert_saida_alembic_sem_dsn(url: str, saida: str, rotulo: str) -> None:
    if url in saida:
        pytest.fail(
            f"Vazamento de DSN detectado na saida do Alembic ({rotulo}) - "
            "a DSN de conexao apareceu na saida capturada. Mensagem fixa: "
            "nem a DSN nem a saida sao exibidas aqui."
        )


def _assert_inventario_0005(estado: dict) -> None:
    """Inventario do head (0006), com as cinco funcoes da 0005 conferidas
    uma a uma."""
    assert estado["versao"] == REVISAO_HEAD
    assert estado["tabelas"] == TABELAS | TABELAS_0006
    assert set(estado["funcoes"]) == FUNCOES_ATE_0004 | set(FUNCOES_0005) | FUNCOES_0006, (
        "O schema precisa ter exatamente as funcoes ate a 0004, as cinco da 0005 e as sete da 0006."
    )
    for nome in FUNCOES_0005:
        funcao = estado["funcoes"][nome]
        assert funcao["dono"] == "nsi_eventos_owner", nome
        assert funcao["secdef"] is True, nome
        assert funcao["config"] == ["search_path=pg_catalog, nsi_operacional, pg_temp"], nome
        assert funcao["execute"] == MATRIZ_EXECUTE[nome], nome


def _dados_sinteticos(url: str, lote_id: str) -> tuple:
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL ROLE nsi_eventos_owner")
            cur.execute("SELECT count(*) FROM nsi_operacional.lotes WHERE lote_id = %s", (lote_id,))
            lotes = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM nsi_operacional.comandos_idempotentes "
                        "WHERE comando = 'registrar_lote' AND chave_idempotencia = %s", (_CHAVE_SINTETICA,))
            recibos = cur.fetchone()[0]
    return lotes, recibos


def test_identidade_do_banco_de_teste_e_comprovada(request):
    url = request.getfixturevalue("url_banco_teste")
    _comprovar_identidade_antes_de_destrutivo(url)


def test_inventario_somente_leitura_do_head(request):
    url = request.getfixturevalue("url_banco_teste")
    estado = _consultar_estado(url)
    _assert_inventario_0005(estado)
    assert estado["role_congelamento"] == (True, 1, True)


def test_ciclo_downgrade_0004_upgrade_0006_preserva_dados_e_role(request):
    """Estado inicial 0006 -> (gate) -> downgrade 0004 -> confirma remocao
    exata das cinco funcoes, com tabelas, dados, recibo e role intactos ->
    upgrade 0006 -> confirma a mesma matriz e as funcoes operando sobre os
    dados preservados, terminando OBRIGATORIAMENTE em 0006."""
    url = request.getfixturevalue("url_banco_teste")
    env = {**os.environ, "NSI_DATABASE_ENV": "test"}
    lote_id = uuid_texto()
    registro = {"registro_coleta_id": uuid_texto(), "nome": "Pessoa Teste", "whatsapp": "5511900000004",
                "produto": "Produto Teste", "valido": True, "motivos_invalidez": None}

    estado_inicial = _consultar_estado(url)
    _assert_inventario_0005(estado_inicial)

    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL ROLE nsi_eventos_owner")
            cur.execute(
                "INSERT INTO nsi_operacional.lotes (lote_id, recebido_em, total_recebido, total_valido, total_invalido, "
                "status, horario_conceitual_congelamento, versao_eventos_atual) "
                "VALUES (%s, now() - interval '193 hours', 1, 1, 0, 'aguardando_d8', now() - interval '1 hour', 1)",
                (lote_id,),
            )
            cur.execute(
                "INSERT INTO nsi_operacional.registros_coleta (registro_coleta_id, lote_id, nome, produto, whatsapp, valido) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (registro["registro_coleta_id"], lote_id, registro["nome"], registro["produto"],
                 registro["whatsapp"], registro["valido"]),
            )
            cur.execute(
                "INSERT INTO nsi_operacional.comandos_idempotentes "
                "(comando, aggregate_id, chave_idempotencia, payload_hash, estado_processamento, resultado, concluido_em) "
                "VALUES ('registrar_lote', %s, %s, %s, 'concluido', %s, now())",
                (lote_id, _CHAVE_SINTETICA, hash_registrar_lote(lote_id, None, [registro]),
                 psycopg.types.json.Jsonb({"teste": "residuo-sintetico"})),
            )
        conn.commit()

    try:
        _comprovar_identidade_antes_de_destrutivo(url)
        resultado_downgrade = _executar_alembic("downgrade", "0004", env=env)
        assert resultado_downgrade.returncode == 0, resultado_downgrade.stderr
        _assert_saida_alembic_sem_dsn(url, resultado_downgrade.stdout, "downgrade 0004 - stdout")
        _assert_saida_alembic_sem_dsn(url, resultado_downgrade.stderr, "downgrade 0004 - stderr")

        estado_pos_downgrade = _consultar_estado(url)
        assert estado_pos_downgrade["versao"] == "0004"
        assert estado_pos_downgrade["tabelas"] == TABELAS
        assert set(estado_pos_downgrade["funcoes"]) == FUNCOES_ATE_0004, (
            "O downgrade precisa remover exatamente as cinco funcoes da 0005 (e os objetos da 0006), "
            "e nenhuma outra."
        )
        assert estado_pos_downgrade["role_congelamento"] == (True, 1, True), (
            "O downgrade nunca toca a role nsi_congelamento, sua membership ou seu USAGE."
        )
        assert _dados_sinteticos(url, lote_id) == (1, 1), "O downgrade nunca toca dados nem recibos."

        resultado_upgrade = _executar_alembic("upgrade", REVISAO_HEAD, env=env)
        assert resultado_upgrade.returncode == 0, resultado_upgrade.stderr
        _assert_saida_alembic_sem_dsn(url, resultado_upgrade.stdout, "upgrade 0006 - stdout")
        _assert_saida_alembic_sem_dsn(url, resultado_upgrade.stderr, "upgrade 0006 - stderr")

        estado_final = _consultar_estado(url)
        _assert_inventario_0005(estado_final)
        assert estado_final["role_congelamento"] == (True, 1, True)
        assert _dados_sinteticos(url, lote_id) == (1, 1)

        # As funcoes recriadas operam sobre os dados preservados.
        with psycopg.connect(url) as conn:
            with conn.cursor() as cur:
                cur.execute("SET LOCAL ROLE nsi_eventos_owner")
                cur.execute("SELECT nsi_operacional.fn_registrar_congelamento(%s)", (lote_id,))
                resultado = cur.fetchone()[0]
                assert resultado["sucesso"] is True
                assert resultado["total_valido_congelado"] == 1
            conn.rollback()
    finally:
        excecao_original_em_andamento = sys.exc_info()[0] is not None

        with psycopg.connect(url) as conn:
            with conn.cursor() as cur:
                cur.execute("SET LOCAL ROLE nsi_eventos_owner")
                cur.execute(
                    "DELETE FROM nsi_operacional.comandos_idempotentes "
                    "WHERE comando = 'registrar_lote' AND aggregate_id = %s AND chave_idempotencia = %s",
                    (lote_id, _CHAVE_SINTETICA),
                )
            conn.commit()

        _comprovar_identidade_antes_de_destrutivo(url)
        estado_para_recuperacao = _consultar_estado(url)
        if estado_para_recuperacao["versao"] != REVISAO_HEAD:
            resultado_recuperacao = _executar_alembic("upgrade", REVISAO_HEAD, env=env)
            _assert_saida_alembic_sem_dsn(url, resultado_recuperacao.stdout, "recuperacao final - stdout")
            _assert_saida_alembic_sem_dsn(url, resultado_recuperacao.stderr, "recuperacao final - stderr")
            if resultado_recuperacao.returncode != 0 and not excecao_original_em_andamento:
                pytest.fail(
                    "Falha ao recuperar nsi_test para 0006 apos o teste - stderr: "
                    f"{resultado_recuperacao.stderr[-500:] if resultado_recuperacao.stderr else '(vazio)'}"
                )

    estado_final = _consultar_estado(url)
    assert estado_final["versao"] == REVISAO_HEAD
    assert _dados_sinteticos(url, lote_id) == (1, 0), "O recibo sintetico nao pode sobreviver ao final deste teste."


def test_dsn_mascarada_nunca_contem_usuario_ou_senha(request):
    url = request.getfixturevalue("url_banco_teste")
    representacao_segura = mascarar_dsn(url)
    assert "@" not in representacao_segura
    assert "://" not in representacao_segura
