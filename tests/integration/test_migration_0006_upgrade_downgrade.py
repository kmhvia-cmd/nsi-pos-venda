# -*- coding: utf-8 -*-
"""
NSI - tests/integration/test_migration_0006_upgrade_downgrade.py
(Sprint B, B5.4 - ADR-010; Especificacao Tecnica, B5.2, itens 10.5, 17 e
18)

Testes de integracao REAIS contra PostgreSQL - nunca SQLite, nunca mock -
da migration 0006, exclusivamente contra nsi_test (nunca nsi_dev -
"Criterios de rollback": nenhum downgrade e executado em nsi_dev).

Revisoes EXPLICITAS em toda chamada ao Alembic - nunca `head`.

GATE DE IDENTIDADE OBRIGATORIO antes de qualquer downgrade: current_
database() = 'nsi_test', servidor local, porta 5432, current_user =
'nsi_test_migrator' - repetido antes de CADA acao destrutiva, inclusive na
recuperacao do 'finally'.

O que e comprovado:
  - inventario somente leitura EXATO do head: as cinco tabelas, com suas
    constraints e indices, as tres triggers e suas funcoes, as quatro
    funcoes de importacao e a nova definicao de fn_criar_claim - e nada
    mais (criterio de aceite 2);
  - ciclo 0006 -> 0005 -> 0006: o downgrade remove exatamente os objetos da
    0006, inclusive o registro tecnico de execucoes NAO promovidas, e
    restaura fn_criar_claim;
  - a definicao restaurada e IDENTICA a da 0003: o ciclo continua ate 0002
    e volta a 0005, onde fn_criar_claim e criada pelo caminho original, e
    as duas definicoes (texto, owner, SECURITY DEFINER, search_path e
    matriz de EXECUTE) sao comparadas;
  - o preflight do downgrade aborta, sem remover nada, se existir lote
    promovido (criterio de aceite 8).

PREFLIGHT SEM COMMIT DE PROMOCAO: a B5.2 (item 17) proibe confirmar uma
promocao em teste, justamente porque o preflight a protegeria para sempre
(o registro tecnico e imutavel). Por isso o teste do preflight executa o
proprio downgrade() da migration dentro de UMA transacao, que contem a
promocao e termina em ROLLBACK - nada e confirmado.

DIVULGACAO DE RESIDUO: o ciclo confirma uma execucao com um lote NAO
promovivel para provar que o downgrade a remove; ela desaparece junto com
as tabelas. O trecho 0005 -> 0002 -> 0005 remove as tabelas da 0004 (e, com
elas, o residuo sintetico de outros testes) e exige zero recibos da B4 -
mesma premissa de test_migration_0004_upgrade_downgrade.py.

Nenhum teste chama pytest nem executa a suite completa internamente.
"""
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import psycopg
import pytest
import sqlalchemy
from alembic.migration import MigrationContext
from alembic.operations import Operations

from config import mascarar_dsn
from tests.apoio_b5 import (
    FUNCOES_DE_IMPORTACAO,
    FUNCOES_DE_TRIGGER_0006,
    TABELAS_0006,
    caminho_do_lote,
    concluir,
    doc_a1,
    doc_a2,
    entrada_de_lote,
    importar_bytes,
    iniciar,
    manifesto_canonico,
    serializar,
    sha256_hex,
    uuid_texto,
)

pytestmark = pytest.mark.pg_integration

NOME_SCHEMA = "nsi_operacional"
USUARIO_MIGRATOR_ESPERADO = "nsi_test_migrator"
ARQUIVO_0006 = Path(__file__).resolve().parents[2] / "migrations" / "versions" / "0006_importacao_legado.py"

TABELAS_ATE_0005 = {"alembic_version", "claims", "eventos_claim", "comandos_idempotentes",
                    "lotes", "registros_coleta", "eventos_lote", "eventos_registro_coleta"}
FUNCOES_ATE_0005 = {
    "fn_criar_claim", "fn_registrar_heartbeat", "fn_liberar_claim", "fn_materializar_expiracao",
    "fn_registrar_revisao_abandono", "fn_reatribuir_claim",
    "fn_bloquear_alteracao_eventos_claim", "fn_bloquear_alteracao_eventos_lote",
    "fn_bloquear_alteracao_eventos_registro_coleta",
    "fn_registrar_lote", "fn_registrar_congelamento", "fn_confirmar_disparo",
    "fn_registrar_correcao", "fn_registrar_tentativa_nao_resolvida",
}
SEARCH_PATH_FIXO = ["search_path=pg_catalog, nsi_operacional, pg_temp"]

