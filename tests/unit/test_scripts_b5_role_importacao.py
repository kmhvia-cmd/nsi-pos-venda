# -*- coding: utf-8 -*-
"""
NSI - tests/unit/test_scripts_b5_role_importacao.py

Testes ESTATICOS (Sprint B, B5.3 - ADR-010, Secao 16; Especificacao
Tecnica, B5.2, itens 4 e 17) do conteudo, ordem, fases e protecoes dos dois
scripts administrativos da role nsi_importacao:

    scripts/postgres_local/provisionar_b5_role_importacao.sql
    scripts/postgres_local/desprovisionar_b5_role_importacao.sql

Nenhum destes testes executa SQL, conecta a um banco, ou depende de
PostgreSQL - apenas le o texto do arquivo e confirma, por inspecao de
string/posicao, que o desenho aprovado esta presente. Mesmo principio de
tests/unit/test_scripts_b4_role_congelamento.py: nenhum teste automatizado
pode executar o provisionamento administrativo real contra o cluster local.

O que estes testes sustentam, do desenho aprovado:

  - READ ONLY obrigatorio fora da Fase 2 (modo religado e conferido depois
    de cada \\c; escrita liberada em um unico ponto);
  - cada fase e autossuficiente (nenhuma variavel de uma fase e
    referenciada em outra; a Fase 2 nao usa variavel de cliente alguma);
  - a Fase 2 executa exatamente tres acoes de escrita, e nenhuma outra;
  - o que e proprio da role nsi_importacao: LOGIN, nenhuma membership,
    CONNECT e USAGE somente em nsi_test (nunca em nsi_dev), revisoes
    aceitas 0005 e 0006, EXECUTE somente nas quatro funcoes de importacao
    e somente em 0006, nenhuma senha no script;
  - no desprovisionamento, alem disso: gate de confirmacao textual antes
    da Fase 2, somente a revisao 0005, funcoes de importacao ausentes, e
    remocao da role condicionada a zero dependencias e zero sessoes.

O lancamento do cliente psql ja e proibido, nas pastas de codigo que aquele
teste varre (adapters, core, integration, services, migrations, tests,
app.py e config.py - a pasta scripts/ nao esta entre elas), por
tests/unit/test_scripts_b4_role_congelamento.py::test_nenhum_arquivo_executa_o_cliente_psql.
"""
import ast
import re
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CAMINHO_PROVISIONAR = BASE_DIR / "scripts" / "postgres_local" / "provisionar_b5_role_importacao.sql"
CAMINHO_DESPROVISIONAR = BASE_DIR / "scripts" / "postgres_local" / "desprovisionar_b5_role_importacao.sql"

MARCADOR_FASE_1 = "-- FASE 1 - PREFLIGHT"
MARCADOR_FASE_2 = "-- FASE 2 - CONVERGENCIA"
MARCADOR_FASE_3 = "-- FASE 3 - POS-VALIDACAO COMPLETA"
MARCADOR_ENCERRAMENTO = "-- ENCERRAMENTO"

DESP_MARCADOR_GATE = "-- GATE DE CONFIRMACAO"
DESP_MARCADOR_FASE_2 = "-- FASE 2 - DESPROVISIONAMENTO"

LIGA_READ_ONLY = "SET default_transaction_read_only = on;"
LIBERA_ESCRITA = "SET default_transaction_read_only = off;"

# Comandos que escrevem (ou que poderiam executar SQL dinamico). Procurados
# somente em CODIGO - comentarios e literais de texto ja removidos.
COMANDOS_DE_ESCRITA = [
    "CREATE", "ALTER", "DROP", "GRANT", "REVOKE", "INSERT", "UPDATE", "DELETE",
    "TRUNCATE", "EXECUTE", "REASSIGN", "COMMENT", "COPY", "MERGE",
]

QUATRO_FUNCOES_DE_IMPORTACAO = [
    "fn_iniciar_importacao_legado", "fn_importar_lote_legado",
    "fn_concluir_importacao_legado", "fn_verificar_paridade_legado",
]

ESCRITAS_APROVADAS_PROVISIONAMENTO = [
    "CREATE ROLE nsi_importacao LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS",
    "GRANT CONNECT ON DATABASE nsi_test TO nsi_importacao",
    "GRANT USAGE ON SCHEMA nsi_operacional TO nsi_importacao",
]

ESCRITAS_APROVADAS_DESPROVISIONAMENTO = [
    "REVOKE USAGE ON SCHEMA nsi_operacional FROM nsi_importacao",
    "REVOKE CONNECT ON DATABASE nsi_test FROM nsi_importacao",
    "DROP ROLE nsi_importacao",
]

FRASE_CONFIRMACAO_B5 = "CONFIRMO-DESPROVISIONAR-NSI-B5-ROLE-IMPORTACAO"
FRASES_DE_OUTRAS_SUBETAPAS = ["CONFIRMO-DESPROVISIONAR-NSI-B4-ROLE-CONGELAMENTO", "CONFIRMO-DESPROVISIONAR-NSI-B3-ROLES"]

PASTAS_DE_CODIGO = ("adapters", "core", "integration", "services", "migrations", "tests", "scripts")
ARQUIVOS_DE_CODIGO = ("app.py", "config.py")


def _linhas_de_codigo(texto: str) -> str:
    """Remove as linhas que sao so comentario SQL ('--')."""
    return "\n".join(linha for linha in texto.splitlines() if not linha.strip().startswith("--"))


def _sem_literais(texto: str) -> str:
    """Remove o conteudo de literais de texto ('...'), para que palavras que
    aparecem apenas em mensagens ou em nomes de privilegio comparados nao
    sejam confundidas com comandos."""
    return re.sub(r"'(?:[^']|'')*'", "''", texto)


def _codigo(texto: str) -> str:
    return _sem_literais(_linhas_de_codigo(texto))


def _comandos(bloco: str) -> list:
    return [l.strip() for l in _linhas_de_codigo(bloco).splitlines() if l.strip()]


def _acoes(fase_2: str) -> list:
    return re.findall(r"DO \$\$.*?END \$\$;", fase_2, flags=re.DOTALL)


def _escritas(bloco: str) -> list:
    return re.findall(r"EXECUTE '([^']*)'", _linhas_de_codigo(bloco))


def _trocas_de_banco(bloco: str) -> list:
    return [l[3:] for l in _comandos(bloco) if l.startswith("\\c ")]


