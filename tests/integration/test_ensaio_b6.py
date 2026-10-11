# -*- coding: utf-8 -*-
"""
NSI - tests/integration/test_ensaio_b6.py
(Sprint B, B6.2 - SPRINT-B6-ESPECIFICACAO-ENSAIO-DE-CORTE.md, Secoes 9, 17,
25 a 28; componentes C3, C7 e C8)

Testes de integracao REAIS contra PostgreSQL, EXCLUSIVAMENTE contra
nsi_test - nenhum teste conecta a nsi_ensaio (que so existe durante uma
rodada do ensaio) nem a nsi_dev. O que se comprova aqui, antes da B6.3:

  - todas as consultas de auditoria_b6_ensaio.sql executam em transacao
    READ ONLY e devolvem a forma esperada;
  - os destinos ESPERADOS pelo gerador sintetico (verificacao V5) sao
    exatamente os que o banco produz, lote a lote, com e sem fuso;
  - a quantificacao de "lotes em andamento" coincide com as evidencias de
    disparo aplicadas por fn_importar_lote_legado;
  - a auditoria detecta adulteracao e nao devolve valor pessoal;
  - o roteiro da Rodada S (gerar, inventariar, copiar, importar) funciona
    de ponta a ponta com o executor, e o gate recusa o cruzamento de
    ambiente e banco.

SOMENTE DADOS SINTETICOS. Todos os testes terminam em ROLLBACK:
  - os que leem tabelas rodam numa transacao do migrator de teste sob SET
    LOCAL ROLE nsi_eventos_owner (a identidade gravada e a do migrator);
  - os do executor conectam como nsi_importacao, com a transacao aberta
    pelo teste, de modo que as transacoes do executor viram savepoints.
Nenhuma promocao e confirmada (B5.2, item 17).
"""
import importlib.util
import json
from pathlib import Path

import psycopg
import pytest

from core import ensaio_corte as ec
from core import ensaio_sintetico as es
from core import importacao_legado as il
from tests.apoio_b5 import url_nsi_importacao, uuid_texto

pytestmark = pytest.mark.pg_integration

RAIZ = Path(__file__).resolve().parents[2]
FIXTURES = RAIZ / "tests" / "fixtures" / "legado"
SP = "America/Sao_Paulo"

CONSULTAS = (
    "a_catalogo", "a_concessoes", "a_objetos_invalidos", "a_revisao", "b_arquivos", "b_execucoes", "b_invariantes",
    "b_tabelas_que_devem_estar_vazias", "c_intervalo_de_criado_em", "c_lotes_em_andamento",
    "c_lotes_por_geracao_e_destino", "c_motivos", "c_registros_por_classificacao", "c_status_literal_por_geracao",
)


def _carregar(nome: str, arquivo: str):
    spec = importlib.util.spec_from_file_location(nome, RAIZ / "scripts" / arquivo)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


executor = _carregar("importar_legado_ensaio_b6", "importar_legado.py")
cli = _carregar("ensaio_corte_integracao", "ensaio_corte.py")


@pytest.fixture
def owner(request):
    """Conexao do migrator de teste: a revisao e lida como o migrator e o
    resto da transacao roda como nsi_eventos_owner. ROLLBACK ao final."""
    conn = psycopg.connect(request.getfixturevalue("url_banco_teste"))
    try:
        conn.revisao = cli.ler_revisao(conn)
        conn.execute("SET LOCAL ROLE nsi_eventos_owner")
        yield conn
    finally:
        conn.rollback()
        conn.close()


@pytest.fixture
def importacao():
    """Conexao como nsi_importacao, com a transacao ja aberta."""
    conn = psycopg.connect(url_nsi_importacao())
    try:
        conn.execute("SELECT 1")
        yield conn
    finally:
        conn.rollback()
        conn.close()


