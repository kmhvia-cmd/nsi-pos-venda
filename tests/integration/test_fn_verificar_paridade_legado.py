# -*- coding: utf-8 -*-
"""
NSI - tests/integration/test_fn_verificar_paridade_legado.py
(Sprint B, B5.4 - ADR-010, Secoes 9.3, 13.5 e 19; Especificacao Tecnica,
B5.2, itens 5.1, 14 e 17)

Testes de integracao REAIS contra PostgreSQL, exclusivamente contra
nsi_test, de fn_verificar_paridade_legado: paridade campo a campo, somente
com booleanos e contagens; deteccao de alteracao do snapshot e da projecao;
manifesto conferido nos dois sentidos; lote evoluido no fluxo novo;
execucao nao concluida; lote 'ja_importado' reverificado no snapshot
original.

SOMENTE DADOS SINTETICOS. Todos os testes rodam numa transacao do migrator
de teste sob SET LOCAL ROLE nsi_eventos_owner e terminam em ROLLBACK -
inclusive o de lote evoluido, que exercita o fluxo novo sobre lote
promovido (B5.2, item 17).

A conferencia do SHA-256 de cada arquivo de ORIGEM contra o registrado e
a parte do executor na paridade (item 14) e pertence a B5.5.
"""
import json

import psycopg
import pytest

from tests.apoio_b5 import (
    FUSO_PADRAO,
    assert_sem_valor_pessoal,
    caminho_do_lote,
    concluir,
    doc_a1,
    doc_a2,
    doc_a3,
    doc_anterior_a1,
    entrada_de_lote,
    entrada_de_tentativa_recusada,
    importar,
    importar_bytes,
    importar_e_concluir,
    iniciar,
    manifesto_canonico,
    paridade,
    serializar,
    sha256_hex,
    uuid_texto,
)

pytestmark = pytest.mark.pg_integration

VERIFICACOES_DO_SNAPSHOT = ("documento_sha256_confere", "quantidade_registros_confere", "conteudo_registros_confere")
VERIFICACOES_DA_PROJECAO = ("projecao_registros_confere", "totais_conferem", "recebido_em_confere")
VERIFICACOES_DO_PROMOVIDO = ("sem_evento_da_importacao", "prova_de_origem_confere")
CHAVES_DO_LOTE = {"caminho_relativo", "lote_id_legado", "destino", "evoluido_no_fluxo_novo",
                  "registro_confere_com_manifesto",
                  *VERIFICACOES_DO_SNAPSHOT, *VERIFICACOES_DA_PROJECAO, *VERIFICACOES_DO_PROMOVIDO}


@pytest.fixture
def cur(request):
    url = request.getfixturevalue("url_banco_teste")
    conn = psycopg.connect(url)
    try:
        cursor = conn.cursor()
        cursor.execute("SET LOCAL ROLE nsi_eventos_owner")
        yield cursor
    finally:
        conn.rollback()
        conn.close()


def _lote(resultado: dict, lote_id_legado: str) -> dict:
    return next(l for l in resultado["lotes"] if l["lote_id_legado"] == lote_id_legado)


def _concluir_com(cur, importacao_id, fuso, entradas, total) -> None:
    concluir(cur, importacao_id, manifesto_canonico(importacao_id, fuso, entradas), total)


def _importar_com_entrada(cur, importacao_id, documento) -> tuple:
    conteudo = serializar(documento)
    resultado = importar_bytes(cur, importacao_id, caminho_do_lote(documento["lote_id"]), conteudo)
    return resultado, entrada_de_lote(caminho_do_lote(documento["lote_id"]), conteudo, resultado)


# ============================================================
# Importacao integra
# ============================================================