@pytest.fixture(scope="module")
def texto():
    return CAMINHO_PROVISIONAR.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def fases(texto):
    """Divide o provisionamento nos blocos do desenho aprovado."""
    i1, i2 = texto.index(MARCADOR_FASE_1), texto.index(MARCADOR_FASE_2)
    i3, i4 = texto.index(MARCADOR_FASE_3), texto.index(MARCADOR_ENCERRAMENTO)
    return {
        "inicio": texto[:i1],
        "fase_1": texto[i1:i2],
        "fase_2": texto[i2:i3],
        "fase_3": texto[i3:i4],
        "encerramento": texto[i4:],
    }


@pytest.fixture(scope="module")
def texto_desp():
    return CAMINHO_DESPROVISIONAR.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def blocos_desp(texto_desp):
    """Divide o desprovisionamento nos blocos do desenho aprovado."""
    i1, ig = texto_desp.index(MARCADOR_FASE_1), texto_desp.index(DESP_MARCADOR_GATE)
    i2, i3 = texto_desp.index(DESP_MARCADOR_FASE_2), texto_desp.index(MARCADOR_FASE_3)
    i4 = texto_desp.index(MARCADOR_ENCERRAMENTO)
    return {
        "inicio": texto_desp[:i1],
        "fase_1": texto_desp[i1:ig],
        "gate": texto_desp[ig:i2],
        "fase_2": texto_desp[i2:i3],
        "fase_3": texto_desp[i3:i4],
        "encerramento": texto_desp[i4:],
    }


# ============================================================
# ============================================================
# provisionar_b5_role_importacao.sql
# ============================================================
# ============================================================

# ------------------------------------------------------------
# Integridade e estrutura
# ------------------------------------------------------------

@pytest.mark.parametrize("caminho", [CAMINHO_PROVISIONAR, CAMINHO_DESPROVISIONAR], ids=["provisionar", "desprovisionar"])
def test_arquivo_esta_integro_e_com_blocos_balanceados(caminho):
    """Nenhum arquivo truncado: termina com quebra de linha, e todo bloco
    DO aberto e fechado, com IF/END IF e LOOP/END LOOP balanceados."""
    bruto = caminho.read_bytes()
    assert bruto.endswith(b"\n") and b"\x00" not in bruto
    codigo = _linhas_de_codigo(bruto.decode("utf-8"))
    aberturas = len(re.findall(r"^DO \$\$", codigo, flags=re.MULTILINE))
    fechamentos = len(re.findall(r"^END \$\$;", codigo, flags=re.MULTILINE))
    assert aberturas == fechamentos and aberturas > 0
    blocos = re.findall(r"^DO \$\$(.*?)^END \$\$;", codigo, flags=re.MULTILINE | re.DOTALL)
    assert len(blocos) == aberturas
    for bloco in blocos:
        limpo = _sem_literais(bloco)
        assert bloco.count("'") % 2 == 0, "Aspas desbalanceadas em um bloco DO."
        assert limpo.count("(") == limpo.count(")"), "Parenteses desbalanceados em um bloco DO."
        fechos_if = len(re.findall(r"\bEND IF\b", limpo))
        assert len(re.findall(r"\bIF\b", limpo)) - fechos_if - len(re.findall(r"\bELSIF\b", limpo)) == fechos_if
        assert len(re.findall(r"\bLOOP\b", limpo)) == 2 * len(re.findall(r"\bEND LOOP\b", limpo))


def test_marcadores_das_fases_existem_uma_vez_e_na_ordem(texto):
    posicoes = []
    for marcador in (MARCADOR_FASE_1, MARCADOR_FASE_2, MARCADOR_FASE_3, MARCADOR_ENCERRAMENTO):
        assert texto.count(marcador) == 1, f"Marcador {marcador!r} deveria aparecer exatamente uma vez."
        posicoes.append(texto.index(marcador))
    assert posicoes == sorted(posicoes), "Os marcadores das fases estao fora de ordem."


def test_tem_on_error_stop_antes_de_qualquer_comando(texto):
    assert _linhas_de_codigo(texto).strip().startswith("\\set ON_ERROR_STOP on")


def test_protecoes_iniciais_verificam_identidade_do_servidor_e_superusuario(fases):
    inicio = fases["inicio"]
    assert "current_database() <> 'postgres'" in inicio
    assert "inet_server_addr()" in inicio
    assert "inet_server_port() <> 5432" in inicio
    assert "PostgreSQL 17" in inicio
    assert "current_setting('is_superuser') <> 'on'" in inicio
    assert "datname = 'nsi_dev'" in inicio and "datname = 'nsi_test'" in inicio


def test_mensagem_final_so_aparece_no_encerramento(texto, fases):
    mensagem = "Fase 3 (pos-validacao completa) passou integralmente."
    assert _linhas_de_codigo(texto).count(mensagem) == 1
    assert mensagem in _linhas_de_codigo(fases["encerramento"])


def test_cabecalho_declara_execucao_manual_e_ausencia_de_senha(fases):
    cabecalho = fases["inicio"]
    for aviso in ("NUNCA PRODUCAO", "NAO CONTEM SENHA", "NAO E EXECUTADO AUTOMATICAMENTE", "procedimento MANUAL"):
        assert aviso in cabecalho, f"Cabecalho sem o aviso {aviso!r}."


# ------------------------------------------------------------
# READ ONLY obrigatorio nas Fases 1 e 3
# ------------------------------------------------------------

@pytest.mark.parametrize("bloco", ["inicio", "fase_1", "fase_3", "encerramento"])
def test_nenhum_comando_de_escrita_fora_da_fase_2(fases, bloco):
    codigo = _codigo(fases[bloco])
    for comando in COMANDOS_DE_ESCRITA:
        assert not re.search(rf"\b{comando}\b", codigo, flags=re.IGNORECASE), (
            f"Comando de escrita {comando!r} encontrado em {bloco!r} - so a Fase 2 pode escrever."
        )


@pytest.mark.parametrize("bloco", ["inicio", "fase_1", "fase_3"])
def test_modo_somente_leitura_e_ligado_no_inicio_do_bloco(fases, bloco):
    comandos_sql = [l for l in _comandos(fases[bloco]) if not l.startswith("\\")]
    assert comandos_sql[0] == LIGA_READ_ONLY
    assert "current_setting('transaction_read_only') <> 'on'" in "\n".join(comandos_sql[1:6])