def _origem_sintetica(tmp_path, fuso, nome="rodada") -> tuple:
    """Instalacao sintetica -> inventario -> copia congelada do escopo, como
    nos passos S2 e S3. Devolve (origem congelada, esperado)."""
    instalacao = tmp_path / f"{nome}-instalacao"
    instalacao.mkdir()
    esperado = es.gerar_instalacao_sintetica(instalacao, FIXTURES, fuso)
    origem = tmp_path / f"{nome}-origem"
    origem.mkdir()
    assert ec.copiar_escopo(instalacao, origem, ec.inventariar(instalacao))["confere"] is True
    return origem, esperado


def _importar_pelas_funcoes(conn, origem, fuso) -> tuple:
    """Mesmo fluxo do executor (item 5 da B5.2), chamando as quatro funcoes
    diretamente: o executor exige session_user = nsi_importacao, e aqui a
    transacao e do migrator sob o owner, para que a auditoria leia o
    resultado na MESMA transacao."""
    importacao_id = uuid_texto()
    conn.execute("SELECT nsi_operacional.fn_iniciar_importacao_legado(%s, %s)", (importacao_id, fuso))
    entradas, retornos = [], {}
    for arquivo in il.enumerar_escopo(origem):
        if arquivo.tipo != il.TIPO_LOTE:
            entradas.append(il.entrada_de_tentativa_recusada(arquivo))
            continue
        retorno = conn.execute(
            "SELECT nsi_operacional.fn_importar_lote_legado(%s, %s, %s, %s)",
            (importacao_id, arquivo.caminho_relativo, il.ler_arquivo_do_escopo(origem, arquivo), arquivo.sha256),
        ).fetchone()[0]
        retornos[arquivo.caminho_relativo] = retorno
        entradas.append(il.entrada_de_lote(arquivo, retorno))
    manifesto = il.montar_manifesto(importacao_id, fuso, entradas)
    conn.execute("SELECT nsi_operacional.fn_concluir_importacao_legado(%s, %s, %s, %s)",
                 (importacao_id, manifesto, il.sha256_bytes(manifesto), len(retornos)))
    return importacao_id, retornos


def _auditar(conn) -> dict:
    return cli.executar_consultas(conn, conn.revisao)


def _da_execucao(obtido: list, esperado: list) -> list:
    """nsi_test guarda residuo sintetico de outros testes com commit real;
    a comparacao considera somente os caminhos desta origem."""
    caminhos = {e["caminho_relativo"] for e in esperado}
    return [a for a in obtido if a["caminho_relativo"] in caminhos]


# ============================================================
# C7 - as consultas executam em READ ONLY
# ============================================================

def test_todas_as_consultas_da_auditoria_executam_em_transacao_read_only(request):
    """Prioridade da B6.2: comprovar, antes da B6.3, que auditoria_b6_ensaio.sql
    roda inteira em modo somente leitura, como o migrator sob o owner."""
    with psycopg.connect(request.getfixturevalue("url_banco_teste")) as conn:
        conn.read_only = True
        revisao = cli.ler_revisao(conn)
        conn.execute("SET LOCAL ROLE nsi_eventos_owner")
        assert conn.execute("SHOW transaction_read_only").fetchone()[0] == "on"
        resultado = cli.executar_consultas(conn, revisao)
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
            conn.execute("DELETE FROM nsi_operacional.lotes_legado")
        conn.rollback()

    assert tuple(sorted(resultado)) == CONSULTAS
    assert resultado["a_revisao"] == {"banco": "nsi_test", "revisao": "0006"}
    assert {k: resultado["a_catalogo"][k] for k in ("tabelas", "funcoes", "funcoes_security_definer", "indices",
                                                    "constraints", "triggers")} == {
        "tabelas": 13, "funcoes": 21, "funcoes_security_definer": 15, "indices": 29, "constraints": 97, "triggers": 6}
    assert len(resultado["a_catalogo"]["impressao_digital"]) == 32
    assert set(resultado["a_objetos_invalidos"].values()) == {0}
    assert resultado["a_concessoes"]["concessoes_em_tabela"] == 0
    assert resultado["a_concessoes"]["execute_de_nsi_importacao"] == sorted(ec.QUATRO_FUNCOES_DE_IMPORTACAO)
    assert isinstance(resultado["b_arquivos"], list)
    for nome in CONSULTAS:
        if nome.startswith("c_") and nome != "c_intervalo_de_criado_em":
            assert isinstance(resultado[nome], list), nome


