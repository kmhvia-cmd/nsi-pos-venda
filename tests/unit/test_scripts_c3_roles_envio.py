# -*- coding: utf-8 -*-
"""
NSI - tests/unit/test_scripts_c3_roles_envio.py
(Sprint C, C3 - ADR-011, Secao 11; SPRINT-C-ESPECIFICACAO-TECNICA.md, Secao 3)

Testes ESTATICOS, sem banco, dos dois scripts administrativos das roles
nsi_envio e nsi_webhook, e testes UNITARIOS da resolucao das URLs dos dois
papeis em config.py.

Os scripts exigem o superusuario e so sao executados manualmente pelo
operador - nenhum teste os executa. O que se comprova aqui e o desenho:
tres fases, somente leitura fora da Fase 2, escritas exatas e na ordem,
gate de confirmacao na reversao, ausencia de senha, de membership e de
comando proibido.
"""
import re
from pathlib import Path

import pytest

from config import (
    BancoFuncionalNaoPermitido,
    Config,
    ConfiguracaoBancoAusente,
    PapelBancoInvalido,
    UsuarioBancoDivergente,
    resolver_url_banco_papel,
)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CAMINHO_PROVISIONAR = BASE_DIR / "scripts" / "postgres_local" / "provisionar_c3_roles_envio.sql"
CAMINHO_DESPROVISIONAR = BASE_DIR / "scripts" / "postgres_local" / "desprovisionar_c3_roles_envio.sql"
OS_DOIS = pytest.mark.parametrize("caminho", [CAMINHO_PROVISIONAR, CAMINHO_DESPROVISIONAR],
                                  ids=["provisionar", "desprovisionar"])

MARCADOR_FASE_1 = "-- FASE 1 - PREFLIGHT"
MARCADOR_FASE_2_PROV = "-- FASE 2 - CONVERGENCIA"
MARCADOR_FASE_2_DESP = "-- FASE 2 - REMOCAO"
MARCADOR_GATE = "-- GATE DE CONFIRMACAO"
MARCADOR_FASE_3 = "-- FASE 3 - POS-VALIDACAO COMPLETA"
MARCADOR_ENCERRAMENTO = "-- ENCERRAMENTO"

LIGA_READ_ONLY = "SET default_transaction_read_only = on;"
LIBERA_ESCRITA = "SET default_transaction_read_only = off;"
FRASE_DE_CONFIRMACAO = "CONFIRMO-DESPROVISIONAR-NSI-C3-ROLES-ENVIO"
ATRIBUTOS = "LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS"

COMANDOS_DE_ESCRITA = ["CREATE", "ALTER", "DROP", "GRANT", "REVOKE", "INSERT", "UPDATE", "DELETE", "TRUNCATE",
                       "EXECUTE", "REASSIGN", "COMMENT", "COPY", "MERGE", "CHECKPOINT"]

ESCRITAS_DO_PROVISIONAMENTO = [
    f"CREATE ROLE nsi_envio {ATRIBUTOS};",
    f"CREATE ROLE nsi_webhook {ATRIBUTOS};",
    "GRANT CONNECT ON DATABASE nsi_dev TO nsi_envio;",
    "GRANT CONNECT ON DATABASE nsi_test TO nsi_envio;",
    "GRANT CONNECT ON DATABASE nsi_dev TO nsi_webhook;",
    "GRANT CONNECT ON DATABASE nsi_test TO nsi_webhook;",
    "GRANT USAGE ON SCHEMA nsi_operacional TO nsi_envio;",
    "GRANT USAGE ON SCHEMA nsi_operacional TO nsi_webhook;",
    "GRANT USAGE ON SCHEMA nsi_operacional TO nsi_envio;",
    "GRANT USAGE ON SCHEMA nsi_operacional TO nsi_webhook;",
]
ESCRITAS_DA_REVERSAO = [
    "REVOKE USAGE ON SCHEMA nsi_operacional FROM nsi_envio;",
    "REVOKE USAGE ON SCHEMA nsi_operacional FROM nsi_webhook;",
    "REVOKE USAGE ON SCHEMA nsi_operacional FROM nsi_envio;",
    "REVOKE USAGE ON SCHEMA nsi_operacional FROM nsi_webhook;",
    "REVOKE CONNECT ON DATABASE nsi_dev FROM nsi_envio;",
    "REVOKE CONNECT ON DATABASE nsi_test FROM nsi_envio;",
    "DROP ROLE nsi_envio;",
    "REVOKE CONNECT ON DATABASE nsi_dev FROM nsi_webhook;",
    "REVOKE CONNECT ON DATABASE nsi_test FROM nsi_webhook;",
    "DROP ROLE nsi_webhook;",
]