def test_paridade_aprovada_para_importacao_integra_das_quatro_geracoes(cur):
    documentos = [doc_anterior_a1(), doc_a1(), doc_a2(), doc_a3()]
    recusado = dict(doc_a2(), campo_nao_previsto=1)
    importacao_id, _ = importar_e_concluir(cur, documentos + [recusado])
    resultado = paridade(cur, importacao_id)

    assert set(resultado) == {"aprovada", "concluida", "motivo", "registro_tecnico", "lotes", "contagens"}
    assert resultado["aprovada"] is True
    assert resultado["concluida"] is True
    assert resultado["motivo"] is None
    assert resultado["registro_tecnico"] == {
        "manifesto_sha256_confere": True, "manifesto_cabecalho_confere": True, "manifesto_sem_lote_orfao": True}
    assert resultado["contagens"] == {
        "lotes": 5, "preservado": 2, "promovido": 2, "recusado": 1, "ja_importado": 0,
        "evoluidos_no_fluxo_novo": 0, "lotes_reprovados": 0}
    assert [l["caminho_relativo"] for l in resultado["lotes"]] == sorted(
        caminho_do_lote(d["lote_id"]) for d in documentos + [recusado])

    for documento in documentos:
        lote = _lote(resultado, documento["lote_id"])
        assert set(lote) == CHAVES_DO_LOTE
        assert lote["registro_confere_com_manifesto"] is True
        assert lote["evoluido_no_fluxo_novo"] is False
        assert all(lote[v] is True for v in VERIFICACOES_DO_SNAPSHOT)
        promovido = lote["destino"] == "promovido"
        for verificacao in VERIFICACOES_DA_PROJECAO + VERIFICACOES_DO_PROMOVIDO:
            assert lote[verificacao] is (True if promovido else None), (
                "Verificacao de projecao so se aplica a lote promovido."
            )

    lote_recusado = _lote(resultado, recusado["lote_id"])
    assert lote_recusado["destino"] == "recusado"
    assert lote_recusado["registro_confere_com_manifesto"] is True
    for verificacao in VERIFICACOES_DO_SNAPSHOT + VERIFICACOES_DA_PROJECAO + VERIFICACOES_DO_PROMOVIDO:
        assert lote_recusado[verificacao] is None, "Lote recusado nao tem snapshot nem projecao."


def test_paridade_devolve_somente_booleanos_contagens_e_identificadores(cur):
    """Item 14: nenhum valor pessoal no retorno."""
    importacao_id, _ = importar_e_concluir(cur, [doc_a1(), doc_a3()])
    resultado = paridade(cur, importacao_id)
    assert_sem_valor_pessoal(json.dumps(resultado, ensure_ascii=False), "retorno da paridade")
    for lote in resultado["lotes"]:
        for chave, valor in lote.items():
            if chave not in ("caminho_relativo", "lote_id_legado", "destino"):
                assert valor is None or isinstance(valor, bool), chave


def test_paridade_e_somente_leitura_e_pode_ser_repetida(cur):
    importacao_id, _ = importar_e_concluir(cur, [doc_a2()])
    primeiro = paridade(cur, importacao_id)
    assert paridade(cur, importacao_id) == primeiro
    cur.execute("SELECT provolatile FROM pg_catalog.pg_proc WHERE proname = 'fn_verificar_paridade_legado'")
    assert cur.fetchone()[0] == "s", "Declarada STABLE: nao pode escrever."


def test_execucao_inexistente_ou_nula_e_recusada(cur):
    for importacao_id in (uuid_texto(), None):
        cur.execute("SAVEPOINT sp")
        with pytest.raises(psycopg.errors.DataException) as exc_info:
            paridade(cur, importacao_id)
        assert exc_info.value.sqlstate == "22000"
        assert exc_info.value.diag.message_primary == "entrada_estrutural_invalida"
        cur.execute("ROLLBACK TO SAVEPOINT sp")


# ============================================================
# Execucao nao concluida
# ============================================================

def test_execucao_nao_concluida_nunca_e_aprovada_mas_e_diagnosticavel(cur):
    importacao_id = iniciar(cur)
    documento = doc_a2()
    importar(cur, importacao_id, documento)
    resultado = paridade(cur, importacao_id)

    assert resultado["aprovada"] is False
    assert resultado["concluida"] is False
    assert resultado["motivo"] == "execucao_nao_concluida"
    assert resultado["registro_tecnico"] == {
        "manifesto_sha256_confere": None, "manifesto_cabecalho_confere": None, "manifesto_sem_lote_orfao": None}
    lote = _lote(resultado, documento["lote_id"])
    assert lote["registro_confere_com_manifesto"] is None, "Sem conclusao nao ha manifesto."
    for verificacao in VERIFICACOES_DO_SNAPSHOT + VERIFICACOES_DA_PROJECAO + VERIFICACOES_DO_PROMOVIDO:
        assert lote[verificacao] is True, "Todas as verificacoes por lote sao devolvidas, para diagnostico."
    assert resultado["contagens"]["lotes_reprovados"] == 0


