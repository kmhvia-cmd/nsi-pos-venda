# -*- coding: utf-8 -*-
r"""
NSI - tests/conftest.py (Sprint B, B2.2 - ADR-008)

Fixtures e hooks compartilhados para os testes de integracao PostgreSQL
real (marcador 'pg_integration'). Nenhum destes testes usa SQLite ou mock
para afirmar conectividade real (Especificacao Tecnica da Sprint B).

Dois modos de execucao, deliberadamente distintos:

  - Execucao comum de desenvolvimento (`pytest`): testes 'pg_integration'
    sao PULADOS quando TEST_DATABASE_URL nao esta definida - preserva o
    fluxo dos 213+ testes legados, sem exigir infraestrutura nova.

  - Comando de aceite da B2/B3 (obrigatorio, distinto):

        PowerShell:
            $env:NSI_REQUIRE_PG_TESTS = "1"
            $env:NSI_DATABASE_ENV = "test"
            $env:TEST_DATABASE_URL = "postgresql://nsi_test_migrator:***@localhost:5432/nsi_test"
            pytest -m pg_integration -v --junitxml=reports/b2_pg_integration.xml
            Remove-Item Env:\NSI_REQUIRE_PG_TESTS, Env:\NSI_DATABASE_ENV, Env:\TEST_DATABASE_URL -ErrorAction SilentlyContinue

        Bash:
            NSI_REQUIRE_PG_TESTS=1 NSI_DATABASE_ENV=test \
              TEST_DATABASE_URL="postgresql://nsi_test_migrator:***@localhost:5432/nsi_test" \
              pytest -m pg_integration -v --junitxml=reports/b2_pg_integration.xml

    Quando NSI_REQUIRE_PG_TESTS=1: ausencia de TEST_DATABASE_URL FALHA
    explicitamente (nunca skip) - o criterio de aceite exige zero skipped
    entre os testes 'pg_integration' neste relatorio (reports/ esta no
    .gitignore - o relatorio nunca fica como residuo untracked).
"""
import os

import pytest


def _modo_aceite_ativo() -> bool:
    return os.getenv("NSI_REQUIRE_PG_TESTS", "") == "1"


@pytest.fixture(autouse=True)
def _protecao_pg_integration(request):
    """
    Aplicada automaticamente a todo teste marcado 'pg_integration' - nao
    exige que cada teste declare a fixture explicitamente. Nunca depende
    apenas de TEST_DATABASE_URL != DATABASE_URL: essa comparacao, por si
    so, nao prova que as duas URLs apontam para servidores/bancos
    diferentes (Especificacao Tecnica da Sprint B, Ponto 5). A prova de
    identidade real (current_database()) ocorre dentro de cada teste, apos
    conectar de fato - esta fixture cobre apenas a decisao de
    pular/falhar/prosseguir antes de qualquer conexao.
    """
    if "pg_integration" not in request.node.keywords:
        return

    tem_test_database_url = bool(os.getenv("TEST_DATABASE_URL", ""))

    if not tem_test_database_url:
        if _modo_aceite_ativo():
            pytest.fail(
                "NSI_REQUIRE_PG_TESTS=1 exige TEST_DATABASE_URL definida - "
                "nenhum teste 'pg_integration' pode ser pulado no comando "
                "de aceite da Sprint B."
            )
        pytest.skip(
            "TEST_DATABASE_URL ausente - teste de integracao PostgreSQL "
            "pulado no modo de desenvolvimento comum."
        )


@pytest.fixture
def url_banco_teste():
    """
    Resolve e devolve a URL do banco de teste, ja validada por
    config.resolver_url_banco('test') - nome de banco restrito a
    Config.NOME_BANCO_TESTE_PERMITIDO ('nsi_test'). Falha explicitamente
    (nunca fallback) se NSI_DATABASE_ENV/TEST_DATABASE_URL nao estiverem
    coerentes com o modo de teste.
    """
    from config import resolver_url_banco
    return resolver_url_banco("test")
