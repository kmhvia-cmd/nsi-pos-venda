# -*- coding: utf-8 -*-
"""
NSI - tests/unit/test_scripts_b4_role_congelamento.py

Testes ESTATICOS (Sprint B, B4.3 Etapa 1 - ADR-009, Secoes 11 e 21) do
conteudo, ordem, fases e protecoes do script administrativo:

    scripts/postgres_local/provisionar_b4_role_congelamento.sql

Nenhum destes testes executa SQL, conecta a um banco, ou depende de
PostgreSQL - apenas le o texto do arquivo e confirma, por inspecao de
string/posicao, que o desenho aprovado esta presente. Mesmo principio de
tests/unit/test_scripts_b3_roles.py: nenhum teste automatizado pode
executar o provisionamento administrativo real contra o cluster local.

O que estes testes sustentam, do desenho aprovado:

  - READ ONLY obrigatorio nas Fases 1 e 3 (modo religado e conferido
    depois de cada \\c; escrita liberada em um unico ponto; nenhum comando
    de escrita fora da Fase 2);
  - cada fase e autossuficiente (nenhuma variavel de uma fase e
    referenciada em outra; a Fase 2 nao usa variavel de cliente alguma);
  - a Fase 2 executa exatamente quatro acoes de escrita, e nenhuma outra.
"""
import ast
import re
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CAMINHO_PROVISIONAR = BASE_DIR / "scripts" / "postgres_local" / "provisionar_b4_role_congelamento.sql"

MARCADOR_FASE_1 = "-- FASE 1 - PREFLIGHT"
MARCADOR_FASE_2 = "-- FASE 2 - CONVERGENCIA"
MARCADOR_FASE_3 = "-- FASE 3 - POS-VALIDACAO COMPLETA"
MARCADOR_ENCERRAMENTO = "-- ENCERRAMENTO"

LIGA_READ_ONLY = "SET default_transaction_read_only = on;"
LIBERA_ESCRITA = "SET default_transaction_read_only = off;"

# Comandos que escrevem (ou que poderiam executar SQL dinamico). Procurados
# somente em CODIGO - comentarios e literais de texto ja removidos.
COMANDOS_DE_ESCRITA = [
    "CREATE", "ALTER", "DROP", "GRANT", "REVOKE", "INSERT", "UPDATE", "DELETE",
    "TRUNCATE", "EXECUTE", "REASSIGN", "COMMENT", "COPY", "MERGE",
]


def _linhas_de_codigo(texto: str) -> str:
    """Remove as linhas que sao so comentario SQL ('--')."""
    return "\n".join(linha for linha in texto.splitlines() if not linha.strip().startswith("--"))


def _sem_literais(texto: str) -> str:
    """Remove o conteudo de literais de texto ('...'), para que palavras
    que aparecem apenas em mensagens ou em nomes de privilegio comparados
    (ex.: 'EXECUTE', 'SELECT, INSERT, UPDATE') nao sejam confundidas com
    comandos."""
    return re.sub(r"'(?:[^']|'')*'", "''", texto)


def _codigo(texto: str) -> str:
    return _sem_literais(_linhas_de_codigo(texto))


@pytest.fixture(scope="module")
def texto():
    return CAMINHO_PROVISIONAR.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def fases(texto):
    """Divide o script nos blocos do desenho aprovado, pelos marcadores."""
    i1, i2 = texto.index(MARCADOR_FASE_1), texto.index(MARCADOR_FASE_2)
    i3, i4 = texto.index(MARCADOR_FASE_3), texto.index(MARCADOR_ENCERRAMENTO)
    return {
        "inicio": texto[:i1],
        "fase_1": texto[i1:i2],
        "fase_2": texto[i2:i3],
        "fase_3": texto[i3:i4],
        "encerramento": texto[i4:],
    }


# ============================================================
# Estrutura
# ============================================================

def test_marcadores_das_fases_existem_uma_vez_e_na_ordem(texto):
    posicoes = []
    for marcador in (MARCADOR_FASE_1, MARCADOR_FASE_2, MARCADOR_FASE_3, MARCADOR_ENCERRAMENTO):
        assert texto.count(marcador) == 1, f"Marcador {marcador!r} deveria aparecer exatamente uma vez."
        posicoes.append(texto.index(marcador))
    assert posicoes == sorted(posicoes), "Os marcadores das fases estao fora de ordem."


def test_tem_on_error_stop_antes_de_qualquer_comando(texto):
    codigo = _linhas_de_codigo(texto).strip()
    assert codigo.startswith("\\set ON_ERROR_STOP on")


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