def test_execucao_aberta_e_sem_lotes(cur):
    resultado = paridade(cur, iniciar(cur))
    assert (resultado["aprovada"], resultado["concluida"], resultado["lotes"]) == (False, False, [])


# ============================================================
# Alteracao do snapshot como owner (ADR-010, Secao 9.3)
# ============================================================

_ALTERACOES_DO_SNAPSHOT = {
    "documento_bruto_alterado": (
        "UPDATE nsi_operacional.lotes_legado SET documento_bruto = documento_bruto || ' '::bytea "
        " WHERE lote_id_legado = %s",
        {"documento_sha256_confere"}),
    "documento_e_hash_do_snapshot_alterados_juntos": (
        "UPDATE nsi_operacional.lotes_legado SET documento_bruto = documento_bruto || ' '::bytea, "
        "       documento_sha256 = encode(sha256(documento_bruto || ' '::bytea), 'hex') WHERE lote_id_legado = %s",
        {"documento_sha256_confere"}),
    "documento_substituido_por_bytes_ilegiveis": (
        "UPDATE nsi_operacional.lotes_legado SET documento_bruto = '\\xff00'::bytea WHERE lote_id_legado = %s",
        {"documento_sha256_confere", "quantidade_registros_confere", "conteudo_registros_confere",
         "projecao_registros_confere", "totais_conferem", "recebido_em_confere"}),
    "conteudo_de_um_registro_alterado": (
        "UPDATE nsi_operacional.registros_legado SET conteudo_bruto = conteudo_bruto || '{\"nome\": \"Outro\"}' "
        " WHERE lista = 'clientes' AND posicao = 0 AND snapshot_lote_id = "
        "       (SELECT snapshot_lote_id FROM nsi_operacional.lotes_legado WHERE lote_id_legado = %s)",
        {"conteudo_registros_confere"}),
    "conteudo_e_hash_de_um_registro_alterados_juntos": (
        "UPDATE nsi_operacional.registros_legado "
        "   SET conteudo_bruto = conteudo_bruto || '{\"nome\": \"Outro\"}', "
        "       conteudo_sha256 = encode(sha256(convert_to((conteudo_bruto || '{\"nome\": \"Outro\"}')::text, 'UTF8')), 'hex') "
        " WHERE lista = 'clientes' AND posicao = 0 AND snapshot_lote_id = "
        "       (SELECT snapshot_lote_id FROM nsi_operacional.lotes_legado WHERE lote_id_legado = %s)",
        {"conteudo_registros_confere"}),
    "hash_de_um_registro_alterado": (
        "UPDATE nsi_operacional.registros_legado SET conteudo_sha256 = repeat('0', 64) "
        " WHERE lista = 'clientes_invalidos' AND posicao = 0 AND snapshot_lote_id = "
        "       (SELECT snapshot_lote_id FROM nsi_operacional.lotes_legado WHERE lote_id_legado = %s)",
        {"conteudo_registros_confere"}),
    "registro_removido": (
        "DELETE FROM nsi_operacional.registros_legado "
        " WHERE lista = 'clientes' AND posicao = 1 AND snapshot_lote_id = "
        "       (SELECT snapshot_lote_id FROM nsi_operacional.lotes_legado WHERE lote_id_legado = %s)",
        {"quantidade_registros_confere"}),
    "registro_acrescentado": (
        "INSERT INTO nsi_operacional.registros_legado "
        "SELECT snapshot_lote_id, 'clientes', 99, '{}'::jsonb, repeat('0', 64), NULL, 'legado_sem_identidade_tecnica' "
        "  FROM nsi_operacional.lotes_legado WHERE lote_id_legado = %s",
        {"quantidade_registros_confere", "conteudo_registros_confere"}),
}


@pytest.mark.parametrize("caso", sorted(_ALTERACOES_DO_SNAPSHOT))
def test_alteracao_do_snapshot_e_detectada(cur, caso):
    """O snapshot e mutavel por ato privilegiado, e sempre de forma
    detectavel: o registro tecnico imutavel guarda o SHA-256 do arquivo."""
    comando, reprovadas = _ALTERACOES_DO_SNAPSHOT[caso]
    documento = doc_a2()
    importacao_id, _ = importar_e_concluir(cur, [documento, doc_a1()])
    assert paridade(cur, importacao_id)["aprovada"] is True

    cur.execute(comando, (documento["lote_id"],))
    assert cur.rowcount == 1
    resultado = paridade(cur, importacao_id)

    assert resultado["aprovada"] is False
    assert resultado["contagens"]["lotes_reprovados"] == 1
    lote = _lote(resultado, documento["lote_id"])
    for verificacao in VERIFICACOES_DO_SNAPSHOT + VERIFICACOES_DA_PROJECAO:
        assert lote[verificacao] is (verificacao not in reprovadas), verificacao


