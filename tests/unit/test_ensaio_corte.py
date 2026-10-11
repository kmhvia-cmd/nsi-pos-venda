# -*- coding: utf-8 -*-
"""
NSI - tests/unit/test_ensaio_corte.py
(Sprint B, B6.2 - SPRINT-B6-ESPECIFICACAO-ENSAIO-DE-CORTE.md, Secoes 11, 17,
22 a 24, 28 e 56; componentes C3 a C7)

Testes UNITARIOS, Python puro, sem banco:

  - core/ensaio_corte.py: area de ensaio (D5, fail closed), inventario
    (C4), copia congelada (C5), levantamento estrutural (C6), evidencias,
    varredura de privacidade e avaliacao da auditoria;
  - scripts/importar_legado.py: gate do executor por ambiente e regra de
    origem (C3);
  - scripts/ensaio_corte.py: comandos e leitor do arquivo de auditoria (C7).

SOMENTE DADOS SINTETICOS, em tmp_path - nunca data/.
"""
import importlib.util
import json
import os
import re
import stat
from pathlib import Path

import pytest

from core import ensaio_corte as ec
from core import importacao_legado as il

RAIZ = Path(__file__).resolve().parents[2]
UUID_A = "3f0c1b7e-5a44-4c0e-9d0a-6f6f1f0a9b01"
TELEFONE = "5511987650001"
NOME = "Pessoa Sintetica Inventario"


def _carregar(nome: str, arquivo: str):
    spec = importlib.util.spec_from_file_location(nome, RAIZ / "scripts" / arquivo)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


executor = _carregar("importar_legado_b6", "importar_legado.py")
cli = _carregar("ensaio_corte_cli", "ensaio_corte.py")


def _gravar(raiz: Path, relativo: str, conteudo: bytes = b"{}") -> Path:
    caminho = raiz / relativo
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(conteudo)
    return caminho


def _lote(lote_id: str, **extras) -> bytes:
    documento = {"lote_id": lote_id, "criado_em": "2026-02-03T09:15:00", "status": "aguardando_d8",
                 "clientes": [{"registro_coleta_id": "0f8fad5b-d9cb-469f-a165-70867728950e", "nome": NOME,
                               "telefone": TELEFONE, "produto": "Produto Sintetico"}]}
    documento.update(extras)
    return json.dumps(documento, ensure_ascii=False, indent=2).encode("utf-8")


@pytest.fixture
def instalacao(tmp_path):
    """Instalacao de origem sintetica: escopo mais arquivos fora dele, com
    nomes que contem telefone (como os logs de resposta reais)."""
    raiz = tmp_path / "instalacao"
    _gravar(raiz, "lotes/NSI-20260203-000001/lote.json", _lote("NSI-20260203-000001"))
    _gravar(raiz, "lotes/NSI-20260203-000002/lote.json", _lote("NSI-20260203-000002"))
    _gravar(raiz, f"correcoes_rejeitadas/2026-02-04/{UUID_A}.json", b'{"t": 1}')
    _gravar(raiz, f"respostas/{TELEFONE}.json", b'{"texto": "ola"}')
    _gravar(raiz, "lotes/NSI-20260203-000001/saida_motor.json", b'{"x": 1}')
    _gravar(raiz, "pdfs/relatorio.pdf", b"%PDF")
    return raiz


@pytest.fixture
def area(tmp_path, monkeypatch):
    """Area de ensaio em tmp_path, informada pela variavel de configuracao."""
    diretorio = tmp_path / "area"
    diretorio.mkdir()
    monkeypatch.setattr(cli.Config, "NSI_ENSAIO_DIR", str(diretorio))
    monkeypatch.setattr(cli.Config, "DATA_DIR", tmp_path / "data")
    return diretorio


# ============================================================
# Area de ensaio (D5 - fail closed)
# ============================================================

@pytest.mark.parametrize("valor", [None, "", "   "])
def test_area_nao_informada_falha_sem_assumir_diretorio(tmp_path, valor):
    with pytest.raises(ec.AreaDeEnsaioInvalida) as exc_info:
        ec.validar_area_de_ensaio(valor, tmp_path / "data", tmp_path / "repo")
    assert "nao existe valor padrao" in str(exc_info.value)


def test_area_valida_e_devolvida(tmp_path):
    area = tmp_path / "area"
    area.mkdir()
    assert ec.validar_area_de_ensaio(str(area), tmp_path / "data", tmp_path / "repo") == area


def test_area_inexistente_e_recusada(tmp_path):
    with pytest.raises(ec.AreaDeEnsaioInvalida):
        ec.validar_area_de_ensaio(tmp_path / "nao-existe", tmp_path / "data", tmp_path / "repo")


@pytest.mark.parametrize("relativo_da_area", ["data", "data/ensaio", "repo", "repo/tmp/ensaio", "."])
def test_area_precisa_ser_disjunta_dos_dados_e_do_repositorio(tmp_path, relativo_da_area):
    """Nem dentro, nem igual, nem contendo o diretorio de dados ou o
    repositorio."""
    (tmp_path / "data" / "ensaio").mkdir(parents=True)
    (tmp_path / "repo" / "tmp" / "ensaio").mkdir(parents=True)
    with pytest.raises(ec.AreaDeEnsaioInvalida) as exc_info:
        ec.validar_area_de_ensaio(tmp_path / relativo_da_area, tmp_path / "data", tmp_path / "repo")
    assert str(tmp_path) not in str(exc_info.value), "A mensagem nunca interpola o caminho."


def test_area_real_do_projeto_nunca_pode_ser_o_repositorio_nem_data():
    for proibida in (RAIZ, RAIZ / "data", RAIZ / "tests", RAIZ.parent):
        if proibida.is_dir():
            with pytest.raises(ec.AreaDeEnsaioInvalida):
                ec.validar_area_de_ensaio(proibida, RAIZ / "data", RAIZ)


