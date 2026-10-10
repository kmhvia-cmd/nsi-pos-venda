# -*- coding: utf-8 -*-
"""
NSI - tests/integration/test_executor_importacao_legado.py
(Sprint B, B5.5 - ADR-010; Especificacao Tecnica, B5.2, itens 5, 14 e 17)

Testes de integracao REAIS contra PostgreSQL, exclusivamente contra
nsi_test, do executor scripts/importar_legado.py, de ponta a ponta:
gate de identidade, enumeracao, abertura, um lote por transacao, manifesto,
conclusao, paridade (a do banco e a conferencia da origem) e relatorio sem
valor pessoal.

SOMENTE DADOS SINTETICOS: tests/fixtures/legado/ e arvores montadas em
tmp_path com os construtores de tests/apoio_b5.py - nunca data/.

Conexao: COMO nsi_importacao (TEST_DATABASE_URL_NSI_IMPORTACAO - B5.2, item
19.6). Sem a credencial, os testes sao pulados em desenvolvimento comum e
FALHAM no comando de aceite (NSI_REQUIRE_PG_TESTS=1).

PROMOCAO SEM COMMIT (B5.2, item 17): o executor roda cada chamada em
'with conexao.transaction()'. Aqui a conexao ja esta numa transacao aberta
pelo teste, de modo que cada bloco vira um savepoint dela, e o teste
termina em ROLLBACK - o fluxo completo, inclusive a promocao das geracoes
a2 e a3, e exercitado sem confirmar nada.

DIVULGACAO DE RESIDUO INTENCIONAL: test_main_executa_e_confirma_somente_
lotes_nao_promoviveis e os demais testes de main() exercitam o
caminho real de producao (autocommit, uma transacao por lote, COMMIT real)
com origens que contem somente lotes NAO promoviveis; execucao, conclusao,
snapshot e registro tecnico ficam como residuo sintetico em nsi_test,
nunca em nsi_dev, ate o downgrade da 0006.
"""
import importlib.util
import json
from pathlib import Path

import psycopg
import pytest

from config import Config, resolver_url_banco_papel
from tests.apoio_b5 import (
    assert_sem_valor_pessoal,
    caminho_do_lote,
    doc_a1,
    doc_a2,
    doc_a3,
    doc_anterior_a1,
    serializar,
    sha256_hex,
    url_nsi_importacao,
    uuid_texto,
)

pytestmark = pytest.mark.pg_integration

RAIZ = Path(__file__).resolve().parents[2]
FIXTURES = RAIZ / "tests" / "fixtures" / "legado"
FUSO = "America/Sao_Paulo"
TENTATIVA = "correcoes_rejeitadas/2026-01-09/3f0c1b7e-5a44-4c0e-9d0a-6f6f1f0a9b01.json"