# ============================================================
# READ ONLY obrigatorio nas Fases 1 e 3
# ============================================================

@pytest.mark.parametrize("bloco", ["inicio", "fase_1", "fase_3", "encerramento"])
def test_nenhum_comando_de_escrita_fora_da_fase_2(fases, bloco):
    codigo = _codigo(fases[bloco])
    for comando in COMANDOS_DE_ESCRITA:
        assert not re.search(rf"\b{comando}\b", codigo, flags=re.IGNORECASE), (
            f"Comando de escrita {comando!r} encontrado em {bloco!r} - so a Fase 2 pode escrever."
        )


@pytest.mark.parametrize("bloco", ["inicio", "fase_1", "fase_3"])
def test_modo_somente_leitura_e_ligado_no_inicio_do_bloco(fases, bloco):
    """O primeiro comando SQL de cada bloco de leitura liga o modo."""
    linhas = [l.strip() for l in _linhas_de_codigo(fases[bloco]).splitlines() if l.strip()]
    comandos_sql = [l for l in linhas if not l.startswith("\\")]
    assert comandos_sql[0] == LIGA_READ_ONLY


@pytest.mark.parametrize("bloco", ["fase_1", "fase_3", "encerramento"])
def test_modo_somente_leitura_e_religado_e_conferido_depois_de_cada_troca_de_banco(fases, bloco):
    """\\c abre uma sessao nova, que nasce em modo normal: logo depois de
    cada \\c, o modo e religado e o modo EFETIVO da sessao e lido."""
    linhas = [l.strip() for l in _linhas_de_codigo(fases[bloco]).splitlines() if l.strip()]
    trocas = [i for i, linha in enumerate(linhas) if linha.startswith("\\c ")]
    assert trocas, f"Esperava ao menos um \\c em {bloco!r}."
    for i in trocas:
        assert linhas[i + 1] == LIGA_READ_ONLY, f"Depois de {linhas[i]!r} o modo somente leitura nao e religado."
        conferencia = "\n".join(linhas[i + 2:i + 8])
        assert "current_setting('transaction_read_only') <> 'on'" in conferencia, (
            f"Depois de {linhas[i]!r} o modo efetivo da sessao nao e conferido."
        )
        assert "RAISE EXCEPTION" in conferencia


def test_fase_1_e_fase_3_trocam_para_os_dois_bancos(fases):
    for bloco in ("fase_1", "fase_3"):
        codigo = _linhas_de_codigo(fases[bloco])
        assert "\\c nsi_dev" in codigo and "\\c nsi_test" in codigo


def test_escrita_e_liberada_em_um_unico_ponto_no_inicio_da_fase_2(texto, fases):
    assert _linhas_de_codigo(texto).count(LIBERA_ESCRITA) == 1
    linhas = [l.strip() for l in _linhas_de_codigo(fases["fase_2"]).splitlines() if l.strip()]
    comandos_sql = [l for l in linhas if not l.startswith("\\")]
    assert comandos_sql[0] == LIBERA_ESCRITA, "A liberacao de escrita deve ser o primeiro comando SQL da Fase 2."


def test_nenhum_outro_comando_altera_o_modo_da_sessao(texto):
    codigo = _codigo(texto)
    assert len(re.findall(r"default_transaction_read_only\s*=", codigo)) == (
        codigo.count(LIGA_READ_ONLY) + codigo.count(LIBERA_ESCRITA)
    )
    for proibido in (r"\bRESET\b", r"\bREAD\s+WRITE\b", r"SESSION\s+CHARACTERISTICS", r"\bset_config\b",
                     r"SET\s+LOCAL", r"SET\s+TRANSACTION", r"\bBEGIN\s*;", r"START\s+TRANSACTION"):
        assert not re.search(proibido, codigo, flags=re.IGNORECASE), f"Comando {proibido!r} nao e permitido no script."


# ============================================================
# Cada fase e autossuficiente
# ============================================================

def test_variaveis_de_cliente_sao_prefixadas_pela_fase_e_nunca_cruzam_fases(texto, fases):
    definidas = re.findall(r"\bAS\s+(\w+)\s*(?:FROM[^\n]*)?\n\\gset", texto)
    assert definidas, "Esperava ao menos uma variavel de cliente (\\gset)."
    for nome in definidas:
        assert nome.startswith(("f1_", "f3_")), f"Variavel de cliente {nome!r} sem prefixo de fase."

    for prefixo, propria in (("f1_", "fase_1"), ("f3_", "fase_3")):
        for bloco, conteudo in fases.items():
            if bloco == propria:
                continue
            assert prefixo not in _linhas_de_codigo(conteudo), (
                f"Variavel {prefixo}* (da {propria}) referenciada em {bloco!r} - nenhuma fase transmite variaveis a outra."
            )


