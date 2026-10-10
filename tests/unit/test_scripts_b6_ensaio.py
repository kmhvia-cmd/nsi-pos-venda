# -*- coding: utf-8 -*-
"""
NSI - tests/unit/test_scripts_b6_ensaio.py
(Sprint B, B6.2 - SPRINT-B6-ESPECIFICACAO-ENSAIO-DE-CORTE.md, Secoes 14, 15,
30, 32 e 34, componente C2)

Testes ESTATICOS, sem banco, dos dois scripts administrativos do ambiente
de ensaio. Os scripts exigem o superusuario e so sao executados manualmente
pelo operador, na B6.3 - nenhum teste os executa. O que se comprova aqui e
o desenho: tres fases, somente leitura fora da Fase 2, escritas exatas e na
ordem, gate de confirmacao no descarte, ausencia de senha e de comando
proibido.
"""
import re
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CAMINHO_PROVISIONAR = BASE_DIR / "scripts" / "postgres_local" / "provisionar_b6_ensaio.sql"
CAMINHO_DESPROVISIONAR = BASE_DIR / "scripts" / "postgres_local" / "desprovisionar_b6_ensaio.sql"

MARCADOR_FASE_1 = "-- FASE 1 - PREFLIGHT"
MARCADOR_FASE_2_PROV = "-- FASE 2 - CONVERGENCIA"
MARCADOR_FASE_2_DESP = "-- FASE 2 - DESCARTE"
MARCADOR_GATE = "-- GATE DE CONFIRMACAO"
MARCADOR_FASE_3 = "-- FASE 3 - POS-VALIDACAO COMPLETA"
MARCADOR_ENCERRAMENTO = "-- ENCERRAMENTO"

LIGA_READ_ONLY = "SET default_transaction_read_only = on;"
LIBERA_ESCRITA = "SET default_transaction_read_only = off;"
FRASE_DE_CONFIRMACAO = "CONFIRMO-DESCARTAR-NSI-B6-AMBIENTE-DE-ENSAIO"

COMANDOS_DE_ESCRITA = ["CREATE", "ALTER", "DROP", "GRANT", "REVOKE", "INSERT", "UPDATE", "DELETE", "TRUNCATE",
                       "EXECUTE", "REASSIGN", "COMMENT", "COPY", "MERGE", "CHECKPOINT"]

ESCRITAS_DO_PROVISIONAMENTO = [
    "CREATE ROLE nsi_ensaio_migrator LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;",
    "GRANT nsi_eventos_owner TO nsi_ensaio_migrator WITH INHERIT FALSE, SET TRUE, ADMIN FALSE;",
    "CREATE DATABASE nsi_ensaio TEMPLATE template0 ENCODING 'UTF8';",
    "REVOKE CONNECT ON DATABASE nsi_ensaio FROM PUBLIC;",
    "GRANT CONNECT ON DATABASE nsi_ensaio TO nsi_ensaio_migrator;",
    "GRANT CONNECT ON DATABASE nsi_ensaio TO nsi_importacao;",
    "CREATE SCHEMA nsi_operacional AUTHORIZATION nsi_eventos_owner;",
    "GRANT USAGE ON SCHEMA nsi_operacional TO nsi_ensaio_migrator;",
    "GRANT USAGE ON SCHEMA nsi_operacional TO nsi_importacao;",
    "CREATE TABLE nsi_operacional.alembic_version (",
    "ALTER TABLE nsi_operacional.alembic_version OWNER TO nsi_ensaio_migrator;",
]
ESCRITAS_DO_DESCARTE = [
    "REVOKE CONNECT ON DATABASE nsi_ensaio FROM nsi_importacao;",
    "DROP DATABASE nsi_ensaio;",
    "REVOKE nsi_eventos_owner FROM nsi_ensaio_migrator;",
    "DROP ROLE nsi_ensaio_migrator;",
    "CHECKPOINT;",
]


def _linhas_de_codigo(texto: str) -> str:
    return "\n".join(linha for linha in texto.splitlines() if not linha.strip().startswith("--"))


def _codigo(texto: str) -> str:
    """Codigo sem comentarios e sem o conteudo de literais de texto."""
    return re.sub(r"'(?:[^']|'')*'", "''", _linhas_de_codigo(texto))


def _escritas(bloco: str) -> list:
    """Comandos de escrita de um bloco, na ordem: linhas de codigo que
    comecam por um comando de escrita."""
    padrao = re.compile(r"^(%s)\b" % "|".join(COMANDOS_DE_ESCRITA))
    return [linha.strip() for linha in _linhas_de_codigo(bloco).splitlines() if padrao.match(linha.strip())]