def _linhas_de_codigo(texto: str) -> str:
    return "\n".join(linha for linha in texto.splitlines() if not linha.strip().startswith("--"))


def _codigo(texto: str) -> str:
    """Codigo sem comentarios e sem o conteudo de literais de texto."""
    return re.sub(r"'(?:[^']|'')*'", "''", _linhas_de_codigo(texto))


def _escritas(bloco: str) -> list:
    padrao = re.compile(r"^(%s)\b" % "|".join(COMANDOS_DE_ESCRITA))
    return [linha.strip() for linha in _linhas_de_codigo(bloco).splitlines() if padrao.match(linha.strip())]


def _dividir(texto: str, marcadores: list, nomes: list) -> dict:
    indices = [texto.index(m) for m in marcadores]
    assert indices == sorted(indices), "Os marcadores das fases precisam aparecer na ordem."
    limites = [0] + indices + [len(texto)]
    return {nome: texto[limites[i]:limites[i + 1]] for i, nome in enumerate(nomes)}


@pytest.fixture(scope="module")
def prov():
    return _dividir(CAMINHO_PROVISIONAR.read_text(encoding="utf-8"),
                    [MARCADOR_FASE_1, MARCADOR_FASE_2_PROV, MARCADOR_FASE_3, MARCADOR_ENCERRAMENTO],
                    ["inicio", "fase_1", "fase_2", "fase_3", "encerramento"])


@pytest.fixture(scope="module")
def desp():
    return _dividir(CAMINHO_DESPROVISIONAR.read_text(encoding="utf-8"),
                    [MARCADOR_FASE_1, MARCADOR_GATE, MARCADOR_FASE_2_DESP, MARCADOR_FASE_3, MARCADOR_ENCERRAMENTO],
                    ["inicio", "fase_1", "gate", "fase_2", "fase_3", "encerramento"])


def _fase_2(caminho) -> str:
    return MARCADOR_FASE_2_PROV if caminho == CAMINHO_PROVISIONAR else MARCADOR_FASE_2_DESP


# ============================================================
# Comuns aos dois scripts
# ============================================================

@OS_DOIS
def test_arquivo_integro_com_blocos_balanceados(caminho):
    texto = caminho.read_text(encoding="utf-8")
    assert texto.isascii(), "Somente ASCII, como os demais scripts administrativos."
    codigo = _linhas_de_codigo(texto)
    assert codigo.count("DO $$") == codigo.count("END $$;") > 0
    assert codigo.count("\\if ") == codigo.count("\\endif") > 0
    assert codigo.count("\\gset") >= 1


@OS_DOIS
def test_para_no_primeiro_erro_e_confere_a_identidade_do_servidor(caminho):
    texto = caminho.read_text(encoding="utf-8")
    inicio = texto[:texto.index(MARCADOR_FASE_1)]
    comandos = [l.strip() for l in _linhas_de_codigo(texto).splitlines() if l.strip()]
    assert comandos[0] == "\\set ON_ERROR_STOP on"
    assert comandos[1] == LIGA_READ_ONLY, "O modo somente leitura e ligado antes de qualquer consulta."
    for exigido in ("current_database() <> 'postgres'", "host(inet_server_addr()) NOT IN ('127.0.0.1', '::1')",
                    "inet_server_port() <> 5432", "version() NOT LIKE '%PostgreSQL 17%'",
                    "current_setting('is_superuser') <> 'on'"):
        assert exigido in inicio, exigido