def test_fase_2_nao_usa_nenhuma_variavel_de_cliente(fases):
    codigo = _linhas_de_codigo(fases["fase_2"])
    assert "\\gset" not in codigo
    assert "\\if" not in codigo
    assert not re.search(r":'?\w+'?", _sem_literais(codigo).replace("::", "")), (
        "A Fase 2 nao pode interpolar variavel de cliente - cada acao le o estado por conta propria."
    )


def test_cada_acao_da_fase_2_le_o_estado_antes_de_escrever(fases):
    """Em cada bloco DO da Fase 2, a leitura do catalogo vem antes do
    comando de escrita do mesmo bloco."""
    blocos = re.findall(r"DO \$\$.*?END \$\$;", fases["fase_2"], flags=re.DOTALL)
    assert len(blocos) == 4, f"A Fase 2 deveria ter exatamente quatro acoes, encontradas {len(blocos)}."
    for bloco in blocos:
        posicao_leitura = bloco.index("FROM pg_roles")
        posicao_escrita = bloco.index("EXECUTE '")
        assert posicao_leitura < posicao_escrita


# ============================================================
# Fase 2 - exatamente quatro acoes, e nenhuma outra
# ============================================================

def test_fase_2_executa_exatamente_as_quatro_escritas_aprovadas(fases):
    codigo = _linhas_de_codigo(fases["fase_2"])
    escritas = re.findall(r"EXECUTE '([^']*)'", codigo)
    assert sorted(escritas) == sorted([
        "CREATE ROLE nsi_congelamento NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS",
        "GRANT nsi_congelamento TO nsi_aplicacao WITH INHERIT FALSE, SET TRUE, ADMIN FALSE",
        "GRANT USAGE ON SCHEMA nsi_operacional TO nsi_congelamento",
        "GRANT USAGE ON SCHEMA nsi_operacional TO nsi_congelamento",
    ])


def test_fase_2_nao_tem_nenhuma_escrita_fora_dos_quatro_execute(fases):
    """Com os literais removidos, o unico comando de escrita que sobra na
    Fase 2 e o proprio EXECUTE (quatro vezes) - nenhum GRANT/REVOKE/ALTER/
    DROP direto."""
    codigo = _codigo(fases["fase_2"])
    assert len(re.findall(r"\bEXECUTE\b", codigo)) == 4
    for comando in COMANDOS_DE_ESCRITA:
        if comando == "EXECUTE":
            continue
        assert not re.search(rf"\b{comando}\b", codigo, flags=re.IGNORECASE), (
            f"Comando de escrita direto {comando!r} encontrado na Fase 2."
        )


def test_criacao_da_role_so_ocorre_quando_ela_esta_ausente(fases):
    bloco = re.findall(r"DO \$\$.*?END \$\$;", fases["fase_2"], flags=re.DOTALL)[0]
    guarda = bloco.index("IF NOT FOUND THEN")
    criacao = bloco.index("EXECUTE 'CREATE ROLE nsi_congelamento")
    retorno = bloco.index("RETURN;")
    assert guarda < criacao < retorno
    assert "Abortando sem corrigir." in bloco, "Role presente em forma diferente deve abortar, nunca corrigir."


def test_membership_so_e_concedida_quando_ausente_e_aborta_se_diferente(fases):
    bloco = re.findall(r"DO \$\$.*?END \$\$;", fases["fase_2"], flags=re.DOTALL)[1]
    assert bloco.index("Abortando sem corrigir.") < bloco.index("IF total_linhas = 0 THEN") < bloco.index("EXECUTE 'GRANT nsi_congelamento")


def test_usage_e_concedido_uma_vez_em_cada_banco(fases):
    codigo = _linhas_de_codigo(fases["fase_2"])
    posicao_dev, posicao_test = codigo.index("\\c nsi_dev"), codigo.index("\\c nsi_test")
    concessoes = [m.start() for m in re.finditer(r"EXECUTE 'GRANT USAGE ON SCHEMA nsi_operacional TO nsi_congelamento'", codigo)]
    assert len(concessoes) == 2
    assert posicao_dev < concessoes[0] < posicao_test < concessoes[1]