def _dividir(texto: str, marcadores: list, nomes: list) -> dict:
    indices = [texto.index(m) for m in marcadores]
    assert indices == sorted(indices), "Os marcadores das fases precisam aparecer na ordem."
    limites = [0] + indices + [len(texto)]
    return {nome: texto[limites[i]:limites[i + 1]] for i, nome in enumerate(nomes)}


@pytest.fixture(scope="module")
def texto_prov():
    return CAMINHO_PROVISIONAR.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def prov(texto_prov):
    return _dividir(texto_prov, [MARCADOR_FASE_1, MARCADOR_FASE_2_PROV, MARCADOR_FASE_3, MARCADOR_ENCERRAMENTO],
                    ["inicio", "fase_1", "fase_2", "fase_3", "encerramento"])


@pytest.fixture(scope="module")
def texto_desp():
    return CAMINHO_DESPROVISIONAR.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def desp(texto_desp):
    return _dividir(texto_desp,
                    [MARCADOR_FASE_1, MARCADOR_GATE, MARCADOR_FASE_2_DESP, MARCADOR_FASE_3, MARCADOR_ENCERRAMENTO],
                    ["inicio", "fase_1", "gate", "fase_2", "fase_3", "encerramento"])


# ============================================================
# Comuns aos dois scripts
# ============================================================

@pytest.mark.parametrize("caminho", [CAMINHO_PROVISIONAR, CAMINHO_DESPROVISIONAR], ids=["provisionar", "descartar"])
def test_arquivo_integro_com_blocos_balanceados(caminho):
    texto = caminho.read_text(encoding="utf-8")
    assert texto.isascii(), "Somente ASCII, como os demais scripts administrativos."
    codigo = _linhas_de_codigo(texto)
    assert codigo.count("DO $$") == codigo.count("END $$;") > 0
    assert codigo.count("\\if ") == codigo.count("\\endif")
    assert codigo.count("\\gset") >= 1


@pytest.mark.parametrize("caminho", [CAMINHO_PROVISIONAR, CAMINHO_DESPROVISIONAR], ids=["provisionar", "descartar"])
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


@pytest.mark.parametrize("caminho", [CAMINHO_PROVISIONAR, CAMINHO_DESPROVISIONAR], ids=["provisionar", "descartar"])
def test_nao_contem_senha_nem_comando_de_senha(caminho):
    codigo = _codigo(caminho.read_text(encoding="utf-8")).upper()
    assert "PASSWORD" not in codigo and "\\PASSWORD" not in codigo
    assert "ENCRYPTED" not in codigo and "VALID UNTIL" not in codigo


@pytest.mark.parametrize("caminho", [CAMINHO_PROVISIONAR, CAMINHO_DESPROVISIONAR], ids=["provisionar", "descartar"])
def test_cabecalho_declara_execucao_manual(caminho):
    cabecalho = caminho.read_text(encoding="utf-8").split("\\set ON_ERROR_STOP on")[0]
    assert "NUNCA PRODUCAO" in cabecalho.upper() or "NUNCA EXECUTAR CONTRA PRODUCAO" in cabecalho.upper()
    assert "MANUAL" in cabecalho.upper()
    assert "NAO CONTEM SENHA" in cabecalho


@pytest.mark.parametrize("caminho", [CAMINHO_PROVISIONAR, CAMINHO_DESPROVISIONAR], ids=["provisionar", "descartar"])
def test_modo_somente_leitura_e_religado_e_conferido_depois_de_cada_troca_de_banco(caminho):
    """\\c abre uma sessao nova, em modo normal. Fora da Fase 2, toda troca
    de banco e seguida por religar e conferir o modo somente leitura."""
    texto = caminho.read_text(encoding="utf-8")
    fase_2 = MARCADOR_FASE_2_PROV if caminho == CAMINHO_PROVISIONAR else MARCADOR_FASE_2_DESP
    fora_da_fase_2 = texto[:texto.index(fase_2)] + texto[texto.index(MARCADOR_FASE_3):]
    comandos = [l.strip() for l in _linhas_de_codigo(fora_da_fase_2).splitlines() if l.strip()]
    trocas = [i for i, comando in enumerate(comandos) if comando.startswith("\\c ")]
    assert trocas, "As Fases 1 e 3 leem mais de um banco."
    for i in trocas:
        assert comandos[i + 1] == LIGA_READ_ONLY, f"Depois de '{comandos[i]}' o modo somente leitura nao e religado."
    assert fora_da_fase_2.count("current_setting('transaction_read_only') <> 'on'") >= len(trocas) - 1