@OS_DOIS
def test_nao_contem_senha_nem_comando_de_senha(caminho):
    texto = caminho.read_text(encoding="utf-8")
    codigo = _codigo(texto).upper()
    assert "PASSWORD" not in codigo and "ENCRYPTED" not in codigo and "VALID UNTIL" not in codigo
    cabecalho = texto.split("\\set ON_ERROR_STOP on")[0]
    assert "NAO CONTEM SENHA" in cabecalho
    assert "NUNCA PRODUCAO" in cabecalho and "MANUAL" in cabecalho


@OS_DOIS
def test_modo_somente_leitura_e_religado_depois_de_cada_troca_de_banco(caminho):
    """\\c abre uma sessao nova, em modo normal. Fora da Fase 2, toda troca
    de banco e seguida por religar o modo somente leitura."""
    texto = caminho.read_text(encoding="utf-8")
    fora = texto[:texto.index(_fase_2(caminho))] + texto[texto.index(MARCADOR_FASE_3):]
    comandos = [l.strip() for l in _linhas_de_codigo(fora).splitlines() if l.strip()]
    trocas = [i for i, comando in enumerate(comandos) if comando.startswith("\\c ")]
    assert len(trocas) >= 6, "As Fases 1 e 3 leem os dois bancos e voltam ao de manutencao."
    for i in trocas:
        assert comandos[i + 1] == LIGA_READ_ONLY, f"Depois de '{comandos[i]}' o modo somente leitura nao e religado."
    assert fora.count("current_setting('transaction_read_only') <> 'on'") >= len(trocas) - 1


@OS_DOIS
def test_escrita_e_liberada_em_um_unico_ponto(caminho):
    texto = caminho.read_text(encoding="utf-8")
    codigo = _linhas_de_codigo(texto)
    assert codigo.count(LIBERA_ESCRITA) == 1
    assert texto.index(_fase_2(caminho)) < texto.index(LIBERA_ESCRITA) < texto.index(MARCADOR_FASE_3)


@OS_DOIS
def test_nenhum_comando_proibido(caminho):
    codigo = _codigo(caminho.read_text(encoding="utf-8")).upper()
    for proibido in ("CASCADE", "DROP OWNED", "REASSIGN OWNED", "PG_TERMINATE_BACKEND", "DISABLE TRIGGER",
                     "TRUNCATE", "DROP SCHEMA", "DROP TABLE", "DROP DATABASE", "DROP FUNCTION", "ALTER ROLE",
                     "ALTER SYSTEM", "DELETE FROM", "CREATE DATABASE", "ALEMBIC UPGRADE", "ALEMBIC DOWNGRADE",
                     "GRANT EXECUTE", "ON TABLE", "ALL PRIVILEGES", "GRANT CREATE", "WITH ADMIN", "WITH GRANT"):
        assert proibido not in codigo, proibido
    assert chr(92) + "!" not in codigo, "Nenhum comando do sistema operacional."


@OS_DOIS
def test_nenhuma_membership_e_criada_ou_removida(caminho):
    """ADR-011, Secao 11: as duas roles nao pertencem a nenhuma role e nao
    tem membros - a excecao unica da ADR-009 (Secao 21) continua unica."""
    codigo = _linhas_de_codigo(caminho.read_text(encoding="utf-8"))
    assert not re.search(r"^\s*GRANT\s+nsi_\w+\s+TO\b", codigo, flags=re.M)
    assert not re.search(r"^\s*REVOKE\s+nsi_\w+\s+FROM\b", codigo, flags=re.M)
    assert "IN ROLE" not in codigo.upper()