@pytest.mark.parametrize("ensaio_id", ["rodada-s-01", "R1", "2026_02_03-a", "a" * 64])
def test_ensaio_id_valido(ensaio_id):
    assert ec.validar_ensaio_id(ensaio_id) == ensaio_id


@pytest.mark.parametrize("ensaio_id", ["", "..", "a/b", "a\\b", "-inicio", "com espaco", "a" * 65, None, 7, "x.y"])
def test_ensaio_id_invalido_nunca_vira_caminho(ensaio_id):
    with pytest.raises(ec.AreaDeEnsaioInvalida):
        ec.validar_ensaio_id(ensaio_id)


def test_preparar_rodada_cria_a_estrutura_fixa_e_nunca_reaproveita(tmp_path):
    base = ec.preparar_rodada(tmp_path, "rodada-1")
    assert sorted(p.name for p in base.iterdir()) == ["backup", "evidencias", "origem", "restauracao"]
    with pytest.raises(ec.AreaDeEnsaioInvalida):
        ec.preparar_rodada(tmp_path, "rodada-1")
    with pytest.raises(ec.AreaDeEnsaioInvalida):
        ec.diretorio_da_rodada(tmp_path, "rodada-1", "outro")


def test_origem_do_ensaio_precisa_ser_a_copia_congelada_de_uma_rodada(tmp_path):
    area = tmp_path / "area"
    base = ec.preparar_rodada(area, "rodada-1") if area.mkdir() is None else None
    assert ec.validar_origem_do_ensaio(base / "origem", area) == Path(os.path.realpath(base / "origem"))

    (area / "solta").mkdir()
    (tmp_path / "fora" / "rodada-1" / "origem").mkdir(parents=True)
    for origem in (base / "backup", base, area, area / "solta", tmp_path / "fora" / "rodada-1" / "origem",
                   base / "origem" / "lotes", None, ""):
        with pytest.raises(ec.AreaDeEnsaioInvalida):
            ec.validar_origem_do_ensaio(origem, area)


# ============================================================
# C4 - Inventario
# ============================================================

def test_inventario_lista_o_escopo_e_agrega_o_resto(instalacao):
    inventario = ec.inventariar(instalacao)
    assert [a.caminho_relativo for a in inventario.arquivos_do_escopo] == [
        f"correcoes_rejeitadas/2026-02-04/{UUID_A}.json",
        "lotes/NSI-20260203-000001/lote.json", "lotes/NSI-20260203-000002/lote.json"]
    assert inventario.fora_do_escopo_arquivos == 3
    assert inventario.fora_do_escopo_bytes == len(b'{"texto": "ola"}') + len(b'{"x": 1}') + len(b"%PDF")
    assert re.fullmatch(r"[0-9a-f]{64}", inventario.fora_do_escopo_resumo)


def test_resumo_do_inventario_nunca_contem_nome_de_arquivo_fora_do_escopo(instalacao):
    """Os nomes dos logs de resposta contem telefone."""
    resumo = ec.resumo_do_inventario(ec.inventariar(instalacao))
    texto = json.dumps(resumo, ensure_ascii=False)
    for proibido in (TELEFONE, "respostas", "saida_motor", "relatorio.pdf", NOME, str(instalacao)):
        assert proibido not in texto
    assert resumo["escopo"] == {"lotes": 2, "tentativas_recusadas": 1,
                                "bytes": sum(a["tamanho_bytes"] for a in resumo["arquivos_do_escopo"]),
                                "resumo": resumo["escopo"]["resumo"]}
    assert resumo["fora_do_escopo"]["arquivos"] == 3


def test_inventario_e_estavel_e_reconstruivel(instalacao):
    primeiro, segundo = ec.inventariar(instalacao), ec.inventariar(str(instalacao))
    assert primeiro == segundo
    assert ec.inventario_do_resumo(json.loads(json.dumps(ec.resumo_do_inventario(primeiro)))) == primeiro
    assert ec.comparar_inventarios(primeiro, segundo) == {
        "identicos": True, "escopo_identico": True, "fora_do_escopo_identico": True,
        "escopo_adicionados": [], "escopo_removidos": [], "escopo_alterados": []}


_ALTERACOES = {
    "lote_alterado": (lambda r: (r / "lotes/NSI-20260203-000002/lote.json").write_bytes(b"{} "),
                      {"escopo_alterados": ["lotes/NSI-20260203-000002/lote.json"]}),
    "lote_removido": (lambda r: (r / "lotes/NSI-20260203-000002/lote.json").unlink(),
                      {"escopo_removidos": ["lotes/NSI-20260203-000002/lote.json"]}),
    "lote_criado": (lambda r: _gravar(r, "lotes/NSI-20260203-000003/lote.json"),
                    {"escopo_adicionados": ["lotes/NSI-20260203-000003/lote.json"]}),
    "resposta_criada": (lambda r: _gravar(r, "respostas/5511900000000.json"), {}),
    "resposta_alterada": (lambda r: (r / f"respostas/{TELEFONE}.json").write_bytes(b'{"texto": "oi!"}'), {}),
    "resposta_renomeada": (lambda r: (r / f"respostas/{TELEFONE}.json").rename(r / "respostas/outro.json"), {}),
    "arquivo_fora_do_escopo_removido": (lambda r: (r / "pdfs/relatorio.pdf").unlink(), {}),
}


