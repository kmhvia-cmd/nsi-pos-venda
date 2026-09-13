# -*- coding: utf-8 -*-
"""
NSI - tests/unit/test_scripts_b3_roles.py

Testes ESTATICOS (Sprint B, B3.1 - ADR-008, Parte 1 da B3 e correcoes de
seguranca da PARTE 2A) do conteudo, ordem, gates e protecoes dos dois
scripts administrativos:

    scripts/postgres_local/provisionar_b3_roles.sql
    scripts/postgres_local/desprovisionar_b3_roles.sql

Nenhum destes testes executa SQL, conecta a um banco, ou depende de
PostgreSQL - apenas le o texto dos arquivos e confirma, por inspecao de
string/posicao, que a estrutura aprovada esta presente e na ordem correta.
Isto e deliberado (correcao de seguranca aprovada): nenhum teste
automatizado pode executar o provisionamento ou o desprovisionamento
administrativo real contra o cluster PostgreSQL local compartilhado -
esses cenarios (incluindo os destrutivos) permanecem exclusivamente
manuais, documentados em
docs/implementation/PROCEDIMENTO-MANUAL-B3-DESTRUTIVO.md.
"""
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CAMINHO_PROVISIONAR = BASE_DIR / "scripts" / "postgres_local" / "provisionar_b3_roles.sql"
CAMINHO_DESPROVISIONAR = BASE_DIR / "scripts" / "postgres_local" / "desprovisionar_b3_roles.sql"


def _ler(caminho: Path) -> str:
    assert caminho.is_file(), f"Arquivo esperado nao encontrado: {caminho}"
    return caminho.read_text(encoding="utf-8")


def _linhas_de_codigo(texto: str) -> str:
    """Remove linhas de comentario ('--' apos strip) - usado para checagens
    de AUSENCIA que nao devem disparar falso-positivo por causa de um
    comentario explicando o que o script deliberadamente NAO faz."""
    return "\n".join(
        linha for linha in texto.splitlines() if not linha.strip().startswith("--")
    )


@pytest.fixture(scope="module")
def texto_provisionar():
    return _ler(CAMINHO_PROVISIONAR)


@pytest.fixture(scope="module")
def texto_desprovisionar():
    return _ler(CAMINHO_DESPROVISIONAR)


# ============================================================
# provisionar_b3_roles.sql
# ============================================================

def test_provisionar_tem_on_error_stop(texto_provisionar):
    assert "\\set ON_ERROR_STOP on" in texto_provisionar


def test_provisionar_verifica_identidade_do_servidor(texto_provisionar):
    assert "current_database() <> 'postgres'" in texto_provisionar
    assert "PostgreSQL 17" in texto_provisionar
    assert "inet_server_port() <> 5432" in texto_provisionar


def test_provisionar_verifica_pre_requisitos_de_b2(texto_provisionar):
    assert "nsi_dev_migrator" in texto_provisionar
    assert "nsi_test_migrator" in texto_provisionar
    assert "provisionar_dev_teste.sql (B2.2)" in texto_provisionar


def test_provisionar_tem_as_tres_fases_na_ordem_correta(texto_provisionar):
    indice_fase1 = texto_provisionar.index("FASE 1 - SOMENTE LEITURA")
    indice_fase2 = texto_provisionar.index("FASE 2 - CONVERGENCIA")
    indice_fase3 = texto_provisionar.index("FASE 3 - POS-VALIDACAO COMPLETA")
    assert indice_fase1 < indice_fase2 < indice_fase3


def test_provisionar_nenhuma_escrita_antes_da_fase_2(texto_provisionar):
    """Nenhum CREATE ROLE, GRANT ou ALTER SCHEMA (fora de comentario) pode
    aparecer antes do marcador da Fase 2 - a preflight e somente leitura."""
    indice_fase2 = texto_provisionar.index("FASE 2 - CONVERGENCIA")
    trecho_fase1 = _linhas_de_codigo(texto_provisionar[:indice_fase2])
    assert "CREATE ROLE" not in trecho_fase1
    assert "ALTER SCHEMA" not in trecho_fase1
    assert "GRANT nsi_eventos_owner" not in trecho_fase1