def test_revisao_e_lida_como_o_migrator_porque_o_owner_nao_alcanca_a_tabela_de_controle(owner):
    """Motivo de a revisao nao estar no arquivo SQL: a tabela de controle do
    Alembic pertence ao migrator."""
    assert owner.revisao == "0006"
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        owner.execute("SELECT version_num FROM nsi_operacional.alembic_version")


def test_impressao_digital_do_catalogo_e_a_mesma_lida_com_e_sem_o_owner(owner):
    """A referencia de nsi_test e lida pelo migrator, sem assumir o owner."""
    assert cli._impressao_do_catalogo_de_teste() == _auditar(owner)["a_catalogo"]["impressao_digital"]


# ============================================================
# C8 - verificacao V5: os destinos esperados sao os do banco
# ============================================================

@pytest.mark.parametrize("fuso", [SP, None, "UTC"])
def test_destinos_esperados_pelo_gerador_sao_os_que_o_banco_produz_lote_a_lote(owner, tmp_path, fuso):
    origem, esperado = _origem_sintetica(tmp_path, fuso)
    _, retornos = _importar_pelas_funcoes(owner, origem, fuso)

    assert len(retornos) == len(esperado)
    obtido = _da_execucao(_auditar(owner)["b_arquivos"], esperado)
    comparacao = es.comparar_com_esperado(esperado, obtido)
    assert comparacao["confere"] is True, comparacao
    assert {a["constraint_violada"] for a in obtido if a["motivo"] == "projecao_incompativel"} <= {
        "ck_registros_coleta_coerencia"}
    if fuso:
        assert any(a["destino"] == "promovido" and a["geracao"] == "a2" for a in obtido)
        assert any(a["destino"] == "promovido" and a["geracao"] == "a3" for a in obtido)
    else:
        assert not any(a["destino"] == "promovido" for a in obtido)


def test_segunda_passada_exercita_ja_importado_e_conflito_de_reimportacao(owner, tmp_path):
    """Os dois destinos que uma unica execucao sobre banco vazio nao alcanca."""
    origem, esperado = _origem_sintetica(tmp_path, SP)
    _, primeira = _importar_pelas_funcoes(owner, origem, SP)
    segunda_origem = tmp_path / "segunda"
    segunda_origem.mkdir()
    alterados = es.origem_da_segunda_passada(origem, segunda_origem)
    _, segunda = _importar_pelas_funcoes(owner, segunda_origem, SP)

    for caminho, retorno in segunda.items():
        antes = primeira[caminho]
        if caminho in alterados:
            assert (retorno["destino"], retorno["motivo"]) == ("recusado", "conflito_de_reimportacao")
        elif antes["destino"] in ("preservado", "promovido"):
            assert retorno["destino"] == "ja_importado"
            assert retorno["destino_original"] == antes["destino"]
            assert retorno["lote_id_promovido"] == antes["lote_id_promovido"]
        else:
            assert (retorno["destino"], retorno["motivo"]) == (antes["destino"], antes["motivo"])
    assert len(alterados) == 1 and len(segunda) == len(esperado)


# ============================================================
# Partes B e C da auditoria
# ============================================================

INVARIANTES_DA_IMPORTACAO = (
    "promovidos_de_geracao_anterior_a_a2", "registros_sem_identidade_com_uuid", "registros_identificados_sem_uuid",
    "registros_nao_promovidos_na_projecao", "lotes_promovidos_fora_do_estado_inicial",
    "registros_promovidos_com_versao_de_eventos", "snapshots_com_sha256_divergente",
)