@pytest.mark.parametrize("caso", sorted(_ALTERACOES))
def test_prova_de_quiescencia_detecta_qualquer_mudanca(instalacao, caso):
    """Secao 23: I1 = I2 so quando NADA mudou - no escopo e fora dele."""
    alterar, escopo_esperado = _ALTERACOES[caso]
    antes = ec.inventariar(instalacao)
    alterar(instalacao)
    comparacao = ec.comparar_inventarios(antes, ec.inventariar(instalacao))

    assert comparacao["identicos"] is False
    assert comparacao["escopo_identico"] is (not escopo_esperado)
    assert comparacao["fora_do_escopo_identico"] is bool(escopo_esperado)
    for chave in ("escopo_adicionados", "escopo_removidos", "escopo_alterados"):
        assert comparacao[chave] == escopo_esperado.get(chave, [])
    assert TELEFONE not in json.dumps(comparacao), "A comparacao nunca devolve nome fora do escopo."


def test_inventariar_diretorio_inexistente_falha(tmp_path):
    with pytest.raises(ec.AreaDeEnsaioInvalida):
        ec.inventariar(tmp_path / "nao-existe")


# ============================================================
# C5 - Copia congelada
# ============================================================

def test_copia_leva_somente_o_escopo_byte_a_byte_e_somente_leitura(instalacao, tmp_path):
    destino = tmp_path / "origem"
    destino.mkdir()
    referencia = ec.inventariar(instalacao)
    resultado = ec.copiar_escopo(instalacao, destino, referencia)

    assert resultado == {"arquivos_copiados": 3, "bytes_copiados": sum(a.tamanho_bytes for a in referencia.arquivos_do_escopo),
                         "lotes": 2, "tentativas_recusadas": 1, "confere": True, "somente_leitura": True}
    copiados = sorted(p.relative_to(destino).as_posix() for p in destino.rglob("*") if p.is_file())
    assert copiados == [a.caminho_relativo for a in referencia.arquivos_do_escopo], "Minimizacao: nada fora do escopo."
    for arquivo in referencia.arquivos_do_escopo:
        copia = destino / arquivo.caminho_relativo
        assert copia.read_bytes() == (instalacao / arquivo.caminho_relativo).read_bytes()
        assert not (copia.stat().st_mode & stat.S_IWRITE), "A copia e somente leitura."
    assert il.enumerar_escopo(destino) == list(referencia.arquivos_do_escopo)


def test_copia_diverge_se_a_origem_mudou_depois_do_inventario(instalacao, tmp_path):
    """Falha F4: o inventario de referencia e o da pausa; se um arquivo mudou
    depois dele, a copia nao confere."""
    destino = tmp_path / "origem"
    destino.mkdir()
    referencia = ec.inventariar(instalacao)
    (instalacao / "lotes/NSI-20260203-000002/lote.json").write_bytes(_lote("NSI-20260203-000002", nome_lote="x"))
    with pytest.raises(ec.CopiaDivergente) as exc_info:
        ec.copiar_escopo(instalacao, destino, referencia)
    assert str(exc_info.value) == "a copia congelada nao confere com o inventario de referencia"


def test_copia_exige_destino_vazio_e_disjunto(instalacao, tmp_path):
    referencia = ec.inventariar(instalacao)
    ocupado = tmp_path / "ocupado"
    _gravar(ocupado, "x.txt")
    for destino in (ocupado, tmp_path / "nao-existe", instalacao, instalacao / "lotes"):
        with pytest.raises(ec.AreaDeEnsaioInvalida):
            ec.copiar_escopo(instalacao, destino, referencia)
    vazio = tmp_path / "vazio"
    vazio.mkdir()
    with pytest.raises(ec.AreaDeEnsaioInvalida):
        ec.copiar_escopo(tmp_path / "instalacao-inexistente", vazio, referencia)


# ============================================================
# C6 - Levantamento estrutural
# ============================================================

def test_levantamento_devolve_chaves_e_tipos_nunca_valores(instalacao):
    levantamento = ec.levantar_estrutura(instalacao)
    assert (levantamento["lotes"], levantamento["lotes_com_divergencia"]) == (2, 0)
    item = levantamento["detalhe"][0]
    assert item["legivel"] is True and item["lote_id_confere_com_o_diretorio"] is True
    assert item["tipos"] == {"lote_id": "texto", "criado_em": "texto", "clientes": "lista", "status": "texto"}
    assert item["clientes"]["chaves"] == ["nome", "produto", "registro_coleta_id", "telefone"]
    assert item["clientes"]["com_registro_coleta_id"] == 1

    texto = json.dumps(levantamento, ensure_ascii=False)
    for valor in (NOME, TELEFONE, "Produto Sintetico", "0f8fad5b-d9cb-469f-a165-70867728950e", "aguardando_d8"):
        assert valor not in texto, "O levantamento nunca devolve valor do documento."


_DIVERGENCIAS = {
    "chave_de_raiz_fora_da_lista": _lote("X", campo_novo=1),
    "chave_de_clientes_fora_da_lista": _lote("X", clientes=[{"registro_coleta_id": UUID_A, "email": "a@b"}]),
    "chave_de_clientes_invalidos_fora_da_lista": _lote("X", clientes_invalidos=[{"registro_coleta_id": UUID_A, "nome": "n"}]),
    "identidade_divergente": _lote("OUTRO"),
    "lote_id_nao_e_texto": _lote(7),
    "criado_em_nao_e_texto": _lote("X", criado_em=20260203),
    "clientes_nao_e_lista": _lote("X", clientes={}),
    "clientes_com_registro_que_nao_e_objeto": _lote("X", clientes=["texto"]),
    "registro_coleta_id_fora_do_formato": _lote("X", clientes=[{"registro_coleta_id": "nao-e-uuid"}]),
    "mistura_de_identidade": _lote("X", clientes=[{"registro_coleta_id": UUID_A}, {"nome": "n"}]),
    "historico_versoes_fora_do_formato": _lote("X", historico_versoes=[]),
    "raiz_nao_e_objeto": b"[1, 2]",
    "documento_ilegivel": b'{"lote_id": ',
    "documento_ilegivel_para_o_banco": b'{"lote_id": "X", "criado_em": "2026", "clientes": [], "nome_lote": "a\\u0000b"}',
}


