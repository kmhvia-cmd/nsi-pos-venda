# -*- coding: utf-8 -*-
"""
NSI - tests/unit/test_config_banco.py

Testes unitarios da Sprint B (B2.1) - resolucao de URL de banco, mascaramento
de credenciais e validacao de sslmode em config.py. Nenhum destes testes toca
um banco de dados real (isso pertence a B2.3, com PostgreSQL de teste real).

Cobre exatamente o mecanismo exigido pela Especificacao Tecnica da Sprint B:
- NSI_DATABASE_ENV como marcador explicito e fechado (development|test);
- nenhum fallback de DATABASE_URL para TEST_DATABASE_URL, em nenhuma direcao;
- protecao de lista de permissao contra banco de teste diferente de nsi_test;
- mascaramento de DSN via parser oficial do psycopg, nunca regex;
- validacao e deteccao de conflito de sslmode.
"""
import pytest

from config import (
    Config,
    AmbienteBancoInvalido,
    ConfiguracaoBancoAusente,
    BancoDeTesteNaoPermitido,
    SSLModeInvalido,
    DSNInvalida,
    resolver_url_banco,
    mascarar_dsn,
    validar_sslmode,
    verificar_conflito_sslmode,
    _extrair_nome_banco,
)


# ============================================================
# resolver_url_banco - mecanismo explicito e fechado
# ============================================================

def test_development_usa_exclusivamente_database_url(monkeypatch):
    monkeypatch.setattr(Config, "DATABASE_URL", "postgresql://u:p@localhost:5432/nsi_dev")
    monkeypatch.setattr(Config, "TEST_DATABASE_URL", "postgresql://u:p@localhost:5432/nsi_test")
    assert resolver_url_banco("development") == "postgresql://u:p@localhost:5432/nsi_dev"


def test_test_usa_exclusivamente_test_database_url(monkeypatch):
    monkeypatch.setattr(Config, "DATABASE_URL", "postgresql://u:p@localhost:5432/nsi_dev")
    monkeypatch.setattr(Config, "TEST_DATABASE_URL", "postgresql://u:p@localhost:5432/nsi_test")
    assert resolver_url_banco("test") == "postgresql://u:p@localhost:5432/nsi_test"


def test_ambiente_default_vem_de_nsi_database_env(monkeypatch):
    monkeypatch.setattr(Config, "NSI_DATABASE_ENV", "development")
    monkeypatch.setattr(Config, "DATABASE_URL", "postgresql://u:p@localhost:5432/nsi_dev")
    assert resolver_url_banco() == "postgresql://u:p@localhost:5432/nsi_dev"


def test_ambiente_invalido_falha(monkeypatch):
    monkeypatch.setattr(Config, "DATABASE_URL", "postgresql://u:p@localhost:5432/nsi_dev")
    with pytest.raises(AmbienteBancoInvalido):
        resolver_url_banco("producao")


def test_development_ausente_falha_sem_fallback(monkeypatch):
    monkeypatch.setattr(Config, "DATABASE_URL", "")
    monkeypatch.setattr(Config, "TEST_DATABASE_URL", "postgresql://u:p@localhost:5432/nsi_test")
    with pytest.raises(ConfiguracaoBancoAusente):
        resolver_url_banco("development")


def test_test_ausente_falha_sem_fallback(monkeypatch):
    monkeypatch.setattr(Config, "DATABASE_URL", "postgresql://u:p@localhost:5432/nsi_dev")
    monkeypatch.setattr(Config, "TEST_DATABASE_URL", "")
    with pytest.raises(ConfiguracaoBancoAusente):
        resolver_url_banco("test")


def test_test_nunca_cai_para_database_url_mesmo_com_valor_presente(monkeypatch):
    """Mesmo com DATABASE_URL preenchida, ausencia de TEST_DATABASE_URL em modo
    'test' precisa falhar - nunca usar a outra URL como substituta."""
    monkeypatch.setattr(Config, "DATABASE_URL", "postgresql://u:p@localhost:5432/nsi_dev")
    monkeypatch.setattr(Config, "TEST_DATABASE_URL", "")
    with pytest.raises(ConfiguracaoBancoAusente):
        resolver_url_banco("test")