@OS_DOIS
def test_variaveis_de_cliente_nao_cruzam_para_a_fase_3(caminho):
    texto = caminho.read_text(encoding="utf-8")
    variaveis = set(re.findall(r"\bAS (\w+)", texto)) | set(re.findall(r":'?(\w+)'?", _linhas_de_codigo(texto)))
    variaveis = {v for v in variaveis if re.match(r"(f\d|conf)_", v)}
    assert variaveis, "O script usa variaveis de cliente."
    fase_3 = texto[texto.index(MARCADOR_FASE_3):]
    for variavel in variaveis:
        assert variavel not in fase_3, f"{variavel} cruza para a Fase 3."


@OS_DOIS
def test_scripts_nao_tocam_as_oito_roles_existentes(caminho):
    escritas = " ".join(_escritas(caminho.read_text(encoding="utf-8")))
    for role in ("nsi_eventos_owner", "nsi_aplicacao", "nsi_expiracao", "nsi_operador_restrito", "nsi_congelamento",
                 "nsi_importacao", "nsi_dev_migrator", "nsi_test_migrator", "PUBLIC"):
        assert role not in escritas, f"{role} nunca e alvo de escrita."


# ============================================================
# provisionar_c3_roles_envio.sql
# ============================================================

def test_prov_fases_1_e_3_nao_escrevem(prov):
    for bloco in ("inicio", "fase_1", "fase_3", "encerramento"):
        assert _escritas(prov[bloco]) == [], bloco
        assert not re.search(r"\bEXECUTE\b", _codigo(prov[bloco])), bloco


def test_prov_fase_2_executa_exatamente_as_escritas_especificadas_na_ordem(prov):
    assert _escritas(prov["fase_2"]) == ESCRITAS_DO_PROVISIONAMENTO


def test_prov_cada_role_so_e_criada_se_faltar_e_a_reexecucao_nunca_toca_senha(prov):
    fase_2 = _linhas_de_codigo(prov["fase_2"])
    assert "NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nsi_envio') AS f2_falta_envio" in fase_2
    assert "NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nsi_webhook') AS f2_falta_webhook" in fase_2
    for variavel, role in (("f2_falta_envio", "nsi_envio"), ("f2_falta_webhook", "nsi_webhook")):
        inicio = fase_2.index(f"\\if :{variavel}")
        bloco = fase_2[inicio:fase_2.index("\\endif", inicio)]
        assert f"CREATE ROLE {role} " in bloco.split("\\else")[0]
        assert _escritas(bloco.split("\\else")[1]) == []
    assert fase_2.count("\\c nsi_dev") == fase_2.count("\\c nsi_test") == fase_2.count("\\c postgres") == 1


def test_prov_preflight_aceita_role_ausente_ou_exata_e_recusa_o_resto(prov):
    fase_1 = prov["fase_1"]
    assert "FOREACH nome_role IN ARRAY ARRAY['nsi_envio', 'nsi_webhook'] LOOP" in fase_1
    assert "CONTINUE;" in fase_1, "Role ausente e um estado previsto."
    for recusa in ("existe com atributos diferentes dos especificados", "membership(s); o especificado e nenhuma",
                   "concessao(oes) de banco fora do especificado", "e dona de % objeto(s)",
                   "Concessao de schema fora do especificado"):
        assert recusa in fase_1, recusa


def test_prov_recusa_o_ambiente_de_ensaio_e_exige_revisao_0006_ou_0007(prov):
    assert "datname = 'nsi_ensaio'" in prov["inicio"] and "desprovisionar_b6_ensaio.sql" in prov["inicio"]
    for fase in ("fase_1", "fase_3"):
        assert prov[fase].count("NOT IN ('0006', '0007')") == 2, fase
        assert "\\c nsi_dev" in prov[fase] and "\\c nsi_test" in prov[fase]


def test_prov_excecao_de_membership_da_adr_009_continua_unica(prov):
    for fase in ("fase_1", "fase_3"):
        assert "g.rolname = 'nsi_congelamento' AND r.rolname = 'nsi_aplicacao'" in prov[fase]
        assert "IF total <> 3 OR total_exatas <> 3 THEN" in prov[fase]


