# -*- coding: utf-8 -*-
"""
NSI - tests/unit/test_config_ensaio_b6.py
(Sprint B, B6.2 - SPRINT-B6-ESPECIFICACAO-ENSAIO-DE-CORTE.md, Secoes 14 e
17, componente C1; decisao D5)

Testes UNITARIOS, sem banco, do ambiente 'ensaio' em config.py: terceiro
valor fechado de NSI_DATABASE_ENV, com variaveis proprias, banco exigido
exato e nenhum fallback de ou para development/test. Os testes existentes
de development e test (tests/unit/test_config_banco.py) nao sao alterados.
"""
import pytest

import config
from config import (
    AmbienteBancoInvalido,
    BancoDeTesteNaoPermitido,
    BancoFuncionalNaoPermitido,
    Config,
    ConfiguracaoBancoAusente,
    DSNInvalida,
    PapelBancoInvalido,
    UsuarioBancoDivergente,
    resolver_url_banco,
    resolver_url_banco_papel,
)

DEV = "postgresql://nsi_dev_migrator:s@localhost:5432/nsi_dev"
TESTE = "postgresql://nsi_test_migrator:s@localhost:5432/nsi_test"
ENSAIO = "postgresql://nsi_ensaio_migrator:s@localhost:5432/nsi_ensaio"
IMPORTACAO_ENSAIO = "postgresql://nsi_importacao:segredo-ensaio@localhost:5432/nsi_ensaio"
IMPORTACAO_TESTE = "postgresql://nsi_importacao:s@localhost:5432/nsi_test"


@pytest.fixture(autouse=True)
def _isolamento(monkeypatch):
    for variavel in ("DATABASE_URL", "TEST_DATABASE_URL", "ENSAIO_DATABASE_URL", "DATABASE_URL_NSI_IMPORTACAO",
                     "TEST_DATABASE_URL_NSI_IMPORTACAO", "ENSAIO_DATABASE_URL_NSI_IMPORTACAO",
                     "DATABASE_URL_NSI_APLICACAO", "TEST_DATABASE_URL_NSI_APLICACAO"):
        monkeypatch.setattr(Config, variavel, "")
    monkeypatch.setattr(Config, "DATABASE_SSLMODE", "prefer")


def test_ambientes_validos_sao_exatamente_tres():
    assert config._AMBIENTES_BANCO_VALIDOS == {"development", "test", "ensaio"}
    assert Config.NOME_BANCO_ENSAIO_PERMITIDO == "nsi_ensaio"


def test_ensaio_usa_exclusivamente_ensaio_database_url(monkeypatch):
    monkeypatch.setattr(Config, "DATABASE_URL", DEV)
    monkeypatch.setattr(Config, "TEST_DATABASE_URL", TESTE)
    monkeypatch.setattr(Config, "ENSAIO_DATABASE_URL", ENSAIO)
    assert resolver_url_banco("ensaio") == ENSAIO
    assert resolver_url_banco("development") == DEV
    assert resolver_url_banco("test") == TESTE


def test_ensaio_vem_de_nsi_database_env(monkeypatch):
    monkeypatch.setattr(Config, "NSI_DATABASE_ENV", "ensaio")
    monkeypatch.setattr(Config, "ENSAIO_DATABASE_URL", ENSAIO)
    assert resolver_url_banco() == ENSAIO


def test_ensaio_ausente_falha_sem_fallback(monkeypatch):
    """As variaveis de ensaio so existem durante uma rodada: fora dela, a
    resolucao falha - nunca cai para development nem para test."""
    monkeypatch.setattr(Config, "DATABASE_URL", DEV)
    monkeypatch.setattr(Config, "TEST_DATABASE_URL", TESTE)
    with pytest.raises(ConfiguracaoBancoAusente):
        resolver_url_banco("ensaio")


@pytest.mark.parametrize("ambiente", ["development", "test"])
def test_development_e_test_nunca_usam_a_url_de_ensaio(monkeypatch, ambiente):
    monkeypatch.setattr(Config, "ENSAIO_DATABASE_URL", ENSAIO)
    with pytest.raises(ConfiguracaoBancoAusente):
        resolver_url_banco(ambiente)


@pytest.mark.parametrize("url", [TESTE, DEV, "postgresql://u:p@localhost:5432/nsi_ensaio2",
                                 "postgresql://u:p@localhost:5432/postgres"])
def test_ensaio_recusa_qualquer_banco_que_nao_seja_nsi_ensaio(monkeypatch, url):
    monkeypatch.setattr(Config, "ENSAIO_DATABASE_URL", url)
    with pytest.raises(BancoDeTesteNaoPermitido):
        resolver_url_banco("ensaio")


def test_test_continua_recusando_o_banco_de_ensaio(monkeypatch):
    monkeypatch.setattr(Config, "TEST_DATABASE_URL", ENSAIO)
    with pytest.raises(BancoDeTesteNaoPermitido):
        resolver_url_banco("test")


@pytest.mark.parametrize("ambiente", ["ENSAIO", "Ensaio", "ensaio ", "staging", "production", "rehearsal", ""])
def test_ambiente_fora_do_conjunto_fechado_continua_invalido(ambiente):
    with pytest.raises(AmbienteBancoInvalido):
        resolver_url_banco(ambiente)
    with pytest.raises(AmbienteBancoInvalido):
        resolver_url_banco_papel("nsi_importacao", ambiente)