# ============================================================
# Seguranca
# ============================================================

def test_nao_contem_senha_nem_comando_de_senha(texto):
    codigo = _linhas_de_codigo(texto)
    assert not re.search(r"\bPASSWORD\b", codigo, flags=re.IGNORECASE)
    assert "\\password" not in codigo


def test_verifica_que_a_role_nao_tem_senha_nas_tres_fases(fases):
    for bloco in ("fase_1", "fase_2", "fase_3"):
        assert "rolpassword IS NOT NULL" in fases[bloco], f"{bloco!r} nao confere que nsi_congelamento esta sem senha."


def test_revisoes_aceitas_sao_exatamente_0004_e_0005(fases):
    for bloco in ("fase_1", "fase_3"):
        assert fases[bloco].count("revisao NOT IN ('0004', '0005')") == 2, (
            f"{bloco!r} deveria conferir a revisao aceita nos dois bancos."
        )


def test_pos_validacao_confere_privilegio_efetivo_no_schema(fases):
    fase_3 = fases["fase_3"]
    for funcao in ("has_schema_privilege", "has_table_privilege", "has_any_column_privilege", "has_function_privilege"):
        assert fase_3.count(funcao + "('nsi_congelamento'") >= 2, f"{funcao} deveria ser conferido nos dois bancos."


# ============================================================
# O script nunca e executado por codigo - sua execucao e sempre manual
# ============================================================
#
# Contrato: nenhum codigo de aplicacao, nenhuma migration e nenhum teste
# pode EXECUTAR o script administrativo. Mencionar o script em
# documentacao (docstring) ou em comentario e permitido - o que se
# verifica e execucao, nunca mera referencia textual.
#
# Duas formas de executar, ambas verificadas:
#   (1) lancar o cliente psql (ou equivalente) por um processo externo;
#   (2) carregar o proprio arquivo .sql em codigo - o que exige o nome do
#       script em um literal de codigo, fora de docstring e de comentario.

PASTAS_DE_CODIGO = ("adapters", "core", "integration", "services", "migrations", "tests")
ARQUIVOS_DE_CODIGO = ("app.py", "config.py")

# Formas de lancar um processo externo.
LANCADORES_DE_PROCESSO = {
    "subprocess": {"run", "Popen", "call", "check_call", "check_output", "getoutput", "getstatusoutput"},
    "os": {"system", "popen", "startfile", "execl", "execle", "execlp", "execlpe", "execv", "execve",
           "execvp", "execvpe", "spawnl", "spawnle", "spawnlp", "spawnlpe", "spawnv", "spawnve",
           "spawnvp", "spawnvpe"},
    "asyncio": {"create_subprocess_exec", "create_subprocess_shell"},
}

# Clientes de linha de comando do PostgreSQL capazes de rodar um script.
CLIENTE_POSTGRES = re.compile(r"\b(psql|pgbench)(\.exe)?\b", flags=re.IGNORECASE)


def _arquivos_python_do_projeto():
    for pasta in PASTAS_DE_CODIGO:
        for caminho in sorted((BASE_DIR / pasta).rglob("*.py")):
            if "__pycache__" not in caminho.parts:
                yield caminho
    for arquivo in ARQUIVOS_DE_CODIGO:
        yield BASE_DIR / arquivo


def _literais_fora_de_docstring(arvore):
    """Todos os literais de texto do arquivo, exceto docstrings (de modulo,
    classe e funcao). Comentarios nao fazem parte da arvore sintatica."""
    docstrings = set()
    for no in ast.walk(arvore):
        if isinstance(no, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            corpo = no.body
            if corpo and isinstance(corpo[0], ast.Expr) and isinstance(corpo[0].value, ast.Constant) \
                    and isinstance(corpo[0].value.value, str):
                docstrings.add(id(corpo[0].value))
    return [no.value for no in ast.walk(arvore)
            if isinstance(no, ast.Constant) and isinstance(no.value, str) and id(no) not in docstrings]


def _lanca_cliente_postgres(codigo_fonte: str) -> bool:
    """True se o codigo lanca um processo externo cujo comando cita um
    cliente de linha de comando do PostgreSQL."""
    arvore = ast.parse(codigo_fonte)

    # Apelidos de importacao: "import subprocess as sp" -> sp e subprocess;
    # "from subprocess import run as executar" -> executar e subprocess.run.
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
        ) or (
            isinstance(funcao, ast.Name) and funcao.id in funcoes
        )
        if not lancador:
            continue
        for filho in ast.walk(no):
            if isinstance(filho, ast.Constant) and isinstance(filho.value, str) and CLIENTE_POSTGRES.search(filho.value):
                return True
    return False


