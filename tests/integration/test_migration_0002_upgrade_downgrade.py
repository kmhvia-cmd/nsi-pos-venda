# -*- coding: utf-8 -*-
"""
NSI - tests/integration/test_migration_0002_upgrade_downgrade.py
(Sprint B, B3.2 - ADR-008, Parte 1 da B3 e correcoes de seguranca;
ciclo estendido ao head 0003 na B3.4, sem reabrir o gate nem o piso
0001 ja aprovados na B3.2)

Testes de integracao REAIS contra PostgreSQL - nunca SQLite, nunca mock -
do ciclo completo de downgrade/upgrade entre a revisao 0001 e o head
atual (0003), exclusivamente contra nsi_test (nunca nsi_dev - ver
docs/implementation/SPRINT-B-ESPECIFICACAO-TECNICA.md, plano de
execucao da B3.2/B3.4).

Revisoes EXPLICITAS em toda chamada ao Alembic (`upgrade 0003`,
`downgrade 0001`) - nunca `head`: identificador explicito evita
qualquer ambiguidade caso uma revisao futura mude o head novamente.

Nenhum teste deste arquivo chama pytest nem executa a suite completa
internamente - a unica invocacao externa e ao proprio Alembic, via
subprocess, no mesmo padrao ja usado em test_alembic_postgres.py (B2).

GATE DE IDENTIDADE OBRIGATORIO antes de qualquer downgrade: current_
database() = 'nsi_test', servidor local, porta 5432, E current_user =
'nsi_test_migrator' (extensao desta rodada sobre o padrao de B2, que so
verificava banco/servidor/porta) - qualquer divergencia aborta o teste
antes de a chamada ao Alembic ocorrer.

INVENTARIO ESTRUTURAL (correcao desta rodada): consulta pg_catalog.
pg_tables - nunca information_schema.tables. information_schema.tables
filtra linhas por PRIVILEGIO do usuario corrente (SELECT/INSERT/UPDATE/
DELETE/TRUNCATE/REFERENCES/TRIGGER) sobre cada tabela - e o migrator
('nsi_test_migrator') nao tem NENHUM privilegio direto em claims/
eventos_claim/comandos_idempotentes (pertencem a nsi_eventos_owner; a
migration 0002 revoga DML de PUBLIC e das tres roles funcionais; e a
membership do migrator em nsi_eventos_owner e WITH INHERIT FALSE - B3.1 -
entao o migrator so age como o owner apos um SET ROLE explicito, nunca
automaticamente). Por isso information_schema.tables devolvia so
'alembic_version' (unica tabela que o migrator realmente possui) mesmo
com as outras tres existindo de fato. pg_catalog.pg_tables lista relacoes
por CATALOGO, sem filtro de privilegio - reflete a existencia estrutural
real, independente de DML ou de search_path.

VAZAMENTO DE DSN (correcao desta rodada): nenhuma funcao de teste deste
arquivo recebe a fixture 'url_banco_teste' como parametro nomeado -
cada uma obtem a URL internamente via request.getfixturevalue(), para
que nenhuma falha de fixture (ex.: erro de conexao) chegue a exibir a
DSN no cabecalho de erro do pytest. Nenhum assert compara diretamente a
DSN bruta contra uma saida capturada (que imprimiria a DSN inteira no
diff de uma falha) - a checagem correspondente usa uma funcao auxiliar
que falha com MENSAGEM FIXA, nunca interpolando a DSN nem a saida
capturada.

Marcado 'pg_integration' (pytestmark) - pulado em execucao comum de
desenvolvimento quando TEST_DATABASE_URL esta ausente (tests/conftest.py);
falha explicitamente (nunca pula) quando NSI_REQUIRE_PG_TESTS=1.
"""
import os
import subprocess
import sys

import psycopg
import pytest

from config import mascarar_dsn

pytestmark = pytest.mark.pg_integration

NOME_SCHEMA = "nsi_operacional"
USUARIO_MIGRATOR_ESPERADO = "nsi_test_migrator"

TABELAS_DE_NEGOCIO_0002 = {"claims", "eventos_claim", "comandos_idempotentes"}