def test_prov_pos_validacao_confere_o_estado_final_exato(prov):
    fase_3 = prov["fase_3"]
    assert "rolcanlogin AND rolinherit AND NOT rolsuper AND NOT rolcreatedb" in fase_3
    assert "IF total <> 2 OR total_esperadas <> 2 THEN" in fase_3, "CONNECT exatamente em nsi_dev e nsi_test."
    assert fase_3.count("has_schema_privilege(nome_role, 'nsi_operacional', 'CREATE')") == 2
    assert fase_3.count("has_table_privilege(nome_role, c.oid, 'SELECT')") == 2
    assert fase_3.count("IF revisao = '0006' AND total <> 0 THEN") == 2, "Antes da 0007, nenhum EXECUTE."
    for banco in ("postgres", "nsi_dev", "nsi_test"):
        assert f"has_database_privilege(nome_role, '{banco}', 'CREATE')" in fase_3


def test_prov_encerramento_orienta_senha_e_variaveis(prov):
    fim = prov["encerramento"]
    assert "Fase 3 (pos-validacao completa) passou integralmente." in fim
    for variavel in ("DATABASE_URL_NSI_ENVIO", "TEST_DATABASE_URL_NSI_ENVIO", "DATABASE_URL_NSI_WEBHOOK",
                     "TEST_DATABASE_URL_NSI_WEBHOOK"):
        assert variavel in fim
    assert "postgresql://" in fim and "migration 0007" in fim


# ============================================================
# desprovisionar_c3_roles_envio.sql
# ============================================================

def test_desp_so_a_fase_2_escreve(desp):
    for bloco in ("inicio", "fase_1", "gate", "fase_3", "encerramento"):
        assert _escritas(desp[bloco]) == [], bloco


def test_desp_fase_2_executa_exatamente_as_escritas_especificadas_na_ordem(desp):
    assert _escritas(desp["fase_2"]) == ESCRITAS_DA_REVERSAO


def test_desp_cada_escrita_esta_condicionada_a_existencia_da_role(desp):
    fase_2 = _linhas_de_codigo(desp["fase_2"])
    profundidade, fora_de_condicional = 0, []
    for linha in (l.strip() for l in fase_2.splitlines()):
        if linha.startswith("\\if "):
            profundidade += 1
        elif linha.startswith("\\endif"):
            profundidade -= 1
        elif profundidade == 0 and _escritas(linha):
            fora_de_condicional.append(linha)
    assert fora_de_condicional == [], "REVOKE e DROP de role inexistente abortariam o script."
    assert fase_2.count("\\if :f2_existe_envio") == fase_2.count("\\if :f2_existe_webhook") == 3


def test_desp_gate_pede_confirmacao_textual_exata_sempre(desp):
    gate = _linhas_de_codigo(desp["gate"])
    assert gate.count("\\prompt") == 1 and desp["gate"].count(FRASE_DE_CONFIRMACAO) == 2
    assert gate.index("\\if :conf_pode_prosseguir") < gate.index("\\else") < gate.index("\\quit") < gate.index("\\endif")
    assert LIGA_READ_ONLY in gate
    texto = CAMINHO_DESPROVISIONAR.read_text(encoding="utf-8")
    for outra in ("CONFIRMO-DESCARTAR-NSI-B6-AMBIENTE-DE-ENSAIO", "CONFIRMO-DESPROVISIONAR-NSI-B5-ROLE-IMPORTACAO"):
        assert outra not in texto, "A frase e propria da C3."


def test_desp_e_bloqueado_pela_migration_0007_e_por_sessao_aberta(desp):
    fase_1 = desp["fase_1"]
    assert fase_1.count("IS DISTINCT FROM '0006'") == 2
    assert fase_1.count("has_function_privilege(r.oid, p.oid, 'EXECUTE')") == 2
    assert "FROM pg_stat_activity WHERE usename IN ('nsi_envio', 'nsi_webhook')" in fase_1
    assert "donas de % objeto(s)" in fase_1 and "membership(s) inesperada(s)" in fase_1