def test_snapshot_removido_e_detectado(cur):
    documento = doc_a1()
    importacao_id, _ = importar_e_concluir(cur, [documento])
    cur.execute("DELETE FROM nsi_operacional.registros_legado WHERE snapshot_lote_id = "
                "(SELECT snapshot_lote_id FROM nsi_operacional.lotes_legado WHERE lote_id_legado = %s)",
                (documento["lote_id"],))
    cur.execute("DELETE FROM nsi_operacional.lotes_legado WHERE lote_id_legado = %s", (documento["lote_id"],))
    resultado = paridade(cur, importacao_id)
    assert resultado["aprovada"] is False
    lote = _lote(resultado, documento["lote_id"])
    assert all(lote[v] is False for v in VERIFICACOES_DO_SNAPSHOT)


# ============================================================
# Alteracao da projecao de lote promovido
# ============================================================

_ALTERACOES_DA_PROJECAO = {
    "nome_alterado": (
        "UPDATE nsi_operacional.registros_coleta SET nome = 'Outro Nome' WHERE registro_coleta_id = %(valido)s",
        "projecao_registros_confere"),
    "whatsapp_alterado": (
        "UPDATE nsi_operacional.registros_coleta SET whatsapp = '5511900000000' WHERE registro_coleta_id = %(valido)s",
        "projecao_registros_confere"),
    "numero_versao_dados_alterado": (
        "UPDATE nsi_operacional.registros_coleta SET numero_versao_dados = 9 WHERE registro_coleta_id = %(valido)s",
        "projecao_registros_confere"),
    "versao_eventos_do_registro_alterada": (
        "UPDATE nsi_operacional.registros_coleta SET versao_eventos_atual = 1 WHERE registro_coleta_id = %(invalido)s",
        "projecao_registros_confere"),
    "motivos_alterados": (
        "UPDATE nsi_operacional.registros_coleta SET motivos_invalidez = ARRAY['whatsapp_ddd_invalido'] "
        " WHERE registro_coleta_id = %(invalido)s",
        "projecao_registros_confere"),
    "registro_removido_da_projecao": (
        "DELETE FROM nsi_operacional.registros_coleta WHERE registro_coleta_id = %(invalido)s",
        "projecao_registros_confere"),
    "totais_alterados": (
        "UPDATE nsi_operacional.lotes SET total_valido = total_valido + 1, total_invalido = total_invalido - 1 "
        " WHERE lote_id = %(lote)s",
        "totais_conferem"),
    "recebido_em_alterado": (
        "UPDATE nsi_operacional.lotes SET recebido_em = recebido_em + interval '1 microsecond', "
        "       horario_conceitual_congelamento = horario_conceitual_congelamento + interval '1 microsecond' "
        " WHERE lote_id = %(lote)s",
        "recebido_em_confere"),
}


@pytest.mark.parametrize("caso", sorted(_ALTERACOES_DA_PROJECAO))
def test_divergencia_entre_projecao_e_legado_e_detectada(cur, caso):
    comando, verificacao_reprovada = _ALTERACOES_DA_PROJECAO[caso]
    documento = doc_a2()
    importacao_id, resultados = importar_e_concluir(cur, [documento])
    cur.execute(comando, {"lote": resultados[0]["lote_id_promovido"],
                          "valido": documento["clientes"][0]["registro_coleta_id"],
                          "invalido": documento["clientes_invalidos"][0]["registro_coleta_id"]})
    assert cur.rowcount == 1

    resultado = paridade(cur, importacao_id)
    assert resultado["aprovada"] is False
    lote = _lote(resultado, documento["lote_id"])
    for verificacao in VERIFICACOES_DO_SNAPSHOT + VERIFICACOES_DA_PROJECAO + VERIFICACOES_DO_PROMOVIDO:
        assert lote[verificacao] is (verificacao != verificacao_reprovada), verificacao