@pytest.mark.parametrize("caminho", [CAMINHO_PROVISIONAR, CAMINHO_DESPROVISIONAR], ids=["provisionar", "descartar"])
def test_escrita_e_liberada_em_um_unico_ponto(caminho):
    texto = caminho.read_text(encoding="utf-8")
    codigo = _linhas_de_codigo(texto)
    assert codigo.count(LIBERA_ESCRITA) == 1
    fase_2 = MARCADOR_FASE_2_PROV if caminho == CAMINHO_PROVISIONAR else MARCADOR_FASE_2_DESP
    assert texto.index(fase_2) < texto.index(LIBERA_ESCRITA) < texto.index(MARCADOR_FASE_3)
    assert "transaction_read_only = off" not in codigo.replace(LIBERA_ESCRITA, "")


@pytest.mark.parametrize("caminho", [CAMINHO_PROVISIONAR, CAMINHO_DESPROVISIONAR], ids=["provisionar", "descartar"])
def test_nenhum_comando_proibido(caminho):
    codigo = _codigo(caminho.read_text(encoding="utf-8")).upper()
    for proibido in ("CASCADE", "DROP OWNED", "REASSIGN OWNED", "WITH (FORCE)", "PG_TERMINATE_BACKEND",
                     "DISABLE TRIGGER", "TRUNCATE", "DROP SCHEMA", "DROP TABLE", "SUPERUSER;", "ALTER ROLE",
                     "ALTER SYSTEM", "DELETE FROM"):
        assert proibido not in codigo, proibido
    for banco_permanente in ("NSI_DEV", "NSI_TEST"):
        for comando in ("DROP DATABASE", "ALTER DATABASE", "GRANT CONNECT ON DATABASE", "REVOKE CONNECT ON DATABASE"):
            assert f"{comando} {banco_permanente}" not in codigo, "Os bancos permanentes nunca sao tocados."


@pytest.mark.parametrize("caminho", [CAMINHO_PROVISIONAR, CAMINHO_DESPROVISIONAR], ids=["provisionar", "descartar"])
def test_variaveis_de_cliente_sao_prefixadas_pelo_bloco(caminho):
    texto = caminho.read_text(encoding="utf-8")
    variaveis = set(re.findall(r"\bAS (\w+)\s*\n\\gset", texto)) | set(re.findall(r":'?(\w+)'?", _linhas_de_codigo(
        "\n".join(l for l in texto.splitlines() if l.strip().startswith("\\if") or "\\gset" in l or ":'" in l))))
    variaveis = {v for v in variaveis if re.match(r"(f\d|conf)_", v)}
    assert variaveis, "O script usa variaveis de cliente."
    fase_3 = texto[texto.index(MARCADOR_FASE_3):]
    for variavel in variaveis:
        assert variavel not in fase_3, f"{variavel} cruza para a Fase 3."


# ============================================================
# provisionar_b6_ensaio.sql
# ============================================================

def test_prov_fases_1_e_3_nao_escrevem(prov):
    for bloco in ("inicio", "fase_1", "fase_3", "encerramento"):
        assert _escritas(prov[bloco]) == [], bloco
        assert not re.search(r"\bEXECUTE\b", _codigo(prov[bloco])), bloco


def test_prov_fase_2_executa_exatamente_as_escritas_especificadas_na_ordem(prov):
    """Secao 14 da especificacao: migrator, membership, banco, isolamento de
    CONNECT, schema, USAGE e tabela de controle - e nada alem."""
    assert _escritas(prov["fase_2"]) == ESCRITAS_DO_PROVISIONAMENTO


def test_prov_so_escreve_quando_o_ambiente_esta_ausente_por_inteiro(prov):
    fase_2 = _linhas_de_codigo(prov["fase_2"])
    assert "NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nsi_ensaio_migrator')" in fase_2
    assert "NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'nsi_ensaio')" in fase_2
    assert fase_2.count("\\if :f2_ambiente_ausente") == 1 and fase_2.count("\\else") == 1
    antes_do_if = fase_2[:fase_2.index("\\if :f2_ambiente_ausente")]
    depois_do_else = fase_2[fase_2.index("\\else"):]
    assert _escritas(antes_do_if) == [] and _escritas(depois_do_else) == []