def test_invariantes_da_importacao_valem_depois_de_uma_rodada_sintetica(owner, tmp_path):
    origem, _ = _origem_sintetica(tmp_path, SP)
    _importar_pelas_funcoes(owner, origem, SP)
    resultado = _auditar(owner)
    for nome in INVARIANTES_DA_IMPORTACAO:
        assert resultado["b_invariantes"][nome] == 0, nome
    assert any(a["motivo"] == "colisao_de_identidade" for a in resultado["b_arquivos"]), (
        "A rodada contem uma colisao legitima - que nao pode ser lida como registro indevido na projecao.")
    assert resultado["b_execucoes"]["conclusoes_com_total_divergente"] == 0
    assert resultado["b_execucoes"]["conclusoes_com_sha256_divergente"] == 0


_ADULTERACOES = {
    "snapshots_com_sha256_divergente":
        "UPDATE nsi_operacional.lotes_legado SET documento_bruto = documento_bruto || ' '::bytea "
        " WHERE snapshot_lote_id = (SELECT min(snapshot_lote_id::text)::uuid FROM nsi_operacional.lotes_legado "
        "                            WHERE importacao_id = %s)",
    "registros_promovidos_com_versao_de_eventos":
        "UPDATE nsi_operacional.registros_coleta SET versao_eventos_atual = 1 "
        " WHERE registro_coleta_id = (SELECT min(r.registro_coleta_id::text)::uuid "
        "   FROM nsi_operacional.registros_coleta r JOIN nsi_operacional.lotes_legado g ON g.lote_id_promovido = r.lote_id "
        "  WHERE g.importacao_id = %s)",
    "lotes_promovidos_fora_do_estado_inicial":
        "UPDATE nsi_operacional.lotes SET versao_eventos_atual = 2 "
        " WHERE lote_id = (SELECT min(lote_id_promovido::text)::uuid FROM nsi_operacional.lotes_legado "
        "                   WHERE importacao_id = %s AND destino = 'promovido')",
    "registros_nao_promovidos_na_projecao":
        "UPDATE nsi_operacional.registros_legado SET classificacao = 'legado_identificado_nao_promovido' "
        " WHERE (snapshot_lote_id, lista, posicao) = (SELECT g.snapshot_lote_id, g.lista, g.posicao "
        "   FROM nsi_operacional.registros_legado g JOIN nsi_operacional.lotes_legado s USING (snapshot_lote_id) "
        "  WHERE s.importacao_id = %s AND g.classificacao = 'legado_promovido' "
        "  ORDER BY g.snapshot_lote_id::text, g.lista, g.posicao LIMIT 1)",
    "promovidos_de_geracao_anterior_a_a2":
        "UPDATE nsi_operacional.lotes_legado SET geracao = 'a1' "
        " WHERE snapshot_lote_id = (SELECT min(snapshot_lote_id::text)::uuid FROM nsi_operacional.lotes_legado "
        "                            WHERE importacao_id = %s AND destino = 'promovido')",
}


@pytest.mark.parametrize("invariante", sorted(_ADULTERACOES))
def test_auditoria_detecta_adulteracao_feita_como_owner(owner, tmp_path, invariante):
    origem, _ = _origem_sintetica(tmp_path, SP)
    importacao_id, _ = _importar_pelas_funcoes(owner, origem, SP)
    antes = _auditar(owner)["b_invariantes"][invariante]
    cursor = owner.execute(_ADULTERACOES[invariante], (importacao_id,))
    assert cursor.rowcount == 1
    assert _auditar(owner)["b_invariantes"][invariante] == antes + 1