def test_registro_acrescentado_a_projecao_e_detectado(cur):
    documento = doc_a2()
    importacao_id, resultados = importar_e_concluir(cur, [documento])
    cur.execute(
        "INSERT INTO nsi_operacional.registros_coleta (registro_coleta_id, lote_id, nome, produto, whatsapp, valido) "
        "VALUES (%s, %s, 'Extra', 'Extra', '5511900000001', true)", (uuid_texto(), resultados[0]["lote_id_promovido"]))
    lote = _lote(paridade(cur, importacao_id), documento["lote_id"])
    assert lote["projecao_registros_confere"] is False


def test_recebido_em_e_reinterpretado_no_fuso_gravado_pela_execucao(cur):
    """ADR-010, Secao 13.5: a paridade usa o fuso gravado no registro
    tecnico - nunca o da sessao que a executa."""
    documento = doc_a2(criado_em="2026-07-05T10:30:00.25")
    importacao_id, _ = importar_e_concluir(cur, [documento], fuso="Europe/Lisbon")
    cur.execute("SET LOCAL TIME ZONE 'Asia/Tokyo'")
    assert _lote(paridade(cur, importacao_id), documento["lote_id"])["recebido_em_confere"] is True


def test_evento_gravado_por_nsi_importacao_reprova_a_paridade(cur):
    """A importacao nunca grava evento. Um evento atribuido a nsi_importacao
    - aqui inserido diretamente pelo teste, como owner - e detectado."""
    documento = doc_a2()
    importacao_id, resultados = importar_e_concluir(cur, [documento])
    cur.execute(
        "INSERT INTO nsi_operacional.eventos_lote (evento_id, aggregate_type, aggregate_id, aggregate_version, tipo, "
        "executado_por_login, motivo) VALUES (%s, 'lote', %s, 2, 'tentativa_correcao_nao_resolvida', "
        "'nsi_importacao', 'codigo_ausente')", (uuid_texto(), resultados[0]["lote_id_promovido"]))
    resultado = paridade(cur, importacao_id)
    lote = _lote(resultado, documento["lote_id"])
    assert lote["sem_evento_da_importacao"] is False
    assert lote["evoluido_no_fluxo_novo"] is True
    assert resultado["aprovada"] is False


# ============================================================
# Lote evoluido no fluxo novo
# ============================================================

def test_lote_promovido_e_depois_congelado_e_evoluido_e_a_paridade_e_aprovada(cur):
    """A paridade e a prova do momento da importacao: depois de um evento
    legitimo do fluxo novo, as comparacoes de projecao nao se aplicam; as
    do snapshot, a ausencia de evento da importacao e a prova de origem
    continuam obrigatorias."""
    documento = doc_a2(criado_em="2026-01-05T10:30:00")
    outro = doc_a2()
    importacao_id, resultados = importar_e_concluir(cur, [documento, outro])

    cur.execute("SELECT nsi_operacional.fn_registrar_congelamento(%s)", (resultados[0]["lote_id_promovido"],))
    assert cur.fetchone()[0]["sucesso"] is True

    resultado = paridade(cur, importacao_id)
    assert resultado["aprovada"] is True
    assert resultado["contagens"]["evoluidos_no_fluxo_novo"] == 1

    lote = _lote(resultado, documento["lote_id"])
    assert lote["evoluido_no_fluxo_novo"] is True
    assert all(lote[v] is None for v in VERIFICACOES_DA_PROJECAO), "Projecao nao comparada."
    assert all(lote[v] is True for v in VERIFICACOES_DO_SNAPSHOT + VERIFICACOES_DO_PROMOVIDO)

    nao_evoluido = _lote(resultado, outro["lote_id"])
    assert nao_evoluido["evoluido_no_fluxo_novo"] is False
    assert all(nao_evoluido[v] is True for v in VERIFICACOES_DA_PROJECAO)


def test_snapshot_alterado_de_lote_evoluido_continua_sendo_detectado(cur):
    documento = doc_a2(criado_em="2026-01-05T10:30:00")
    importacao_id, resultados = importar_e_concluir(cur, [documento])
    cur.execute("SELECT nsi_operacional.fn_registrar_congelamento(%s)", (resultados[0]["lote_id_promovido"],))
    cur.execute("UPDATE nsi_operacional.lotes_legado SET documento_bruto = documento_bruto || ' '::bytea "
                "WHERE lote_id_legado = %s", (documento["lote_id"],))
    resultado = paridade(cur, importacao_id)
    assert resultado["aprovada"] is False
    assert _lote(resultado, documento["lote_id"])["documento_sha256_confere"] is False