def test_development_nunca_usa_test_database_url_mesmo_com_valor_presente(monkeypatch):
    """Mesmo com TEST_DATABASE_URL preenchida, ausencia de DATABASE_URL em modo
    'development' precisa falhar - nunca usar a URL de teste como substituta."""
    monkeypatch.setattr(Config, "DATABASE_URL", "")
    monkeypatch.setattr(Config, "TEST_DATABASE_URL", "postgresql://u:p@localhost:5432/nsi_test")
    with pytest.raises(ConfiguracaoBancoAusente):
        resolver_url_banco("development")


def test_test_recusa_banco_diferente_do_nome_permitido(monkeypatch):
    monkeypatch.setattr(Config, "TEST_DATABASE_URL", "postgresql://u:p@localhost:5432/outro_banco")
    with pytest.raises(BancoDeTesteNaoPermitido):
        resolver_url_banco("test")


def test_test_aceita_exatamente_nsi_test(monkeypatch):
    monkeypatch.setattr(Config, "TEST_DATABASE_URL", "postgresql://u:p@localhost:5432/nsi_test")
    assert resolver_url_banco("test") == "postgresql://u:p@localhost:5432/nsi_test"


# ============================================================
# mascarar_dsn - nunca usuario, senha ou query string
# ============================================================

def test_mascarar_dsn_oculta_usuario_e_senha():
    dsn = "postgresql://usuario_teste:senha_de_teste_fake@localhost:5432/nsi_test"
    resultado = mascarar_dsn(dsn)
    assert "usuario_teste" not in resultado
    assert "senha_de_teste_fake" not in resultado
    assert "localhost" in resultado
    assert "5432" in resultado
    assert "nsi_test" in resultado


def test_mascarar_dsn_com_senha_de_caracteres_especiais_percent_encoded():
    # senha bruta fictícia: p@ss/w:rd#1 -> percent-encoded na URL
    dsn = "postgresql://usuario_teste:p%40ss%2Fw%3Ard%231@localhost:5432/nsi_test"
    resultado = mascarar_dsn(dsn)
    assert "p@ss/w:rd#1" not in resultado
    assert "p%40ss" not in resultado
    assert "usuario_teste" not in resultado
    assert "nsi_test" in resultado


def test_mascarar_dsn_nunca_lanca_excecao_em_entrada_invalida():
    resultado = mascarar_dsn("isto nao e uma dsn valida ###")
    assert isinstance(resultado, str)
    assert "nao pode ser exibida" in resultado


def test_mascarar_dsn_nao_exibe_query_string_completa():
    dsn = "postgresql://usuario_teste:senha_de_teste_fake@localhost:5432/nsi_test?sslmode=require&options=-c%20algo_sensivel"
    resultado = mascarar_dsn(dsn)
    assert "algo_sensivel" not in resultado
    assert "sslmode" not in resultado
    assert "senha_de_teste_fake" not in resultado


# ============================================================
# validar_sslmode / verificar_conflito_sslmode
# ============================================================

@pytest.mark.parametrize("valor", ["disable", "allow", "prefer", "require", "verify-ca", "verify-full"])
def test_validar_sslmode_aceita_valores_conhecidos(valor):
    assert validar_sslmode(valor) == valor


def test_validar_sslmode_rejeita_valor_desconhecido():
    with pytest.raises(SSLModeInvalido):
        validar_sslmode("modo-inventado")


def test_verificar_conflito_sslmode_aceita_quando_url_nao_especifica():
    verificar_conflito_sslmode("postgresql://u:p@localhost:5432/nsi_test", "prefer")  # nao lanca


def test_verificar_conflito_sslmode_aceita_quando_valores_batem():
    verificar_conflito_sslmode(
        "postgresql://u:p@localhost:5432/nsi_test?sslmode=prefer", "prefer"
    )  # nao lanca


def test_verificar_conflito_sslmode_detecta_divergencia():
    with pytest.raises(SSLModeInvalido):
        verificar_conflito_sslmode(
            "postgresql://u:p@localhost:5432/nsi_test?sslmode=require", "prefer"
        )


# ============================================================
# DSNInvalida - a excecao original do parser NUNCA pode propagar
#
# Confirmado empiricamente (fora desta suite, antes da correcao) que o
# parser do psycopg pode ecoar a DSN inteira - incluindo usuario e senha -
# na propria mensagem de erro para determinadas URIs malformadas (ex.: URI
# com colchete IPv6 desbalanceado). As excecoes originais do parser NUNCA
# devem chegar a str(exc)/repr(exc)/log/saida capturada - apenas DSNInvalida,
# com mensagem fixa, sem interpolar a entrada recebida.
# ============================================================