# Inventario EXATO dos objetos das cinco tabelas (criterio de aceite 2).
CONSTRAINTS_0006 = {
    "importacoes_legado": {
        "importacoes_legado_pkey", "ck_importacoes_legado_fuso_formato",
    },
    "importacoes_legado_arquivos": {
        "importacoes_legado_arquivos_importacao_id_fkey", "uq_importacoes_legado_arquivos_caminho",
        "ck_importacoes_legado_arquivos_caminho", "ck_importacoes_legado_arquivos_sha256",
        "ck_importacoes_legado_arquivos_geracao", "ck_importacoes_legado_arquivos_destino",
        "ck_importacoes_legado_arquivos_constraint_violada", "ck_importacoes_legado_arquivos_coerencia",
    },
    "importacoes_legado_conclusoes": {
        "importacoes_legado_conclusoes_pkey", "importacoes_legado_conclusoes_importacao_id_fkey",
        "ck_importacoes_legado_conclusoes_sha256", "ck_importacoes_legado_conclusoes_sha256_recalculado",
        "ck_importacoes_legado_conclusoes_total",
    },
    "lotes_legado": {
        "lotes_legado_pkey", "lotes_legado_importacao_id_fkey", "lotes_legado_lote_id_promovido_fkey",
        "uq_lotes_legado_lote_id_legado", "ck_lotes_legado_sha256", "ck_lotes_legado_geracao",
        "ck_lotes_legado_status_legado", "ck_lotes_legado_destino", "ck_lotes_legado_coerencia",
    },
    "registros_legado": {
        "pk_registros_legado", "registros_legado_snapshot_lote_id_fkey", "ck_registros_legado_lista",
        "ck_registros_legado_posicao", "ck_registros_legado_conteudo_objeto", "ck_registros_legado_sha256",
        "ck_registros_legado_classificacao", "ck_registros_legado_identidade",
    },
}
INDICES_0006 = {
    "importacoes_legado": {"importacoes_legado_pkey"},
    "importacoes_legado_arquivos": {"uq_importacoes_legado_arquivos_caminho"},
    "importacoes_legado_conclusoes": {"importacoes_legado_conclusoes_pkey"},
    "lotes_legado": {"lotes_legado_pkey", "uq_lotes_legado_lote_id_legado"},
    "registros_legado": {"pk_registros_legado", "registros_legado_registro_coleta_id"},
}
COLUNAS_0006 = {
    "importacoes_legado": ["importacao_id", "iniciada_em", "executado_por_login", "fuso_declarado"],
    "importacoes_legado_arquivos": [
        "importacao_id", "caminho_relativo", "documento_sha256", "lote_id_legado", "geracao", "destino",
        "motivo", "constraint_violada", "lote_id_promovido", "registrado_em"],
    "importacoes_legado_conclusoes": [
        "importacao_id", "concluida_em", "manifesto_canonico", "manifesto_sha256", "total_arquivos"],
    "lotes_legado": [
        "snapshot_lote_id", "importacao_id", "lote_id_legado", "caminho_relativo", "documento_bruto",
        "documento_sha256", "geracao", "status_legado", "criado_em_bruto", "destino", "motivo_nao_promocao",
        "lote_id_promovido"],
    "registros_legado": [
        "snapshot_lote_id", "lista", "posicao", "conteudo_bruto", "conteudo_sha256", "registro_coleta_id",
        "classificacao"],
}
TRIGGERS_0006 = {f"{t}_bloqueia_alteracao" for t in TABELAS_0006[:3]}


def _executar_alembic(*args: str, env: dict) -> "subprocess.CompletedProcess[str]":
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        capture_output=True,
        text=True,
        env=env,
    )