def test_avaliacao_reprova_nsi_test_pelos_motivos_certos_e_nunca_o_confunde_com_o_ensaio(owner, tmp_path):
    """Em nsi_test a avaliacao da auditoria precisa REPROVAR: o banco, as
    concessoes e a identidade nao sao os do ambiente de ensaio. Isso prova
    que a auditoria nao aprovaria, por engano, um banco que nao e o do
    ensaio."""
    origem, _ = _origem_sintetica(tmp_path, SP)
    _importar_pelas_funcoes(owner, origem, SP)
    resultado = _auditar(owner)
    avaliacao = ec.avaliar_auditoria(
        resultado, cli.BANCO_DE_ENSAIO, cli.PAPEIS_COM_ACESSO_AO_ENSAIO, "nsi_importacao", SP,
        resultado["a_catalogo"]["impressao_digital"])

    assert avaliacao["aprovada"] is False
    for codigo in ("a_banco_ou_revisao", "a_connect_fora_do_previsto", "a_usage_fora_do_previsto",
                   "b_identidade_tecnica"):
        assert codigo in avaliacao["divergencias"], codigo
    for codigo in ("a_objeto_invalido", "a_concessao_em_tabela", "a_execute_fora_do_previsto",
                   "a_catalogo_diferente_do_de_teste", "b_total_de_arquivos", "b_sha256_do_manifesto"):
        assert codigo not in avaliacao["divergencias"], codigo


def test_quantificacao_de_lotes_em_andamento_coincide_com_as_evidencias_do_banco(owner, tmp_path):
    """Secao 28, parte C: a consulta reaplica as evidencias de disparo do
    item 6.3. Ela precisa contar como 'com evidencia' exatamente os lotes que
    fn_importar_lote_legado deixou de promover por 'evidencia_de_disparo'."""
    def totais(resultado) -> tuple:
        linhas = resultado["c_lotes_em_andamento"]
        return (sum(l["lotes"] for l in linhas), sum(l["em_andamento"] for l in linhas),
                sum(l["com_evidencia_de_disparo"] for l in linhas))

    antes = _auditar(owner)
    origem, esperado = _origem_sintetica(tmp_path, SP)
    _importar_pelas_funcoes(owner, origem, SP)
    depois = _auditar(owner)

    no_snapshot = [e for e in esperado if e["destino"] in ("preservado", "promovido")]
    com_evidencia = [e for e in esperado if e["motivo"] == "evidencia_de_disparo"]
    assert len(com_evidencia) == 2
    lotes, em_andamento, evidencia = (d - a for d, a in zip(totais(depois), totais(antes)))
    assert (lotes, em_andamento, evidencia) == (len(no_snapshot), len(no_snapshot) - 2, 2)

    def status(resultado, literal) -> int:
        return sum(l["lotes"] for l in resultado["c_status_literal_por_geracao"] if l["status_literal"] == literal)

    assert status(depois, "disparado") - status(antes, "disparado") == 1, "O status legado e contado pelo valor literal."
    intervalo = depois["c_intervalo_de_criado_em"]
    assert intervalo["lotes_no_snapshot"] - antes["c_intervalo_de_criado_em"]["lotes_no_snapshot"] == len(no_snapshot)
    assert intervalo["lotes_na_projecao"] - antes["c_intervalo_de_criado_em"]["lotes_na_projecao"] == sum(
        1 for e in esperado if e["destino"] == "promovido")


def test_quantificacao_por_geracao_destino_e_motivo_bate_com_o_esperado(owner, tmp_path):
    def contagem(resultado, consulta, chaves) -> dict:
        return {tuple(l[c] for c in chaves): l["lotes"] for l in resultado[consulta]}

    antes = _auditar(owner)
    origem, esperado = _origem_sintetica(tmp_path, SP)
    _importar_pelas_funcoes(owner, origem, SP)
    depois = _auditar(owner)

    resumo = es.resumir_esperado(esperado)
    por_geracao = contagem(depois, "c_lotes_por_geracao_e_destino", ("geracao", "destino"))
    por_geracao_antes = contagem(antes, "c_lotes_por_geracao_e_destino", ("geracao", "destino"))
    for geracao, destinos in resumo["por_geracao_e_destino"].items():
        chave_da_geracao = None if geracao == "nao_classificado" else geracao
        for destino, quantidade in destinos.items():
            chave = (chave_da_geracao, destino)
            assert por_geracao.get(chave, 0) - por_geracao_antes.get(chave, 0) == quantidade, chave

    motivos = contagem(depois, "c_motivos", ("destino", "motivo"))
    motivos_antes = contagem(antes, "c_motivos", ("destino", "motivo"))
    for destino, esperados in (("preservado", resumo["motivos_de_nao_promocao"]), ("recusado", resumo["motivos_de_recusa"])):
        for motivo, quantidade in esperados.items():
            assert motivos.get((destino, motivo), 0) - motivos_antes.get((destino, motivo), 0) == quantidade, motivo