# ============================================================
# Registro tecnico contra o manifesto, nos dois sentidos
# ============================================================

@pytest.mark.parametrize("campo,valor", [
    ("sha256", "0" * 64), ("geracao", "a3"), ("destino", "preservado"), ("motivo", "fuso_nao_declarado"),
])
def test_linha_do_registro_tecnico_divergente_do_manifesto_reprova(cur, campo, valor):
    importacao_id = iniciar(cur)
    documento = doc_a2()
    _, entrada = _importar_com_entrada(cur, importacao_id, documento)
    assert entrada[campo] != valor
    _concluir_com(cur, importacao_id, FUSO_PADRAO, [dict(entrada, **{campo: valor})], 1)

    resultado = paridade(cur, importacao_id)
    assert resultado["aprovada"] is False
    lote = _lote(resultado, documento["lote_id"])
    assert lote["registro_confere_com_manifesto"] is False
    assert all(lote[v] is True for v in VERIFICACOES_DO_SNAPSHOT + VERIFICACOES_DA_PROJECAO)


def test_linha_do_registro_tecnico_sem_entrada_no_manifesto_reprova(cur):
    importacao_id = iniciar(cur)
    documento, omitido = doc_a1(), doc_a1()
    _, entrada = _importar_com_entrada(cur, importacao_id, documento)
    importar(cur, importacao_id, omitido)
    _concluir_com(cur, importacao_id, FUSO_PADRAO, [entrada], 2)

    resultado = paridade(cur, importacao_id)
    assert resultado["aprovada"] is False
    assert _lote(resultado, omitido["lote_id"])["registro_confere_com_manifesto"] is False
    assert _lote(resultado, documento["lote_id"])["registro_confere_com_manifesto"] is True


def test_entrada_duplicada_no_manifesto_reprova(cur):
    importacao_id = iniciar(cur)
    documento = doc_a1()
    _, entrada = _importar_com_entrada(cur, importacao_id, documento)
    _concluir_com(cur, importacao_id, FUSO_PADRAO, [entrada, dict(entrada)], 1)
    resultado = paridade(cur, importacao_id)
    assert resultado["aprovada"] is False
    assert _lote(resultado, documento["lote_id"])["registro_confere_com_manifesto"] is False


def test_entrada_de_lote_no_manifesto_sem_linha_no_registro_tecnico_reprova(cur):
    importacao_id = iniciar(cur)
    documento, fantasma = doc_a1(), doc_a1()
    _, entrada = _importar_com_entrada(cur, importacao_id, documento)
    conteudo = serializar(fantasma)
    entrada_fantasma = entrada_de_lote(
        caminho_do_lote(fantasma["lote_id"]), conteudo,
        {"geracao": "a1", "destino": "preservado", "motivo": "geracao_nao_promovivel",
         "lote_id_legado": fantasma["lote_id"], "lote_id_promovido": None})
    _concluir_com(cur, importacao_id, FUSO_PADRAO, [entrada, entrada_fantasma], 1)

    resultado = paridade(cur, importacao_id)
    assert resultado["aprovada"] is False
    assert resultado["registro_tecnico"]["manifesto_sem_lote_orfao"] is False
    assert resultado["contagens"]["lotes_reprovados"] == 0, "Os lotes registrados, em si, conferem."


def test_tentativa_recusada_no_manifesto_nao_exige_linha_no_registro_tecnico(cur):
    importacao_id = iniciar(cur)
    documento = doc_a1()
    _, entrada = _importar_com_entrada(cur, importacao_id, documento)
    tentativa = entrada_de_tentativa_recusada("correcoes_rejeitadas/2026-01-09/%s.json" % uuid_texto(), b"{}")
    _concluir_com(cur, importacao_id, FUSO_PADRAO, [entrada, tentativa], 1)
    resultado = paridade(cur, importacao_id)
    assert resultado["aprovada"] is True
    assert resultado["registro_tecnico"]["manifesto_sem_lote_orfao"] is True
    assert resultado["contagens"]["lotes"] == 1