def _consultar_estado(url: str) -> dict:
    """Le, numa unica conexao, revisao, tabelas, funcoes (owner, SECURITY
    DEFINER, search_path, matriz de EXECUTE e definicao), constraints,
    indices, colunas e triggers das tabelas da 0006, e o EXECUTE efetivo de
    nsi_importacao - sempre o estado real do banco, nunca presumido."""
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT version_num FROM nsi_operacional.alembic_version")
            linha = cur.fetchone()
            versao = linha[0] if linha else None

            cur.execute("SELECT tablename, tableowner FROM pg_catalog.pg_tables WHERE schemaname = %s",
                        (NOME_SCHEMA,))
            donos_das_tabelas = dict(cur.fetchall())

            cur.execute("""
                SELECT p.proname, pg_get_userbyid(p.proowner), p.prosecdef, p.proconfig,
                       ARRAY(SELECT pg_get_userbyid(a.grantee) FROM aclexplode(p.proacl) a
                              WHERE a.privilege_type = 'EXECUTE' AND a.grantee <> p.proowner AND a.grantee <> 0
                              ORDER BY 1),
                       EXISTS (SELECT 1 FROM aclexplode(p.proacl) a WHERE a.grantee = 0),
                       pg_get_functiondef(p.oid)
                  FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
                 WHERE n.nspname = %s
            """, (NOME_SCHEMA,))
            funcoes = {}
            for nome, dono, secdef, config, grantees, public_tem, definicao in cur.fetchall():
                assert nome not in funcoes, f"{nome} existe em mais de uma assinatura."
                funcoes[nome] = {"dono": dono, "secdef": secdef, "config": config, "execute": set(grantees),
                                 "public": public_tem, "definicao": definicao}

            cur.execute("""
                SELECT c.relname, o.conname FROM pg_catalog.pg_constraint o
                  JOIN pg_catalog.pg_class c ON c.oid = o.conrelid
                  JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
                 WHERE n.nspname = %s AND c.relname = ANY(%s)
            """, (NOME_SCHEMA, list(TABELAS_0006)))
            constraints = {}
            for tabela, nome in cur.fetchall():
                constraints.setdefault(tabela, set()).add(nome)

            cur.execute("SELECT tablename, indexname FROM pg_catalog.pg_indexes "
                        "WHERE schemaname = %s AND tablename = ANY(%s)", (NOME_SCHEMA, list(TABELAS_0006)))
            indices = {}
            for tabela, nome in cur.fetchall():
                indices.setdefault(tabela, set()).add(nome)

            cur.execute("""
                SELECT c.relname, array_agg(a.attname::text ORDER BY a.attnum)
                  FROM pg_catalog.pg_attribute a
                  JOIN pg_catalog.pg_class c ON c.oid = a.attrelid
                  JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
                 WHERE n.nspname = %s AND c.relname = ANY(%s) AND a.attnum > 0 AND NOT a.attisdropped
                 GROUP BY c.relname
            """, (NOME_SCHEMA, list(TABELAS_0006)))
            colunas = dict(cur.fetchall())

            cur.execute("""
                SELECT t.tgname FROM pg_catalog.pg_trigger t
                  JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
                  JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
                 WHERE n.nspname = %s AND c.relname = ANY(%s) AND NOT t.tgisinternal
            """, (NOME_SCHEMA, list(TABELAS_0006)))
            triggers = {r[0] for r in cur.fetchall()}

            cur.execute("""
                SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'nsi_importacao'),
                       has_schema_privilege('nsi_importacao', 'nsi_operacional', 'USAGE'),
                       ARRAY(SELECT p.proname::text FROM pg_catalog.pg_proc p
                               JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
                              WHERE n.nspname = 'nsi_operacional'
                                AND has_function_privilege('nsi_importacao', p.oid, 'EXECUTE') ORDER BY 1)
            """)
            role_existe, role_usage, role_execute = cur.fetchone()

    return {
        "versao": versao, "tabelas": set(donos_das_tabelas), "donos_das_tabelas": donos_das_tabelas,
        "funcoes": funcoes, "constraints": constraints, "indices": indices, "colunas": colunas,
        "triggers": triggers, "role_importacao": (role_existe, role_usage, role_execute),
    }


def _comprovar_identidade_antes_de_destrutivo(url: str) -> None:
    """GATE OBRIGATORIO antes de qualquer 'alembic downgrade' - mesmo
    mecanismo de test_migration_0002/0004/0005_upgrade_downgrade.py."""
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database(), inet_server_addr(), inet_server_port(), current_user")
            banco_real, endereco_servidor, porta_real, usuario_real = cur.fetchone()

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
    assert usuario_real == USUARIO_MIGRATOR_ESPERADO, (
        f"Usuario de conexao inesperado (current_user={usuario_real!r}), esperado "
        f"{USUARIO_MIGRATOR_ESPERADO!r}. Nenhuma acao adicional e executada."
    )