def _cita_o_script_em_codigo(codigo_fonte: str, nome_do_script: str) -> bool:
    """True se o nome do script aparece em um literal de codigo - fora de
    docstring e de comentario."""
    return any(nome_do_script in literal for literal in _literais_fora_de_docstring(ast.parse(codigo_fonte)))


def test_nenhum_arquivo_executa_o_cliente_psql():
    """Nenhum codigo de aplicacao, migration ou teste lanca o psql (ou
    equivalente) - unica forma de rodar um script administrativo .sql como
    foi escrito."""
    for caminho in _arquivos_python_do_projeto():
        assert not _lanca_cliente_postgres(caminho.read_text(encoding="utf-8-sig")), (
            f"{caminho.relative_to(BASE_DIR)} lanca um cliente de linha de comando do PostgreSQL - "
            "scripts administrativos nunca sao executados por codigo."
        )


def test_nenhum_arquivo_carrega_o_script_em_codigo():
    """Nenhum codigo de aplicacao, migration ou teste usa o arquivo do
    script em codigo executavel (abrir, ler para executar, passar como
    argumento). Menciona-lo em docstring ou comentario e permitido.

    Unica excecao: este proprio arquivo, que LE o texto do script para
    inspeciona-lo - e nunca o executa (ver CAMINHO_PROVISIONAR)."""
    nome = CAMINHO_PROVISIONAR.name
    for caminho in _arquivos_python_do_projeto():
        if caminho.resolve() == Path(__file__).resolve():
            continue
        assert not _cita_o_script_em_codigo(caminho.read_text(encoding="utf-8-sig"), nome), (
            f"{caminho.relative_to(BASE_DIR)} usa {nome} em codigo executavel - "
            "o script nunca pode ser executado por codigo; cita-lo so e permitido em docstring ou comentario."
        )


@pytest.mark.parametrize("codigo_fonte,esperado", [
    ('import subprocess\nsubprocess.run(["psql", "-f", "x.sql"])\n', True),
    ('import subprocess\nsubprocess.Popen("psql.exe -U postgres -f x.sql", shell=True)\n', True),
    ('import os\nos.system("psql -d postgres -f x.sql")\n', True),
    ('from subprocess import check_call\ncheck_call(["PSQL", "-f", "x.sql"])\n', True),
    ('import subprocess\nsubprocess.call(["psql", "-f", "x.sql"])\n', True),
    ('import subprocess\nsubprocess.check_output(["psql", "-f", "x.sql"])\n', True),
    ('import subprocess as sp\nsp.run(["psql", "-f", "x.sql"])\n', True),
    ('from subprocess import run as executar\nexecutar(["psql", "-f", "x.sql"])\n', True),
    ('import asyncio\nasyncio.create_subprocess_exec("psql", "-f", "x.sql")\n', True),
    ('def run(x):\n    return x\nrun(["psql"])\n', False),
    ('import subprocess\nsubprocess.run(["alembic", "upgrade", "0004"])\n', False),
    ('"""Execute manualmente: psql -U postgres -f x.sql"""\nx = 1  # psql -f x.sql\n', False),
    ('mensagem = "rode o psql manualmente"\n', False),
])
def test_detector_de_lancamento_do_psql(codigo_fonte, esperado):
    """Prova o detector: um detector que nunca detecta aprovaria tudo."""
    assert _lanca_cliente_postgres(codigo_fonte) is esperado


@pytest.mark.parametrize("codigo_fonte,esperado", [
    ('caminho = "scripts/postgres_local/provisionar_b4_role_congelamento.sql"\n', True),
    ('sql = open(BASE / "provisionar_b4_role_congelamento.sql").read()\ncur.execute(sql)\n', True),
    ('"""Pre-requisito: provisionar_b4_role_congelamento.sql ja executado manualmente."""\n', False),
    ('def f():\n    """Ver provisionar_b4_role_congelamento.sql."""\n    return 1\n', False),
    ('x = 1  # provisionar_b4_role_congelamento.sql\n', False),
])
def test_detector_de_uso_do_script_em_codigo(codigo_fonte, esperado):
    assert _cita_o_script_em_codigo(codigo_fonte, "provisionar_b4_role_congelamento.sql") is esperado