# ============================================================
# Privacidade (Secao 28, parte D)
# ============================================================

def test_auditoria_nao_devolve_valor_pessoal_e_a_amostra_fica_so_em_memoria(owner, tmp_path):
    origem, _ = _origem_sintetica(tmp_path, SP)
    _importar_pelas_funcoes(owner, origem, SP)
    resultado = _auditar(owner)
    valores = cli.amostrar_valores_pessoais(owner)

    assert any(es.NOME_SINTETICO in v for v in valores), "A amostra precisa conter valor pessoal, ou nada prova."
    assert any(v.startswith(es.PREFIXO_TELEFONE_SINTETICO) for v in valores)
    texto = json.dumps(resultado, ensure_ascii=False)
    for valor in valores + list(es.VALORES_PESSOAIS_SINTETICOS):
        assert valor not in texto, "A saida da auditoria nunca contem valor pessoal."

    evidencias = tmp_path / "evidencias"
    evidencias.mkdir()
    ec.gravar_evidencia(evidencias, "E10_auditoria.json", resultado)
    assert ec.varrer_evidencias(evidencias, valores)["sem_valor_pessoal"] is True
    ec.gravar_evidencia(evidencias, "vazamento_simulado.json", {"x": valores[0]})
    varredura = ec.varrer_evidencias(evidencias, valores)
    assert varredura["arquivos_com_valor_pessoal"] == ["vazamento_simulado.json"]
    assert valores[0] not in json.dumps(varredura, ensure_ascii=False)


# ============================================================
# Roteiro da Rodada S com o executor (como nsi_importacao)
# ============================================================

@pytest.mark.parametrize("fuso", [SP, None])
def test_executor_sobre_a_origem_sintetica_confere_com_o_esperado(importacao, tmp_path, fuso):
    """Verificacao V5 pela forma agregada do relatorio do executor."""
    origem, esperado = _origem_sintetica(tmp_path, fuso)
    relatorio = executor.executar_importacao(importacao, origem, fuso)
    resumo = es.resumir_esperado(esperado)

    assert relatorio["lotes"] == resumo["lotes"]
    assert relatorio["por_geracao_e_destino"] == resumo["por_geracao_e_destino"]
    assert relatorio["motivos_de_nao_promocao"] == resumo["motivos_de_nao_promocao"]
    assert relatorio["motivos_de_recusa"] == resumo["motivos_de_recusa"]
    assert relatorio["tentativas_recusadas_somente_manifesto"] == 2
    assert relatorio["paridade"]["aprovada"] is True
    assert relatorio["paridade"]["contagens"]["evoluidos_no_fluxo_novo"] == 0
    texto = json.dumps(relatorio, ensure_ascii=False)
    for valor in es.VALORES_PESSOAIS_SINTETICOS:
        assert valor not in texto