def _executar_alembic(*args: str, env: dict) -> "subprocess.CompletedProcess[str]":
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        capture_output=True,
        text=True,
        env=env,
    )


def _consultar_estado(url: str) -> dict:
    """
    Le, numa unica conexao, o carimbo de revisao (alembic_version) e o
    inventario de objetos de nsi_operacional - usado apos cada chamada ao
    Alembic para confirmar o estado real do banco, nunca presumido a
    partir do texto de saida do comando.

    pg_catalog.pg_tables - NUNCA information_schema.tables - para que o
    inventario nao dependa de privilegio DML nem do search_path da
    sessao (ver docstring do modulo).
    """
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT version_num FROM nsi_operacional.alembic_version")
            linha = cur.fetchone()
            versao = linha[0] if linha else None

            cur.execute(
                "SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname = %s",
                (NOME_SCHEMA,),
            )
            tabelas = {r[0] for r in cur.fetchall()}

            cur.execute(
                "SELECT tableowner FROM pg_catalog.pg_tables WHERE schemaname = %s AND tablename = 'claims'",
                (NOME_SCHEMA,),
            )
            linha_owner_claims = cur.fetchone()
            owner_claims = linha_owner_claims[0] if linha_owner_claims else None

            cur.execute(
                "SELECT tableowner FROM pg_catalog.pg_tables WHERE schemaname = %s AND tablename = 'alembic_version'",
                (NOME_SCHEMA,),
            )
            linha_owner_av = cur.fetchone()
            owner_alembic_version = linha_owner_av[0] if linha_owner_av else None

    return {
        "versao": versao,
        "tabelas": tabelas,
        "owner_claims": owner_claims,
        "owner_alembic_version": owner_alembic_version,
    }


def _comprovar_identidade_antes_de_destrutivo(url: str) -> None:
    """
    GATE OBRIGATORIO antes de qualquer 'alembic downgrade': comprova, por
    CONSULTA ATIVA apos conectar de fato - nunca apenas pela string de
    conexao - que o banco e exatamente 'nsi_test', o servidor e local, a
    porta e 5432, E o usuario de conexao e exatamente 'nsi_test_migrator'.
    Qualquer divergencia aborta este teste ANTES de qualquer chamada ao
    Alembic. Mensagens mostram somente banco/servidor/porta/usuario -
    nunca a DSN.
    """
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT current_database(), inet_server_addr(), inet_server_port(), current_user"
            )
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
    """
    Confirma ausencia da DSN bruta na saida capturada do Alembic, SEM
    jamais interpolar a DSN nem a saida capturada na mensagem de falha -
    mensagem deliberadamente FIXA (mesmo padrao de DSNInvalida em
    config.py), para que o proprio teste de seguranca nunca se torne o
    vazamento que ele existe para impedir.
    """
    if url in saida:
        pytest.fail(
            f"Vazamento de DSN detectado na saida do Alembic ({rotulo}) - "
            "a DSN de conexao apareceu na saida capturada. Mensagem fixa: "
            "nem a DSN nem a saida sao exibidas aqui."
        )


def test_identidade_do_banco_de_teste_e_comprovada(request):
    """Reaproveita _comprovar_identidade_antes_de_destrutivo como teste
    isolado - ver docstring da funcao para o que exatamente e verificado.
    A URL e obtida internamente (request.getfixturevalue), nunca como
    parametro nomeado da funcao de teste."""
    url = request.getfixturevalue("url_banco_teste")
    _comprovar_identidade_antes_de_destrutivo(url)


