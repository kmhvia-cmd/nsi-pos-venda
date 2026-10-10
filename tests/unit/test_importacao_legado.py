# -*- coding: utf-8 -*-
"""
NSI - tests/unit/test_importacao_legado.py
(Sprint B, B5.5 - ADR-010, Secoes 18 a 20; Especificacao Tecnica, B5.2,
itens 5, 6.1, 7, 13, 14 e 17)

Testes UNITARIOS, Python puro, sem banco:

  - core/importacao_legado.py: enumeracao do escopo (ignorando o que esta
    fora dele), SHA-256 de bytes, manifesto canonico deterministico, ordem
    estavel, ausencia de valor pessoal, recusa de origem igual ao diretorio
    de dados, conferencia da origem e relatorio;
  - scripts/importar_legado.py: gate de identidade e de ambiente, e as
    recusas do executor que ocorrem ANTES de qualquer conexao.

SOMENTE DADOS SINTETICOS: arvores montadas em tmp_path e
tests/fixtures/legado/ - nunca data/.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path

import pytest

from core import importacao_legado as il
from core.importacao_legado import ArquivoDoEscopo

RAIZ = Path(__file__).resolve().parents[2]
FIXTURES = RAIZ / "tests" / "fixtures" / "legado"
UUID_A = "3f0c1b7e-5a44-4c0e-9d0a-6f6f1f0a9b01"
UUID_B = "7a1d2c3e-0b4f-4a6d-8e9f-0123456789ab"

VALORES_PESSOAIS_DAS_FIXTURES = ("Pessoa Sintetica Legado", "Produto Sintetico Legado", "55119876")


def _carregar_executor():
    spec = importlib.util.spec_from_file_location("importar_legado_sob_teste", RAIZ / "scripts" / "importar_legado.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


executor = _carregar_executor()


def _gravar(raiz: Path, relativo: str, conteudo: bytes = b"{}") -> Path:
    caminho = raiz / relativo
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(conteudo)
    return caminho


@pytest.fixture
def origem(tmp_path):
    """Arvore com os dois padroes do escopo e com tudo o que fica fora."""
    raiz = tmp_path / "origem"
    _gravar(raiz, "lotes/NSI-20260102-B00002/lote.json", b'{"lote_id": "NSI-20260102-B00002"}')
    _gravar(raiz, "lotes/NSI-20260101-A00001/lote.json", b'{"lote_id": "NSI-20260101-A00001"}\r\n')
    _gravar(raiz, f"correcoes_rejeitadas/2026-01-09/{UUID_A}.json", b'{"t": 1}')
    _gravar(raiz, f"correcoes_rejeitadas/2026-01-08/{UUID_B}.json", b'{"t": 2}')
    # Fora do escopo - nunca enumerado.
    _gravar(raiz, "lotes/NSI-20260101-A00001/saida_motor.json")
    _gravar(raiz, "lotes/NSI-20260101-A00001/original.csv", b"nome,whatsapp,produto\n")
    _gravar(raiz, "lotes/NSI-20260101-A00001/sub/lote.json")
    _gravar(raiz, "lotes/lote.json")
    _gravar(raiz, "lotes/NSI-20260103-C00003/LOTE.JSON.bak")
    _gravar(raiz, "correcoes_rejeitadas/2026-01-09/nota.txt")
    _gravar(raiz, "correcoes_rejeitadas/2026-01-09/nao-e-uuid.json")
    _gravar(raiz, f"correcoes_rejeitadas/sem-data/{UUID_A}.json")
    _gravar(raiz, f"correcoes_rejeitadas/2026-01-09/sub/{UUID_A}.json")
    _gravar(raiz, f"correcoes_rejeitadas/{UUID_A}.json")
    _gravar(raiz, "respostas/5511987650001.json")
    _gravar(raiz, "empresas/empresa.json")
    _gravar(raiz, "pdfs/relatorio.pdf", b"%PDF")
    _gravar(raiz, "logs/app.log")
    _gravar(raiz, "lote.json")
    _gravar(raiz, "saida_motor.json")
    return raiz


# ============================================================
# SHA-256 (item 13)
# ============================================================

def test_sha256_dos_bytes_brutos_em_hexadecimal_minusculo():
    assert il.sha256_bytes(b"") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    conteudo = "{\"nome\": \"Ação\"}".encode("utf-8")
    assert il.sha256_bytes(conteudo) == hashlib.sha256(conteudo).hexdigest()
    assert len(il.sha256_bytes(conteudo)) == 64 and il.sha256_bytes(conteudo).islower()


def test_sha256_nao_normaliza_nada():
    assert il.sha256_bytes(b'{"a": 1}\n') != il.sha256_bytes(b'{"a": 1}\r\n')
    assert il.sha256_bytes(b'{"a": 1}') != il.sha256_bytes(b'{"a":1}')
    assert il.sha256_bytes(b"\xef\xbb\xbf{}") != il.sha256_bytes(b"{}")


# ============================================================
# Enumeracao do escopo (item 6.1)
# ============================================================

def test_enumera_somente_os_dois_padroes_do_escopo_em_ordem_lexicografica(origem):
    arquivos = il.enumerar_escopo(origem)
    assert [(a.caminho_relativo, a.tipo) for a in arquivos] == [
        (f"correcoes_rejeitadas/2026-01-08/{UUID_B}.json", "tentativa_recusada"),
        (f"correcoes_rejeitadas/2026-01-09/{UUID_A}.json", "tentativa_recusada"),
        ("lotes/NSI-20260101-A00001/lote.json", "lote"),
        ("lotes/NSI-20260102-B00002/lote.json", "lote"),
    ]


def test_enumeracao_traz_tamanho_e_sha256_dos_bytes_brutos(origem):
    arquivo = next(a for a in il.enumerar_escopo(origem) if a.caminho_relativo.endswith("A00001/lote.json"))
    conteudo = b'{"lote_id": "NSI-20260101-A00001"}\r\n'
    assert arquivo == ArquivoDoEscopo(
        "lotes/NSI-20260101-A00001/lote.json", "lote", len(conteudo), hashlib.sha256(conteudo).hexdigest())


def test_caminho_relativo_usa_sempre_barra(origem):
    for arquivo in il.enumerar_escopo(origem):
        assert "\\" not in arquivo.caminho_relativo
        assert not arquivo.caminho_relativo.startswith("/")
        assert not os.path.isabs(arquivo.caminho_relativo)


def test_enumeracao_e_estavel(origem):
    assert il.enumerar_escopo(origem) == il.enumerar_escopo(origem) == il.enumerar_escopo(str(origem))


def test_diretorios_fora_do_escopo_nunca_sao_percorridos(origem, monkeypatch):
    """Os nomes de arquivo dos logs de resposta contem telefone: respostas/
    e os demais diretorios nao podem sequer ser listados."""
    listados = []
    iterdir_original = Path.iterdir

    def iterdir_registrando(self):
        listados.append(self.relative_to(origem).as_posix())
        return iterdir_original(self)

    monkeypatch.setattr(Path, "iterdir", iterdir_registrando)
    il.enumerar_escopo(origem)

    assert set(listados) == {"lotes", "correcoes_rejeitadas",
                             "correcoes_rejeitadas/2026-01-08", "correcoes_rejeitadas/2026-01-09"}


@pytest.mark.parametrize("preparar", [
    lambda raiz: None,
    lambda raiz: (raiz / "lotes").mkdir(),
    lambda raiz: _gravar(raiz, "lotes"),                      # 'lotes' e um arquivo
    lambda raiz: _gravar(raiz, "respostas/5511987650001.json"),
])
def test_origem_sem_arquivos_do_escopo_enumera_vazio(tmp_path, preparar):
    raiz = tmp_path / "origem"
    raiz.mkdir()
    preparar(raiz)
    assert il.enumerar_escopo(raiz) == []


def test_enumeracao_das_fixtures_sinteticas():
    arquivos = il.enumerar_escopo(FIXTURES)
    assert [a.tipo for a in arquivos].count("lote") == 8
    assert [a.tipo for a in arquivos].count("tentativa_recusada") == 1
    assert all(a.caminho_relativo != "LEIAME.md" for a in arquivos)
    assert [a.caminho_relativo for a in arquivos] == sorted(a.caminho_relativo for a in arquivos)


def test_leitura_devolve_os_bytes_exatos_da_enumeracao(origem):
    arquivo = next(a for a in il.enumerar_escopo(origem) if a.caminho_relativo.endswith("A00001/lote.json"))
    assert il.ler_arquivo_do_escopo(origem, arquivo) == b'{"lote_id": "NSI-20260101-A00001"}\r\n'


@pytest.mark.parametrize("novo_conteudo", [b'{"lote_id": "outro"}', b'{"lote_id": "NSI-20260101-A00001"}\r\n ',
                                           b'{"lote_id": "NSI-20260101-A00009"}\r\n'])
def test_arquivo_alterado_depois_da_enumeracao_e_detectado_na_leitura(origem, novo_conteudo):
    arquivo = next(a for a in il.enumerar_escopo(origem) if a.caminho_relativo.endswith("A00001/lote.json"))
    (origem / arquivo.caminho_relativo).write_bytes(novo_conteudo)
    with pytest.raises(il.ArquivoDeOrigemAlterado) as exc_info:
        il.ler_arquivo_do_escopo(origem, arquivo)
    assert str(exc_info.value) == "arquivo de origem alterado durante a execucao"


# ============================================================
# Origem (item 5, passo 2)
# ============================================================

def test_origem_valida_e_devolvida_como_caminho(tmp_path):
    origem = tmp_path / "origem"
    origem.mkdir()
    assert il.validar_origem(str(origem), tmp_path / "data") == origem


@pytest.mark.parametrize("origem", [None, "", "   "])
def test_origem_nao_informada_e_recusada(tmp_path, origem):
    with pytest.raises(il.OrigemInvalida) as exc_info:
        il.validar_origem(origem, tmp_path / "data")
    assert "nao existe valor padrao" in str(exc_info.value)


def test_origem_igual_ao_diretorio_de_dados_e_recusada(tmp_path):
    dados = tmp_path / "data"
    dados.mkdir()
    with pytest.raises(il.OrigemInvalida) as exc_info:
        il.validar_origem(dados, dados)
    assert str(exc_info.value) == "a origem nao pode ser o diretorio de dados da aplicacao"
    assert str(tmp_path) not in str(exc_info.value), "A mensagem nunca interpola o caminho."


def test_origem_igual_ao_diretorio_de_dados_por_outra_grafia_e_recusada(tmp_path, monkeypatch):
    dados = tmp_path / "data"
    (dados / "lotes").mkdir(parents=True)
    grafias = [str(dados) + os.sep, str(dados / "lotes" / ".."), str(dados / "." / "")]
    if os.path.normcase("A") == "a":
        grafias.append(str(dados).upper())
    monkeypatch.chdir(tmp_path)
    grafias.append("data")
    for grafia in grafias:
        with pytest.raises(il.OrigemInvalida):
            il.validar_origem(grafia, dados)


def test_origem_inexistente_ou_que_nao_e_diretorio_e_recusada(tmp_path):
    arquivo = _gravar(tmp_path, "arquivo.json")
    for origem in (tmp_path / "nao-existe", arquivo):
        with pytest.raises(il.OrigemInvalida) as exc_info:
            il.validar_origem(origem, tmp_path / "data")
        assert str(exc_info.value) == "a origem nao e um diretorio existente"


def test_diretorio_de_dados_nao_informado_e_recusado(tmp_path):
    with pytest.raises(il.OrigemInvalida):
        il.validar_origem(tmp_path, None)


# ============================================================
# Manifesto canonico (item 7)
# ============================================================

IMPORTACAO_ID = "0f8fad5b-d9cb-469f-a165-70867728950e"


def _retorno(**campos) -> dict:
    retorno = {"geracao": "a1", "destino": "preservado", "motivo": "geracao_nao_promovivel",
               "lote_id_legado": "NSI-20260101-A00001", "lote_id_promovido": None, "constraint_violada": None}
    retorno.update(campos)
    return retorno


def _entradas() -> list:
    lote_a = ArquivoDoEscopo("lotes/NSI-20260101-A00001/lote.json", "lote", 10, "a" * 64)
    lote_b = ArquivoDoEscopo("lotes/NSI-20260102-B00002/lote.json", "lote", 20, "b" * 64)
    tentativa = ArquivoDoEscopo(f"correcoes_rejeitadas/2026-01-09/{UUID_A}.json", "tentativa_recusada", 5, "c" * 64)
    return [
        il.entrada_de_lote(lote_b, _retorno(
            geracao="a2", destino="promovido", motivo=None, lote_id_legado="NSI-20260102-B00002",
            lote_id_promovido="6f9619ff-8b86-d011-b42d-00c04fc964ff")),
        il.entrada_de_tentativa_recusada(tentativa),
        il.entrada_de_lote(lote_a, _retorno()),
    ]


def test_manifesto_tem_exatamente_o_layout_do_item_7():
    manifesto = json.loads(il.montar_manifesto(IMPORTACAO_ID, "America/Sao_Paulo", _entradas()))
    assert set(manifesto) == {"formato", "importacao_id", "fuso_declarado", "arquivos"}
    assert manifesto["formato"] == "nsi-manifesto-legado/1"
    assert manifesto["importacao_id"] == IMPORTACAO_ID
    assert manifesto["fuso_declarado"] == "America/Sao_Paulo"
    for entrada in manifesto["arquivos"]:
        assert set(entrada) == {"caminho_relativo", "tamanho_bytes", "sha256", "tipo", "geracao", "destino",
                                "motivo", "lote_id_legado", "lote_id_promovido"}
    assert [(e["tipo"], e["geracao"], e["destino"], e["motivo"]) for e in manifesto["arquivos"]] == [
        ("tentativa_recusada", None, "somente_manifesto", None),
        ("lote", "a1", "preservado", "geracao_nao_promovivel"),
        ("lote", "a2", "promovido", None),
    ]


def test_manifesto_e_canonico_byte_a_byte():
    """Chaves ordenadas, separadores sem espaco, UTF-8 sem escape."""
    arquivo = ArquivoDoEscopo("lotes/Ação/lote.json", "lote", 3, "d" * 64)
    manifesto = il.montar_manifesto(IMPORTACAO_ID.upper(), None, [il.entrada_de_lote(arquivo, _retorno(
        geracao=None, destino="recusado", motivo="documento_ilegivel", lote_id_legado=None))])
    assert manifesto == (
        '{"arquivos":[{"caminho_relativo":"lotes/Ação/lote.json","destino":"recusado","geracao":null,'
        '"lote_id_legado":null,"lote_id_promovido":null,"motivo":"documento_ilegivel","sha256":"' + "d" * 64 + '",'
        '"tamanho_bytes":3,"tipo":"lote"}],"formato":"nsi-manifesto-legado/1","fuso_declarado":null,'
        '"importacao_id":"' + IMPORTACAO_ID + '"}'
    ).encode("utf-8")


def test_manifesto_e_deterministico_e_independe_da_ordem_das_entradas():
    entradas = _entradas()
    referencia = il.montar_manifesto(IMPORTACAO_ID, "UTC", entradas)
    assert il.montar_manifesto(IMPORTACAO_ID, "UTC", list(reversed(entradas))) == referencia
    assert il.montar_manifesto(IMPORTACAO_ID, "UTC", [dict(reversed(list(e.items()))) for e in entradas]) == referencia
    caminhos = [e["caminho_relativo"] for e in json.loads(referencia)["arquivos"]]
    assert caminhos == sorted(caminhos)


def test_manifesto_muda_com_qualquer_campo():
    entradas = _entradas()
    referencia = il.sha256_bytes(il.montar_manifesto(IMPORTACAO_ID, "UTC", entradas))
    assert il.sha256_bytes(il.montar_manifesto(IMPORTACAO_ID, None, entradas)) != referencia
    assert il.sha256_bytes(il.montar_manifesto(IMPORTACAO_ID, "UTC", entradas[:-1])) != referencia
    alterada = [dict(entradas[0], destino="preservado")] + entradas[1:]
    assert il.sha256_bytes(il.montar_manifesto(IMPORTACAO_ID, "UTC", alterada)) != referencia


def test_entrada_de_lote_copia_somente_os_campos_do_manifesto():
    arquivo = ArquivoDoEscopo("lotes/X/lote.json", "lote", 1, "e" * 64)
    entrada = il.entrada_de_lote(arquivo, _retorno(
        destino="ja_importado", motivo=None, constraint_violada="ck_qualquer", destino_original="promovido",
        campo_inesperado="valor"))
    assert "constraint_violada" not in entrada and "destino_original" not in entrada
    assert "campo_inesperado" not in entrada
    assert entrada["destino"] == "ja_importado"


def test_entradas_exigem_o_tipo_de_arquivo_correto():
    lote = ArquivoDoEscopo("lotes/X/lote.json", "lote", 1, "e" * 64)
    tentativa = ArquivoDoEscopo(f"correcoes_rejeitadas/2026-01-09/{UUID_A}.json", "tentativa_recusada", 1, "f" * 64)
    with pytest.raises(ValueError):
        il.entrada_de_lote(tentativa, _retorno())
    with pytest.raises(ValueError):
        il.entrada_de_tentativa_recusada(lote)
    with pytest.raises(ValueError):
        il.entrada_de_lote(lote, _retorno(destino="somente_manifesto"))


def test_manifesto_das_fixtures_nao_contem_valor_pessoal():
    """O manifesto so carrega caminho, tamanho, hash, tipo, geracao,
    destino, motivo e identificadores - nunca o conteudo dos arquivos."""
    arquivos = il.enumerar_escopo(FIXTURES)
    conteudo_das_fixtures = b"".join((FIXTURES / a.caminho_relativo).read_bytes() for a in arquivos)
    assert all(v.encode() in conteudo_das_fixtures for v in VALORES_PESSOAIS_DAS_FIXTURES), (
        "As fixtures precisam conter os valores procurados, ou o teste nada prova."
    )
    entradas = [il.entrada_de_lote(a, _retorno(lote_id_legado=a.caminho_relativo.split("/")[1]))
                if a.tipo == "lote" else il.entrada_de_tentativa_recusada(a) for a in arquivos]
    manifesto = il.montar_manifesto(IMPORTACAO_ID, "America/Sao_Paulo", entradas).decode("utf-8")
    for valor in VALORES_PESSOAIS_DAS_FIXTURES:
        assert valor not in manifesto


# ============================================================
# Conferencia da origem (item 14, parte do executor)
# ============================================================

def _entradas_da_origem(origem) -> tuple:
    arquivos = il.enumerar_escopo(origem)
    entradas = [il.entrada_de_lote(a, _retorno()) if a.tipo == "lote" else il.entrada_de_tentativa_recusada(a)
                for a in arquivos]
    return arquivos, entradas


def test_conferencia_aprovada_para_origem_integra(origem):
    arquivos, entradas = _entradas_da_origem(origem)
    assert il.conferir_origem(origem, arquivos, entradas) == {
        "origem_confere": True, "manifesto_completo": True, "arquivos_conferidos": 4,
        "arquivos_alterados": [], "arquivos_sem_destino": [], "entradas_fora_da_enumeracao": []}


def test_arquivo_de_origem_alterado_depois_da_importacao_reprova(origem):
    arquivos, entradas = _entradas_da_origem(origem)
    (origem / "lotes/NSI-20260102-B00002/lote.json").write_bytes(b'{"lote_id": "NSI-20260102-B00002"} ')
    resultado = il.conferir_origem(origem, arquivos, entradas)
    assert resultado["origem_confere"] is False
    assert resultado["arquivos_alterados"] == ["lotes/NSI-20260102-B00002/lote.json"]
    assert resultado["manifesto_completo"] is True


def test_tentativa_recusada_alterada_tambem_reprova(origem):
    arquivos, entradas = _entradas_da_origem(origem)
    (origem / f"correcoes_rejeitadas/2026-01-09/{UUID_A}.json").write_bytes(b"{}")
    assert il.conferir_origem(origem, arquivos, entradas)["origem_confere"] is False


def test_arquivo_de_origem_removido_reprova(origem):
    arquivos, entradas = _entradas_da_origem(origem)
    (origem / "lotes/NSI-20260101-A00001/lote.json").unlink()
    resultado = il.conferir_origem(origem, arquivos, entradas)
    assert resultado["origem_confere"] is False
    assert resultado["arquivos_alterados"] == ["lotes/NSI-20260101-A00001/lote.json"]


def test_arquivo_enumerado_sem_entrada_no_manifesto_reprova(origem):
    arquivos, entradas = _entradas_da_origem(origem)
    resultado = il.conferir_origem(origem, arquivos, entradas[1:])
    assert resultado["manifesto_completo"] is False
    assert resultado["arquivos_sem_destino"] == [arquivos[0].caminho_relativo]


def test_entrada_sem_destino_duplicada_ou_fora_da_enumeracao_reprova(origem):
    arquivos, entradas = _entradas_da_origem(origem)
    sem_destino = [dict(entradas[0], destino=None)] + entradas[1:]
    assert il.conferir_origem(origem, arquivos, sem_destino)["manifesto_completo"] is False
    assert il.conferir_origem(origem, arquivos, entradas + [dict(entradas[0])])["manifesto_completo"] is False
    extra = dict(entradas[0], caminho_relativo="lotes/NAO-ENUMERADO/lote.json")
    resultado = il.conferir_origem(origem, arquivos, entradas + [extra])
    assert resultado["manifesto_completo"] is False
    assert resultado["entradas_fora_da_enumeracao"] == ["lotes/NAO-ENUMERADO/lote.json"]


# ============================================================
# Relatorio (item 5, passo 9)
# ============================================================

def _paridade_do_banco(aprovada=True, concluida=True) -> dict:
    return {"aprovada": aprovada, "concluida": concluida, "motivo": None,
            "registro_tecnico": {"manifesto_sha256_confere": True, "manifesto_cabecalho_confere": True,
                                 "manifesto_sem_lote_orfao": True},
            "lotes": [{"caminho_relativo": "x", "lote_id_legado": "y", "destino": "preservado"}],
            "contagens": {"lotes": 6, "lotes_reprovados": 0}}


def _conferencia(origem_confere=True, manifesto_completo=True) -> dict:
    return {"origem_confere": origem_confere, "manifesto_completo": manifesto_completo, "arquivos_conferidos": 7,
            "arquivos_alterados": [], "arquivos_sem_destino": [], "entradas_fora_da_enumeracao": []}


def _retornos_variados() -> list:
    return [
        _retorno(geracao="anterior_a1"),
        _retorno(),
        _retorno(geracao="a2", destino="promovido", motivo=None),
        _retorno(geracao="a2", motivo="projecao_incompativel", constraint_violada="ck_registros_coleta_coerencia"),
        _retorno(geracao="a3", motivo="fuso_nao_declarado"),
        _retorno(geracao="formato_desconhecido", destino="recusado", motivo="formato_desconhecido"),
        _retorno(geracao=None, destino="recusado", motivo="documento_ilegivel"),
        _retorno(geracao="a1", destino="ja_importado", motivo=None, destino_original="preservado"),
    ]


def test_relatorio_conta_por_geracao_e_destino_e_por_motivo():
    retornos = _retornos_variados()
    entradas = _entradas()
    manifesto = il.montar_manifesto(IMPORTACAO_ID, "UTC", entradas)
    relatorio = il.montar_relatorio(IMPORTACAO_ID, "UTC", entradas, retornos, manifesto,
                                    _paridade_do_banco(), _conferencia())

    assert relatorio["importacao_id"] == IMPORTACAO_ID
    assert relatorio["fuso_declarado"] == "UTC"
    assert relatorio["lotes"] == 8
    assert relatorio["arquivos_no_manifesto"] == 3
    assert relatorio["tentativas_recusadas_somente_manifesto"] == 1
    assert relatorio["por_geracao_e_destino"] == {
        "anterior_a1": {"preservado": 1},
        "a1": {"preservado": 1, "ja_importado": 1},
        "a2": {"promovido": 1, "preservado": 1},
        "a3": {"preservado": 1},
        "formato_desconhecido": {"recusado": 1},
        "nao_classificado": {"recusado": 1},
    }
    assert relatorio["motivos_de_nao_promocao"] == {
        "fuso_nao_declarado": 1, "geracao_nao_promovivel": 2, "projecao_incompativel": 1}
    assert relatorio["motivos_de_recusa"] == {"documento_ilegivel": 1, "formato_desconhecido": 1}
    assert relatorio["constraints_violadas"] == {"ck_registros_coleta_coerencia": 1}
    assert relatorio["manifesto_sha256"] == il.sha256_bytes(manifesto)
    assert relatorio["paridade"]["aprovada"] is True
    assert "lotes" not in relatorio["paridade"], "O detalhe por lote do banco nao e copiado para o relatorio."
    json.dumps(relatorio)


@pytest.mark.parametrize("banco,concluida,origem_confere,manifesto_completo,esperado", [
    (True, True, True, True, True),
    (False, True, True, True, False),
    (False, False, True, True, False),
    (True, True, False, True, False),
    (True, True, True, False, False),
])
def test_paridade_aprovada_exige_todos_os_itens(banco, concluida, origem_confere, manifesto_completo, esperado):
    relatorio = il.montar_relatorio(
        IMPORTACAO_ID, None, [], [], il.montar_manifesto(IMPORTACAO_ID, None, []),
        _paridade_do_banco(banco, concluida), _conferencia(origem_confere, manifesto_completo))
    paridade = relatorio["paridade"]
    assert paridade["aprovada"] is esperado
    assert (paridade["banco_aprovada"], paridade["concluida"]) == (banco, concluida)
    assert (paridade["origem_confere"], paridade["manifesto_completo"]) == (origem_confere, manifesto_completo)


# ============================================================
# Pureza do modulo
# ============================================================

def test_modulo_de_producao_e_puro():
    fonte = (RAIZ / "core" / "importacao_legado.py").read_text(encoding="utf-8")
    for proibido in ("import psycopg", "from psycopg", "import config", "from config", "sqlalchemy", "alembic",
                     "Config.", "os.environ", "os.getenv"):
        assert proibido not in fonte, proibido


# ============================================================
# Executor - gate de identidade e recusas anteriores a conexao
# ============================================================

def test_gate_aceita_exatamente_a_identidade_da_b5():
    for endereco in ("127.0.0.1", "::1", "::1/128", "127.0.0.1/32", None):
        executor.validar_identidade("nsi_test", endereco, 5432, "nsi_importacao")


@pytest.mark.parametrize("identidade,trecho", [
    (("nsi_dev", "127.0.0.1", 5432, "nsi_importacao"), "banco"),
    (("postgres", "127.0.0.1", 5432, "nsi_importacao"), "banco"),
    (("nsi_test", "10.0.0.5", 5432, "nsi_importacao"), "servidor"),
    (("nsi_test", "192.168.0.10/32", 5432, "nsi_importacao"), "servidor"),
    (("nsi_test", "127.0.0.1", 5433, "nsi_importacao"), "porta"),
    (("nsi_test", "127.0.0.1", None, "nsi_importacao"), "porta"),
    (("nsi_test", "127.0.0.1", 5432, "nsi_aplicacao"), "usuario"),
    (("nsi_test", "127.0.0.1", 5432, "nsi_test_migrator"), "usuario"),
    (("nsi_test", "127.0.0.1", 5432, "postgres"), "usuario"),
    (("nsi_test", "127.0.0.1", 5432, "nsi_eventos_owner"), "usuario"),
])
def test_gate_recusa_qualquer_divergencia(identidade, trecho):
    with pytest.raises(executor.IdentidadeNaoComprovada) as exc_info:
        executor.validar_identidade(*identidade)
    assert trecho in str(exc_info.value)
    for valor in ("nsi_dev", "10.0.0.5", "5433", "nsi_aplicacao", "postgres"):
        if valor in map(str, identidade) and valor not in ("nsi_test",):
            assert valor not in str(exc_info.value), "A mensagem do gate e fixa."


@pytest.mark.parametrize("ambiente", ["development", "production", "", "TEST", "staging"])
def test_executor_aceita_somente_o_ambiente_test(ambiente):
    with pytest.raises(executor.IdentidadeNaoComprovada):
        executor.validar_ambiente(ambiente)
    executor.validar_ambiente("test")


def _sem_conexao(monkeypatch):
    def _proibido(*args, **kwargs):
        raise AssertionError("o executor tentou conectar")
    monkeypatch.setattr(executor.psycopg, "connect", _proibido)


def test_main_recusa_origem_igual_ao_diretorio_de_dados_sem_conectar(monkeypatch, capsys):
    """Nenhuma execucao da B5 abre o diretorio de dados da aplicacao."""
    _sem_conexao(monkeypatch)
    monkeypatch.setattr(executor.Config, "NSI_DATABASE_ENV", "test")
    monkeypatch.setattr(executor, "enumerar_escopo", lambda origem: pytest.fail("a origem foi lida"))

    assert executor.main(["--origem", str(executor.Config.DATA_DIR)]) == executor.SAIDA_RECUSADA_OU_ABORTADA
    saida = json.loads(capsys.readouterr().out)
    assert saida == {"executada": False, "importacao_id_aberta": None,
                     "motivo": "a origem nao pode ser o diretorio de dados da aplicacao"}


def test_main_recusa_ambiente_diferente_de_test_sem_conectar(monkeypatch, capsys, tmp_path):
    _sem_conexao(monkeypatch)
    monkeypatch.setattr(executor.Config, "NSI_DATABASE_ENV", "development")
    assert executor.main(["--origem", str(tmp_path)]) == executor.SAIDA_RECUSADA_OU_ABORTADA
    saida = json.loads(capsys.readouterr().out)
    assert saida["executada"] is False
    assert "NSI_DATABASE_ENV=test" in saida["motivo"]


def test_main_recusa_importacao_id_invalido_sem_conectar(monkeypatch, capsys, tmp_path):
    _sem_conexao(monkeypatch)
    monkeypatch.setattr(executor.Config, "NSI_DATABASE_ENV", "test")
    assert executor.main(["--origem", str(tmp_path), "--importacao-id", "nao-e-uuid"]) == 2
    assert json.loads(capsys.readouterr().out)["motivo"] == "importacao_id_invalido"


def test_main_exige_origem_explicita(capsys):
    """Sem valor padrao: --origem e obrigatorio."""
    with pytest.raises(SystemExit) as exc_info:
        executor.main([])
    assert exc_info.value.code == 2
    capsys.readouterr()


def test_falha_de_conexao_nunca_expoe_a_dsn(monkeypatch, capsys, tmp_path):
    dsn_falsa = "postgresql://nsi_importacao:senha-secreta@localhost:5432/nsi_test"

    def _falhar(*args, **kwargs):
        raise RuntimeError(f"connection failed: {dsn_falsa}")

    monkeypatch.setattr(executor.psycopg, "connect", _falhar)
    monkeypatch.setattr(executor.Config, "NSI_DATABASE_ENV", "test")
    monkeypatch.setattr(executor, "resolver_url_banco_papel", lambda papel, ambiente: dsn_falsa)

    assert executor.main(["--origem", str(tmp_path)]) == executor.SAIDA_RECUSADA_OU_ABORTADA
    saida = capsys.readouterr()
    assert "senha-secreta" not in saida.out + saida.err
    assert json.loads(saida.out)["motivo"] == "nao foi possivel conectar como nsi_importacao em nsi_test"


def test_executor_nao_tem_origem_nem_fuso_padrao():
    argumentos = executor._argumentos(["--origem", "x"])
    assert (argumentos.fuso, argumentos.importacao_id) == (None, None)
    fonte = (RAIZ / "scripts" / "importar_legado.py").read_text(encoding="utf-8")
    assert "America/" not in fonte.split('"""', 2)[2], "Nenhum fuso embutido no codigo do executor."