def test_ensaio_resolve_nsi_importacao_pela_variavel_propria(monkeypatch):
    monkeypatch.setattr(Config, "TEST_DATABASE_URL_NSI_IMPORTACAO", IMPORTACAO_TESTE)
    monkeypatch.setattr(Config, "ENSAIO_DATABASE_URL_NSI_IMPORTACAO", IMPORTACAO_ENSAIO)
    assert resolver_url_banco_papel("nsi_importacao", "ensaio") == IMPORTACAO_ENSAIO
    assert resolver_url_banco_papel("nsi_importacao", "test") == IMPORTACAO_TESTE


def test_ensaio_nunca_cai_para_a_variavel_de_teste_do_papel(monkeypatch):
    monkeypatch.setattr(Config, "TEST_DATABASE_URL_NSI_IMPORTACAO", IMPORTACAO_TESTE)
    monkeypatch.setattr(Config, "DATABASE_URL_NSI_IMPORTACAO", "postgresql://nsi_importacao:s@localhost:5432/nsi_dev")
    with pytest.raises(ConfiguracaoBancoAusente):
        resolver_url_banco_papel("nsi_importacao", "ensaio")


def test_test_nunca_usa_a_variavel_de_ensaio_do_papel(monkeypatch):
    monkeypatch.setattr(Config, "ENSAIO_DATABASE_URL_NSI_IMPORTACAO", IMPORTACAO_ENSAIO)
    with pytest.raises(ConfiguracaoBancoAusente):
        resolver_url_banco_papel("nsi_importacao", "test")


@pytest.mark.parametrize("papel", ["nsi_aplicacao", "nsi_expiracao", "nsi_operador_restrito"])
def test_papeis_do_fluxo_novo_nao_existem_no_ensaio(monkeypatch, papel):
    """Somente nsi_importacao conecta ao banco de ensaio (Secao 14)."""
    monkeypatch.setattr(Config, "TEST_DATABASE_URL_NSI_APLICACAO",
                        "postgresql://nsi_aplicacao:s@localhost:5432/nsi_test")
    with pytest.raises(PapelBancoInvalido):
        resolver_url_banco_papel(papel, "ensaio")


@pytest.mark.parametrize("url", [IMPORTACAO_TESTE, "postgresql://nsi_importacao:s@localhost:5432/nsi_dev"])
def test_ensaio_exige_o_banco_nsi_ensaio_para_o_papel(monkeypatch, url):
    monkeypatch.setattr(Config, "ENSAIO_DATABASE_URL_NSI_IMPORTACAO", url)
    with pytest.raises(BancoFuncionalNaoPermitido):
        resolver_url_banco_papel("nsi_importacao", "ensaio")


@pytest.mark.parametrize("usuario", ["postgres", "nsi_ensaio_migrator", "nsi_aplicacao", "nsi_test_migrator"])
def test_ensaio_exige_o_usuario_exato_do_papel(monkeypatch, usuario):
    monkeypatch.setattr(Config, "ENSAIO_DATABASE_URL_NSI_IMPORTACAO",
                        f"postgresql://{usuario}:s@localhost:5432/nsi_ensaio")
    with pytest.raises(UsuarioBancoDivergente):
        resolver_url_banco_papel("nsi_importacao", "ensaio")


def test_nenhuma_excecao_do_ensaio_expoe_a_senha(monkeypatch):
    for url, excecao in (
        ("postgresql://nsi_importacao:segredo-ensaio@localhost:5432/outro", BancoFuncionalNaoPermitido),
        ("postgresql://outro:segredo-ensaio@localhost:5432/nsi_ensaio", UsuarioBancoDivergente),
        ("postgresql://nsi_importacao:segredo-ensaio@[::1/nsi_ensaio", DSNInvalida),
    ):
        monkeypatch.setattr(Config, "ENSAIO_DATABASE_URL_NSI_IMPORTACAO", url)
        with pytest.raises(excecao) as exc_info:
            resolver_url_banco_papel("nsi_importacao", "ensaio")
        assert "segredo-ensaio" not in str(exc_info.value) + repr(exc_info.value)

    monkeypatch.setattr(Config, "ENSAIO_DATABASE_URL", "postgresql://u:segredo-ensaio@localhost:5432/outro")
    with pytest.raises(BancoDeTesteNaoPermitido) as exc_info:
        resolver_url_banco("ensaio")
    assert "segredo-ensaio" not in str(exc_info.value)


def test_ensaio_respeita_a_politica_de_sslmode(monkeypatch):
    monkeypatch.setattr(Config, "ENSAIO_DATABASE_URL_NSI_IMPORTACAO", IMPORTACAO_ENSAIO + "?sslmode=disable")
    with pytest.raises(config.SSLModeInvalido):
        resolver_url_banco_papel("nsi_importacao", "ensaio")


def test_area_de_ensaio_nao_tem_valor_padrao():
    """Decisao D5: a area de ensaio vem exclusivamente de variavel de
    ambiente, sem valor padrao - o codigo nunca embute um diretorio."""
    fonte = open(config.__file__, encoding="utf-8").read()
    assert 'NSI_ENSAIO_DIR = os.getenv("NSI_ENSAIO_DIR", "")' in fonte
    for variavel in ("ENSAIO_DATABASE_URL", "ENSAIO_DATABASE_URL_NSI_IMPORTACAO"):
        assert f'os.getenv("{variavel}", "")' in fonte