def test_ciclo_downgrade_0001_upgrade_0003(request):
    """
    Ciclo completo, adaptado na B3.4 para o head atual: estado inicial
    0003 (aplicado manualmente pelo operador antes desta suite rodar) ->
    (gate de identidade) -> downgrade 0001 -> confirma inventario ->
    upgrade 0003 -> terminando OBRIGATORIAMENTE em 0003. O piso 0001 e o
    gate de identidade sao exatamente os aprovados na B3.2 - nao foram
    reabertos.

    A identidade do banco (nsi_test, servidor local, porta 5432, usuario
    nsi_test_migrator) e comprovada ANTES do downgrade - unica chamada
    destrutiva deste ciclo. A URL e obtida internamente, nunca como
    parametro nomeado da funcao de teste.
    """
    url = request.getfixturevalue("url_banco_teste")
    env = {**os.environ, "NSI_DATABASE_ENV": "test"}

    # Estado inicial: 0003 (head) - o fluxo real aprovado aplica 'alembic
    # upgrade 0003' MANUALMENTE antes de rodar esta suite (ordem de
    # execucao da B3.4); este teste nunca faz o primeiro upgrade ele
    # mesmo. Nunca presumido, sempre confirmado antes de qualquer acao.
    estado_inicial = _consultar_estado(url)
    assert estado_inicial["versao"] == "0003", (
        f"Estado inicial inesperado: alembic_version={estado_inicial['versao']!r}, "
        "esperado '0003' antes deste teste rodar - o fluxo aprovado exige "
        "'alembic upgrade 0003' aplicado manualmente antes da suite."
    )
    assert estado_inicial["tabelas"] == ({"alembic_version"} | TABELAS_DE_NEGOCIO_0002), (
        "Inventario inicial precisa ser exatamente alembic_version mais as "
        f"tres tabelas de negocio - encontrado: {estado_inicial['tabelas']}"
    )
    assert estado_inicial["owner_claims"] == "nsi_eventos_owner"
    assert estado_inicial["owner_alembic_version"] == USUARIO_MIGRATOR_ESPERADO

    # GATE OBRIGATORIO antes do downgrade.
    _comprovar_identidade_antes_de_destrutivo(url)

    # downgrade 0001 - unica acao destrutiva deste ciclo.
    resultado_downgrade = _executar_alembic("downgrade", "0001", env=env)
    assert resultado_downgrade.returncode == 0, resultado_downgrade.stderr
    _assert_saida_alembic_sem_dsn(url, resultado_downgrade.stdout, "downgrade 0001 - stdout")
    _assert_saida_alembic_sem_dsn(url, resultado_downgrade.stderr, "downgrade 0001 - stderr")

    estado_pos_downgrade = _consultar_estado(url)
    assert estado_pos_downgrade["versao"] == "0001"
    assert estado_pos_downgrade["tabelas"] == {"alembic_version"}, (
        "Downgrade precisa remover exatamente as tres tabelas de negocio, "
        f"sem residuo - encontrado: {estado_pos_downgrade['tabelas']}"
    )

    # upgrade 0003 - o ciclo TERMINA aplicado em 0003 (head), exigencia
    # explicita da B3.4.
    resultado_upgrade = _executar_alembic("upgrade", "0003", env=env)
    assert resultado_upgrade.returncode == 0, resultado_upgrade.stderr
    _assert_saida_alembic_sem_dsn(url, resultado_upgrade.stdout, "upgrade 0003 - stdout")
    _assert_saida_alembic_sem_dsn(url, resultado_upgrade.stderr, "upgrade 0003 - stderr")

    estado_final = _consultar_estado(url)
    assert estado_final["versao"] == "0003", (
        "O ciclo de testes precisa terminar com nsi_test novamente em 0003 - "
        f"estado final encontrado: {estado_final['versao']!r}"
    )
    assert estado_final["tabelas"] == ({"alembic_version"} | TABELAS_DE_NEGOCIO_0002)
    assert estado_final["owner_claims"] == "nsi_eventos_owner"
    assert estado_final["owner_alembic_version"] == USUARIO_MIGRATOR_ESPERADO


def test_dsn_mascarada_nunca_contem_usuario_ou_senha(request):
    """Mesmo padrao ja usado em test_alembic_postgres.py (B2) - nenhuma
    credencial em texto puro em nenhuma representacao usada por este
    arquivo. A URL e obtida internamente, nunca como parametro nomeado
    da funcao de teste; o assert compara apenas a representacao JA
    MASCARADA, nunca a DSN bruta."""
    url = request.getfixturevalue("url_banco_teste")
    representacao_segura = mascarar_dsn(url)
    assert "@" not in representacao_segura
    assert "://" not in representacao_segura
