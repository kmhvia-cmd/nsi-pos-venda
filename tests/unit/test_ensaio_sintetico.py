# -*- coding: utf-8 -*-
"""
NSI - tests/unit/test_ensaio_sintetico.py
(Sprint B, B6.2 - SPRINT-B6-ESPECIFICACAO-ENSAIO-DE-CORTE.md, Secoes 9 e
17, componente C8; decisao D10)

Testes UNITARIOS, sem banco, do gerador da instalacao sintetica da Rodada
S: composicao exigida pela D10, determinismo, destinos esperados e
ausencia de dado real. Que os destinos esperados sao os que o banco
realmente produz e comprovado em tests/integration/test_ensaio_b6.py.
"""
import json
from pathlib import Path

import pytest

from core import ensaio_corte as ec
from core import ensaio_sintetico as es
from core import importacao_legado as il

RAIZ = Path(__file__).resolve().parents[2]
FIXTURES = RAIZ / "tests" / "fixtures" / "legado"
SP = "America/Sao_Paulo"


def _gerar(tmp_path, nome="instalacao", **argumentos) -> tuple:
    destino = tmp_path / nome
    destino.mkdir()
    return destino, es.gerar_instalacao_sintetica(destino, FIXTURES, **argumentos)


def _pares(esperado) -> set:
    return {(e["geracao"], e["destino"], e["motivo"]) for e in esperado}


def test_composicao_exercita_geracoes_destinos_recusas_e_promocoes(tmp_path):
    """Decisao D10 e criterio da Rodada S (Secao 9)."""
    _, esperado = _gerar(tmp_path, fuso=SP)
    pares = _pares(esperado)

    assert {g for g, _, _ in pares} == {"anterior_a1", "a1", "a2", "a3", "formato_desconhecido", None}
    assert {d for _, d, _ in pares} == {"preservado", "promovido", "recusado"}
    assert ("a2", "promovido", None) in pares and ("a3", "promovido", None) in pares
    assert {m for _, d, m in pares if d == "recusado"} == {
        "documento_ilegivel", "identidade_divergente", "formato_desconhecido"}
    assert {m for _, d, m in pares if d == "preservado"} == {
        "geracao_nao_promovivel", "evidencia_de_disparo", "lote_id_legado_invalido", "m0_invalido",
        "m0_inexistente_ou_ambiguo", "identidade_repetida", "colisao_de_identidade", "totais_incoerentes",
        "historico_incoerente", "projecao_incompativel"}


def test_sem_fuso_nenhum_lote_e_esperado_como_promovido(tmp_path):
    _, esperado = _gerar(tmp_path, fuso=None)
    assert "promovido" not in {e["destino"] for e in esperado}
    motivos_a2_a3 = {e["motivo"] for e in esperado if e["geracao"] in ("a2", "a3")}
    assert motivos_a2_a3 == {"fuso_nao_declarado"}, "Sem fuso, o criterio 'fuso_nao_declarado' vem antes dos demais."
    assert {e["motivo"] for e in esperado if e["geracao"] in ("anterior_a1", "a1")} == {"geracao_nao_promovivel"}


def test_caso_de_horario_de_verao_so_existe_para_o_fuso_em_que_foi_escolhido(tmp_path):
    _, com_sp = _gerar(tmp_path, "a", fuso=SP)
    _, com_utc = _gerar(tmp_path, "b", fuso="UTC")
    assert "m0_inexistente_ou_ambiguo" in {e["motivo"] for e in com_sp}
    assert "m0_inexistente_ou_ambiguo" not in {e["motivo"] for e in com_utc}
    assert len(com_sp) == len(com_utc) + 1


def test_esperado_cobre_exatamente_os_lotes_gerados(tmp_path):
    destino, esperado = _gerar(tmp_path, fuso=SP)
    lotes = [a.caminho_relativo for a in il.enumerar_escopo(destino) if a.tipo == "lote"]
    assert [e["caminho_relativo"] for e in esperado] == lotes, "Um esperado por lote, na ordem do caminho."
    tentativas = [a for a in il.enumerar_escopo(destino) if a.tipo == "tentativa_recusada"]
    assert len(tentativas) == 2, "A da fixture e uma gerada - so entram no manifesto."


