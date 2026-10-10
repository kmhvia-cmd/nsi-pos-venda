# -*- coding: utf-8 -*-
"""
NSI - tests/unit/test_migration_0006_estatico.py
(Sprint B, B5.4 - ADR-010; Especificacao Tecnica, B5.2, itens 5.1, 10.4 e
10.5)

Testes ESTATICOS da migration 0006 - Python puro, sem banco:

  - o downgrade carrega a definicao de fn_criar_claim do proprio arquivo da
    0003, sem copia-la (item 10.5);
  - as quatro funcoes de importacao nunca referenciam comandos_idempotentes
    e nunca escrevem em evento (item 10.4: garantia por construcao);
  - forma comum das quatro funcoes (item 5.1);
  - 0001 a 0005 nao sao tocadas pela 0006.
"""
import ast
import importlib.util
import re
from pathlib import Path

import pytest

DIRETORIO_VERSOES = Path(__file__).resolve().parents[2] / "migrations" / "versions"
ARQUIVO_0006 = DIRETORIO_VERSOES / "0006_importacao_legado.py"
ARQUIVO_0003 = DIRETORIO_VERSOES / "0003_seis_funcoes_claim.py"

FUNCOES_DE_IMPORTACAO = ("fn_iniciar_importacao_legado", "fn_importar_lote_legado",
                         "fn_concluir_importacao_legado", "fn_verificar_paridade_legado")