def _assert_saida_alembic_sem_dsn(url: str, saida: str, rotulo: str) -> None:
    if url in saida:
        pytest.fail(
            f"Vazamento de DSN detectado na saida do Alembic ({rotulo}) - "
            "a DSN de conexao apareceu na saida capturada. Mensagem fixa: "
            "nem a DSN nem a saida sao exibidas aqui."
        )


def _alembic(url: str, env: dict, comando: str, revisao: str) -> None:
    """Gate de identidade antes de TODO downgrade; saida sem DSN; falha com
    o stderr do Alembic."""
    if comando == "downgrade":
        _comprovar_identidade_antes_de_destrutivo(url)
    resultado = _executar_alembic(comando, revisao, env=env)
    _assert_saida_alembic_sem_dsn(url, resultado.stdout, f"{comando} {revisao} - stdout")
    _assert_saida_alembic_sem_dsn(url, resultado.stderr, f"{comando} {revisao} - stderr")
    assert resultado.returncode == 0, resultado.stderr[-1500:]


def _assert_inventario_0006(estado: dict) -> None:
    assert estado["versao"] == "0006"
    assert estado["tabelas"] == TABELAS_ATE_0005 | set(TABELAS_0006), (
        "A 0006 cria exatamente as cinco tabelas dos itens 8 e 16."
    )
    assert set(estado["funcoes"]) == FUNCOES_ATE_0005 | set(FUNCOES_DE_IMPORTACAO) | set(FUNCOES_DE_TRIGGER_0006), (
        "A 0006 cria exatamente as quatro funcoes de importacao e as tres funcoes de trigger."
    )
    for tabela in TABELAS_0006:
        assert estado["donos_das_tabelas"][tabela] == "nsi_eventos_owner", tabela
    assert estado["constraints"] == CONSTRAINTS_0006
    assert estado["indices"] == INDICES_0006
    assert estado["colunas"] == COLUNAS_0006
    assert estado["triggers"] == TRIGGERS_0006, "Triggers so no registro tecnico; nenhuma no snapshot."

    for nome in FUNCOES_DE_IMPORTACAO:
        funcao = estado["funcoes"][nome]
        assert funcao["dono"] == "nsi_eventos_owner", nome
        assert funcao["secdef"] is True, nome
        assert funcao["config"] == SEARCH_PATH_FIXO, nome
        assert funcao["execute"] == {"nsi_importacao"}, nome
        assert funcao["public"] is False, nome
    for nome in FUNCOES_DE_TRIGGER_0006:
        funcao = estado["funcoes"][nome]
        assert (funcao["dono"], funcao["secdef"], funcao["execute"], funcao["public"]) == (
            "nsi_eventos_owner", False, set(), False), nome

    criar_claim = estado["funcoes"]["fn_criar_claim"]
    assert (criar_claim["dono"], criar_claim["secdef"], criar_claim["config"], criar_claim["execute"],
            criar_claim["public"]) == ("nsi_eventos_owner", True, SEARCH_PATH_FIXO, {"nsi_aplicacao"}, False)
    assert "registro_legado_nao_promovido" in criar_claim["definicao"]
    assert estado["role_importacao"] == (True, True, sorted(FUNCOES_DE_IMPORTACAO))


def _assert_inventario_0005(estado: dict) -> None:
    assert estado["versao"] == "0005"
    assert estado["tabelas"] == TABELAS_ATE_0005, "O downgrade remove exatamente as cinco tabelas da 0006."
    assert set(estado["funcoes"]) == FUNCOES_ATE_0005, "O downgrade remove exatamente as sete funcoes da 0006."
    assert estado["constraints"] == {} and estado["indices"] == {} and estado["triggers"] == set()
    assert estado["role_importacao"] == (True, True, []), (
        "A migration nunca cria, altera ou remove a role; em 0005 ela nao tem EXECUTE em nenhuma funcao."
    )


def _forma_de_fn_criar_claim(estado: dict) -> tuple:
    f = estado["funcoes"]["fn_criar_claim"]
    return f["definicao"], f["dono"], f["secdef"], f["config"], f["execute"], f["public"]


def _carregar_migration_0006():
    spec = importlib.util.spec_from_file_location("migration_0006_sob_teste", ARQUIVO_0006)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_identidade_do_banco_de_teste_e_comprovada(request):
    url = request.getfixturevalue("url_banco_teste")
    _comprovar_identidade_antes_de_destrutivo(url)


def test_inventario_somente_leitura_do_head(request):
    url = request.getfixturevalue("url_banco_teste")
    _assert_inventario_0006(_consultar_estado(url))