@pytest.mark.parametrize("linha_esperada", [
    "CREATE ROLE nsi_eventos_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;",
    "CREATE ROLE nsi_aplicacao LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;",
    "CREATE ROLE nsi_expiracao LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;",
    "CREATE ROLE nsi_operador_restrito LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;",
])
def test_provisionar_cria_roles_com_atributos_explicitos(texto_provisionar, linha_esperada):
    assert linha_esperada in texto_provisionar


def test_provisionar_create_role_so_aparece_depois_da_fase_2(texto_provisionar):
    indice_fase2 = texto_provisionar.index("FASE 2 - CONVERGENCIA")
    for role in ("nsi_eventos_owner", "nsi_aplicacao", "nsi_expiracao", "nsi_operador_restrito"):
        indice_create = texto_provisionar.index(f"CREATE ROLE {role} ")
        assert indice_create > indice_fase2, f"CREATE ROLE {role} aparece antes da Fase 2"


def test_provisionar_create_role_esta_guardado_por_if(texto_provisionar):
    for var_gset in ("precisa_criar_owner", "precisa_criar_aplicacao", "precisa_criar_expiracao", "precisa_criar_operador"):
        assert f"\\if :{var_gset}" in texto_provisionar


def test_provisionar_membership_dos_migrators_com_opcoes_corretas(texto_provisionar):
    assert "GRANT nsi_eventos_owner TO nsi_dev_migrator WITH INHERIT FALSE, SET TRUE, ADMIN FALSE;" in texto_provisionar
    assert "GRANT nsi_eventos_owner TO nsi_test_migrator WITH INHERIT FALSE, SET TRUE, ADMIN FALSE;" in texto_provisionar


def test_provisionar_conecta_migrator_apenas_no_proprio_banco(texto_provisionar):
    assert "GRANT CONNECT ON DATABASE nsi_dev  TO nsi_dev_migrator;" in texto_provisionar
    assert "GRANT CONNECT ON DATABASE nsi_test TO nsi_test_migrator;" in texto_provisionar
    assert "REVOKE CONNECT ON DATABASE nsi_dev  FROM PUBLIC;" in texto_provisionar
    assert "REVOKE CONNECT ON DATABASE nsi_test FROM PUBLIC;" in texto_provisionar


def test_provisionar_conecta_tres_roles_funcionais_nos_dois_bancos(texto_provisionar):
    assert "GRANT CONNECT ON DATABASE nsi_dev  TO nsi_aplicacao, nsi_expiracao, nsi_operador_restrito;" in texto_provisionar
    assert "GRANT CONNECT ON DATABASE nsi_test TO nsi_aplicacao, nsi_expiracao, nsi_operador_restrito;" in texto_provisionar


def test_provisionar_valida_ausencia_de_membership_inesperada(texto_provisionar):
    """Correcao aprovada: as quatro roles funcionais nao podem pertencer a
    nenhuma outra role nao prevista - checado tanto na preflight quanto na
    pos-validacao (duas ocorrencias por role, oito no total)."""
    ocorrencias = texto_provisionar.count("pg_auth_members m JOIN pg_roles r ON r.oid = m.member")
    assert ocorrencias == 8


def test_provisionar_valida_rolinherit(texto_provisionar):
    assert "rolinherit" in texto_provisionar


def test_provisionar_nunca_usa_has_privilege_com_pseudo_role_public(texto_provisionar):
    """has_database_privilege('public', ...)/has_function_privilege('public', ...)
    tratariam 'public' como nome de role real (inexistente) - nunca como o
    pseudo-role PUBLIC. So pode aparecer dentro de um COMENTARIO explicando
    a decisao, nunca em uma linha de codigo executavel."""
    codigo = _linhas_de_codigo(texto_provisionar)
    assert "has_database_privilege('public'" not in codigo
    assert "has_function_privilege('public'" not in codigo
    # a explicacao em comentario precisa existir (prova de que a decisao
    # foi deliberada, nao apenas ausente por esquecimento).
    assert "has_database_privilege('public'" in texto_provisionar