@pytest.mark.parametrize("bloco", ["fase_1", "fase_3", "encerramento"])
def test_modo_somente_leitura_e_religado_e_conferido_depois_de_cada_troca_de_banco(fases, bloco):
    """\\c abre uma sessao nova, que nasce em modo normal: logo depois de
    cada \\c, o modo e religado e o modo EFETIVO da sessao e lido."""
    linhas = _comandos(fases[bloco])
    trocas = [i for i, linha in enumerate(linhas) if linha.startswith("\\c ")]
    assert trocas, f"Esperava ao menos um \\c em {bloco!r}."
    for i in trocas:
        assert linhas[i + 1] == LIGA_READ_ONLY, f"Depois de {linhas[i]!r} o modo somente leitura nao e religado."
        conferencia = "\n".join(linhas[i + 2:i + 8])
        assert "current_setting('transaction_read_only') <> 'on'" in conferencia
        assert "RAISE EXCEPTION" in conferencia


def test_fase_1_e_fase_3_leem_os_dois_bancos(fases):
    for bloco in ("fase_1", "fase_3"):
        assert _trocas_de_banco(fases[bloco])[:2] == ["nsi_dev", "nsi_test"]


def test_escrita_e_liberada_em_um_unico_ponto_no_inicio_da_fase_2(texto, fases):
    assert _linhas_de_codigo(texto).count(LIBERA_ESCRITA) == 1
    comandos_sql = [l for l in _comandos(fases["fase_2"]) if not l.startswith("\\")]
    assert comandos_sql[0] == LIBERA_ESCRITA


def test_nenhum_outro_comando_altera_o_modo_da_sessao(texto):
    codigo = _codigo(texto)
    assert len(re.findall(r"default_transaction_read_only\s*=", codigo)) == (
        codigo.count(LIGA_READ_ONLY) + codigo.count(LIBERA_ESCRITA)
    )
    for proibido in (r"\bRESET\b", r"\bREAD\s+WRITE\b", r"SESSION\s+CHARACTERISTICS", r"\bset_config\b",
                     r"SET\s+LOCAL", r"SET\s+TRANSACTION", r"\bBEGIN\s*;", r"START\s+TRANSACTION"):
        assert not re.search(proibido, codigo, flags=re.IGNORECASE), f"Comando {proibido!r} nao e permitido no script."


# ------------------------------------------------------------
# Cada fase e autossuficiente
# ------------------------------------------------------------

def test_variaveis_de_cliente_sao_prefixadas_pela_fase_e_nunca_cruzam_fases(texto, fases):
    definidas = re.findall(r"\bAS\s+(\w+)\s*(?:FROM[^\n]*)?\n\\gset", texto)
    assert definidas, "Esperava ao menos uma variavel de cliente (\\gset)."
    for nome in definidas:
        assert nome.startswith(("f1_", "f3_")), f"Variavel de cliente {nome!r} sem prefixo de fase."
    for prefixo, propria in (("f1_", "fase_1"), ("f3_", "fase_3")):
        for bloco, conteudo in fases.items():
            if bloco != propria:
                assert prefixo not in _linhas_de_codigo(conteudo), (
                    f"Variavel {prefixo}* (da {propria}) referenciada em {bloco!r}."
                )


def test_fase_2_nao_usa_nenhuma_variavel_de_cliente(fases):
    codigo = _linhas_de_codigo(fases["fase_2"])
    assert "\\gset" not in codigo
    assert "\\if" not in codigo
    assert not re.search(r":(?:'\w+'|\"\w+\"|[A-Za-z_]\w*)", codigo.replace("::", "")), (
        "A Fase 2 nao pode interpolar variavel de cliente - cada acao le o estado por conta propria."
    )


# ------------------------------------------------------------
# Fase 2 - exatamente tres acoes, e nenhuma outra
# ------------------------------------------------------------

def test_fase_2_executa_exatamente_as_tres_escritas_aprovadas_na_ordem(fases):
    assert len(_acoes(fases["fase_2"])) == 3
    assert _escritas(fases["fase_2"]) == ESCRITAS_APROVADAS_PROVISIONAMENTO


def test_fase_2_nao_tem_nenhuma_escrita_fora_dos_tres_execute(fases):
    codigo = _codigo(fases["fase_2"])
    assert len(re.findall(r"\bEXECUTE\b", codigo)) == 3
    for comando in COMANDOS_DE_ESCRITA:
        if comando != "EXECUTE":
            assert not re.search(rf"\b{comando}\b", codigo, flags=re.IGNORECASE), (
                f"Comando de escrita direto {comando!r} encontrado na Fase 2."
            )


def test_cada_acao_da_fase_2_le_o_estado_antes_de_escrever_e_nunca_corrige(fases):
    for acao in _acoes(fases["fase_2"]):
        assert acao.index("FROM pg_roles") < acao.index("EXECUTE '")
        assert "Abortando sem corrigir." in acao, "Estado diferente do esperado deve abortar, nunca ser corrigido."


def test_criacao_da_role_so_ocorre_quando_ela_esta_ausente(fases):
    acao = _acoes(fases["fase_2"])[0]
    assert acao.index("IF NOT FOUND THEN") < acao.index("EXECUTE 'CREATE ROLE nsi_importacao") < acao.index("RETURN;")


def test_fase_2_so_escreve_em_postgres_e_em_nsi_test_nunca_em_nsi_dev(fases):
    """CONNECT e USAGE somente em nsi_test (B5.2, item 4; ADR-010, Secao
    16.2): a Fase 2 nunca troca para nsi_dev."""
    assert _trocas_de_banco(fases["fase_2"]) == ["nsi_test", "postgres"]
    for escrita in _escritas(fases["fase_2"]):
        assert "nsi_dev" not in escrita


def test_connect_e_confirmado_logo_depois_da_concessao(fases):
    acao = _acoes(fases["fase_2"])[1]
    depois = acao.split("EXECUTE 'GRANT CONNECT ON DATABASE nsi_test TO nsi_importacao'", 1)[1]
    assert "total_depois <> 1" in depois and "RAISE EXCEPTION" in depois


# ------------------------------------------------------------
# O que e proprio da role nsi_importacao
# ------------------------------------------------------------