def test_nenhuma_tabela_nova_tem_coluna_de_valor_pessoal_no_registro_tecnico(request):
    """Item 16: o registro tecnico nao tem coluna para nome, telefone,
    produto ou conteudo de registro - o dado pessoal vive so no snapshot."""
    url = request.getfixturevalue("url_banco_teste")
    colunas = _consultar_estado(url)["colunas"]
    for tabela in TABELAS_0006[:3]:
        for coluna in colunas[tabela]:
            assert not any(p in coluna for p in ("nome", "telefone", "whatsapp", "produto", "conteudo", "documento_bruto")), (
                f"{tabela}.{coluna}"
            )


def test_ciclo_downgrade_0005_upgrade_0006_restaura_fn_criar_claim_da_0003(request):
    """0006 -> (gate) -> downgrade 0005 -> downgrade 0002 -> upgrade 0005 ->
    upgrade 0006, terminando OBRIGATORIAMENTE em 0006."""
    url = request.getfixturevalue("url_banco_teste")
    env = {**os.environ, "NSI_DATABASE_ENV": "test"}

    estado_inicial = _consultar_estado(url)
    _assert_inventario_0006(estado_inicial)

    # Execucao confirmada com um lote NAO promovivel: o downgrade a remove
    # junto com as tabelas, sem ser barrado pelo preflight.
    documento = doc_a1()
    conteudo = serializar(documento)
    with psycopg.connect(url) as conn:
        cur = conn.cursor()
        cur.execute("SET LOCAL ROLE nsi_eventos_owner")
        importacao_id = iniciar(cur)
        resultado = importar_bytes(cur, importacao_id, caminho_do_lote(documento["lote_id"]), conteudo)
        assert resultado["destino"] == "preservado"
        concluir(cur, importacao_id, manifesto_canonico(
            importacao_id, "America/Sao_Paulo",
            [entrada_de_lote(caminho_do_lote(documento["lote_id"]), conteudo, resultado)]), 1)
        conn.commit()

    try:
        _alembic(url, env, "downgrade", "0005")
        estado_0005_restaurado = _consultar_estado(url)
        _assert_inventario_0005(estado_0005_restaurado)
        assert "registro_legado_nao_promovido" not in estado_0005_restaurado["funcoes"]["fn_criar_claim"]["definicao"]
        assert "registros_legado" not in estado_0005_restaurado["funcoes"]["fn_criar_claim"]["definicao"]

        # Definicao criada pelo caminho ORIGINAL (0003), sem passar pela 0006.
        _alembic(url, env, "downgrade", "0002")
        assert "fn_criar_claim" not in _consultar_estado(url)["funcoes"]
        _alembic(url, env, "upgrade", "0005")
        estado_0005_original = _consultar_estado(url)
        _assert_inventario_0005(estado_0005_original)

        assert _forma_de_fn_criar_claim(estado_0005_restaurado) == _forma_de_fn_criar_claim(estado_0005_original), (
            "O downgrade da 0006 precisa restaurar EXATAMENTE a definicao da 0003: texto, owner, "
            "SECURITY DEFINER, search_path e matriz de EXECUTE."
        )

        _alembic(url, env, "upgrade", "0006")
        estado_final = _consultar_estado(url)
        _assert_inventario_0006(estado_final)
        assert _forma_de_fn_criar_claim(estado_final) == _forma_de_fn_criar_claim(estado_inicial), (
            "O novo upgrade recria a mesma definicao de fn_criar_claim da 0006."
        )

        # As funcoes recriadas operam; a execucao confirmada antes do ciclo
        # foi removida com as tabelas.
        with psycopg.connect(url) as conn:
            cur = conn.cursor()
            cur.execute("SET LOCAL ROLE nsi_eventos_owner")
            cur.execute("SELECT count(*) FROM nsi_operacional.importacoes_legado")
            assert cur.fetchone()[0] == 0
            nova = iniciar(cur)
            assert importar_bytes(cur, nova, caminho_do_lote(documento["lote_id"]), conteudo)["destino"] == "preservado"
            conn.rollback()
    finally:
        excecao_original_em_andamento = sys.exc_info()[0] is not None

        _comprovar_identidade_antes_de_destrutivo(url)
        if _consultar_estado(url)["versao"] != "0006":
            resultado_recuperacao = _executar_alembic("upgrade", "0006", env=env)
            _assert_saida_alembic_sem_dsn(url, resultado_recuperacao.stdout, "recuperacao final - stdout")
            _assert_saida_alembic_sem_dsn(url, resultado_recuperacao.stderr, "recuperacao final - stderr")
            if resultado_recuperacao.returncode != 0 and not excecao_original_em_andamento:
                pytest.fail(
                    "Falha ao recuperar nsi_test para 0006 apos o teste - stderr: "
                    f"{resultado_recuperacao.stderr[-500:] if resultado_recuperacao.stderr else '(vazio)'}"
                )

    assert _consultar_estado(url)["versao"] == "0006"