@pytest.mark.parametrize("divergencia", sorted(_DIVERGENCIAS))
def test_levantamento_antecipa_divergencia_contra_as_listas_da_b5_2(tmp_path, divergencia):
    """Risco RT1: um lote real fora das listas seria recusado e nao
    preservado - o levantamento revela isso antes da importacao."""
    _gravar(tmp_path, "lotes/X/lote.json", _DIVERGENCIAS[divergencia])
    levantamento = ec.levantar_estrutura(tmp_path)
    assert divergencia in levantamento["divergencias"]
    assert levantamento["caminhos_com_divergencia"] == ["lotes/X/lote.json"]
    assert levantamento["lotes_sem_divergencia"] == 0


def test_levantamento_de_documento_com_bom_e_de_chave_muito_longa(tmp_path):
    _gravar(tmp_path, "lotes/X/lote.json", b"\xef\xbb\xbf" + _lote("X"))
    _gravar(tmp_path, "lotes/Y/lote.json", _lote("Y", **{"k" * 500: 1}))
    levantamento = ec.levantar_estrutura(tmp_path)
    assert levantamento["divergencias"]["documento_ilegivel"] == 1, "BOM: ilegivel como UTF-8 puro."
    assert levantamento["chaves_de_raiz_fora_da_lista"] == ["k" * 60], "Chave inesperada e truncada."


def test_levantamento_das_fixtures_da_b5():
    levantamento = ec.levantar_estrutura(RAIZ / "tests" / "fixtures" / "legado")
    assert levantamento["lotes"] == 8
    assert levantamento["caminhos_com_divergencia"] == [
        f"lotes/NSI-2026010{n}-A0000{n}/lote.json" for n in (5, 6, 7, 8)]
    assert levantamento["divergencias"] == {"chave_de_raiz_fora_da_lista": 1, "documento_ilegivel": 1,
                                            "identidade_divergente": 1, "mistura_de_identidade": 1}


def test_listas_fechadas_sao_as_mesmas_da_migration_0006():
    """As listas do item 6.2 existem em dois lugares: na funcao SQL e aqui.
    Este teste impede que se afastem."""
    fonte = (RAIZ / "migrations" / "versions" / "0006_importacao_legado.py").read_text(encoding="utf-8")

    def lista_sql(apos: str) -> set:
        trecho = fonte[fonte.index(apos):]
        return set(re.findall(r"'([a-z_]+)'", trecho[trecho.index("ARRAY["):trecho.index("]")]))

    assert lista_sql("FROM jsonb_object_keys(v_doc) AS k") == ec.CHAVES_DE_RAIZ_PERMITIDAS
    assert lista_sql("WHEN 'clientes' THEN ARRAY[") == ec.CHAVES_DE_CLIENTES_PERMITIDAS
    assert lista_sql("ELSE ARRAY[") == ec.CHAVES_DE_CLIENTES_INVALIDOS_PERMITIDAS


# ============================================================
# Evidencias e privacidade
# ============================================================

def test_evidencia_nunca_e_sobrescrita_e_o_indice_detecta_alteracao(tmp_path):
    ec.gravar_evidencia(tmp_path, "E7_levantamento.json", {"lotes": 2})
    with pytest.raises(ec.AreaDeEnsaioInvalida):
        ec.gravar_evidencia(tmp_path, "E7_levantamento.json", {"lotes": 3})
    for nome in ("indice.json", "../fora.json", "sem-extensao", "a/b.json", ""):
        with pytest.raises(ec.AreaDeEnsaioInvalida):
            ec.gravar_evidencia(tmp_path, nome, {})
    ec.gravar_evidencia(tmp_path, "E8_relatorio.json", {"ok": True})

    indice = ec.fechar_indice(tmp_path)
    assert indice["arquivos"] == 2 and re.fullmatch(r"[0-9a-f]{64}", indice["indice_sha256"])
    assert ec.conferir_indice(tmp_path) == {"confere": True, "indice_sha256": indice["indice_sha256"],
                                            "alterados": [], "ausentes": [], "nao_registrados": []}
    with pytest.raises(ec.AreaDeEnsaioInvalida):
        ec.fechar_indice(tmp_path)

    (tmp_path / "E8_relatorio.json").write_bytes(b'{"ok": false}')
    (tmp_path / "E7_levantamento.json").unlink()
    (tmp_path / "extra.json").write_bytes(b"{}")
    conferencia = ec.conferir_indice(tmp_path)
    assert conferencia["confere"] is False
    assert (conferencia["alterados"], conferencia["ausentes"], conferencia["nao_registrados"]) == (
        ["E8_relatorio.json"], ["E7_levantamento.json"], ["extra.json"])


def test_varredura_de_privacidade_aponta_o_arquivo_sem_devolver_o_valor(tmp_path):
    ec.gravar_evidencia(tmp_path, "limpa.json", {"lotes": 2})
    ec.gravar_evidencia(tmp_path, "vazada.json", {"observacao": f"contato de {NOME}"})
    varredura = ec.varrer_evidencias(tmp_path, [NOME, TELEFONE, "ab", "   ", None])
    assert varredura == {"arquivos_varridos": 2, "valores_procurados": 2,
                         "arquivos_com_valor_pessoal": ["vazada.json"], "sem_valor_pessoal": False}
    assert NOME not in json.dumps(varredura, ensure_ascii=False)
    assert ec.varrer_evidencias(tmp_path, [TELEFONE])["sem_valor_pessoal"] is True