def test_provisionar_usa_aclexplode_para_checar_public(texto_provisionar):
    assert "aclexplode" in texto_provisionar
    assert "acl.grantee = 0" in texto_provisionar


def test_provisionar_has_schema_privilege_so_com_roles_nomeadas(texto_provisionar):
    """has_schema_privilege() e valido com nome de role REAL (diferente do
    caso 'public' acima) - confirma que as chamadas usam nomes de role
    existentes, nunca o pseudo-role."""
    assert "has_schema_privilege('nsi_dev_migrator'" in texto_provisionar
    assert "has_schema_privilege('nsi_test_migrator'" in texto_provisionar
    assert "has_schema_privilege('public'" not in texto_provisionar


def test_provisionar_pos_validacao_confere_alembic_version(texto_provisionar):
    assert "tableowner FROM pg_tables WHERE schemaname = 'nsi_operacional' AND tablename = 'alembic_version'" in texto_provisionar
    assert "<> 'nsi_dev_migrator'" in texto_provisionar
    assert "<> 'nsi_test_migrator'" in texto_provisionar


def test_provisionar_pos_validacao_esta_apos_fase_2(texto_provisionar):
    indice_fase2 = texto_provisionar.index("FASE 2 - CONVERGENCIA")
    indice_fase3 = texto_provisionar.index("FASE 3 - POS-VALIDACAO COMPLETA")
    indice_pos_validacao_owner = texto_provisionar.index("Pos-validacao falhou: schema nsi_operacional em nsi_dev")
    assert indice_fase2 < indice_fase3 < indice_pos_validacao_owner


def test_provisionar_nao_contem_senha_literal(texto_provisionar):
    """As linhas de CREATE ROLE nunca incluem a clausula SQL PASSWORD '...' -
    a unica mencao permitida a senha e a referencia ao comando interativo
    \\password (meta-comando do psql, nunca um valor embutido)."""
    assert "PASSWORD '" not in texto_provisionar
    assert "ENCRYPTED PASSWORD" not in texto_provisionar.upper()


def test_provisionar_menciona_procedimento_manual_de_senha(texto_provisionar):
    assert "\\password nsi_aplicacao" in texto_provisionar
    assert "\\password nsi_expiracao" in texto_provisionar
    assert "\\password nsi_operador_restrito" in texto_provisionar


def test_provisionar_nunca_e_chamado_automaticamente(texto_provisionar):
    assert "NAO E EXECUTADO AUTOMATICAMENTE" in texto_provisionar


# ============================================================
# desprovisionar_b3_roles.sql
# ============================================================

def test_desprovisionar_tem_on_error_stop(texto_desprovisionar):
    assert "\\set ON_ERROR_STOP on" in texto_desprovisionar


def test_desprovisionar_exige_revisao_exata_0001_nos_dois_bancos(texto_desprovisionar):
    assert texto_desprovisionar.count("version_num INTO valor_revisao FROM nsi_operacional.alembic_version") == 2
    assert texto_desprovisionar.count("IF valor_revisao <> '0001' THEN") == 2


def test_desprovisionar_nunca_recomenda_downgrade_base(texto_desprovisionar):
    """'alembic downgrade base' so pode aparecer em COMENTARIO explicando o
    que este script deliberadamente NAO usa como referencia - nunca como
    uma instrucao executavel (este script nunca invoca o Alembic)."""
    codigo = _linhas_de_codigo(texto_desprovisionar)
    assert "alembic downgrade base" not in codigo.lower()
    assert "downgrade base" in texto_desprovisionar.lower()  # presente so no comentario


def test_desprovisionar_gate1_antes_do_prompt(texto_desprovisionar):
    indice_gate1 = texto_desprovisionar.index("GATE 1")
    indice_prompt = texto_desprovisionar.index("\\prompt")
    assert indice_gate1 < indice_prompt


def test_desprovisionar_exige_confirmacao_textual_exata(texto_desprovisionar):
    assert "CONFIRMO-DESPROVISIONAR-NSI-B3-ROLES" in texto_desprovisionar
    assert "\\prompt" in texto_desprovisionar