def test_roteiro_da_rodada_s_pela_linha_de_comando_e_pelo_executor(importacao, tmp_path, monkeypatch, capsys):
    """Passos S2 a S5: gerar a instalacao sintetica, provar a quiescencia,
    copiar o escopo, levantar a estrutura e importar a copia congelada."""
    area = tmp_path / "area"
    area.mkdir()
    monkeypatch.setattr(cli.Config, "NSI_ENSAIO_DIR", str(area))
    monkeypatch.setattr(cli.Config, "DATA_DIR", tmp_path / "data")

    def comando(*argumentos) -> dict:
        codigo = cli.main(list(argumentos))
        saida = json.loads(capsys.readouterr().out)
        assert codigo == cli.SAIDA_SUCESSO, saida
        return saida

    comando("preparar", "--ensaio-id", "s1")
    gerado = comando("gerar-sintetico", "--ensaio-id", "s1", "--fuso", SP, "--lotes-extras", "3")
    instalacao = str(area / "s1" / es.SUBDIRETORIO_DA_INSTALACAO_SINTETICA)
    for rotulo in ("I1", "I2"):
        comando("inventario", "--ensaio-id", "s1", "--rotulo", rotulo, "--diretorio", instalacao)
    assert comando("comparar", "--ensaio-id", "s1", "--a", "I1", "--b", "I2")["identicos"] is True
    assert comando("copiar", "--ensaio-id", "s1", "--instalacao", instalacao, "--referencia", "I1")["confere"] is True
    levantamento = comando("levantamento", "--ensaio-id", "s1")
    assert levantamento["lotes_com_divergencia"] == sum(gerado["motivos_de_recusa"].values())

    origem = area / "s1" / "origem"
    relatorio = executor.executar_importacao(importacao, origem, SP)
    esperado = json.loads((area / "s1" / "evidencias" / "esperado.json").read_bytes())
    assert relatorio["por_geracao_e_destino"] == esperado["resumo"]["por_geracao_e_destino"] == gerado["por_geracao_e_destino"]
    assert relatorio["paridade"]["aprovada"] is True

    # A origem congelada e somente leitura e e a que o ambiente de ensaio exige.
    monkeypatch.setattr(executor.Config, "NSI_ENSAIO_DIR", str(area))
    monkeypatch.setattr(executor.Config, "DATA_DIR", tmp_path / "data")
    assert executor.validar_origem_do_ambiente(origem, "ensaio").name == "origem"
    with pytest.raises(ec.AreaDeEnsaioInvalida):
        executor.validar_origem_do_ambiente(instalacao, "ensaio")


def test_gate_recusa_o_ambiente_de_ensaio_numa_conexao_de_nsi_test(importacao, tmp_path, monkeypatch):
    """Cruzamento de ambiente e banco: com ambiente 'ensaio', uma conexao
    real a nsi_test e recusada antes de qualquer leitura da origem."""
    monkeypatch.setattr(executor, "enumerar_escopo", lambda origem: pytest.fail("a origem foi lida"))
    monkeypatch.setattr(executor, "validar_origem_do_ambiente", lambda *a: pytest.fail("a origem foi validada"))
    with pytest.raises(executor.IdentidadeNaoComprovada) as exc_info:
        executor.executar_importacao(importacao, tmp_path, SP, None, "ensaio")
    assert str(exc_info.value) == "banco nao permitido - esperado nsi_ensaio"
    with pytest.raises(executor.IdentidadeNaoComprovada):
        executor.comprovar_identidade(importacao, "development")
    executor.comprovar_identidade(importacao, "test")


def test_auditar_recusa_conexao_que_nao_seja_o_migrator_de_ensaio(request):
    """O comando 'auditar' so roda como nsi_ensaio_migrator em nsi_ensaio: a
    identidade real do migrator de teste, em nsi_test, e recusada."""
    with psycopg.connect(request.getfixturevalue("url_banco_teste")) as conn:
        identidade = conn.execute(
            "SELECT current_database(), inet_server_addr()::text, inet_server_port(), session_user").fetchone()
        conn.rollback()
    assert identidade[0] == "nsi_test" and identidade[3] == "nsi_test_migrator"
    with pytest.raises(cli.EnsaioRecusado) as exc_info:
        cli.validar_identidade_da_auditoria(*identidade)
    assert str(exc_info.value) == "banco nao permitido - esperado nsi_ensaio"