def _carregar_executor():
    spec = importlib.util.spec_from_file_location("importar_legado_integracao", RAIZ / "scripts" / "importar_legado.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


executor = _carregar_executor()


@pytest.fixture
def conexao():
    """Conexao como nsi_importacao, com uma transacao ja aberta: as
    transacoes do executor viram savepoints, e tudo e revertido ao final."""
    conn = psycopg.connect(url_nsi_importacao())
    try:
        conn.execute("SELECT 1")
        assert conn.info.transaction_status == psycopg.pq.TransactionStatus.INTRANS
        yield conn
    finally:
        conn.rollback()
        conn.close()


def _montar_origem(raiz: Path, documentos=(), brutos=None, tentativas=()) -> Path:
    """Origem sintetica: um lotes/<lote_id>/lote.json por documento, arquivos
    brutos por caminho relativo, tentativas recusadas e ruido fora do
    escopo."""
    raiz.mkdir(parents=True, exist_ok=True)
    for documento in documentos:
        caminho = raiz / caminho_do_lote(documento["lote_id"])
        caminho.parent.mkdir(parents=True)
        caminho.write_bytes(serializar(documento))
    for relativo, conteudo in (brutos or {}).items():
        caminho = raiz / relativo
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_bytes(conteudo)
    for relativo in tentativas:
        caminho = raiz / relativo
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_bytes(b'{"motivo": "codigo_tecnico_invalido"}')
    (raiz / "respostas").mkdir(exist_ok=True)
    (raiz / "respostas" / "5511987650001.json").write_bytes(b"{}")
    (raiz / "saida_motor.json").write_bytes(b"{}")
    return raiz


def _paridade_do_banco(conexao, importacao_id: str) -> dict:
    with conexao.transaction():
        return conexao.execute(
            "SELECT nsi_operacional.fn_verificar_paridade_legado(%s)", (importacao_id,)).fetchone()[0]


# ============================================================
# Gate de identidade (item 5, passo 1)
# ============================================================

def test_gate_aprova_a_conexao_real_de_nsi_importacao(conexao):
    executor.comprovar_identidade(conexao)


@pytest.mark.parametrize("papel", ["nsi_aplicacao", "nsi_expiracao", "nsi_operador_restrito"])
def test_gate_recusa_conexao_de_outra_role_antes_de_qualquer_chamada(papel, tmp_path, monkeypatch):
    monkeypatch.setattr(executor, "enumerar_escopo", lambda origem: pytest.fail("a origem foi lida apos o gate falhar"))
    conn = psycopg.connect(resolver_url_banco_papel(papel, "test"))
    try:
        with pytest.raises(executor.IdentidadeNaoComprovada) as exc_info:
            executor.executar_importacao(conn, _montar_origem(tmp_path / "origem", [doc_a1()]), FUSO)
        assert "usuario da sessao" in str(exc_info.value)
        assert papel not in str(exc_info.value)
    finally:
        conn.rollback()
        conn.close()


def test_gate_recusa_o_migrator_de_teste(request, tmp_path):
    """Os migrators aplicam a 0006; nunca executam importacao (item 4)."""
    conn = psycopg.connect(request.getfixturevalue("url_banco_teste"))
    try:
        with pytest.raises(executor.IdentidadeNaoComprovada):
            executor.executar_importacao(conn, _montar_origem(tmp_path / "origem", [doc_a1()]), FUSO)
    finally:
        conn.rollback()
        conn.close()


def test_gate_usa_session_user_e_nao_current_user(request):
    """SET ROLE nao engana o gate: a identidade e a da sessao."""
    conn = psycopg.connect(request.getfixturevalue("url_banco_teste"))
    try:
        conn.execute("SET LOCAL ROLE nsi_eventos_owner")
        with pytest.raises(executor.IdentidadeNaoComprovada):
            executor.comprovar_identidade(conn)
    finally:
        conn.rollback()
        conn.close()


def test_origem_igual_ao_diretorio_de_dados_e_recusada_sem_abrir_execucao(conexao, monkeypatch):
    monkeypatch.setattr(executor, "enumerar_escopo", lambda origem: pytest.fail("a origem foi lida"))
    with pytest.raises(executor.OrigemInvalida):
        executor.executar_importacao(conexao, Config.DATA_DIR, FUSO, uuid_texto())


# ============================================================
# Fluxo completo com as fixtures (ROLLBACK)
# ============================================================

def test_fluxo_completo_com_as_fixtures_das_quatro_geracoes(conexao):
    relatorio = executor.executar_importacao(conexao, FIXTURES, FUSO)

    assert relatorio["fuso_declarado"] == FUSO
    assert relatorio["lotes"] == 8
    assert relatorio["tentativas_recusadas_somente_manifesto"] == 1
    assert relatorio["arquivos_no_manifesto"] == 9
    assert relatorio["por_geracao_e_destino"] == {
        "anterior_a1": {"preservado": 1},
        "a1": {"preservado": 1},
        "a2": {"promovido": 1},
        "a3": {"promovido": 1},
        "formato_desconhecido": {"recusado": 2},
        "nao_classificado": {"recusado": 2},
    }
    assert relatorio["motivos_de_nao_promocao"] == {"geracao_nao_promovivel": 2}
    assert relatorio["motivos_de_recusa"] == {
        "documento_ilegivel": 1, "formato_desconhecido": 2, "identidade_divergente": 1}

    paridade = relatorio["paridade"]
    assert paridade["aprovada"] is True
    assert (paridade["concluida"], paridade["banco_aprovada"]) == (True, True)
    assert (paridade["origem_confere"], paridade["manifesto_completo"]) == (True, True)
    assert paridade["registro_tecnico"] == {
        "manifesto_sha256_confere": True, "manifesto_cabecalho_confere": True, "manifesto_sem_lote_orfao": True}
    assert paridade["contagens"] == {
        "lotes": 8, "preservado": 2, "promovido": 2, "recusado": 4, "ja_importado": 0,
        "evoluidos_no_fluxo_novo": 0, "lotes_reprovados": 0}

    # O manifesto gravado e o que o modulo de producao monta; o banco
    # confere cada linha contra ele (paridade acima).
    assert len(relatorio["manifesto_sha256"]) == 64


def test_relatorio_nao_contem_valor_pessoal(conexao):
    relatorio = executor.executar_importacao(conexao, FIXTURES, FUSO)
    texto = json.dumps(relatorio, ensure_ascii=False)
    assert_sem_valor_pessoal(texto, "relatorio do executor")
    for arquivo in FIXTURES.glob("lotes/*/lote.json"):
        for registro_id in (r.get("registro_coleta_id") for lista in ("clientes", "clientes_invalidos")
                            for r in _ler_json(arquivo).get(lista, []) if isinstance(r, dict)):
            assert registro_id is None or registro_id not in texto


def _ler_json(caminho: Path) -> dict:
    try:
        return json.loads(caminho.read_bytes())
    except ValueError:
        return {}


def test_execucao_sem_declaracao_de_fuso_processa_tudo_e_nao_promove_nada(conexao):
    """Item 5: a ausencia de fuso nao impede a execucao; nenhum lote e
    promovido, e o relatorio registra o motivo."""
    relatorio = executor.executar_importacao(conexao, FIXTURES)

    assert relatorio["fuso_declarado"] is None
    assert relatorio["por_geracao_e_destino"]["a2"] == {"preservado": 1}
    assert relatorio["por_geracao_e_destino"]["a3"] == {"preservado": 1}
    assert relatorio["motivos_de_nao_promocao"] == {"fuso_nao_declarado": 2, "geracao_nao_promovivel": 2}
    assert relatorio["paridade"]["contagens"]["promovido"] == 0
    assert relatorio["paridade"]["aprovada"] is True


def test_arquivos_fora_do_escopo_nao_entram_na_execucao(conexao, tmp_path):
    origem = _montar_origem(tmp_path / "origem", [doc_a1()], tentativas=[TENTATIVA])
    relatorio = executor.executar_importacao(conexao, origem, FUSO)
    assert (relatorio["lotes"], relatorio["tentativas_recusadas_somente_manifesto"]) == (1, 1)
    assert relatorio["arquivos_no_manifesto"] == 2, "respostas/ e saida_motor.json nunca entram no manifesto."
    assert relatorio["paridade"]["contagens"]["lotes"] == 1, "A tentativa recusada nao tem linha no registro tecnico."
    assert relatorio["paridade"]["aprovada"] is True


def test_origem_sem_nenhum_arquivo_do_escopo_e_concluida_vazia(conexao, tmp_path):
    relatorio = executor.executar_importacao(conexao, _montar_origem(tmp_path / "origem"), FUSO)
    assert (relatorio["lotes"], relatorio["arquivos_no_manifesto"]) == (0, 0)
    assert relatorio["paridade"]["aprovada"] is True


def test_promocao_de_ponta_a_ponta_pelo_executor(conexao, tmp_path):
    documentos = [doc_a2(), doc_a3(), doc_a2(criado_em="2018-11-04T00:30:00")]
    relatorio = executor.executar_importacao(conexao, _montar_origem(tmp_path / "origem", documentos), FUSO)
    assert relatorio["por_geracao_e_destino"] == {"a2": {"preservado": 1, "promovido": 1}, "a3": {"promovido": 1}}
    assert relatorio["motivos_de_nao_promocao"] == {"m0_inexistente_ou_ambiguo": 1}
    assert relatorio["paridade"]["aprovada"] is True


def test_constraint_violada_aparece_no_relatorio_so_pelo_nome(conexao, tmp_path):
    documento = doc_a2()
    documento["clientes"][0]["telefone"] = "11987650001"
    relatorio = executor.executar_importacao(conexao, _montar_origem(tmp_path / "origem", [documento]), FUSO)
    assert relatorio["motivos_de_nao_promocao"] == {"projecao_incompativel": 1}
    assert relatorio["constraints_violadas"] == {"ck_registros_coleta_coerencia": 1}
    assert_sem_valor_pessoal(json.dumps(relatorio, ensure_ascii=False), "relatorio com projecao incompativel")


# ============================================================
# Retomada, reimportacao e idempotencia
# ============================================================

def test_retomada_de_execucao_aberta_conclui_com_os_lotes_ja_importados_em_replay(conexao, tmp_path):
    """Execucao interrompida depois de um lote: a retomada reapresenta o
    lote ja registrado (replay, sem nova escrita), importa os demais e
    conclui."""
    documentos = [doc_anterior_a1(), doc_a1(), doc_a2()]
    origem = _montar_origem(tmp_path / "origem", documentos, tentativas=[TENTATIVA])
    importacao_id = uuid_texto()
    caminho = caminho_do_lote(documentos[1]["lote_id"])
    conteudo = (origem / caminho).read_bytes()
    with conexao.transaction():
        conexao.execute("SELECT nsi_operacional.fn_iniciar_importacao_legado(%s, %s)", (importacao_id, FUSO))
        conexao.execute("SELECT nsi_operacional.fn_importar_lote_legado(%s, %s, %s, %s)",
                        (importacao_id, caminho, conteudo, sha256_hex(conteudo)))

    relatorio = executor.executar_importacao(conexao, origem, FUSO, importacao_id.upper())
    assert relatorio["importacao_id"] == importacao_id
    assert relatorio["por_geracao_e_destino"] == {
        "anterior_a1": {"preservado": 1}, "a1": {"preservado": 1}, "a2": {"promovido": 1}}
    assert relatorio["paridade"]["aprovada"] is True
    assert relatorio["paridade"]["contagens"]["ja_importado"] == 0, "O lote ja registrado e replay, nao reimportacao."


def test_execucao_ja_concluida_nunca_e_retomada(conexao, tmp_path, monkeypatch):
    """Item 12: execucao concluida nao aceita novos lotes."""
    origem = _montar_origem(tmp_path / "origem", [doc_a1()])
    importacao_id = uuid_texto()
    executor.executar_importacao(conexao, origem, FUSO, importacao_id)

    monkeypatch.setattr(executor, "ler_arquivo_do_escopo", lambda *a: pytest.fail("um lote foi reapresentado"))
    with pytest.raises(executor.ExecucaoAbortada) as exc_info:
        executor.executar_importacao(conexao, origem, FUSO, importacao_id)
    assert exc_info.value.motivo == "execucao_ja_concluida"
    assert _paridade_do_banco(conexao, importacao_id)["aprovada"] is True, "A execucao concluida fica intocada."


def test_nova_execucao_sobre_a_mesma_origem_resulta_em_ja_importado(conexao, tmp_path):
    origem = _montar_origem(tmp_path / "origem", [doc_a1(), doc_a2()])
    primeiro = executor.executar_importacao(conexao, origem, FUSO)
    segundo = executor.executar_importacao(conexao, origem, FUSO)

    assert segundo["importacao_id"] != primeiro["importacao_id"]
    assert segundo["por_geracao_e_destino"] == {"a1": {"ja_importado": 1}, "a2": {"ja_importado": 1}}
    assert segundo["paridade"]["aprovada"] is True, "Lote ja_importado e reverificado no snapshot original."
    assert segundo["paridade"]["contagens"]["ja_importado"] == 2


def test_lote_alterado_depois_de_importado_e_conflito_de_reimportacao_registrado(conexao, tmp_path):
    documento = doc_a1()
    origem = _montar_origem(tmp_path / "origem", [documento])
    executor.executar_importacao(conexao, origem, FUSO)

    (origem / caminho_do_lote(documento["lote_id"])).write_bytes(serializar(dict(documento, nome_lote="Alterado")))
    relatorio = executor.executar_importacao(conexao, origem, FUSO)
    assert relatorio["motivos_de_recusa"] == {"conflito_de_reimportacao": 1}
    assert relatorio["paridade"]["aprovada"] is True, "A execucao e concluida normalmente (item 11)."


def test_retomada_com_outro_fuso_e_abortada(conexao, tmp_path):
    origem = _montar_origem(tmp_path / "origem", [doc_a1()])
    importacao_id = uuid_texto()
    executor.executar_importacao(conexao, origem, FUSO, importacao_id)
    with pytest.raises(executor.ExecucaoAbortada) as exc_info:
        executor.executar_importacao(conexao, origem, None, importacao_id)
    assert exc_info.value.motivo == "conflito_de_idempotencia_na_abertura"


@pytest.mark.parametrize("fuso", ["Etc/GMT+3", "America/Nao_Existe", "-03:00", "EST"])
def test_fuso_invalido_aborta_antes_de_importar(conexao, tmp_path, fuso, monkeypatch):
    monkeypatch.setattr(executor, "ler_arquivo_do_escopo", lambda *a: pytest.fail("um lote foi lido"))
    with pytest.raises(executor.ExecucaoAbortada) as exc_info:
        executor.executar_importacao(conexao, _montar_origem(tmp_path / "origem", [doc_a1()]), fuso)
    assert exc_info.value.motivo == "fuso_ou_execucao_invalidos"
    assert exc_info.value.importacao_id is None


# ============================================================
# Arquivo que muda durante a execucao (item 5, passo 5; item 12)
# ============================================================

def test_arquivo_alterado_entre_a_enumeracao_e_a_importacao_aborta_a_execucao(conexao, tmp_path, monkeypatch):
    documento, outro = doc_a1(), doc_a1()
    origem = _montar_origem(tmp_path / "origem", [documento, outro])
    importacao_id = uuid_texto()
    enumerar_original = executor.enumerar_escopo

    def enumerar_e_alterar(raiz):
        arquivos = enumerar_original(raiz)
        (origem / arquivos[-1].caminho_relativo).write_bytes(b'{"alterado": true}')
        return arquivos

    monkeypatch.setattr(executor, "enumerar_escopo", enumerar_e_alterar)
    with pytest.raises(executor.ExecucaoAbortada) as exc_info:
        executor.executar_importacao(conexao, origem, FUSO, importacao_id)
    assert exc_info.value.motivo == "arquivo_alterado_durante_a_execucao"
    assert exc_info.value.importacao_id == importacao_id

    paridade = _paridade_do_banco(conexao, importacao_id)
    assert (paridade["concluida"], paridade["aprovada"]) == (False, False), "A execucao permanece aberta."
    assert paridade["contagens"]["lotes"] == 1, "O lote anterior ao arquivo alterado ja estava importado."


def test_conflito_de_idempotencia_do_banco_aborta_e_a_execucao_nunca_e_concluida(conexao, tmp_path):
    """Retomada de uma execucao aberta cujo arquivo mudou: o banco levanta
    22023 para o mesmo caminho com SHA-256 diferente."""
    documento = doc_a1()
    origem = _montar_origem(tmp_path / "origem", [documento])
    caminho = caminho_do_lote(documento["lote_id"])
    importacao_id = uuid_texto()
    conteudo = (origem / caminho).read_bytes()
    with conexao.transaction():
        conexao.execute("SELECT nsi_operacional.fn_iniciar_importacao_legado(%s, %s)", (importacao_id, FUSO))
        conexao.execute("SELECT nsi_operacional.fn_importar_lote_legado(%s, %s, %s, %s)",
                        (importacao_id, caminho, conteudo, sha256_hex(conteudo)))

    (origem / caminho).write_bytes(serializar(dict(documento, nome_lote="Alterado")))
    with pytest.raises(executor.ExecucaoAbortada) as exc_info:
        executor.executar_importacao(conexao, origem, FUSO, importacao_id)
    assert exc_info.value.motivo == "arquivo_alterado_durante_a_execucao"
    assert exc_info.value.importacao_id == importacao_id
    assert _paridade_do_banco(conexao, importacao_id)["concluida"] is False


def test_arquivo_de_origem_alterado_depois_da_importacao_reprova_a_paridade(conexao, tmp_path, monkeypatch):
    """Item 14: o executor confere o SHA-256 de cada arquivo de origem
    contra o registrado. O banco, que so conhece o que recebeu, aprova."""
    documento, outro = doc_a1(), doc_a2()
    origem = _montar_origem(tmp_path / "origem", [documento, outro])
    montar_original = executor.montar_manifesto

    def montar_e_alterar(*args):
        manifesto = montar_original(*args)
        (origem / caminho_do_lote(documento["lote_id"])).write_bytes(serializar(dict(documento, nome_lote="Alterado")))
        return manifesto

    monkeypatch.setattr(executor, "montar_manifesto", montar_e_alterar)
    relatorio = executor.executar_importacao(conexao, origem, FUSO)

    paridade = relatorio["paridade"]
    assert paridade["aprovada"] is False
    assert paridade["banco_aprovada"] is True
    assert paridade["origem_confere"] is False
    assert paridade["arquivos_alterados"] == [caminho_do_lote(documento["lote_id"])]


# ============================================================
# Caminho real de producao: main(), autocommit, COMMIT real
# ============================================================

def _origem_nao_promovivel(raiz: Path) -> tuple:
    documentos = [doc_anterior_a1(), doc_a1()]
    desconhecido = dict(doc_a1(), campo_nao_previsto=1)
    origem = _montar_origem(
        raiz, documentos + [desconhecido],
        brutos={f"lotes/ILEGIVEL-{uuid_texto()[:8]}/lote.json": b'{"lote_id": '},
        tentativas=[f"correcoes_rejeitadas/2026-01-09/{uuid_texto()}.json"])
    return origem, documentos


def test_main_executa_e_confirma_somente_lotes_nao_promoviveis(request, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(executor.Config, "NSI_DATABASE_ENV", "test")
    url_nsi_importacao()  # pula (ou falha, no aceite) se a credencial faltar
    origem, documentos = _origem_nao_promovivel(tmp_path / "origem")

    codigo = executor.main(["--origem", str(origem), "--fuso", FUSO])
    saida = capsys.readouterr()
    relatorio = json.loads(saida.out)

    assert codigo == executor.SAIDA_PARIDADE_APROVADA, relatorio.get("motivo")
    assert relatorio["executada"] is True
    assert relatorio["por_geracao_e_destino"] == {
        "anterior_a1": {"preservado": 1}, "a1": {"preservado": 1},
        "formato_desconhecido": {"recusado": 1}, "nao_classificado": {"recusado": 1}}
    assert relatorio["tentativas_recusadas_somente_manifesto"] == 1
    assert relatorio["paridade"]["aprovada"] is True
    assert relatorio["paridade"]["contagens"]["promovido"] == 0
    assert_sem_valor_pessoal(saida.out + saida.err, "saida do executor")
    assert str(tmp_path) not in saida.out, "Nenhum caminho absoluto na saida."

    # Lido depois pelo owner: tudo foi confirmado sob a identidade
    # nsi_importacao, com os bytes exatos dos arquivos.
    with psycopg.connect(request.getfixturevalue("url_banco_teste")) as conn:
        cur = conn.cursor()
        cur.execute("SET LOCAL ROLE nsi_eventos_owner")
        cur.execute("SELECT executado_por_login, fuso_declarado FROM nsi_operacional.importacoes_legado "
                    "WHERE importacao_id = %s", (relatorio["importacao_id"],))
        assert cur.fetchone() == ("nsi_importacao", FUSO)
        cur.execute("SELECT manifesto_sha256, total_arquivos FROM nsi_operacional.importacoes_legado_conclusoes "
                    "WHERE importacao_id = %s", (relatorio["importacao_id"],))
        assert cur.fetchone() == (relatorio["manifesto_sha256"], 4)
        cur.execute("SELECT count(*) FILTER (WHERE destino = 'promovido'), count(*) "
                    "FROM nsi_operacional.importacoes_legado_arquivos WHERE importacao_id = %s",
                    (relatorio["importacao_id"],))
        assert cur.fetchone() == (0, 4)
        for documento in documentos:
            cur.execute("SELECT documento_bruto FROM nsi_operacional.lotes_legado WHERE lote_id_legado = %s",
                        (documento["lote_id"],))
            assert bytes(cur.fetchone()[0]) == (origem / caminho_do_lote(documento["lote_id"])).read_bytes()
        conn.rollback()


def test_main_com_importacao_id_informado_e_sem_fuso(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(executor.Config, "NSI_DATABASE_ENV", "test")
    url_nsi_importacao()
    origem, _ = _origem_nao_promovivel(tmp_path / "origem")
    importacao_id = uuid_texto()
    argumentos = ["--origem", str(origem), "--importacao-id", importacao_id]

    assert executor.main(argumentos) == executor.SAIDA_PARIDADE_APROVADA
    relatorio = json.loads(capsys.readouterr().out)
    assert relatorio["importacao_id"] == importacao_id
    assert relatorio["fuso_declarado"] is None

    # A execucao ja concluida nunca e retomada.
    assert executor.main(argumentos) == executor.SAIDA_RECUSADA_OU_ABORTADA
    assert json.loads(capsys.readouterr().out) == {
        "executada": False, "importacao_id_aberta": importacao_id, "motivo": "execucao_ja_concluida"}

    # Com outro fuso, a mesma execucao nunca e reaproveitada.
    assert executor.main(argumentos + ["--fuso", FUSO]) == executor.SAIDA_RECUSADA_OU_ABORTADA
    assert json.loads(capsys.readouterr().out) == {
        "executada": False, "importacao_id_aberta": importacao_id,
        "motivo": "conflito_de_idempotencia_na_abertura"}


def test_main_reporta_paridade_reprovada_com_codigo_de_saida_1(tmp_path, monkeypatch, capsys):
    """Origem alterada depois da importacao: execucao concluida, paridade
    reprovada, saida 1. Lote nao promovivel, COMMIT real."""
    monkeypatch.setattr(executor.Config, "NSI_DATABASE_ENV", "test")
    url_nsi_importacao()
    documento = doc_a1()
    origem = _montar_origem(tmp_path / "origem", [documento])
    montar_original = executor.montar_manifesto

    def montar_e_alterar(*args):
        manifesto = montar_original(*args)
        (origem / caminho_do_lote(documento["lote_id"])).write_bytes(b"{}")
        return manifesto

    monkeypatch.setattr(executor, "montar_manifesto", montar_e_alterar)
    assert executor.main(["--origem", str(origem)]) == executor.SAIDA_PARIDADE_REPROVADA
    relatorio = json.loads(capsys.readouterr().out)
    assert relatorio["executada"] is True
    assert relatorio["paridade"]["aprovada"] is False
    assert relatorio["paridade"]["origem_confere"] is False