def test_role_e_criada_com_login_e_todos_os_atributos_de_seguranca_explicitos(fases):
    criacao = _escritas(fases["fase_2"])[0]
    for atributo in ("LOGIN", "NOSUPERUSER", "NOCREATEDB", "NOCREATEROLE", "NOREPLICATION", "NOBYPASSRLS"):
        assert re.search(rf"\b{atributo}\b", criacao)
    assert "NOLOGIN" not in criacao


def test_forma_exata_da_role_e_conferida_nas_tres_fases(fases):
    """LOGIN verdadeiro e os demais atributos falsos - nas tres fases."""
    for bloco in ("fase_1", "fase_2", "fase_3"):
        assert "canlogin_atual IS DISTINCT FROM true OR super_atual IS DISTINCT FROM false" in fases[bloco]


def test_nenhuma_membership_e_concedida_e_a_ausencia_e_conferida_nas_tres_fases(texto, fases):
    """ADR-010, Secao 16.2: nsi_importacao nao pertence a nenhuma role e
    nao tem membros - nenhuma segunda excecao a regra da B3.1."""
    for escrita in _escritas(texto):
        assert not re.match(r"GRANT\s+nsi_\w+\s+TO\b", escrita), f"Concessao de membership encontrada: {escrita!r}"
    assert "WITH INHERIT" not in _linhas_de_codigo(texto)
    for bloco in ("fase_1", "fase_2", "fase_3"):
        assert "total_pertence <> 0 OR total_membros <> 0" in fases[bloco]


def test_nao_contem_senha_nem_comando_de_senha(texto):
    codigo = _linhas_de_codigo(texto)
    assert not re.search(r"\bPASSWORD\b", codigo, flags=re.IGNORECASE)
    assert "\\password" not in codigo
    assert "rolpassword" not in codigo, "O script nunca le nem verifica a senha - ela e definida depois, pelo operador."


def test_revisoes_aceitas_sao_exatamente_0005_e_0006(texto, fases):
    for bloco in ("fase_1", "fase_3"):
        assert fases[bloco].count("revisao NOT IN ('0005', '0006')") == 2
    assert len(re.findall(r"revisao NOT IN \(", texto)) == 4
    assert "\\if :f1_revisoes_divergem" in fases["fase_1"]
    assert "\\if :f3_revisoes_divergem" in fases["fase_3"]


def test_execute_so_e_aceito_nas_quatro_funcoes_e_somente_em_0006(texto, fases):
    for nome in QUATRO_FUNCOES_DE_IMPORTACAO:
        assert nome in fases["fase_1"] and nome in fases["fase_3"]
    for bloco, minimo in (("fase_1", 2), ("fase_3", 4)):
        assert fases[bloco].count("revisao = '0006'") >= minimo
    assert "nenhuma em 0005" in fases["fase_1"]
    assert fases["fase_3"].count("IF total_linhas <> 4 THEN") == 2
    for escrita in _escritas(texto):
        assert "EXECUTE ON" not in escrita and "FUNCTION" not in escrita, "O script nunca concede EXECUTE."


def test_dependencias_no_cluster_aceitam_somente_o_previsto(fases):
    for bloco in ("fase_1", "fase_3"):
        conteudo = fases[bloco]
        assert "FROM pg_shdepend" in conteudo
        assert "s.classid = 'pg_database'::regclass AND s.dbid = 0" in conteudo
        assert "s.classid = 'pg_namespace'::regclass" in conteudo
        assert "s.classid = 'pg_proc'::regclass" in conteudo


def test_concessao_de_banco_e_restrita_a_connect_em_nsi_test(fases):
    condicao = "d.datname = 'nsi_test' AND a.privilege_type = 'CONNECT' AND NOT a.is_grantable"
    for bloco in ("fase_1", "fase_2", "fase_3"):
        assert condicao in fases[bloco]


def test_fase_3_exige_ausencia_de_connect_e_de_usage_em_nsi_dev(fases):
    fase_3 = fases["fase_3"]
    assert "IF has_database_privilege('nsi_importacao', 'nsi_dev', 'CONNECT') THEN" in fase_3
    assert "IF NOT has_database_privilege('nsi_importacao', 'nsi_test', 'CONNECT') THEN" in fase_3
    assert "IF has_schema_privilege('nsi_importacao', 'nsi_operacional', 'USAGE') THEN" in fase_3
    assert "IF NOT has_schema_privilege('nsi_importacao', 'nsi_operacional', 'USAGE') THEN" in fase_3


def test_fase_1_nao_aceita_concessao_de_schema_em_nsi_dev(fases):
    fase_1 = fases["fase_1"]
    trecho_dev = fase_1[fase_1.index("\\c nsi_dev"):fase_1.index("\\c nsi_test")]
    assert "esperado zero (nsi_importacao so recebe USAGE em nsi_test)" in trecho_dev


def test_pos_validacao_confere_privilegio_efetivo_nos_dois_bancos(fases):
    fase_3 = fases["fase_3"]
    for funcao in ("has_schema_privilege", "has_table_privilege", "has_any_column_privilege", "has_function_privilege"):
        assert fase_3.count(funcao + "('nsi_importacao'") >= 2, f"{funcao} deveria ser conferido nos dois bancos."


def test_fases_1_e_3_confirmam_b3_1_e_b4_3_integras(fases):
    for bloco in ("fase_1", "fase_3"):
        conteudo = fases[bloco]
        assert "ARRAY['nsi_eventos_owner', 'nsi_aplicacao', 'nsi_expiracao', 'nsi_operador_restrito']" in conteudo
        assert "ARRAY['nsi_dev_migrator', 'nsi_test_migrator']" in conteudo
        assert "WHERE g.rolname <> 'nsi_congelamento'" in conteudo
        assert "rolname = 'nsi_congelamento'" in conteudo
    assert "a.grantee = 0 AND a.privilege_type = 'CONNECT'" in fases["fase_3"]