# ============================================================
# Avaliacao da auditoria (Secao 28, partes A e B)
# ============================================================

PAPEIS = ("nsi_ensaio_migrator", "nsi_importacao")


def _auditoria_integra() -> dict:
    return {
        "a_revisao": {"banco": "nsi_ensaio", "revisao": "0006"},
        "a_catalogo": {"impressao_digital": "abc"},
        "a_objetos_invalidos": {"indices_invalidos": 0, "constraints_nao_validadas": 0, "triggers_desabilitadas": 0,
                                "security_definer_sem_search_path_fixo": 0, "funcoes_com_execute_de_public": 0,
                                "objetos_com_outro_dono": 0},
        "a_concessoes": {"connect_no_banco": sorted(PAPEIS), "usage_no_schema": sorted(PAPEIS),
                         "concessoes_em_tabela": 0,
                         "execute_de_nsi_importacao": sorted(ec.QUATRO_FUNCOES_DE_IMPORTACAO)},
        "b_tabelas_que_devem_estar_vazias": {"eventos_lote": 0, "eventos_registro_coleta": 0, "eventos_claim": 0,
                                             "claims": 0, "comandos_idempotentes": 0},
        "b_execucoes": {"execucoes": 1, "concluidas": 1, "logins": ["nsi_importacao"],
                        "fusos_declarados": ["America/Sao_Paulo"], "conclusoes_com_total_divergente": 0,
                        "conclusoes_com_sha256_divergente": 0},
        "b_invariantes": {"promovidos_de_geracao_anterior_a_a2": 0, "snapshots_com_sha256_divergente": 0},
    }


def _avaliar(resultado, fuso="America/Sao_Paulo", referencia="abc"):
    return ec.avaliar_auditoria(resultado, "nsi_ensaio", PAPEIS, "nsi_importacao", fuso, referencia)


def test_auditoria_integra_e_aprovada():
    assert _avaliar(_auditoria_integra()) == {"aprovada": True, "divergencias": []}


def test_execucao_sem_fuso_e_avaliada_contra_fuso_nulo():
    resultado = _auditoria_integra()
    resultado["b_execucoes"]["fusos_declarados"] = [None]
    assert _avaliar(resultado, fuso=None)["aprovada"] is True
    assert _avaliar(resultado)["divergencias"] == ["b_fuso_declarado"]


_DEFEITOS = {
    "a_banco_ou_revisao": lambda r: r["a_revisao"].update({"revisao": "0005"}),
    "a_objeto_invalido": lambda r: r["a_objetos_invalidos"].update({"funcoes_com_execute_de_public": 1}),
    "a_connect_fora_do_previsto": lambda r: r["a_concessoes"].update({"connect_no_banco": sorted(PAPEIS + ("nsi_aplicacao",))}),
    "a_usage_fora_do_previsto": lambda r: r["a_concessoes"].update({"usage_no_schema": ["nsi_importacao"]}),
    "a_concessao_em_tabela": lambda r: r["a_concessoes"].update({"concessoes_em_tabela": 1}),
    "a_execute_fora_do_previsto": lambda r: r["a_concessoes"]["execute_de_nsi_importacao"].append("fn_criar_claim"),
    "a_catalogo_diferente_do_de_teste": lambda r: r["a_catalogo"].update({"impressao_digital": "outra"}),
    "b_evento_recibo_ou_claim": lambda r: r["b_tabelas_que_devem_estar_vazias"].update({"claims": 1}),
    "b_execucao_unica_e_concluida": lambda r: r["b_execucoes"].update({"concluidas": 0}),
    "b_identidade_tecnica": lambda r: r["b_execucoes"].update({"logins": ["nsi_ensaio_migrator"]}),
    "b_fuso_declarado": lambda r: r["b_execucoes"].update({"fusos_declarados": ["UTC"]}),
    "b_total_de_arquivos": lambda r: r["b_execucoes"].update({"conclusoes_com_total_divergente": 1}),
    "b_sha256_do_manifesto": lambda r: r["b_execucoes"].update({"conclusoes_com_sha256_divergente": 1}),
    "b_promovidos_de_geracao_anterior_a_a2": lambda r: r["b_invariantes"].update({"promovidos_de_geracao_anterior_a_a2": 1}),
    "b_snapshots_com_sha256_divergente": lambda r: r["b_invariantes"].update({"snapshots_com_sha256_divergente": 2}),
}


@pytest.mark.parametrize("codigo", sorted(_DEFEITOS))
def test_cada_divergencia_da_auditoria_reprova_com_codigo_fixo(codigo):
    resultado = _auditoria_integra()
    _DEFEITOS[codigo](resultado)
    assert _avaliar(resultado) == {"aprovada": False, "divergencias": [codigo]}


def test_catalogo_nao_comparado_nunca_e_aprovado():
    assert _avaliar(_auditoria_integra(), referencia=None) == {
        "aprovada": False, "divergencias": ["a_catalogo_nao_comparado"]}


# ============================================================
# C3 - Gate do executor por ambiente e regra de origem
# ============================================================

def test_pares_de_ambiente_e_banco_sao_fechados():
    assert executor.BANCO_POR_AMBIENTE == {"test": "nsi_test", "ensaio": "nsi_ensaio"}
    assert executor.validar_ambiente("test") == "nsi_test"
    assert executor.validar_ambiente("ensaio") == "nsi_ensaio"
    for ambiente in ("development", "production", "", "ENSAIO", "staging"):
        with pytest.raises(executor.IdentidadeNaoComprovada):
            executor.validar_ambiente(ambiente)