def test_desp_pos_validacao_confirma_o_retorno_ao_estado_anterior(desp):
    fase_3 = desp["fase_3"]
    assert "rolname IN ('nsi_envio', 'nsi_webhook')" in fase_3 and "ainda existe" in fase_3
    assert "IF total <> 3 OR total_exatas <> 3 THEN" in fase_3
    assert fase_3.count("IS DISTINCT FROM '0006'") == 2


def test_scripts_da_c3_nunca_sao_carregados_por_codigo():
    for pasta in ("adapters", "core", "integration", "services", "migrations", "scripts"):
        for caminho in (BASE_DIR / pasta).rglob("*.py"):
            if "__pycache__" in caminho.parts:
                continue
            fonte = caminho.read_text(encoding="utf-8-sig")
            for nome in ("provisionar_c3_roles_envio.sql", "desprovisionar_c3_roles_envio.sql"):
                assert nome not in fonte, f"{caminho.relative_to(BASE_DIR)} cita {nome}"


# ============================================================
# config.py - URLs dos dois papeis
# ============================================================

URLS = {
    ("nsi_envio", "development"): ("DATABASE_URL_NSI_ENVIO", "postgresql://nsi_envio:s@localhost:5432/nsi_dev"),
    ("nsi_envio", "test"): ("TEST_DATABASE_URL_NSI_ENVIO", "postgresql://nsi_envio:s@localhost:5432/nsi_test"),
    ("nsi_webhook", "development"): ("DATABASE_URL_NSI_WEBHOOK", "postgresql://nsi_webhook:s@localhost:5432/nsi_dev"),
    ("nsi_webhook", "test"): ("TEST_DATABASE_URL_NSI_WEBHOOK", "postgresql://nsi_webhook:s@localhost:5432/nsi_test"),
}


@pytest.fixture
def sem_urls(monkeypatch):
    for variavel, _ in URLS.values():
        monkeypatch.setattr(Config, variavel, "")
    monkeypatch.setattr(Config, "DATABASE_SSLMODE", "prefer")
    return monkeypatch


@pytest.mark.parametrize("papel,ambiente", sorted(URLS))
def test_papel_resolve_somente_pela_propria_variavel(sem_urls, papel, ambiente):
    variavel, url = URLS[(papel, ambiente)]
    with pytest.raises(ConfiguracaoBancoAusente):
        resolver_url_banco_papel(papel, ambiente)
    for outra, outra_url in URLS.values():
        if outra != variavel:
            sem_urls.setattr(Config, outra, outra_url)
    with pytest.raises(ConfiguracaoBancoAusente):
        resolver_url_banco_papel(papel, ambiente)  # nenhum fallback entre papeis nem entre ambientes
    sem_urls.setattr(Config, variavel, url)
    assert resolver_url_banco_papel(papel, ambiente) == url


@pytest.mark.parametrize("papel,ambiente", sorted(URLS))
def test_papel_recusa_banco_e_usuario_trocados(sem_urls, papel, ambiente):
    variavel, url = URLS[(papel, ambiente)]
    outro_banco = "nsi_test" if ambiente == "development" else "nsi_dev"
    sem_urls.setattr(Config, variavel, url.rsplit("/", 1)[0] + "/" + outro_banco)
    with pytest.raises(BancoFuncionalNaoPermitido):
        resolver_url_banco_papel(papel, ambiente)
    outro_usuario = "nsi_webhook" if papel == "nsi_envio" else "nsi_envio"
    sem_urls.setattr(Config, variavel, url.replace(f"//{papel}:", f"//{outro_usuario}:"))
    with pytest.raises(UsuarioBancoDivergente) as exc_info:
        resolver_url_banco_papel(papel, ambiente)
    assert ":s@" not in str(exc_info.value), "A excecao nunca carrega a senha."


@pytest.mark.parametrize("papel", ["nsi_envio", "nsi_webhook"])
def test_papeis_de_envio_nao_existem_no_ambiente_de_ensaio(sem_urls, papel):
    with pytest.raises(PapelBancoInvalido):
        resolver_url_banco_papel(papel, "ensaio")