def test_fixtures_existentes_sao_copiadas_byte_a_byte(tmp_path):
    destino, esperado = _gerar(tmp_path, fuso=SP)
    for arquivo in il.enumerar_escopo(FIXTURES):
        assert (destino / arquivo.caminho_relativo).read_bytes() == (FIXTURES / arquivo.caminho_relativo).read_bytes()
    das_fixtures = {e["caminho_relativo"]: (e["geracao"], e["destino"], e["motivo"]) for e in esperado
                    if "-A0000" in e["caminho_relativo"]}
    assert das_fixtures == {
        "lotes/NSI-20260101-A00001/lote.json": ("anterior_a1", "preservado", "geracao_nao_promovivel"),
        "lotes/NSI-20260102-A00002/lote.json": ("a1", "preservado", "geracao_nao_promovivel"),
        "lotes/NSI-20260103-A00003/lote.json": ("a2", "promovido", None),
        "lotes/NSI-20260104-A00004/lote.json": ("a3", "promovido", None),
        "lotes/NSI-20260105-A00005/lote.json": ("formato_desconhecido", "recusado", "formato_desconhecido"),
        "lotes/NSI-20260106-A00006/lote.json": ("formato_desconhecido", "recusado", "formato_desconhecido"),
        "lotes/NSI-20260107-A00007/lote.json": (None, "recusado", "documento_ilegivel"),
        "lotes/NSI-20260108-A00008/lote.json": (None, "recusado", "identidade_divergente"),
    }


def test_geracao_e_deterministica_para_a_mesma_semente(tmp_path):
    a, esperado_a = _gerar(tmp_path, "a", fuso=SP, semente=7)
    b, esperado_b = _gerar(tmp_path, "b", fuso=SP, semente=7)
    c, _ = _gerar(tmp_path, "c", fuso=SP, semente=8)
    assert esperado_a == esperado_b
    assert ec.inventariar(a) == ec.inventariar(b)
    assert ec.inventariar(a) != ec.inventariar(c)


def test_lotes_extras_aumentam_cada_geracao(tmp_path):
    _, poucos = _gerar(tmp_path, "a", fuso=SP, lotes_extras=1)
    _, muitos = _gerar(tmp_path, "b", fuso=SP, lotes_extras=4)
    assert len(muitos) - len(poucos) == 3 * 4


def test_instalacao_tem_ruido_fora_do_escopo_que_nunca_e_copiado(tmp_path):
    """O ruido existe para exercitar o inventario agregado e a minimizacao
    da copia congelada."""
    destino, _ = _gerar(tmp_path, fuso=SP)
    inventario = ec.inventariar(destino)
    assert inventario.fora_do_escopo_arquivos >= 4
    assert (destino / "respostas").is_dir()

    origem = tmp_path / "origem"
    origem.mkdir()
    ec.copiar_escopo(destino, origem, inventario)
    assert not (origem / "respostas").exists() and not (origem / "pdfs").exists()
    assert ec.inventariar(origem).fora_do_escopo_arquivos == 0


def test_levantamento_estrutural_antecipa_as_recusas_esperadas(tmp_path):
    """Todo lote que o gerador espera como recusado tem divergencia no
    levantamento; nenhum lote esperado como preservado ou promovido tem."""
    destino, esperado = _gerar(tmp_path, fuso=SP)
    com_divergencia = set(ec.levantar_estrutura(destino)["caminhos_com_divergencia"])
    assert com_divergencia == {e["caminho_relativo"] for e in esperado if e["destino"] == "recusado"}