SEGREDO_URI = "SEGREDO_SINTETICO_URI_9f3a"
SEGREDO_DSN = "SEGREDO_SINTETICO_DSN_7c2b"

# URI malformada (colchete IPv6 desbalanceado) - o parser do psycopg,
# SEM a correcao desta rodada, ecoa a DSN inteira (incluindo o segredo)
# na propria mensagem de erro.
_URI_MALFORMADA = f"postgresql://usuario_teste:{SEGREDO_URI}@[localhost:5432/nsi_test"

# DSN key=value malformada (aspas nao fechadas).
_DSN_MALFORMADA = f"host=localhost dbname='nsi_test password={SEGREDO_DSN}"


@pytest.mark.parametrize("dsn_malformada,segredo", [
    (_URI_MALFORMADA, SEGREDO_URI),
    (_DSN_MALFORMADA, SEGREDO_DSN),
])
def test_extrair_nome_banco_nunca_vaza_segredo_de_dsn_malformada(dsn_malformada, segredo, capsys, caplog):
    import logging

    with pytest.raises(DSNInvalida) as exc_info:
        _extrair_nome_banco(dsn_malformada)

    exc = exc_info.value
    assert segredo not in str(exc)
    assert segredo not in repr(exc)
    assert dsn_malformada not in str(exc)
    assert dsn_malformada not in repr(exc)
    # 'from None' precisa ter suprimido o encadeamento - a excecao original
    # do parser (que pode conter o segredo) nao pode estar acessivel nem
    # por __context__/__cause__, ou um formatador de traceback ainda a exibiria.
    assert exc.__cause__ is None
    assert exc.__context__ is None

    # Mesmo que alguem faca print(exc)/logging.exception(exc) no ponto de
    # chamada, nada sensivel deve aparecer, pois a propria excecao ja nunca
    # carrega o segredo.
    print(exc)
    print(repr(exc))
    logging.getLogger("teste_dsn").error("erro ao processar conexao: %s", exc)
    saida = capsys.readouterr()
    assert segredo not in saida.out
    assert segredo not in saida.err
    assert segredo not in caplog.text
    assert dsn_malformada not in saida.out
    assert dsn_malformada not in caplog.text


@pytest.mark.parametrize("dsn_malformada,segredo", [
    (_URI_MALFORMADA, SEGREDO_URI),
    (_DSN_MALFORMADA, SEGREDO_DSN),
])
def test_verificar_conflito_sslmode_nunca_vaza_segredo_de_dsn_malformada(dsn_malformada, segredo):
    with pytest.raises(DSNInvalida) as exc_info:
        verificar_conflito_sslmode(dsn_malformada, "prefer")

    exc = exc_info.value
    assert segredo not in str(exc)
    assert segredo not in repr(exc)
    assert exc.__cause__ is None
    assert exc.__context__ is None


def test_resolver_url_banco_test_com_dsn_malformada_nunca_vaza_segredo(monkeypatch):
    """Caminho de ponta a ponta: resolver_url_banco('test') chama
    _extrair_nome_banco internamente - a DSNInvalida precisa se propagar sem
    o segredo, nunca a excecao original do parser."""
    monkeypatch.setattr(Config, "TEST_DATABASE_URL", _URI_MALFORMADA)
    with pytest.raises(DSNInvalida) as exc_info:
        resolver_url_banco("test")
    exc = exc_info.value
    assert SEGREDO_URI not in str(exc)
    assert SEGREDO_URI not in repr(exc)
    assert exc.__cause__ is None
    assert exc.__context__ is None


def test_dsn_invalida_mensagem_e_sempre_fixa():
    """A mensagem de DSNInvalida nunca varia com a entrada - garante que
    nenhuma implementacao futura volte a interpolar a DSN por engano."""
    with pytest.raises(DSNInvalida) as e1:
        _extrair_nome_banco(_URI_MALFORMADA)
    with pytest.raises(DSNInvalida) as e2:
        _extrair_nome_banco(_DSN_MALFORMADA)
    assert str(e1.value) == str(e2.value)