def test_fase_3_reconfere_nsi_congelamento_com_o_mesmo_rigor_da_fase_1(fases):
    """A pos-validacao nao e mais fraca que a preflight: todos os atributos
    de nsi_congelamento e o seu membro unico sao reconferidos."""
    for bloco in ("fase_1", "fase_3"):
        conteudo = fases[bloco]
        assert "FROM pg_roles WHERE rolname = 'nsi_congelamento'" in conteudo
        assert "WHERE g.rolname = 'nsi_congelamento'" in conteudo, f"{bloco!r} nao confere os membros de nsi_congelamento."
        assert "WHERE r.rolname <> 'nsi_aplicacao'" in conteudo
    trecho = fases["fase_3"][fases["fase_3"].index("FROM pg_roles WHERE rolname = 'nsi_congelamento'"):]
    condicao = trecho[:trecho.index("RAISE EXCEPTION")]
    for atributo in ("canlogin_atual", "super_atual", "createdb_atual", "createrole_atual",
                     "replication_atual", "bypassrls_atual", "inherit_atual"):
        assert atributo in condicao, f"A Fase 3 nao reconfere {atributo} de nsi_congelamento."


def test_escritas_so_tocam_a_role_nsi_importacao(fases):
    for escrita in _escritas(fases["fase_2"]):
        assert "nsi_importacao" in escrita
        for alheio in ("nsi_eventos_owner", "nsi_aplicacao", "nsi_expiracao", "nsi_operador_restrito",
                       "nsi_congelamento", "migrator", "PUBLIC", "TABLE"):
            assert alheio not in escrita, f"Escrita {escrita!r} toca objeto fora do provisionamento ({alheio})."


# ============================================================
# ============================================================
# desprovisionar_b5_role_importacao.sql
# ============================================================
# ============================================================

DESP_BLOCOS_SOMENTE_LEITURA = ["inicio", "fase_1", "gate", "fase_3", "encerramento"]


def test_desprov_marcadores_existem_uma_vez_e_na_ordem(texto_desp):
    posicoes = []
    for marcador in (MARCADOR_FASE_1, DESP_MARCADOR_GATE, DESP_MARCADOR_FASE_2, MARCADOR_FASE_3, MARCADOR_ENCERRAMENTO):
        assert texto_desp.count(marcador) == 1, f"Marcador {marcador!r} deveria aparecer exatamente uma vez."
        posicoes.append(texto_desp.index(marcador))
    assert posicoes == sorted(posicoes)


def test_desprov_tem_on_error_stop_antes_de_qualquer_comando(texto_desp):
    assert _linhas_de_codigo(texto_desp).strip().startswith("\\set ON_ERROR_STOP on")


def test_desprov_cabecalho_declara_natureza_destrutiva_e_manual(blocos_desp):
    cabecalho = blocos_desp["inicio"]
    for aviso in ("SCRIPT DESTRUTIVO", "NUNCA EXECUTAR CONTRA PRODUCAO", "NUNCA EXECUTADO AUTOMATICAMENTE",
                  "NENHUM TESTE AUTOMATIZADO CHAMA ESTE ARQUIVO", "NAO CONTEM SENHA"):
        assert aviso in cabecalho, f"Cabecalho sem o aviso {aviso!r}."


def test_desprov_cabecalho_delimita_reversao_da_0006_ao_downgrade_do_alembic(blocos_desp):
    cabecalho = re.sub(r"\s*\n--\s*", " ", blocos_desp["inicio"])
    assert "remove EXCLUSIVAMENTE os efeitos administrativos" in cabecalho
    assert "revertida EXCLUSIVAMENTE pelo downgrade do Alembic" in cabecalho


def test_desprov_protecoes_iniciais_verificam_identidade_do_servidor_e_superusuario(blocos_desp):
    inicio = blocos_desp["inicio"]
    assert "current_database() <> 'postgres'" in inicio
    assert "inet_server_addr()" in inicio
    assert "inet_server_port() <> 5432" in inicio
    assert "PostgreSQL 17" in inicio
    assert "current_setting('is_superuser') <> 'on'" in inicio
    assert "datname = 'nsi_dev'" in inicio and "datname = 'nsi_test'" in inicio


def test_desprov_mensagem_final_so_aparece_no_encerramento(texto_desp, blocos_desp):
    mensagem = "Fase 3 (pos-validacao completa) passou integralmente."
    assert _linhas_de_codigo(texto_desp).count(mensagem) == 1
    assert mensagem in _linhas_de_codigo(blocos_desp["encerramento"])


@pytest.mark.parametrize("bloco", DESP_BLOCOS_SOMENTE_LEITURA)
def test_desprov_nenhum_comando_de_escrita_fora_da_fase_2(blocos_desp, bloco):
    codigo = _codigo(blocos_desp[bloco])
    for comando in COMANDOS_DE_ESCRITA:
        assert not re.search(rf"\b{comando}\b", codigo, flags=re.IGNORECASE), (
            f"Comando de escrita {comando!r} encontrado em {bloco!r} - so a Fase 2 realiza operacoes de escrita."
        )


@pytest.mark.parametrize("bloco", ["inicio", "fase_1", "gate", "fase_3"])
def test_desprov_modo_somente_leitura_e_ligado_no_inicio_do_bloco(blocos_desp, bloco):
    comandos_sql = [l for l in _comandos(blocos_desp[bloco]) if not l.startswith("\\")]
    assert comandos_sql[0] == LIGA_READ_ONLY
    assert "current_setting('transaction_read_only') <> 'on'" in "\n".join(comandos_sql[1:6])


@pytest.mark.parametrize("bloco", ["fase_1", "fase_3", "encerramento"])
def test_desprov_modo_somente_leitura_e_religado_e_conferido_depois_de_cada_troca_de_banco(blocos_desp, bloco):
    linhas = _comandos(blocos_desp[bloco])
    trocas = [i for i, linha in enumerate(linhas) if linha.startswith("\\c ")]
    assert trocas, f"Esperava ao menos um \\c em {bloco!r}."
    for i in trocas:
        assert linhas[i + 1] == LIGA_READ_ONLY
        conferencia = "\n".join(linhas[i + 2:i + 8])
        assert "current_setting('transaction_read_only') <> 'on'" in conferencia
        assert "RAISE EXCEPTION" in conferencia


def test_desprov_modo_somente_leitura_so_e_desativado_na_fase_2(texto_desp, blocos_desp):
    assert _linhas_de_codigo(texto_desp).count(LIBERA_ESCRITA) == 1
    comandos_sql = [l for l in _comandos(blocos_desp["fase_2"]) if not l.startswith("\\")]
    assert comandos_sql[0] == LIBERA_ESCRITA