@pytest.mark.parametrize("banco,banco_esperado,aceito", [
    ("nsi_test", "nsi_test", True), ("nsi_ensaio", "nsi_ensaio", True),
    ("nsi_ensaio", "nsi_test", False), ("nsi_test", "nsi_ensaio", False),      # cruzamentos
    ("nsi_dev", "nsi_test", False), ("nsi_dev", "nsi_ensaio", False),
    ("nsi_dev", "nsi_dev", False), ("postgres", "postgres", False),            # banco fora dos pares
])
def test_gate_recusa_todo_cruzamento_de_ambiente_e_banco(banco, banco_esperado, aceito):
    argumentos = (banco, "127.0.0.1", 5432, "nsi_importacao")
    if aceito:
        executor.validar_identidade(*argumentos, banco_esperado=banco_esperado)
    else:
        with pytest.raises(executor.IdentidadeNaoComprovada) as exc_info:
            executor.validar_identidade(*argumentos, banco_esperado=banco_esperado)
        assert "nsi_dev" not in str(exc_info.value) and "postgres" not in str(exc_info.value)


def test_gate_do_ensaio_mantem_servidor_porta_e_usuario():
    for identidade in (("nsi_ensaio", "10.0.0.5", 5432, "nsi_importacao"),
                       ("nsi_ensaio", "127.0.0.1", 5433, "nsi_importacao"),
                       ("nsi_ensaio", "127.0.0.1", 5432, "nsi_ensaio_migrator"),
                       ("nsi_ensaio", "127.0.0.1", 5432, "postgres")):
        with pytest.raises(executor.IdentidadeNaoComprovada):
            executor.validar_identidade(*identidade, banco_esperado="nsi_ensaio")


def test_origem_dentro_do_diretorio_de_dados_e_recusada_em_qualquer_ambiente(tmp_path, monkeypatch):
    dados = tmp_path / "data"
    (dados / "lotes").mkdir(parents=True)
    (dados / "copia" / "origem").mkdir(parents=True)
    monkeypatch.setattr(executor.Config, "DATA_DIR", dados)
    for origem in (dados / "lotes", dados / "copia" / "origem"):
        for ambiente in ("test", "ensaio"):
            with pytest.raises(il.OrigemInvalida) as exc_info:
                executor.validar_origem_do_ambiente(origem, ambiente)
            assert str(exc_info.value) == "a origem nao pode estar dentro do diretorio de dados da aplicacao"