def test_desprovisionar_gate2_verifica_dependencias_antes_do_drop(texto_desprovisionar):
    indice_gate2 = texto_desprovisionar.index("GATE 2")
    indice_drop = texto_desprovisionar.index("DROP ROLE IF EXISTS nsi_aplicacao")
    assert indice_gate2 < indice_drop
    assert texto_desprovisionar.count("pg_class c JOIN pg_roles r ON r.oid = c.relowner") == 2
    assert texto_desprovisionar.count("pg_proc p JOIN pg_roles r ON r.oid = p.proowner") == 2


def test_desprovisionar_prompt_antes_do_gate2(texto_desprovisionar):
    indice_prompt = texto_desprovisionar.index("\\prompt")
    indice_gate2 = texto_desprovisionar.index("GATE 2")
    assert indice_prompt < indice_gate2


def test_desprovisionar_remove_exatamente_as_quatro_roles_de_b3(texto_desprovisionar):
    assert "DROP ROLE IF EXISTS nsi_aplicacao;" in texto_desprovisionar
    assert "DROP ROLE IF EXISTS nsi_expiracao;" in texto_desprovisionar
    assert "DROP ROLE IF EXISTS nsi_operador_restrito;" in texto_desprovisionar
    assert "DROP ROLE IF EXISTS nsi_eventos_owner;" in texto_desprovisionar
    assert "DROP ROLE IF EXISTS nsi_dev_migrator" not in texto_desprovisionar
    assert "DROP ROLE IF EXISTS nsi_test_migrator" not in texto_desprovisionar
    assert "DROP DATABASE" not in texto_desprovisionar


def test_desprovisionar_preserva_connect_dos_migrators(texto_desprovisionar):
    """Correcao aprovada: o CONNECT explicito de cada migrator no proprio
    banco NUNCA e revogado por este script - so o das tres roles
    funcionais."""
    assert "REVOKE CONNECT ON DATABASE nsi_dev  FROM nsi_dev_migrator" not in texto_desprovisionar
    assert "REVOKE CONNECT ON DATABASE nsi_test FROM nsi_test_migrator" not in texto_desprovisionar
    assert "REVOKE CONNECT ON DATABASE nsi_dev  FROM nsi_aplicacao, nsi_expiracao, nsi_operador_restrito;" in texto_desprovisionar
    assert "REVOKE CONNECT ON DATABASE nsi_test FROM nsi_aplicacao, nsi_expiracao, nsi_operador_restrito;" in texto_desprovisionar


def test_desprovisionar_nunca_concede_connect_a_public(texto_desprovisionar):
    """PUBLIC nao recupera CONNECT automaticamente - nenhuma linha deste
    script concede CONNECT a PUBLIC."""
    assert "GRANT CONNECT" not in texto_desprovisionar or "TO PUBLIC" not in texto_desprovisionar
    codigo = _linhas_de_codigo(texto_desprovisionar)
    assert "TO PUBLIC" not in codigo


def test_desprovisionar_schema_volta_ao_migrator(texto_desprovisionar):
    assert "ALTER SCHEMA nsi_operacional OWNER TO nsi_dev_migrator;" in texto_desprovisionar
    assert "ALTER SCHEMA nsi_operacional OWNER TO nsi_test_migrator;" in texto_desprovisionar


def test_desprovisionar_nao_contem_senha(texto_desprovisionar):
    assert "password" not in texto_desprovisionar.lower()
    assert "PASSWORD '" not in texto_desprovisionar


def test_desprovisionar_nunca_e_chamado_automaticamente(texto_desprovisionar):
    assert "NENHUM TESTE AUTOMATIZADO CHAMA ESTE ARQUIVO" in texto_desprovisionar


def test_desprovisionar_identico_padrao_de_identidade_do_servidor(texto_desprovisionar):
    assert "current_database() <> 'postgres'" in texto_desprovisionar
    assert "PostgreSQL 17" in texto_desprovisionar