def test_preflight_do_downgrade_aborta_sem_remover_nada_se_existir_lote_promovido(request):
    """Executa o proprio downgrade() da 0006 dentro de uma unica transacao
    que contem uma promocao e termina em ROLLBACK (ver docstring do
    modulo). O preflight precisa abortar antes de qualquer DROP."""
    url = request.getfixturevalue("url_banco_teste")
    _comprovar_identidade_antes_de_destrutivo(url)
    estado_inicial = _consultar_estado(url)
    _assert_inventario_0006(estado_inicial)
    migration = _carregar_migration_0006()

    documento = doc_a2()
    conteudo = serializar(documento)
    importacao_id = uuid_texto()

    engine = sqlalchemy.create_engine(url.replace("postgresql://", "postgresql+psycopg://", 1))
    try:
        with engine.connect() as conexao:
            transacao = conexao.begin()
            try:
                conexao.exec_driver_sql("SET LOCAL ROLE nsi_eventos_owner")
                conexao.exec_driver_sql(
                    "SELECT nsi_operacional.fn_iniciar_importacao_legado(%s, %s)", (importacao_id, "America/Sao_Paulo"))
                resultado = conexao.exec_driver_sql(
                    "SELECT nsi_operacional.fn_importar_lote_legado(%s, %s, %s, %s)",
                    (importacao_id, caminho_do_lote(documento["lote_id"]), conteudo, sha256_hex(conteudo)),
                ).scalar_one()
                assert resultado["destino"] == "promovido"
                conexao.exec_driver_sql("RESET ROLE")

                with Operations.context(MigrationContext.configure(conexao)):
                    with pytest.raises(sqlalchemy.exc.DBAPIError) as exc_info:
                        migration.downgrade()
                assert isinstance(exc_info.value.orig, psycopg.errors.RaiseException)
                mensagem = exc_info.value.orig.diag.message_primary
                assert mensagem.startswith("Downgrade de 0006 abortado: 1 lote(s) promovido(s)")
                assert documento["lote_id"] not in mensagem
            finally:
                transacao.rollback()
    finally:
        engine.dispose()

    estado_final = _consultar_estado(url)
    _assert_inventario_0006(estado_final)
    assert _forma_de_fn_criar_claim(estado_final) == _forma_de_fn_criar_claim(estado_inicial)
    with psycopg.connect(url) as conn:
        cur = conn.cursor()
        cur.execute("SET LOCAL ROLE nsi_eventos_owner")
        cur.execute("SELECT count(*) FROM nsi_operacional.importacoes_legado_arquivos WHERE destino = 'promovido'")
        assert cur.fetchone()[0] == 0, "Nenhuma promocao pode ter sido confirmada por este teste."
        conn.rollback()


def test_nsi_test_nao_tem_nenhum_lote_promovido_confirmado(request):
    """Regra de limpeza da B5.2 (item 17): testes com commit real usam
    somente lotes nao promoviveis. Um lote promovido confirmado bloquearia o
    downgrade da 0006 para sempre."""
    url = request.getfixturevalue("url_banco_teste")
    with psycopg.connect(url) as conn:
        cur = conn.cursor()
        cur.execute("SET LOCAL ROLE nsi_eventos_owner")
        cur.execute("SELECT count(*) FROM nsi_operacional.importacoes_legado_arquivos WHERE destino = 'promovido'")
        promovidos = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM nsi_operacional.lotes_legado WHERE destino = 'promovido'")
        snapshots_promovidos = cur.fetchone()[0]
        conn.rollback()
    assert (promovidos, snapshots_promovidos) == (0, 0)


def test_dsn_mascarada_nunca_contem_usuario_ou_senha(request):
    url = request.getfixturevalue("url_banco_teste")
    representacao_segura = mascarar_dsn(url)
    assert "@" not in representacao_segura
    assert "://" not in representacao_segura