def test_prov_preflight_recusa_ambiente_pela_metade(prov):
    assert "IF role_existe <> banco_existe THEN" in prov["fase_1"]
    assert "Ambiente de ensaio pela metade" in prov["fase_1"]
    assert "desprovisionar_b6_ensaio.sql" in prov["fase_1"]


def test_prov_migrator_tem_a_mesma_membership_dos_outros_migrators(prov):
    assert "WITH INHERIT FALSE, SET TRUE, ADMIN FALSE" in prov["fase_2"]
    for fase in ("fase_1", "fase_3"):
        assert "'nsi_dev_migrator', 'nsi_test_migrator'" in prov[fase]
        assert "nsi_ensaio_migrator" in prov[fase]
    assert "NOT m.inherit_option AND m.set_option AND NOT m.admin_option" in prov["fase_3"]


def test_prov_somente_o_migrator_e_nsi_importacao_recebem_acesso(texto_prov, prov):
    escritas = " ".join(_escritas(prov["fase_2"]))
    for role in ("nsi_aplicacao", "nsi_expiracao", "nsi_operador_restrito", "nsi_congelamento",
                 "nsi_dev_migrator", "nsi_test_migrator"):
        assert role not in escritas, f"{role} nao recebe nada no ambiente de ensaio."
    for role in ("nsi_aplicacao", "nsi_expiracao", "nsi_operador_restrito", "nsi_dev_migrator", "nsi_test_migrator"):
        assert f"has_database_privilege('{role}', 'nsi_ensaio', 'CONNECT')" in prov["fase_3"]
    assert "REVOKE CONNECT ON DATABASE nsi_ensaio FROM PUBLIC;" in prov["fase_2"]


def test_prov_nao_concede_execute_nem_privilegio_em_tabela(prov):
    escritas = _escritas(prov["fase_2"])
    assert not any("EXECUTE" in e or " ON TABLE " in e or "ALL PRIVILEGES" in e for e in escritas)
    assert not any(e.startswith("GRANT CREATE") for e in escritas)
    assert "has_schema_privilege('nsi_ensaio_migrator', 'nsi_operacional', 'CREATE')" in prov["fase_3"]


def test_prov_exige_as_oito_roles_e_os_dois_bancos_em_0006(prov):
    for fase in ("fase_1", "fase_3"):
        for role in ("nsi_eventos_owner", "nsi_aplicacao", "nsi_expiracao", "nsi_operador_restrito",
                     "nsi_congelamento", "nsi_importacao", "nsi_dev_migrator", "nsi_test_migrator"):
            assert f"'{role}'" in prov[fase], (fase, role)
        assert prov[fase].count("IS DISTINCT FROM '0006'") == 2, fase
        assert "\\c nsi_dev" in prov[fase] and "\\c nsi_test" in prov[fase]


def test_prov_banco_de_ensaio_tem_a_codificacao_e_a_localidade_de_nsi_test(prov):
    for fase in ("fase_1", "fase_3"):
        assert "pg_encoding_to_char(e.encoding) = 'UTF8'" in prov[fase]
        assert "e.datcollate = t.datcollate AND e.datctype = t.datctype" in prov[fase]


def test_prov_tabela_de_controle_e_a_mesma_que_o_alembic_cria(prov):
    fase_2 = prov["fase_2"]
    assert "version_num VARCHAR(32) NOT NULL" in fase_2
    assert "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)" in fase_2


def test_prov_nao_aplica_migration_e_orienta_somente_upgrade(texto_prov, prov):
    codigo = _codigo(prov["fase_2"]).lower()
    assert "alembic upgrade" not in codigo and "alembic downgrade" not in codigo and chr(92) + "!" not in codigo
    assert "NSI_DATABASE_ENV=ensaio alembic upgrade 0006" in prov["encerramento"]
    assert "NUNCA executar downgrade em nsi_ensaio" in prov["encerramento"]
    assert "Fase 3 (pos-validacao completa) passou integralmente." in prov["encerramento"]
    assert texto_prov.count("passou integralmente") == 1


# ============================================================
# desprovisionar_b6_ensaio.sql
# ============================================================

def test_desp_so_a_fase_2_escreve(desp):
    for bloco in ("inicio", "fase_1", "gate", "fase_3", "encerramento"):
        assert _escritas(desp[bloco]) == [], bloco


def test_desp_fase_2_executa_exatamente_as_escritas_especificadas_na_ordem(desp):
    assert _escritas(desp["fase_2"]) == ESCRITAS_DO_DESCARTE


