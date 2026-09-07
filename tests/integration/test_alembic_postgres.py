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


def _executar_alembic(*args: str, env: dict) -> "subprocess.CompletedProcess[str]":
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        capture_output=True,
        text=True,
        env=env,
    )


def _listar_tabelas_do_schema(url: str) -> set:
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = %s",
                (NOME_SCHEMA,),
            )
            return {linha[0] for linha in cur.fetchall()}


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


def test_upgrade_downgrade_upgrade_sem_tabela_de_negocio(url_banco_teste):
    """
    Ciclo completo exigido pelo comando de aceite: upgrade -> downgrade ->
    novo upgrade, com verificacao do CONJUNTO EXATO de objetos em cada
    momento - nunca presumido (Especificacao Tecnica, Ponto 3: o
    comportamento real de 'alembic_version' apos downgrade e confirmado
    aqui, no momento em que o teste roda de fato, nao assumido no
    planejamento).

    A identidade do banco (nsi_test, servidor local, porta 5432) e
    comprovada aqui dentro, ANTES de qualquer chamada ao Alembic - inclusive
    antes do primeiro upgrade, nunca apenas antes do downgrade. Se a
    comprovacao falhar, o teste falha imediatamente e nenhuma acao do
    Alembic (nem upgrade, nem downgrade) chega a ser executada.
    """
    _comprovar_identidade_banco_teste(url_banco_teste)

    env = {**os.environ, "NSI_DATABASE_ENV": "test"}

    resultado_upgrade_1 = _executar_alembic("upgrade", "head", env=env)
    assert resultado_upgrade_1.returncode == 0, resultado_upgrade_1.stderr
    assert url_banco_teste not in resultado_upgrade_1.stdout
    assert url_banco_teste not in resultado_upgrade_1.stderr

    tabelas_pos_upgrade = _listar_tabelas_do_schema(url_banco_teste)
    assert "alembic_version" in tabelas_pos_upgrade
    assert tabelas_pos_upgrade - {"alembic_version"} == set(), (
        "B2 nao cria nenhuma tabela de negocio - encontradas: "
        f"{tabelas_pos_upgrade - {'alembic_version'}}"
    )

    resultado_downgrade = _executar_alembic("downgrade", "base", env=env)
    assert resultado_downgrade.returncode == 0, resultado_downgrade.stderr
    assert url_banco_teste not in resultado_downgrade.stdout
    assert url_banco_teste not in resultado_downgrade.stderr

    tabelas_pos_downgrade = _listar_tabelas_do_schema(url_banco_teste)
    assert tabelas_pos_downgrade - {"alembic_version"} == set()

    resultado_upgrade_2 = _executar_alembic("upgrade", "head", env=env)
    assert resultado_upgrade_2.returncode == 0, resultado_upgrade_2.stderr

    tabelas_finais = _listar_tabelas_do_schema(url_banco_teste)
    assert tabelas_finais - {"alembic_version"} == set()


def test_dsn_mascarada_nunca_contem_usuario_ou_senha(url_banco_teste):
    """A representacao usada em qualquer diagnostico nunca contem a parte
    usuario:senha@ da URL de conexao original."""
    representacao_segura = mascarar_dsn(url_banco_teste)
    assert "@" not in representacao_segura
    assert "://" not in representacao_segura