def _carregar(caminho: Path):
    spec = importlib.util.spec_from_file_location(f"migration_{caminho.stem}_estatico", caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _sql_de_upgrade() -> list:
    """Todas as strings SQL literais passadas a op.execute() em upgrade()."""
    arvore = ast.parse(ARQUIVO_0006.read_text(encoding="utf-8"))
    upgrade = next(n for n in arvore.body if isinstance(n, ast.FunctionDef) and n.name == "upgrade")
    return [no.value for no in ast.walk(upgrade) if isinstance(no, ast.Constant) and isinstance(no.value, str)]


def _corpo(nome_funcao: str) -> str:
    candidatos = [s for s in _sql_de_upgrade()
                  if re.search(rf"CREATE (OR REPLACE )?FUNCTION nsi_operacional\.{nome_funcao}\(", s)]
    assert len(candidatos) == 1, nome_funcao
    return candidatos[0]


def _sem_comentarios(sql: str) -> str:
    return "\n".join(linha.split("--", 1)[0] for linha in sql.splitlines())


def test_revisao_e_encadeamento():
    migration = _carregar(ARQUIVO_0006)
    assert (migration.revision, migration.down_revision) == ("0006", "0005")


def test_downgrade_le_os_tres_comandos_de_fn_criar_claim_do_arquivo_da_0003():
    comandos = _carregar(ARQUIVO_0006)._comandos_fn_criar_claim_da_0003()
    fonte_0003 = ARQUIVO_0003.read_text(encoding="utf-8")

    assert len(comandos) == 3
    assert comandos[0].lstrip().startswith("CREATE FUNCTION nsi_operacional.fn_criar_claim(")
    assert comandos[1] == "REVOKE ALL ON FUNCTION nsi_operacional.fn_criar_claim(UUID, TEXT, TEXT, TEXT) FROM PUBLIC"
    assert comandos[2] == ("GRANT EXECUTE ON FUNCTION nsi_operacional.fn_criar_claim(UUID, TEXT, TEXT, TEXT) "
                           "TO nsi_aplicacao")
    assert comandos[0] in fonte_0003, "O CREATE FUNCTION restaurado e, byte a byte, o texto do arquivo da 0003."
    assert "registros_legado" not in comandos[0]
    assert "fn_registrar_heartbeat" not in comandos[0], "Somente fn_criar_claim - nenhuma outra funcao da 0003."


def test_definicao_da_0003_nao_e_copiada_dentro_da_0006():
    """O arquivo da 0006 contem uma unica definicao de fn_criar_claim (a
    nova); a antiga nunca e copiada a mao."""
    fonte = ARQUIVO_0006.read_text(encoding="utf-8")
    assert len(re.findall(r"FUNCTION nsi_operacional\.fn_criar_claim\(\n", fonte)) == 1
    assert "CREATE OR REPLACE FUNCTION nsi_operacional.fn_criar_claim(" in fonte


def test_nova_fn_criar_claim_muda_somente_a_recusa_do_legado():
    """Item 10.5: mesmo envelope de idempotencia e mesmos efeitos; a unica
    diferenca e a consulta a registros_legado, no MESMO comando que grava o
    claim, e a recusa nova."""
    nova = _corpo("fn_criar_claim")
    antiga = _carregar(ARQUIVO_0006)._comandos_fn_criar_claim_da_0003()[0]

    for trecho in (
        "LANGUAGE plpgsql", "SECURITY DEFINER", "SET search_path = pg_catalog, nsi_operacional, pg_temp",
        "ON CONFLICT (comando, aggregate_id, chave_idempotencia) DO NOTHING",
        "RAISE EXCEPTION 'conflito_de_idempotencia' USING ERRCODE = '22023'",
        "WHERE nsi_operacional.claims.estado = 'liberado'",
        "'claim_criado'", "'registro_ocupado'",
        "p_registro_coleta_id  UUID", "p_token_hash          TEXT",
        "p_chave_idempotencia  TEXT", "p_payload_hash        TEXT",
    ):
        assert trecho in antiga and trecho in nova, trecho

    assert "registro_legado_nao_promovido" in nova and "registro_legado_nao_promovido" not in antiga
    assert "legado_identificado_nao_promovido" in nova

    # A leitura de registros_legado e o INSERT em claims estao no mesmo comando.
    comando = nova[nova.index("WITH legado AS"):nova.index("INTO v_legado_nao_promovido, v_versao;")]
    assert "nsi_operacional.registros_legado" in comando
    assert "INSERT INTO nsi_operacional.claims" in comando
    assert comando.count(";") == 0, "Um unico comando SQL."
    assert _sem_comentarios(nova).count("nsi_operacional.registros_legado") == 1


@pytest.mark.parametrize("funcao", FUNCOES_DE_IMPORTACAO)
def test_funcoes_de_importacao_tem_a_forma_comum(funcao):
    corpo = _corpo(funcao)
    for trecho in ("RETURNS JSONB", "LANGUAGE plpgsql", "SECURITY DEFINER",
                   "SET search_path = pg_catalog, nsi_operacional, pg_temp"):
        assert trecho in corpo, trecho
    assert "current_user" not in _sem_comentarios(corpo), "A identidade do chamador e sempre session_user."


@pytest.mark.parametrize("funcao", FUNCOES_DE_IMPORTACAO)
def test_funcoes_de_importacao_nunca_referenciam_comandos_idempotentes(funcao):
    """Item 10.4: a ausencia de recibos gravados pela importacao e garantida
    por construcao."""
    assert "comandos_idempotentes" not in _corpo(funcao)


@pytest.mark.parametrize("funcao", FUNCOES_DE_IMPORTACAO)
def test_funcoes_de_importacao_nunca_escrevem_em_evento(funcao):
    """ADR-010, Principio 1: nenhum dos cinco eventos da ADR-009 e gravado
    pela importacao. Somente a paridade LE os logs de evento."""
    corpo = _sem_comentarios(_corpo(funcao))
    assert not re.search(r"(INSERT INTO|UPDATE|DELETE FROM)\s+nsi_operacional\.eventos_", corpo)
    if funcao != "fn_verificar_paridade_legado":
        assert "nsi_operacional.eventos_" not in corpo
    assert "eventos_claim" not in corpo


def test_paridade_nao_escreve_em_tabela_nenhuma():
    corpo = _sem_comentarios(_corpo("fn_verificar_paridade_legado"))
    assert "STABLE" in corpo
    assert not re.search(r"\b(INSERT INTO|UPDATE|DELETE FROM|LOCK TABLE)\b", corpo)


def test_somente_a_importacao_de_lote_escreve_no_snapshot_e_na_projecao():
    escritas = re.compile(r"INSERT INTO\s+nsi_operacional\.(\w+)")
    assert set(escritas.findall(_sem_comentarios(_corpo("fn_iniciar_importacao_legado")))) == {"importacoes_legado"}
    assert set(escritas.findall(_sem_comentarios(_corpo("fn_concluir_importacao_legado")))) == {
        "importacoes_legado_conclusoes"}
    assert set(escritas.findall(_sem_comentarios(_corpo("fn_importar_lote_legado")))) == {
        "lotes", "registros_coleta", "lotes_legado", "registros_legado", "importacoes_legado_arquivos"}
    for funcao in FUNCOES_DE_IMPORTACAO:
        assert not re.search(r"\b(UPDATE|DELETE FROM)\s+nsi_operacional\.", _sem_comentarios(_corpo(funcao))), (
            f"{funcao}: nenhuma funcao de importacao altera ou remove linha ja gravada."
        )


def test_bloqueios_do_item_12_e_do_item_10_5():
    importar = _sem_comentarios(_corpo("fn_importar_lote_legado"))
    concluir = _sem_comentarios(_corpo("fn_concluir_importacao_legado"))
    assert "FOR SHARE" in importar and "FOR UPDATE" not in importar
    assert "FOR UPDATE" in concluir
    assert "LOCK TABLE nsi_operacional.claims IN SHARE ROW EXCLUSIVE MODE" in importar
    assert importar.index("FROM nsi_operacional.lotes_legado") < importar.index("LOCK TABLE") < importar.index(
        "FROM nsi_operacional.claims"), "Reimportacao antes do bloqueio; verificacao de claim depois dele."


def test_matriz_de_execute_declarada_na_migration():
    sql = _sql_de_upgrade()
    concessoes = [s for s in sql if s.startswith("GRANT ")]
    assert len(concessoes) == 4
    assert all(s.rstrip().endswith("TO nsi_importacao") and s.startswith("GRANT EXECUTE ON FUNCTION") for s in concessoes)
    revogacoes_de_public = [s for s in sql if s.startswith("REVOKE ALL ON FUNCTION") and s.rstrip().endswith("FROM PUBLIC")]
    assert len(revogacoes_de_public) == 4, "Uma por funcao de importacao."
    assert ('f"REVOKE ALL ON FUNCTION nsi_operacional.fn_bloquear_alteracao_{tabela}() FROM PUBLIC"'
            in ARQUIVO_0006.read_text(encoding="utf-8")), "E a das tres funcoes de trigger, no laco."
    assert not any("GRANT" in s and " ON TABLE " in s for s in sql), "Nenhuma concessao em tabela."


def test_migration_nunca_cria_altera_ou_remove_role():
    fonte = _sem_comentarios(ARQUIVO_0006.read_text(encoding="utf-8"))
    assert not re.search(r"\b(CREATE|ALTER|DROP)\s+ROLE\b", fonte)
    assert "pg_catalog.pg_roles WHERE rolname = 'nsi_importacao'" in fonte


def test_nenhuma_mensagem_de_erro_das_funcoes_interpola_valor():
    """Item 15: mensagens fixas, sem DETAIL."""
    for funcao in FUNCOES_DE_IMPORTACAO + ("fn_criar_claim",):
        corpo = _sem_comentarios(_corpo(funcao))
        mensagens = set(re.findall(r"RAISE EXCEPTION '([^']*)'", corpo))
        assert mensagens <= {"entrada_estrutural_invalida", "conflito_de_idempotencia",
                             "violacao_de_constraint", "invariante_violada"}, funcao
        assert "DETAIL" not in corpo and "HINT" not in corpo, funcao