def test_desp_descarte_e_por_remocao_do_banco_nunca_por_downgrade(texto_desp):
    codigo = _codigo(texto_desp).lower()
    assert "drop database nsi_ensaio;" in codigo
    assert "alembic upgrade" not in codigo and "downgrade" not in codigo and chr(92) + "!" not in codigo
    assert "nunca downgrade" in texto_desp.lower()


def test_desp_gate_pede_confirmacao_textual_exata_sempre(texto_desp, desp):
    assert texto_desp.count("\\prompt") == 1 and "\\prompt" in desp["gate"]
    assert desp["gate"].count(FRASE_DE_CONFIRMACAO) == 2
    for outra in ("CONFIRMO-DESPROVISIONAR-NSI-B5-ROLE-IMPORTACAO", "CONFIRMO-DESPROVISIONAR-NSI-B4-ROLE-CONGELAMENTO",
                  "CONFIRMO-DESPROVISIONAR-NSI-B3-ROLES"):
        assert outra not in texto_desp, "A frase e propria da B6."
    gate = _linhas_de_codigo(desp["gate"])
    assert gate.index("\\if :conf_pode_prosseguir") < gate.index("\\else") < gate.index("\\quit") < gate.index("\\endif")
    assert LIGA_READ_ONLY in gate


def test_desp_nunca_derruba_sessao_e_aborta_se_houver_alguma(desp):
    assert "FROM pg_stat_activity WHERE datname = 'nsi_ensaio'" in desp["fase_1"]
    assert "pg_stat_activity WHERE datname = 'nsi_ensaio'" in desp["fase_2"]
    fase_2 = _linhas_de_codigo(desp["fase_2"])
    assert fase_2.index("pg_stat_activity") < fase_2.index("DROP DATABASE nsi_ensaio;")


def test_desp_aceita_estado_parcial(desp):
    """Cada objeto ausente ou presente: o que existir e removido."""
    fase_2 = _linhas_de_codigo(desp["fase_2"])
    assert fase_2.count("\\if :f2_banco_existe") == 1 and fase_2.count("\\if :f2_role_existe") == 1
    assert fase_2.index("\\if :f2_banco_existe") < fase_2.index("DROP DATABASE nsi_ensaio;") \
        < fase_2.index("\\if :f2_role_existe") < fase_2.index("DROP ROLE nsi_ensaio_migrator;")
    assert "IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nsi_ensaio_migrator') THEN" in desp["fase_1"]


def test_desp_role_so_e_removida_sem_dependencia_fora_do_ensaio(desp):
    fase_1 = desp["fase_1"]
    assert "FROM pg_shdepend s JOIN pg_roles r ON r.oid = s.refobjid" in fase_1
    assert "dependencia(s) fora do banco de ensaio" in fase_1
    assert "g.rolname <> 'nsi_eventos_owner'" in fase_1


def test_desp_pos_validacao_confirma_o_retorno_ao_estado_permanente(desp):
    fase_3 = desp["fase_3"]
    assert "o banco nsi_ensaio ainda existe" in fase_3 and "a role nsi_ensaio_migrator ainda existe" in fase_3
    assert "r.rolname IN ('nsi_dev_migrator', 'nsi_test_migrator')" in fase_3
    assert "d.datname = 'nsi_test' AND a.privilege_type = 'CONNECT'" in fase_3
    assert fase_3.count("IS DISTINCT FROM '0006'") == 2
    assert "passou integralmente - ambiente de ensaio descartado" in desp["encerramento"]


def test_desp_reduz_o_residuo_no_log_de_transacoes(desp):
    fase_2 = _linhas_de_codigo(desp["fase_2"])
    assert "CHECKPOINT;" in fase_2 and "pg_switch_wal()" in fase_2
    assert fase_2.index("DROP ROLE nsi_ensaio_migrator;") < fase_2.index("CHECKPOINT;")


def test_scripts_do_ensaio_nunca_sao_carregados_por_codigo():
    """Nenhum codigo de aplicacao, script ou teste executa os scripts
    administrativos: o nome so aparece em docstring, comentario ou neste
    teste."""
    for pasta in ("adapters", "core", "integration", "services", "migrations", "scripts"):
        for caminho in (BASE_DIR / pasta).rglob("*.py"):
            if "__pycache__" in caminho.parts:
                continue
            fonte = caminho.read_text(encoding="utf-8-sig")
            for nome in ("provisionar_b6_ensaio.sql", "desprovisionar_b6_ensaio.sql"):
                assert nome not in fonte, f"{caminho.relative_to(BASE_DIR)} cita {nome}"