def test_desprov_nenhum_outro_comando_altera_o_modo_da_sessao(texto_desp):
    codigo = _codigo(texto_desp)
    assert len(re.findall(r"default_transaction_read_only\s*=", codigo)) == (
        codigo.count(LIGA_READ_ONLY) + codigo.count(LIBERA_ESCRITA)
    )
    for proibido in (r"\bRESET\b", r"\bREAD\s+WRITE\b", r"SESSION\s+CHARACTERISTICS", r"\bset_config\b",
                     r"SET\s+LOCAL", r"SET\s+TRANSACTION", r"\bBEGIN\s*;", r"START\s+TRANSACTION"):
        assert not re.search(proibido, codigo, flags=re.IGNORECASE)


# ------------------------------------------------------------
# Gate de confirmacao
# ------------------------------------------------------------

def test_desprov_prompt_existe_uma_unica_vez_e_somente_no_gate(texto_desp, blocos_desp):
    assert _linhas_de_codigo(texto_desp).count("\\prompt") == 1
    assert "\\prompt" in _linhas_de_codigo(blocos_desp["gate"])


def test_desprov_frase_de_confirmacao_e_exata_e_propria_da_b5(blocos_desp, texto_desp):
    gate = _linhas_de_codigo(blocos_desp["gate"])
    prompt = next(l for l in gate.splitlines() if l.strip().startswith("\\prompt"))
    assert FRASE_CONFIRMACAO_B5 in prompt
    assert f":'conf_frase' = '{FRASE_CONFIRMACAO_B5}'" in gate, "A comparacao deve ser exata, com a frase completa."
    for frase_alheia in FRASES_DE_OUTRAS_SUBETAPAS:
        assert frase_alheia not in texto_desp


def test_desprov_confirmacao_incorreta_encerra_antes_da_fase_2(blocos_desp):
    gate = _linhas_de_codigo(blocos_desp["gate"])
    assert gate.index("\\if :conf_pode_prosseguir") < gate.index("\\else") < gate.index("\\quit") < gate.index("\\endif")
    assert gate.count("\\quit") == 1


# ------------------------------------------------------------
# Cada fase e autossuficiente
# ------------------------------------------------------------

def test_desprov_variaveis_de_cliente_sao_prefixadas_pelo_bloco_e_nunca_cruzam_blocos(texto_desp, blocos_desp):
    definidas = re.findall(r"\bAS\s+(\w+)\s*(?:FROM[^\n]*)?\n\\gset", texto_desp)
    definidas += re.findall(r"^\\prompt\s+'[^']*'\s+(\w+)", texto_desp, flags=re.MULTILINE)
    assert definidas
    for nome in definidas:
        assert nome.startswith(("f1_", "conf_", "f3_")), f"Variavel de cliente {nome!r} sem prefixo de bloco."
    for prefixo, propria in (("f1_", "fase_1"), ("conf_", "gate"), ("f3_", "fase_3")):
        for bloco, conteudo in blocos_desp.items():
            if bloco != propria:
                assert not re.search(rf"\b{prefixo}\w+", _linhas_de_codigo(conteudo)), (
                    f"Variavel {prefixo}* (de {propria}) referenciada em {bloco!r}."
                )


def test_desprov_fase_2_nao_usa_nenhuma_variavel_de_cliente(blocos_desp):
    codigo = _linhas_de_codigo(blocos_desp["fase_2"])
    assert "\\gset" not in codigo
    assert "\\if" not in codigo
    assert not re.search(r":(?:'\w+'|\"\w+\"|[A-Za-z_]\w*)", codigo.replace("::", ""))


# ------------------------------------------------------------
# Fase 2 - exatamente tres acoes, na ordem inversa do provisionamento
# ------------------------------------------------------------

def test_desprov_fase_2_executa_exatamente_as_tres_escritas_aprovadas_na_ordem(blocos_desp):
    assert len(_acoes(blocos_desp["fase_2"])) == 3
    assert _escritas(blocos_desp["fase_2"]) == ESCRITAS_APROVADAS_DESPROVISIONAMENTO


def test_desprov_fase_2_nao_tem_nenhuma_escrita_fora_dos_tres_execute(blocos_desp):
    codigo = _codigo(blocos_desp["fase_2"])
    assert len(re.findall(r"\bEXECUTE\b", codigo)) == 3
    for comando in COMANDOS_DE_ESCRITA:
        if comando != "EXECUTE":
            assert not re.search(rf"\b{comando}\b", codigo, flags=re.IGNORECASE)


def test_desprov_fase_2_segue_a_ordem_inversa_do_provisionamento(blocos_desp):
    """nsi_test (USAGE) -> postgres (CONNECT, depois a role). Nunca nsi_dev."""
    assert _trocas_de_banco(blocos_desp["fase_2"]) == ["nsi_test", "postgres"]
    codigo = _linhas_de_codigo(blocos_desp["fase_2"])
    escritas = [m.start() for m in re.finditer(r"EXECUTE '", codigo)]
    assert codigo.index("\\c nsi_test") < escritas[0] < codigo.index("\\c postgres") < escritas[1] < escritas[2]


def test_desprov_cada_acao_le_o_estado_antes_e_confirma_o_efeito_depois(blocos_desp):
    for acao in _acoes(blocos_desp["fase_2"]):
        antes, depois = acao.split("EXECUTE '", 1)
        assert "FROM pg_roles" in antes, "A acao deve ler o estado do servidor antes de escrever."
        assert "RETURN;" in antes, "Objeto ja ausente deve resultar em 'nada a fazer' antes da escrita."
        assert "RAISE EXCEPTION" in antes, "Forma diferente da exata deve abortar antes da escrita."
        assert re.search(r"\b(SELECT|PERFORM)\b", depois), "A acao deve reler o catalogo depois da escrita."
        assert "RAISE EXCEPTION" in depois, "Escrita sem efeito deve abortar a acao."


def test_desprov_acoes_abortam_sem_corrigir(blocos_desp):
    acoes = _acoes(blocos_desp["fase_2"])
    for acao in acoes[:2]:
        assert "Abortando sem corrigir." in acao
    assert "Abortando sem remover." in acoes[2]


def test_desprov_usage_so_e_revogado_com_as_funcoes_de_importacao_ausentes(blocos_desp):
    antes = _acoes(blocos_desp["fase_2"])[0].split("EXECUTE '", 1)[0]
    for nome in QUATRO_FUNCOES_DE_IMPORTACAO:
        assert nome in antes