def test_no_ensaio_a_origem_precisa_estar_na_area_de_ensaio(tmp_path, monkeypatch):
    area = tmp_path / "area"
    area.mkdir()
    base = ec.preparar_rodada(area, "rodada-1")
    fora = tmp_path / "fora"
    fora.mkdir()
    monkeypatch.setattr(executor.Config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(executor.Config, "NSI_ENSAIO_DIR", str(area))

    assert executor.validar_origem_do_ambiente(base / "origem", "ensaio").name == "origem"
    assert executor.validar_origem_do_ambiente(fora, "test") == fora, "Em 'test' a regra da area nao se aplica."
    for origem in (fora, base / "backup", area):
        with pytest.raises(ec.AreaDeEnsaioInvalida):
            executor.validar_origem_do_ambiente(origem, "ensaio")


def test_no_ensaio_sem_a_variavel_da_area_o_executor_falha_fechado(tmp_path, monkeypatch, capsys):
    origem = tmp_path / "x" / "rodada-1" / "origem"
    origem.mkdir(parents=True)
    monkeypatch.setattr(executor.Config, "NSI_DATABASE_ENV", "ensaio")
    monkeypatch.setattr(executor.Config, "NSI_ENSAIO_DIR", "")
    monkeypatch.setattr(executor.Config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(executor.psycopg, "connect", lambda *a, **k: pytest.fail("o executor tentou conectar"))

    assert executor.main(["--origem", str(origem)]) == executor.SAIDA_RECUSADA_OU_ABORTADA
    saida = json.loads(capsys.readouterr().out)
    assert saida == {"executada": False, "importacao_id_aberta": None,
                     "motivo": "area de ensaio nao informada - nao existe valor padrao"}


def test_no_ensaio_a_conexao_usa_a_url_de_ensaio_e_a_falha_nao_expoe_dsn(tmp_path, monkeypatch, capsys):
    area = tmp_path / "area"
    area.mkdir()
    base = ec.preparar_rodada(area, "rodada-1")
    pedidos = []

    def resolver(papel, ambiente):
        pedidos.append((papel, ambiente))
        return "postgresql://nsi_importacao:senha-secreta@localhost:5432/nsi_ensaio"

    def falhar(*args, **kwargs):
        raise RuntimeError("falha: postgresql://nsi_importacao:senha-secreta@localhost:5432/nsi_ensaio")

    monkeypatch.setattr(executor.Config, "NSI_DATABASE_ENV", "ensaio")
    monkeypatch.setattr(executor.Config, "NSI_ENSAIO_DIR", str(area))
    monkeypatch.setattr(executor.Config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(executor, "resolver_url_banco_papel", resolver)
    monkeypatch.setattr(executor.psycopg, "connect", falhar)

    assert executor.main(["--origem", str(base / "origem")]) == executor.SAIDA_RECUSADA_OU_ABORTADA
    saida = capsys.readouterr()
    assert pedidos == [("nsi_importacao", "ensaio")]
    assert "senha-secreta" not in saida.out + saida.err
    assert json.loads(saida.out)["motivo"] == "nao foi possivel conectar como nsi_importacao em nsi_ensaio"


# ============================================================
# Linha de comando do ensaio
# ============================================================

def _cli(capsys, *argumentos) -> tuple:
    codigo = cli.main(list(argumentos))
    return codigo, json.loads(capsys.readouterr().out)


def test_todo_comando_falha_fechado_sem_a_area_de_ensaio(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(cli.Config, "NSI_ENSAIO_DIR", "")
    for argumentos in (("preparar", "--ensaio-id", "r1"), ("levantamento", "--ensaio-id", "r1"),
                       ("inventario", "--ensaio-id", "r1", "--rotulo", "I1", "--diretorio", str(tmp_path)),
                       ("indice", "--ensaio-id", "r1"), ("auditar", "--ensaio-id", "r1")):
        codigo, saida = _cli(capsys, *argumentos)
        assert codigo == cli.SAIDA_RECUSADA
        assert saida["motivo"] == "area de ensaio nao informada - nao existe valor padrao"


def test_roteiro_de_pausa_copia_e_levantamento_pela_linha_de_comando(area, instalacao, capsys):
    """Passos R3 a R8 sobre uma instalacao sintetica: inventarios, prova de
    quiescencia, copia congelada, levantamento e indice de evidencias."""
    assert _cli(capsys, "preparar", "--ensaio-id", "r1")[0] == 0
    for rotulo in ("I1", "I2"):
        codigo, saida = _cli(capsys, "inventario", "--ensaio-id", "r1", "--rotulo", rotulo,
                             "--diretorio", str(instalacao))
        assert codigo == 0 and saida["escopo"]["lotes"] == 2
        assert "duracao_segundos" in saida
    codigo, saida = _cli(capsys, "comparar", "--ensaio-id", "r1", "--a", "I1", "--b", "I2")
    assert (codigo, saida["identicos"]) == (0, True)

    codigo, saida = _cli(capsys, "copiar", "--ensaio-id", "r1", "--instalacao", str(instalacao), "--referencia", "I1")
    assert (codigo, saida["confere"], saida["arquivos_copiados"]) == (0, True, 3)
    codigo, saida = _cli(capsys, "levantamento", "--ensaio-id", "r1")
    assert (codigo, saida["lotes"], saida["lotes_com_divergencia"]) == (0, 2, 0)
    assert "detalhe" not in saida

    # Depois da copia, a instalacao muda: I3 != I1 e reprovacao (falha F8).
    (instalacao / "lotes/NSI-20260203-000001/lote.json").write_bytes(b"{}")
    _cli(capsys, "inventario", "--ensaio-id", "r1", "--rotulo", "I3", "--diretorio", str(instalacao))
    codigo, saida = _cli(capsys, "comparar", "--ensaio-id", "r1", "--a", "I1", "--b", "I3")
    assert (codigo, saida["identicos"]) == (cli.SAIDA_REPROVADA, False)

    codigo, saida = _cli(capsys, "indice", "--ensaio-id", "r1")
    assert codigo == 0 and saida["arquivos"] == 7
    evidencias = area / "r1" / "evidencias"
    assert ec.conferir_indice(evidencias)["confere"] is True
    todas = b"".join(p.read_bytes() for p in evidencias.iterdir())
    for proibido in (TELEFONE.encode(), NOME.encode(), b"respostas", str(instalacao).encode()):
        assert proibido not in todas, "Nenhuma evidencia contem valor pessoal, nome fora do escopo ou caminho absoluto."


def test_gerar_sintetico_usa_por_padrao_a_composicao_da_d10(area, capsys):
    """Decisao D10: as fixtures mais pelo menos 20 lotes por geracao."""
    assert cli.LOTES_EXTRAS_DA_RODADA_S == 20
    _cli(capsys, "preparar", "--ensaio-id", "s1")
    codigo, saida = _cli(capsys, "gerar-sintetico", "--ensaio-id", "s1", "--fuso", "America/Sao_Paulo")
    assert codigo == 0
    for geracao in ("anterior_a1", "a1", "a2", "a3"):
        assert sum(saida["por_geracao_e_destino"][geracao].values()) >= 20, geracao
    assert saida["por_geracao_e_destino"]["a2"]["promovido"] >= 20
    assert saida["por_geracao_e_destino"]["a3"]["promovido"] >= 20
    assert _cli(capsys, "gerar-sintetico", "--ensaio-id", "s1")[0] == cli.SAIDA_RECUSADA, "Nunca regenera."


def test_comandos_recusam_rodada_inexistente_e_evidencia_repetida(area, instalacao, capsys):
    codigo, saida = _cli(capsys, "levantamento", "--ensaio-id", "nao-existe")
    assert (codigo, saida["motivo"]) == (cli.SAIDA_RECUSADA, "rodada inexistente - execute 'preparar' antes")
    _cli(capsys, "preparar", "--ensaio-id", "r1")
    assert _cli(capsys, "preparar", "--ensaio-id", "r1")[0] == cli.SAIDA_RECUSADA
    argumentos = ("inventario", "--ensaio-id", "r1", "--rotulo", "I1", "--diretorio", str(instalacao))
    assert _cli(capsys, *argumentos)[0] == 0
    assert _cli(capsys, *argumentos)[0] == cli.SAIDA_RECUSADA, "Uma evidencia nunca e sobrescrita."
    assert _cli(capsys, "comparar", "--ensaio-id", "r1", "--a", "I1", "--b", "I9")[0] == cli.SAIDA_RECUSADA
    assert _cli(capsys, "inventario", "--ensaio-id", "r1", "--rotulo", "../x", "--diretorio", str(instalacao))[0] == 2


def test_falha_inesperada_da_linha_de_comando_nao_expoe_caminho(area, capsys, monkeypatch):
    _cli(capsys, "preparar", "--ensaio-id", "r1")

    def explodir(*args, **kwargs):
        raise RuntimeError(f"erro em {area} com {NOME}")

    monkeypatch.setattr(cli.ec, "levantar_estrutura", explodir)
    codigo = cli.main(["levantamento", "--ensaio-id", "r1"])
    saida = capsys.readouterr().out
    assert codigo == cli.SAIDA_RECUSADA
    assert json.loads(saida) == {"comando": "levantamento", "executado": False, "motivo": "falha_inesperada",
                                 "tipo": "RuntimeError"}
    assert NOME not in saida


# ============================================================
# C7 - Leitor do arquivo de auditoria e gate da auditoria
# ============================================================

def test_arquivo_de_auditoria_tem_somente_consultas_select():
    consultas = cli.ler_consultas()
    assert sorted(consultas) == [
        "a_catalogo", "a_concessoes", "a_objetos_invalidos", "a_revisao", "b_arquivos", "b_execucoes",
        "b_invariantes", "b_tabelas_que_devem_estar_vazias", "c_intervalo_de_criado_em", "c_lotes_em_andamento",
        "c_lotes_por_geracao_e_destino", "c_motivos", "c_registros_por_classificacao", "c_status_literal_por_geracao"]
    proibidos = re.compile(r"\b(INSERT|UPDATE|DELETE|TRUNCATE|DROP|ALTER|CREATE|GRANT|REVOKE|COPY|MERGE|LOCK|"
                           r"BEGIN|COMMIT|ROLLBACK|SET|RESET|EXECUTE|CALL|DO)\b", re.IGNORECASE)
    for nome, sql in consultas.items():
        sem_literais = re.sub(r"'(?:[^']|'')*'", "''", sql)
        assert sql.upper().startswith("SELECT"), nome
        assert not proibidos.search(sem_literais), f"{nome}: a auditoria e somente leitura."
        assert ";" not in sql, nome


@pytest.mark.parametrize("conteudo", [
    "-- @consulta a\nUPDATE x SET y = 1;\n",
    "-- @consulta a\nSELECT 1; DELETE FROM x;\n",
    "-- @consulta a\nSELECT 1;\n-- @consulta a\nSELECT 2;\n",
    "-- so comentario\n",
    "-- @consulta a\n-- vazio\n",
])
def test_leitor_recusa_arquivo_de_auditoria_que_nao_seja_somente_select(tmp_path, conteudo):
    caminho = tmp_path / "auditoria.sql"
    caminho.write_text(conteudo, encoding="utf-8")
    with pytest.raises(cli.EnsaioRecusado):
        cli.ler_consultas(caminho)


def test_auditoria_e_quantificacao_nao_selecionam_coluna_pessoal():
    """A auditoria le o snapshot so para contar: nenhuma consulta devolve
    conteudo de registro. O unico acesso a campos pessoais e o que aplica as
    evidencias de disparo do item 6.3, dentro de um EXISTS."""
    for nome, sql in cli.ler_consultas().items():
        assert "conteudo_bruto" not in sql, nome
        assert "manifesto_canonico" not in sql or "sha256(c.manifesto_canonico)" in sql, nome
        for campo in ("'nome'", "'telefone'", "'produto'", "'nome_bruto'", "'whatsapp_bruto'"):
            assert campo not in sql, f"{nome} referencia {campo}"


@pytest.mark.parametrize("identidade", [
    ("nsi_test", "127.0.0.1", 5432, "nsi_ensaio_migrator"),
    ("nsi_dev", "127.0.0.1", 5432, "nsi_ensaio_migrator"),
    ("nsi_ensaio", "10.1.1.1", 5432, "nsi_ensaio_migrator"),
    ("nsi_ensaio", "127.0.0.1", 5433, "nsi_ensaio_migrator"),
    ("nsi_ensaio", "127.0.0.1", 5432, "nsi_test_migrator"),
    ("nsi_ensaio", "127.0.0.1", 5432, "nsi_importacao"),
    ("nsi_ensaio", "127.0.0.1", 5432, "postgres"),
])
def test_gate_da_auditoria_recusa_qualquer_divergencia(identidade):
    with pytest.raises(cli.EnsaioRecusado):
        cli.validar_identidade_da_auditoria(*identidade)
    cli.validar_identidade_da_auditoria("nsi_ensaio", "::1/128", 5432, "nsi_ensaio_migrator")


def test_auditar_sem_url_de_ensaio_e_recusado_sem_expor_dsn(area, capsys, monkeypatch):
    _cli(capsys, "preparar", "--ensaio-id", "r1")
    monkeypatch.setattr(cli.Config, "ENSAIO_DATABASE_URL", "")
    codigo, saida = _cli(capsys, "auditar", "--ensaio-id", "r1")
    assert codigo == cli.SAIDA_RECUSADA
    assert saida["motivo"] == "nao foi possivel conectar como o migrator de ensaio em nsi_ensaio"


def test_modulos_do_ensaio_sao_puros_e_nunca_conectam_a_nsi_dev():
    for arquivo in ("core/ensaio_corte.py", "core/ensaio_sintetico.py"):
        fonte = (RAIZ / arquivo).read_text(encoding="utf-8")
        for proibido in ("import psycopg", "from psycopg", "import config", "from config", "Config.", "os.environ",
                         "os.getenv", "subprocess"):
            assert proibido not in fonte, f"{arquivo}: {proibido}"
    fonte_da_cli = (RAIZ / "scripts" / "ensaio_corte.py").read_text(encoding="utf-8")
    assert 'resolver_url_banco("development")' not in fonte_da_cli
    assert "DATABASE_URL" not in fonte_da_cli.split('"""', 2)[2].replace("ENSAIO_DATABASE_URL", "").replace(
        "TEST_DATABASE_URL", "")