def test_todo_valor_pessoal_gerado_e_sintetico_e_marcado(tmp_path):
    destino, esperado = _gerar(tmp_path, fuso=SP)
    for item in esperado:
        try:
            documento = json.loads((destino / item["caminho_relativo"]).read_bytes())
        except ValueError:
            continue
        for lista in ("clientes", "clientes_invalidos"):
            for registro in documento.get(lista, []):
                for campo in ("nome", "nome_bruto", "produto", "produto_bruto"):
                    if registro.get(campo):
                        assert "Sintetic" in registro[campo]
    texto = json.dumps(esperado, ensure_ascii=False)
    for valor in es.VALORES_PESSOAIS_SINTETICOS:
        assert valor not in texto, "Os destinos esperados nao carregam valor pessoal."


def test_resumo_do_esperado_tem_a_forma_do_relatorio_do_executor(tmp_path):
    _, esperado = _gerar(tmp_path, fuso=SP)
    resumo = es.resumir_esperado(esperado)
    assert resumo["lotes"] == len(esperado)
    assert sum(sum(d.values()) for d in resumo["por_geracao_e_destino"].values()) == len(esperado)
    assert resumo["por_geracao_e_destino"]["nao_classificado"] == {"recusado": 4}
    assert resumo["motivos_de_recusa"] == {"documento_ilegivel": 2, "formato_desconhecido": 4,
                                           "identidade_divergente": 2}
    assert "promovido" not in resumo["motivos_de_nao_promocao"]


def test_comparacao_com_o_esperado_aponta_cada_tipo_de_divergencia():
    esperado = [{"caminho_relativo": "lotes/A/lote.json", "geracao": "a2", "destino": "promovido", "motivo": None},
                {"caminho_relativo": "lotes/B/lote.json", "geracao": "a1", "destino": "preservado",
                 "motivo": "geracao_nao_promovivel"}]
    obtido = [dict(e, constraint_violada=None) for e in esperado]
    assert es.comparar_com_esperado(esperado, obtido) == {
        "confere": True, "esperados": 2, "obtidos": 2, "divergentes": [], "ausentes": [], "inesperados": []}

    divergente = [dict(obtido[0], destino="preservado", motivo="m0_invalido"), obtido[1]]
    assert es.comparar_com_esperado(esperado, divergente)["divergentes"] == ["lotes/A/lote.json"]
    assert es.comparar_com_esperado(esperado, obtido[:1])["ausentes"] == ["lotes/B/lote.json"]
    extra = obtido + [{"caminho_relativo": "lotes/C/lote.json", "geracao": "a1", "destino": "preservado", "motivo": "x"}]
    resultado = es.comparar_com_esperado(esperado, extra)
    assert (resultado["confere"], resultado["inesperados"]) == (False, ["lotes/C/lote.json"])


def test_destino_precisa_existir_vazio_e_as_fixtures_precisam_estar_completas(tmp_path):
    ocupado = tmp_path / "ocupado"
    ocupado.mkdir()
    (ocupado / "x").write_bytes(b"")
    for destino in (ocupado, tmp_path / "nao-existe"):
        with pytest.raises(ValueError):
            es.gerar_instalacao_sintetica(destino, FIXTURES)
    vazio = tmp_path / "vazio"
    vazio.mkdir()
    with pytest.raises(ValueError):
        es.gerar_instalacao_sintetica(vazio, tmp_path)


def test_segunda_passada_altera_um_unico_lote_preservado(tmp_path):
    destino, _ = _gerar(tmp_path, fuso=SP)
    origem = tmp_path / "origem"
    origem.mkdir()
    ec.copiar_escopo(destino, origem, ec.inventariar(destino))
    segunda = tmp_path / "segunda"
    segunda.mkdir()

    alterados = es.origem_da_segunda_passada(origem, segunda)
    comparacao = ec.comparar_inventarios(ec.inventariar(origem), ec.inventariar(segunda))
    assert alterados == ["lotes/NSI-20260102-A00002/lote.json"]
    assert comparacao["escopo_alterados"] == alterados
    assert comparacao["escopo_adicionados"] == comparacao["escopo_removidos"] == []