def test_desprov_remocao_da_role_exige_zero_membership_dependencias_e_sessoes(blocos_desp):
    acao = _acoes(blocos_desp["fase_2"])[2]
    antes = acao.split("EXECUTE 'DROP ROLE nsi_importacao'", 1)[0]
    assert "FROM pg_shdepend" in antes and "FROM pg_stat_activity WHERE usename = 'nsi_importacao'" in antes
    for condicao in ("total_dependencias <> 0", "total_membros <> 0", "total_pertence <> 0", "total_sessoes <> 0"):
        assert condicao in antes, f"A remocao da role deveria ser bloqueada por {condicao!r}."


# ------------------------------------------------------------
# Comandos proibidos e seguranca
# ------------------------------------------------------------

@pytest.mark.parametrize("proibido", [
    r"\bDROP\s+OWNED\b", r"\bREASSIGN\b", r"\bCASCADE\b", r"\bIF\s+EXISTS\b",
    r"\bGRANT\b", r"\bCREATE\b", r"\bALTER\b", r"\bPASSWORD\b",
    r"\bALEMBIC\b", r"\bDOWNGRADE\b", r"\bFUNCTION\b", r"\bEXECUTE\s+ON\b",
])
def test_desprov_comando_proibido_nao_aparece_em_codigo_nem_nas_escritas(texto_desp, proibido):
    assert not re.search(proibido, _codigo(texto_desp), flags=re.IGNORECASE)
    assert not re.search(proibido, " ".join(_escritas(texto_desp)), flags=re.IGNORECASE)


def test_desprov_escritas_so_tocam_os_objetos_do_provisionamento(blocos_desp):
    for escrita in _escritas(blocos_desp["fase_2"]):
        assert "nsi_importacao" in escrita and "nsi_dev" not in escrita
        for alheio in ("nsi_eventos_owner", "nsi_aplicacao", "nsi_expiracao", "nsi_operador_restrito",
                       "nsi_congelamento", "migrator", "PUBLIC", "TABLE"):
            assert alheio not in escrita, f"Escrita {escrita!r} toca objeto fora do provisionamento ({alheio})."


def test_desprov_nao_le_nem_altera_senha(texto_desp):
    codigo = _linhas_de_codigo(texto_desp)
    assert "rolpassword" not in codigo and "\\password" not in codigo


# ------------------------------------------------------------
# Revisao aceita e ausencia das funcoes de importacao
# ------------------------------------------------------------

def test_desprov_revisao_aceita_e_somente_0005(texto_desp, blocos_desp):
    for bloco in ("fase_1", "fase_3"):
        assert blocos_desp[bloco].count("revisao NOT IN ('0005')") == 2
    assert len(re.findall(r"revisao NOT IN \(", texto_desp)) == 4
    assert not re.search(r"NOT IN \([^)]*'0006'", texto_desp)
    assert "\\if :f1_revisoes_divergem" in blocos_desp["fase_1"]
    assert "\\if :f3_revisoes_divergem" in blocos_desp["fase_3"]


def test_desprov_funcoes_de_importacao_devem_estar_ausentes_na_fase_1_e_na_fase_3(blocos_desp):
    for bloco in ("fase_1", "fase_3"):
        for nome in QUATRO_FUNCOES_DE_IMPORTACAO:
            assert blocos_desp[bloco].count(f"'{nome}'") == 2, (
                f"{bloco!r} deveria exigir {nome} ausente nos dois bancos."
            )


def test_desprov_preflight_nao_aceita_concessao_em_funcao(blocos_desp):
    """Mais estrito que o provisionamento: no pg_shdepend, so CONNECT em
    nsi_test e ACL em schema de nsi_test; nenhuma ACL de funcao."""
    fase_1 = blocos_desp["fase_1"]
    assert "s.classid = 'pg_database'::regclass AND s.dbid = 0" in fase_1
    assert "s.classid = 'pg_namespace'::regclass" in fase_1
    assert "'pg_proc'::regclass" not in fase_1
    assert fase_1.count("esperado zero com a 0006 ausente") == 2


# ------------------------------------------------------------
# Pos-validacao
# ------------------------------------------------------------

def test_desprov_fase_3_confirma_role_ausente_em_pg_roles_e_pg_authid(blocos_desp):
    fase_3 = blocos_desp["fase_3"]
    assert "PERFORM 1 FROM pg_roles WHERE rolname = 'nsi_importacao'" in fase_3
    assert "PERFORM 1 FROM pg_authid WHERE rolname = 'nsi_importacao'" in fase_3


def test_desprov_fase_3_preserva_b3_1_e_a_excecao_da_adr_009(blocos_desp):
    """Este script nunca toca a B4.3: a excecao de membership da ADR-009
    continua reconhecida na Fase 3 (diferente do desprovisionamento da B4)."""
    fase_3 = blocos_desp["fase_3"]
    assert "ARRAY['nsi_eventos_owner', 'nsi_aplicacao', 'nsi_expiracao', 'nsi_operador_restrito']" in fase_3
    assert "WHERE g.rolname <> 'nsi_congelamento'" in fase_3
    assert "ARRAY['nsi_dev_migrator', 'nsi_test_migrator']" in fase_3
    assert "a.grantee = 0 AND a.privilege_type = 'CONNECT'" in fase_3


def test_desprov_fase_3_procura_dependencias_e_acls_orfas(blocos_desp):
    fase_3 = blocos_desp["fase_3"]
    assert "NOT EXISTS (SELECT 1 FROM pg_authid a WHERE a.oid = s.refobjid)" in fase_3
    assert fase_3.count("NOT EXISTS (SELECT 1 FROM pg_roles g WHERE g.oid = a.grantee)") == 9, (
        "ACL orfa deveria ser procurada em banco (uma vez) e em schema, tabela, coluna e funcao, nos dois bancos."
    )


# ============================================================
# Os scripts nunca sao executados por codigo
# ============================================================

def _arquivos_python_do_projeto():
    for pasta in PASTAS_DE_CODIGO:
        for caminho in sorted((BASE_DIR / pasta).rglob("*.py")):
            if "__pycache__" not in caminho.parts:
                yield caminho
    for arquivo in ARQUIVOS_DE_CODIGO:
        yield BASE_DIR / arquivo


