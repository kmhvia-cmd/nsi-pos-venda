# -*- coding: utf-8 -*-
"""
NSI - tests/integration/test_alembic_postgres.py (Sprint B, B2.2/B2.3 - ADR-008)

Testes de integracao REAIS contra PostgreSQL - nunca SQLite, nunca mock,
para as garantias de transacao, upgrade/downgrade e ausencia de vazamento
de credenciais (Especificacao Tecnica da Sprint B).

Marcados 'pg_integration' (pytestmark, abaixo) - pulados em execucao comum
de desenvolvimento quando TEST_DATABASE_URL esta ausente (ver
tests/conftest.py); falham explicitamente (nunca pulam) quando
NSI_REQUIRE_PG_TESTS=1 (comando de aceite da B2/B3 - ver docstring de
tests/conftest.py para os comandos PowerShell/Bash completos).

Nesta rodada (B2.2), estes testes sao apenas CRIADOS e COLETAVEIS - nenhuma
acao real contra PostgreSQL foi executada nesta sessao (nenhum banco, role
ou schema foi provisionado; nenhum comando de aceite com TEST_DATABASE_URL
definida foi rodado).
"""
import os
import subprocess
import sys

import psycopg
import pytest

from config import mascarar_dsn

pytestmark = pytest.mark.pg_integration

NOME_SCHEMA = "nsi_operacional"

# Sete tabelas de negocio existentes no head atual (0005, ADR-008/ADR-009)
# - tres da B3 (migration 0002) mais quatro da B4 (migration 0004); a
# migration 0005 (B4.3) cria somente funcoes, nenhuma tabela.
# Corrigido nesta rodada: quando este arquivo foi escrito (B2.2), o head
# nao criava nenhuma tabela de negocio - isso deixou de ser verdade a
# partir da migration 0002 e permanece assim no head atual.
TABELAS_DE_NEGOCIO_HEAD_0004 = {
    "claims", "eventos_claim", "comandos_idempotentes",
    "lotes", "registros_coleta", "eventos_lote", "eventos_registro_coleta",
}


def _executar_alembic(*args: str, env: dict) -> "subprocess.CompletedProcess[str]":
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        capture_output=True,
        text=True,
        env=env,
    )


def _listar_tabelas_do_schema(url: str) -> set:
    """pg_catalog.pg_tables - NUNCA information_schema.tables. A segunda
    filtra linhas por PRIVILEGIO do usuario corrente (SELECT/INSERT/
    UPDATE/DELETE/...) sobre cada tabela - e o migrator (nsi_test_migrator)
    nao tem NENHUM privilegio direto nas tabelas de negocio (pertencem a
    nsi_eventos_owner; membership do migrator e WITH INHERIT FALSE -
    B3.1). Corrigido nesta rodada: essa troca ficou mascarada desde a
    B2.2 porque, na epoca, o head realmente nao criava tabela de negocio
    nenhuma - o defeito so se tornou visivel quando o inventario
    esperado deixou de ser vazio. pg_catalog.pg_tables lista relacoes
    por CATALOGO, sem filtro de privilegio - reflete a existencia
    estrutural real, independente de DML ou de search_path (mesmo
    padrao ja usado em test_migration_0002/0004_upgrade_downgrade.py)."""
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname = %s",
                (NOME_SCHEMA,),
            )
            return {linha[0] for linha in cur.fetchall()}


def _consultar_revisao_atual(url: str) -> str | None:
    """Le o carimbo de revisao atual, sem presumir nada a partir da
    saida de nenhum comando do Alembic - usado exclusivamente pela
    recuperacao obrigatoria do ciclo destrutivo (B4.2)."""
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT version_num FROM nsi_operacional.alembic_version")
            linha = cur.fetchone()
            return linha[0] if linha else None


def _comprovar_identidade_banco_teste(url: str) -> None:
    """
    Protecao contra banco de producao (Especificacao Tecnica, Ponto 5) e
    contra servidor remoto: nunca basta comparar strings de URL - apos
    conectar de fato, confirma por CONSULTA ATIVA que o banco e exatamente
    'nsi_test', que o servidor e local e que a porta e a esperada. Nunca
    confia apenas no que a string de conexao alegava.

    Usada por qualquer teste que vá executar uma acao destrutiva
    (downgrade) - a comprovacao ocorre e falha ANTES de qualquer chamada
    ao Alembic, nunca depois.
    """
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT current_database(), inet_server_addr(), inet_server_port()"
            )
            banco_real, endereco_servidor, porta_real = cur.fetchone()

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


def test_identidade_do_banco_de_teste_e_comprovada(url_banco_teste):
    """Reaproveita _comprovar_identidade_banco_teste como teste isolado -
    ver docstring da funcao para o que exatamente e verificado."""
    _comprovar_identidade_banco_teste(url_banco_teste)