@pytest.mark.parametrize("cabecalho", ["importacao_id", "fuso_declarado"])
def test_cabecalho_do_manifesto_divergente_da_execucao_reprova(cur, cabecalho):
    importacao_id = iniciar(cur)
    documento = doc_a1()
    _, entrada = _importar_com_entrada(cur, importacao_id, documento)
    manifesto = manifesto_canonico(
        uuid_texto() if cabecalho == "importacao_id" else importacao_id,
        "UTC" if cabecalho == "fuso_declarado" else FUSO_PADRAO, [entrada])
    concluir(cur, importacao_id, manifesto, 1)

    resultado = paridade(cur, importacao_id)
    assert resultado["aprovada"] is False
    assert resultado["registro_tecnico"] == {
        "manifesto_sha256_confere": True, "manifesto_cabecalho_confere": False, "manifesto_sem_lote_orfao": True}


def test_fuso_nulo_no_manifesto_confere_com_execucao_sem_fuso(cur):
    importacao_id, _ = importar_e_concluir(cur, [doc_a2()], fuso=None)
    resultado = paridade(cur, importacao_id)
    assert resultado["aprovada"] is True
    assert resultado["lotes"][0]["destino"] == "preservado"


@pytest.mark.parametrize("manifesto", [b"isto nao e json", b"[]", b"{}", b'{"arquivos": {}}', b"\xff\xfe"])
def test_manifesto_gravado_ilegivel_ou_sem_estrutura_reprova(cur, manifesto):
    """A conclusao grava os bytes e confere so o SHA-256; e a paridade que
    exige um manifesto legivel e coerente."""
    importacao_id = iniciar(cur)
    documento = doc_a1()
    importar(cur, importacao_id, documento)
    concluir(cur, importacao_id, manifesto, 1)

    resultado = paridade(cur, importacao_id)
    assert resultado["aprovada"] is False
    assert resultado["concluida"] is True
    assert resultado["registro_tecnico"] == {
        "manifesto_sha256_confere": True, "manifesto_cabecalho_confere": False, "manifesto_sem_lote_orfao": False}
    assert _lote(resultado, documento["lote_id"])["registro_confere_com_manifesto"] is False


# ============================================================
# Lote 'ja_importado'
# ============================================================

@pytest.mark.parametrize("construtor", [doc_a1, doc_a2])
def test_lote_ja_importado_e_reverificado_por_inteiro_no_snapshot_original(cur, construtor):
    documento = construtor()
    importar_e_concluir(cur, [documento])
    segunda, resultados = importar_e_concluir(cur, [documento])
    assert resultados[0]["destino"] == "ja_importado"

    resultado = paridade(cur, segunda)
    assert resultado["aprovada"] is True
    assert resultado["contagens"]["ja_importado"] == 1
    lote = _lote(resultado, documento["lote_id"])
    assert lote["destino"] == "ja_importado"
    assert all(lote[v] is True for v in VERIFICACOES_DO_SNAPSHOT)
    promovido = resultados[0]["destino_original"] == "promovido"
    for verificacao in VERIFICACOES_DA_PROJECAO + VERIFICACOES_DO_PROMOVIDO:
        assert lote[verificacao] is (True if promovido else None)


def test_lote_ja_importado_e_reprovado_quando_o_snapshot_original_e_alterado(cur):
    documento = doc_a1()
    primeira, _ = importar_e_concluir(cur, [documento])
    segunda, _ = importar_e_concluir(cur, [documento])
    cur.execute("UPDATE nsi_operacional.lotes_legado SET documento_bruto = documento_bruto || ' '::bytea "
                "WHERE lote_id_legado = %s", (documento["lote_id"],))

    for importacao_id in (primeira, segunda):
        resultado = paridade(cur, importacao_id)
        assert resultado["aprovada"] is False
        assert _lote(resultado, documento["lote_id"])["documento_sha256_confere"] is False


def test_lote_recusado_por_conflito_de_reimportacao_nao_e_verificado_contra_o_snapshot_alheio(cur):
    documento = doc_a1()
    importar_e_concluir(cur, [documento])
    alterado = dict(documento, nome_lote="Lote Sintetico Alterado")
    segunda, resultados = importar_e_concluir(cur, [alterado])
    assert resultados[0]["motivo"] == "conflito_de_reimportacao"

    resultado = paridade(cur, segunda)
    assert resultado["aprovada"] is True
    lote = _lote(resultado, documento["lote_id"])
    assert lote["destino"] == "recusado"
    assert all(lote[v] is None for v in VERIFICACOES_DO_SNAPSHOT)
    assert sha256_hex(serializar(alterado)) != sha256_hex(serializar(documento))