def _cita_o_script_em_codigo(codigo_fonte: str, nome_do_script: str) -> bool:
    """True se o nome do script aparece em um literal de codigo - fora de
    docstring e de comentario."""
    arvore = ast.parse(codigo_fonte)
    docstrings = set()
    for no in ast.walk(arvore):
        if isinstance(no, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            corpo = no.body
            if corpo and isinstance(corpo[0], ast.Expr) and isinstance(corpo[0].value, ast.Constant) \
                    and isinstance(corpo[0].value.value, str):
                docstrings.add(id(corpo[0].value))
    return any(
        nome_do_script in no.value for no in ast.walk(arvore)
        if isinstance(no, ast.Constant) and isinstance(no.value, str) and id(no) not in docstrings
    )


@pytest.mark.parametrize("caminho_script", [CAMINHO_PROVISIONAR, CAMINHO_DESPROVISIONAR], ids=["provisionar", "desprovisionar"])
def test_nenhum_arquivo_carrega_o_script_em_codigo(caminho_script):
    """Nenhum codigo de aplicacao, migration, script ou teste usa o arquivo
    em codigo executavel. Unica excecao: este proprio arquivo, que LE o
    texto do script para inspeciona-lo - e nunca o executa."""
    for caminho in _arquivos_python_do_projeto():
        if caminho.resolve() == Path(__file__).resolve():
            continue
        assert not _cita_o_script_em_codigo(caminho.read_text(encoding="utf-8-sig"), caminho_script.name), (
            f"{caminho.relative_to(BASE_DIR)} usa {caminho_script.name} em codigo executavel - "
            "o script nunca pode ser executado por codigo; cita-lo so e permitido em docstring ou comentario."
        )


@pytest.mark.parametrize("codigo_fonte,esperado", [
    ('caminho = "scripts/postgres_local/provisionar_b5_role_importacao.sql"\n', True),
    ('sql = open(BASE / "provisionar_b5_role_importacao.sql").read()\ncur.execute(sql)\n', True),
    ('"""Pre-requisito: provisionar_b5_role_importacao.sql ja executado manualmente."""\n', False),
    ('def f():\n    """Ver provisionar_b5_role_importacao.sql."""\n    return 1\n', False),
    ('x = 1  # provisionar_b5_role_importacao.sql\n', False),
])
def test_detector_de_uso_do_script_em_codigo(codigo_fonte, esperado):
    """Prova o detector: um detector que nunca detecta aprovaria tudo."""
    assert _cita_o_script_em_codigo(codigo_fonte, "provisionar_b5_role_importacao.sql") is esperado


# ============================================================
# Nenhum codigo Python em scripts/ lanca o cliente psql
# ============================================================
#
# O detector de tests/unit/test_scripts_b4_role_congelamento.py varre
# adapters, core, integration, services, migrations, tests, app.py e
# config.py - nao a pasta scripts/, que ate a B5.3 so continha arquivos
# .sql. A partir da B5.5 ela passa a conter codigo Python (o executor da
# importacao): este teste estende a mesma garantia a essa pasta.

LANCADORES_DE_PROCESSO = {
    "subprocess": {"run", "Popen", "call", "check_call", "check_output", "getoutput", "getstatusoutput"},
    "os": {"system", "popen", "startfile", "execl", "execle", "execlp", "execlpe", "execv", "execve",
           "execvp", "execvpe", "spawnl", "spawnle", "spawnlp", "spawnlpe", "spawnv", "spawnve",
           "spawnvp", "spawnvpe"},
    "asyncio": {"create_subprocess_exec", "create_subprocess_shell"},
}
CLIENTE_POSTGRES = re.compile(r"\b(psql|pgbench)(\.exe)?\b", flags=re.IGNORECASE)


def _lanca_cliente_postgres(codigo_fonte: str) -> bool:
    """True se o codigo lanca um processo externo cujo comando cita um
    cliente de linha de comando do PostgreSQL."""
    arvore = ast.parse(codigo_fonte)
    modulos, funcoes = {}, set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            for item in no.names:
                if item.name in LANCADORES_DE_PROCESSO:
                    modulos[item.asname or item.name] = item.name
        elif isinstance(no, ast.ImportFrom) and no.module in LANCADORES_DE_PROCESSO:
            for item in no.names:
                if item.name in LANCADORES_DE_PROCESSO[no.module]:
                    funcoes.add(item.asname or item.name)

    for no in ast.walk(arvore):
        if not isinstance(no, ast.Call):
            continue
        funcao = no.func
        lancador = (
            isinstance(funcao, ast.Attribute) and isinstance(funcao.value, ast.Name)
            and funcao.attr in LANCADORES_DE_PROCESSO.get(modulos.get(funcao.value.id, funcao.value.id), ())
        ) or (isinstance(funcao, ast.Name) and funcao.id in funcoes)
        if not lancador:
            continue
        for filho in ast.walk(no):
            if isinstance(filho, ast.Constant) and isinstance(filho.value, str) and CLIENTE_POSTGRES.search(filho.value):
                return True
    return False


def test_nenhum_codigo_python_em_scripts_lanca_o_cliente_psql():
    for caminho in sorted((BASE_DIR / "scripts").rglob("*.py")):
        if "__pycache__" in caminho.parts:
            continue
        assert not _lanca_cliente_postgres(caminho.read_text(encoding="utf-8-sig")), (
            f"{caminho.relative_to(BASE_DIR)} lanca um cliente de linha de comando do PostgreSQL - "
            "scripts administrativos nunca sao executados por codigo."
        )


@pytest.mark.parametrize("codigo_fonte,esperado", [
    ('import subprocess\nsubprocess.run(["psql", "-f", "x.sql"])\n', True),
    ('import os\nos.system("psql -d postgres -f x.sql")\n', True),
    ('import subprocess as sp\nsp.Popen("psql.exe -U postgres -f x.sql", shell=True)\n', True),
    ('from subprocess import check_call as executar\nexecutar(["PSQL", "-f", "x.sql"])\n', True),
    ('import subprocess\nsubprocess.run(["alembic", "upgrade", "0006"])\n', False),
    ('"""Execute manualmente: psql -U postgres -f x.sql"""\nx = 1  # psql -f x.sql\n', False),
    ('mensagem = "rode o psql manualmente"\n', False),
])
def test_detector_de_lancamento_do_psql(codigo_fonte, esperado):
    """Prova o detector: um detector que nunca detecta aprovaria tudo."""
    assert _lanca_cliente_postgres(codigo_fonte) is esperado