def test_upgrade_downgrade_upgrade_com_inventario_do_head(url_banco_teste):
    """
    Ciclo completo exigido pelo comando de aceite: upgrade -> downgrade ->
    novo upgrade, com verificacao do CONJUNTO EXATO de objetos em cada
    momento - nunca presumido (Especificacao Tecnica, Ponto 3: o
    comportamento real de 'alembic_version' apos downgrade e confirmado
    aqui, no momento em que o teste roda de fato, nao assumido no
    planejamento).

    Renomeado nesta rodada (B4.2): o nome antigo
    ('..._sem_tabela_de_negocio') so era verdade na B2.2, quando o head
    nao criava nenhuma tabela de negocio. Desde a migration 0002, o head
    sempre cria tabelas de negocio reais - o nome e a verificacao agora
    refletem exatamente o inventario esperado no head atual (0005).

    A identidade do banco (nsi_test, servidor local, porta 5432) e
    comprovada aqui dentro, ANTES de qualquer chamada ao Alembic - inclusive
    antes do primeiro upgrade, nunca apenas antes do downgrade. Se a
    comprovacao falhar, o teste falha imediatamente e nenhuma acao do
    Alembic (nem upgrade, nem downgrade) chega a ser executada. O gate
    e repetido explicitamente tambem imediatamente antes do downgrade.

    RECUPERACAO OBRIGATORIA (B4.2): todo o ciclo destrutivo roda dentro
    de um try/finally. O finally repete o gate completo de identidade,
    consulta a revisao atual e executa somente 'alembic upgrade head'
    se nsi_test nao estiver no head - nunca contra nsi_dev - confirmando
    ao final que o head resolvido e exatamente '0005' (o head atual do
    projeto nesta rodada; este teste continua validando 'head'/'base'
    semanticamente, nunca fixado em '0005' como alvo literal do ciclo
    em si). Se ja houver uma excecao original em andamento, uma falha
    da propria recuperacao nunca a mascara - e apenas reportada via
    'print', sem DSN nem credenciais.
    """
    _comprovar_identidade_banco_teste(url_banco_teste)

    env = {**os.environ, "NSI_DATABASE_ENV": "test"}

    try:
        resultado_upgrade_1 = _executar_alembic("upgrade", "head", env=env)
        assert resultado_upgrade_1.returncode == 0, resultado_upgrade_1.stderr
        assert url_banco_teste not in resultado_upgrade_1.stdout
        assert url_banco_teste not in resultado_upgrade_1.stderr

        tabelas_pos_upgrade = _listar_tabelas_do_schema(url_banco_teste)
        assert tabelas_pos_upgrade == ({"alembic_version"} | TABELAS_DE_NEGOCIO_HEAD_0004), (
            "Apos 'upgrade head', o inventario precisa ser exatamente alembic_version "
            f"mais as sete tabelas de negocio do head atual (0005) - encontrado: {tabelas_pos_upgrade}"
        )

        # GATE OBRIGATORIO antes de qualquer downgrade.
        _comprovar_identidade_banco_teste(url_banco_teste)

        resultado_downgrade = _executar_alembic("downgrade", "base", env=env)
        assert resultado_downgrade.returncode == 0, resultado_downgrade.stderr
        assert url_banco_teste not in resultado_downgrade.stdout
        assert url_banco_teste not in resultado_downgrade.stderr

        tabelas_pos_downgrade = _listar_tabelas_do_schema(url_banco_teste)
        assert tabelas_pos_downgrade == {"alembic_version"}, (
            "Apos 'downgrade base', o inventario precisa ser exatamente alembic_version, "
            f"sem nenhuma tabela de negocio - encontrado: {tabelas_pos_downgrade}"
        )

        resultado_upgrade_2 = _executar_alembic("upgrade", "head", env=env)
        assert resultado_upgrade_2.returncode == 0, resultado_upgrade_2.stderr

        tabelas_finais = _listar_tabelas_do_schema(url_banco_teste)
        assert tabelas_finais == ({"alembic_version"} | TABELAS_DE_NEGOCIO_HEAD_0004), (
            "Apos o segundo 'upgrade head', o inventario precisa ser exatamente "
            f"alembic_version mais as sete tabelas de negocio - encontrado: {tabelas_finais}"
        )
    finally:
        excecao_original_em_andamento = sys.exc_info()[0] is not None

        # Gate completo repetido antes de qualquer acao de recuperacao.
        _comprovar_identidade_banco_teste(url_banco_teste)

        revisao_atual = _consultar_revisao_atual(url_banco_teste)
        if revisao_atual != "0005":
            resultado_recuperacao = _executar_alembic("upgrade", "head", env=env)
            assert url_banco_teste not in resultado_recuperacao.stdout
            assert url_banco_teste not in resultado_recuperacao.stderr
            revisao_atual = _consultar_revisao_atual(url_banco_teste)

        inventario_recuperado = _listar_tabelas_do_schema(url_banco_teste)
        recuperacao_completa = (
            revisao_atual == "0005"
            and inventario_recuperado == ({"alembic_version"} | TABELAS_DE_NEGOCIO_HEAD_0004)
        )

        if not recuperacao_completa:
            mensagem = (
                "Recuperacao para o head (0005) nao foi confirmada apos o teste - "
                f"revisao encontrada: {revisao_atual!r}, inventario encontrado: "
                f"{inventario_recuperado!r} (sem DSN/credenciais)."
            )
            if excecao_original_em_andamento:
                # Nunca mascara a excecao original - so acrescenta
                # informacao segura sobre a falha de recuperacao.
                print(f"AVISO (nao mascara a falha original): {mensagem}")
            else:
                pytest.fail(mensagem)


def test_dsn_mascarada_nunca_contem_usuario_ou_senha(url_banco_teste):
    """A representacao usada em qualquer diagnostico nunca contem a parte
    usuario:senha@ da URL de conexao original."""
    representacao_segura = mascarar_dsn(url_banco_teste)
    assert "@" not in representacao_segura
    assert "://" not in representacao_segura
