# -*- coding: utf-8 -*-
"""
NSI - tests/integration/test_fn_importar_lote_legado.py
(Sprint B, B5.4 - ADR-010; Especificacao Tecnica, B5.2, itens 5.1, 6, 8 a
13, 15 e 17)

Testes de integracao REAIS contra PostgreSQL, exclusivamente contra
nsi_test, de fn_importar_lote_legado: ordem fixa de avaliacao,
classificacao por geracao, recusas, preservacao, criterios e efeitos da
promocao, fuso, fluxo novo sobre lote promovido, reimportacao, idempotencia,
concorrencia e privacidade.

SOMENTE DADOS SINTETICOS (tests/apoio_b5.py e tests/fixtures/legado/).

Identidade (B5.2, item 17): os testes rodam numa transacao do migrator de
teste sob SET LOCAL ROLE nsi_eventos_owner, terminada em ROLLBACK - todo
teste de promocao termina em ROLLBACK. A identidade tecnica gravada e a do
migrator; a gravacao da identidade nsi_importacao e comprovada em
test_permissoes_b5.py, que conecta como a propria role.

DIVULGACAO DE RESIDUO INTENCIONAL: test_duas_importacoes_concorrentes_do_
mesmo_arquivo e test_duas_importacoes_concorrentes_com_sha256_diferente
exigem COMMIT real e usam somente lotes NAO promoviveis (geracao a1). O
snapshot e o registro tecnico desses lotes ficam como residuo sintetico em
nsi_test, nunca em nsi_dev, ate o downgrade da 0006 remover as tabelas.
"""
import threading

import psycopg
import pytest

from tests.apoio_b4_3 import aguardar_bloqueio, posicionar_fronteira
from tests.apoio_b5 import (
    FUSO_PADRAO,
    assert_sem_valor_pessoal,
    caminho_do_lote,
    cliente_invalido,
    conectar_como_owner,
    contar,
    doc_a1,
    doc_a2,
    doc_a3,
    doc_anterior_a1,
    ids_do_documento,
    importar,
    importar_bytes,
    iniciar,
    ler_fixture,
    novo_lote_id_legado,
    serializar,
    sha256_hex,
    uuid_texto,
    versao_historico,
)
from core.payload_hash import hash_registrar_correcao

pytestmark = pytest.mark.pg_integration

CHAVES_DO_RETORNO = {"geracao", "destino", "motivo", "lote_id_legado", "lote_id_promovido", "constraint_violada"}


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


def _assert_erro_fixo(exc_info, sqlstate: str, mensagem: str) -> None:
    assert exc_info.value.sqlstate == sqlstate
    assert exc_info.value.diag.message_primary == mensagem
    assert exc_info.value.diag.message_detail is None
    assert_sem_valor_pessoal(str(exc_info.value) + repr(exc_info.value), "mensagem de erro")


def _linhas_escritas(cur) -> tuple:
    """Contagem das tabelas que a importacao pode gravar, mais as que ela
    nunca pode tocar (eventos e recibos)."""
    return tuple(contar(cur, t) for t in (
        "lotes_legado", "registros_legado", "lotes", "registros_coleta", "importacoes_legado_arquivos",
        "eventos_lote", "eventos_registro_coleta", "comandos_idempotentes"))


def _snapshot(cur, lote_id_legado: str):
    cur.execute(
        "SELECT snapshot_lote_id, importacao_id, caminho_relativo, documento_bruto, documento_sha256, geracao, "
        "       status_legado, criado_em_bruto, destino, motivo_nao_promocao, lote_id_promovido "
        "  FROM nsi_operacional.lotes_legado WHERE lote_id_legado = %s", (lote_id_legado,))
    return cur.fetchone()


def _assert_nao_promovido(cur, importacao_id, documento, motivo: str, geracao=None) -> dict:
    antes = _linhas_escritas(cur)
    resultado = importar(cur, importacao_id, documento)
    depois = _linhas_escritas(cur)

    assert resultado["destino"] == "preservado"
    assert resultado["motivo"] == motivo
    assert resultado["lote_id_promovido"] is None
    if geracao:
        assert resultado["geracao"] == geracao
    n_registros = len(documento["clientes"]) + len(documento.get("clientes_invalidos", []))
    assert depois[0] == antes[0] + 1, "Lote nao promovido continua preservado."
    assert depois[1] == antes[1] + n_registros
    assert depois[2:4] == antes[2:4], "Nenhuma linha em lotes nem em registros_coleta."
    assert depois[5:] == antes[5:], "Nenhum evento e nenhum recibo."
    assert contar(cur, "registros_legado r JOIN nsi_operacional.lotes_legado g USING (snapshot_lote_id)",
                  "g.lote_id_legado = %s AND r.classificacao = 'legado_promovido'", (documento["lote_id"],)) == 0
    return resultado


# ============================================================
# Passo 1 e 2 - parametros, caminho, execucao e SHA-256 (22000)
# ============================================================

@pytest.mark.parametrize("indice_nulo", [0, 1, 2, 3])
def test_parametro_nulo_e_recusado(cur, indice_nulo):
    importacao_id = iniciar(cur)
    conteudo = serializar(doc_a1())
    parametros = [importacao_id, "lotes/X/lote.json", conteudo, sha256_hex(conteudo)]
    parametros[indice_nulo] = None
    with pytest.raises(psycopg.errors.DataException) as exc_info:
        cur.execute("SELECT nsi_operacional.fn_importar_lote_legado(%s, %s, %s, %s)", parametros)
    _assert_erro_fixo(exc_info, "22000", "entrada_estrutural_invalida")


@pytest.mark.parametrize("caminho", [
    "lote.json", "lotes/lote.json", "lotes//lote.json", "lotes/A/B/lote.json", "/lotes/A/lote.json",
    "lotes/A/lote.json/", "lotes/A/saida_motor.json", "lotes/A/lote.JSON", "lotes\\A\\lote.json",
    "correcoes_rejeitadas/2026-01-09/3f0c1b7e-5a44-4c0e-9d0a-6f6f1f0a9b01.json",
    "respostas/5511999990000.json", "data/lotes/A/lote.json", "lotes/A/lotexjson", "",
])
def test_caminho_fora_do_escopo_e_recusado(cur, caminho):
    """Item 6.1: somente lotes/<diretorio>/lote.json e importado."""
    importacao_id = iniciar(cur)
    conteudo = serializar(doc_a1())
    with pytest.raises(psycopg.errors.DataException) as exc_info:
        importar_bytes(cur, importacao_id, caminho, conteudo)
    _assert_erro_fixo(exc_info, "22000", "entrada_estrutural_invalida")


@pytest.mark.parametrize("sha256", ["", "abc", "A" * 64, "g" * 64, "a" * 63, "a" * 65])
def test_sha256_fora_do_formato_e_recusado(cur, sha256):
    importacao_id = iniciar(cur)
    documento = doc_a1()
    with pytest.raises(psycopg.errors.DataException) as exc_info:
        importar_bytes(cur, importacao_id, caminho_do_lote(documento["lote_id"]), serializar(documento), sha256)
    _assert_erro_fixo(exc_info, "22000", "entrada_estrutural_invalida")


def test_sha256_divergente_do_recalculado_e_recusado_sem_escrita(cur):
    """Item 13: o banco recalcula o SHA-256 sobre os bytes brutos."""
    importacao_id = iniciar(cur)
    documento = doc_a2()
    antes = _linhas_escritas(cur)
    cur.execute("SAVEPOINT sp")
    with pytest.raises(psycopg.errors.DataException) as exc_info:
        importar_bytes(cur, importacao_id, caminho_do_lote(documento["lote_id"]), serializar(documento), "0" * 64)
    _assert_erro_fixo(exc_info, "22000", "entrada_estrutural_invalida")
    assert "0" * 64 not in str(exc_info.value)
    cur.execute("ROLLBACK TO SAVEPOINT sp")
    assert _linhas_escritas(cur) == antes


def test_execucao_inexistente_e_recusada(cur):
    documento = doc_a1()
    with pytest.raises(psycopg.errors.DataException) as exc_info:
        importar(cur, uuid_texto(), documento)
    _assert_erro_fixo(exc_info, "22000", "entrada_estrutural_invalida")


# ============================================================
# Passo 4 - legibilidade
# ============================================================

@pytest.mark.parametrize("conteudo", [
    b"",
    b"{",
    b'{"lote_id": "X", ',
    b"isto nao e json",
    b"\xff\xfe\x00\x00",                                   # bytes que nao sao UTF-8
    b'{"lote_id": "\xe9"}',                                # latin-1, nao UTF-8
    b'\xef\xbb\xbf{"lote_id": "X"}',                       # marca de ordem de bytes
    b'{"lote_id": "X", "nome_lote": "a\\u0000b"}',         # caractere que o jsonb nao aceita
    b'{"lote_id": "X"} {"outro": 1}',
    b'{"lote_id": "X", "n": 1e999999}',
])
def test_documento_ilegivel_e_recusa_registrada(cur, conteudo):
    importacao_id = iniciar(cur)
    antes = _linhas_escritas(cur)
    resultado = importar_bytes(cur, importacao_id, "lotes/X/lote.json", conteudo)
    depois = _linhas_escritas(cur)

    assert set(resultado) == CHAVES_DO_RETORNO
    assert resultado == {"geracao": None, "destino": "recusado", "motivo": "documento_ilegivel",
                         "lote_id_legado": None, "lote_id_promovido": None, "constraint_violada": None}
    assert depois[4] == antes[4] + 1, "A recusa e registrada no registro tecnico."
    assert depois[:4] + depois[5:] == antes[:4] + antes[5:], "Nada no snapshot nem na projecao."


def test_fixture_de_documento_ilegivel(cur):
    importacao_id = iniciar(cur)
    resultado = importar_bytes(cur, importacao_id, "lotes/NSI-20260107-A00007/lote.json",
                               ler_fixture("lotes/NSI-20260107-A00007/lote.json"))
    assert (resultado["destino"], resultado["motivo"]) == ("recusado", "documento_ilegivel")


# ============================================================
# Passo 5 - identidade divergente
# ============================================================

def test_lote_id_diferente_do_diretorio_e_recusa_registrada(cur):
    importacao_id = iniciar(cur)
    documento = doc_a2()
    outro_diretorio = novo_lote_id_legado()
    antes = _linhas_escritas(cur)
    resultado = importar_bytes(cur, importacao_id, caminho_do_lote(outro_diretorio), serializar(documento))
    depois = _linhas_escritas(cur)

    assert resultado["destino"] == "recusado"
    assert resultado["motivo"] == "identidade_divergente"
    assert resultado["geracao"] is None, "A identidade divergente e decidida antes da classificacao."
    assert resultado["lote_id_legado"] == documento["lote_id"]
    assert depois[4] == antes[4] + 1
    assert depois[:4] + depois[5:] == antes[:4] + antes[5:]


def test_fixture_de_identidade_divergente(cur):
    importacao_id = iniciar(cur)
    resultado = importar_bytes(cur, importacao_id, "lotes/NSI-20260108-A00008/lote.json",
                               ler_fixture("lotes/NSI-20260108-A00008/lote.json"))
    assert (resultado["destino"], resultado["motivo"]) == ("recusado", "identidade_divergente")


def test_identidade_divergente_vem_antes_do_formato_desconhecido(cur):
    """Ordem fixa: o passo 5 decide antes do passo 6."""
    importacao_id = iniciar(cur)
    documento = doc_a2()
    documento["chave_nao_prevista"] = True
    resultado = importar_bytes(cur, importacao_id, caminho_do_lote(novo_lote_id_legado()), serializar(documento))
    assert resultado["motivo"] == "identidade_divergente"


# ============================================================
# Passo 6 - classificacao por geracao
# ============================================================

@pytest.mark.parametrize("construtor,geracao", [
    (doc_anterior_a1, "anterior_a1"), (doc_a1, "a1"), (doc_a2, "a2"), (doc_a3, "a3"),
])
def test_cada_geracao_e_classificada_pela_estrutura(cur, construtor, geracao):
    importacao_id = iniciar(cur)
    documento = construtor()
    resultado = importar(cur, importacao_id, documento)
    assert set(resultado) == CHAVES_DO_RETORNO
    assert resultado["geracao"] == geracao
    assert resultado["destino"] in ("preservado", "promovido")
    assert resultado["lote_id_legado"] == documento["lote_id"]
    assert _snapshot(cur, documento["lote_id"])[5] == geracao


@pytest.mark.parametrize("diretorio,geracao", [
    ("NSI-20260101-A00001", "anterior_a1"), ("NSI-20260102-A00002", "a1"),
    ("NSI-20260103-A00003", "a2"), ("NSI-20260104-A00004", "a3"),
])
def test_fixtures_das_quatro_geracoes(cur, diretorio, geracao):
    importacao_id = iniciar(cur)
    resultado = importar_bytes(cur, importacao_id, f"lotes/{diretorio}/lote.json",
                               ler_fixture(f"lotes/{diretorio}/lote.json"))
    assert resultado["geracao"] == geracao
    assert resultado["destino"] == ("promovido" if geracao in ("a2", "a3") else "preservado")


def test_lote_a3_sem_nenhuma_correcao_e_classificado_como_a2(cur):
    """Sem historico_versoes, um lote da A3 tem a estrutura - e a semantica -
    da A2."""
    importacao_id = iniciar(cur)
    documento = doc_a3()
    del documento["historico_versoes"]
    assert importar(cur, importacao_id, documento)["geracao"] == "a2"


def test_lote_sem_registros_e_sem_marcas_da_a2_e_anterior_a1(cur):
    importacao_id = iniciar(cur)
    documento = doc_a1(n=0)
    resultado = importar(cur, importacao_id, documento)
    assert (resultado["geracao"], resultado["destino"]) == ("anterior_a1", "preservado")


def _mutar(documento, alteracao):
    alteracao(documento)
    return documento


_CAUSAS_DE_FORMATO_DESCONHECIDO = {
    "chave_extra_na_raiz": lambda: _mutar(doc_a2(), lambda d: d.update({"campo_nao_previsto": 1})),
    "chave_extra_em_clientes": lambda: _mutar(doc_a2(), lambda d: d["clientes"][0].update({"email": "x"})),
    "chave_extra_em_clientes_invalidos":
        lambda: _mutar(doc_a2(), lambda d: d["clientes_invalidos"][0].update({"telefone": "x"})),
    "chave_de_invalido_em_clientes": lambda: _mutar(doc_a2(), lambda d: d["clientes"][0].update({"motivos": []})),
    "mistura_de_identidade_a1": lambda: _mutar(doc_a1(), lambda d: d["clientes"][1].pop("registro_coleta_id")),
    "mistura_de_identidade_a2": lambda: _mutar(doc_a2(), lambda d: d["clientes"][0].pop("registro_coleta_id")),
    "invalido_sem_identidade":
        lambda: _mutar(doc_a2(), lambda d: d["clientes_invalidos"][0].pop("registro_coleta_id")),
    "registro_coleta_id_fora_do_formato_uuid":
        lambda: _mutar(doc_a1(), lambda d: d["clientes"][0].update({"registro_coleta_id": "nao-e-uuid"})),
    "registro_coleta_id_nao_textual":
        lambda: _mutar(doc_a1(), lambda d: d["clientes"][0].update({"registro_coleta_id": 123})),
    "registro_coleta_id_nulo":
        lambda: _mutar(doc_a1(), lambda d: d["clientes"][0].update({"registro_coleta_id": None})),
    "criado_em_ausente": lambda: _mutar(doc_a2(), lambda d: d.pop("criado_em")),
    "criado_em_nao_textual": lambda: _mutar(doc_a2(), lambda d: d.update({"criado_em": 20260105})),
    "clientes_ausente": lambda: _mutar(doc_a1(), lambda d: d.pop("clientes")),
    "clientes_nao_e_lista": lambda: _mutar(doc_a1(), lambda d: d.update({"clientes": {}})),
    "cliente_nao_e_objeto": lambda: _mutar(doc_a1(), lambda d: d["clientes"].append("texto")),
    "clientes_invalidos_nao_e_lista": lambda: _mutar(doc_a2(), lambda d: d.update({"clientes_invalidos": None})),
    "invalido_nao_e_objeto": lambda: _mutar(doc_a2(), lambda d: d["clientes_invalidos"].append([1])),
    "a2_sem_um_dos_totais": lambda: _mutar(doc_a2(), lambda d: d.pop("total_invalido")),
    "a2_sem_clientes_invalidos": lambda: _mutar(doc_a2(), lambda d: d.pop("clientes_invalidos")),
    "a1_com_um_total_da_a2": lambda: _mutar(doc_a1(), lambda d: d.update({"total_recebido": 2})),
    "anterior_a1_com_clientes_invalidos":
        lambda: _mutar(doc_anterior_a1(), lambda d: d.update({"clientes_invalidos": []})),
    "historico_sem_marcas_da_a2": lambda: _mutar(doc_a1(), lambda d: d.update({"historico_versoes": {}})),
    "historico_nao_e_objeto": lambda: _mutar(doc_a2(), lambda d: d.update({"historico_versoes": []})),
    "historico_com_valor_que_nao_e_lista":
        lambda: _mutar(doc_a3(), lambda d: d["historico_versoes"].update({uuid_texto(): {"numero_versao": 1}})),
}


@pytest.mark.parametrize("causa", sorted(_CAUSAS_DE_FORMATO_DESCONHECIDO))
def test_formato_desconhecido_e_recusa_registrada_sem_escrita(cur, causa):
    importacao_id = iniciar(cur)
    documento = _CAUSAS_DE_FORMATO_DESCONHECIDO[causa]()
    antes = _linhas_escritas(cur)
    resultado = importar(cur, importacao_id, documento)
    depois = _linhas_escritas(cur)

    assert resultado["geracao"] == "formato_desconhecido"
    assert resultado["destino"] == "recusado"
    assert resultado["motivo"] == "formato_desconhecido"
    assert resultado["lote_id_legado"] == documento["lote_id"]
    assert depois[4] == antes[4] + 1
    assert depois[:4] + depois[5:] == antes[:4] + antes[5:]


@pytest.mark.parametrize("conteudo", [b"[]", b"null", b"42", b'"texto"', b"{}", b'{"lote_id": 7}'])
def test_raiz_sem_a_estrutura_comum_e_formato_desconhecido(cur, conteudo):
    importacao_id = iniciar(cur)
    resultado = importar_bytes(cur, importacao_id, "lotes/X/lote.json", conteudo)
    assert resultado == {"geracao": "formato_desconhecido", "destino": "recusado",
                         "motivo": "formato_desconhecido", "lote_id_legado": None,
                         "lote_id_promovido": None, "constraint_violada": None}


@pytest.mark.parametrize("diretorio", ["NSI-20260105-A00005", "NSI-20260106-A00006"])
def test_fixtures_de_formato_desconhecido(cur, diretorio):
    importacao_id = iniciar(cur)
    resultado = importar_bytes(cur, importacao_id, f"lotes/{diretorio}/lote.json",
                               ler_fixture(f"lotes/{diretorio}/lote.json"))
    assert (resultado["destino"], resultado["motivo"]) == ("recusado", "formato_desconhecido")


def test_chave_duplicada_segue_o_jsonb_e_os_bytes_preservam_o_original(cur):
    """Item 6.2: na classificacao prevalece o ultimo valor; documento_bruto
    guarda os bytes exatos."""
    importacao_id = iniciar(cur)
    lote_id = novo_lote_id_legado()
    conteudo = serializar(doc_a1(lote_id)).replace(
        b'"nome_lote": "Lote Sintetico"', b'"nome_lote": "Primeiro", "nome_lote": "Ultimo"')
    assert conteudo.count(b'"nome_lote"') == 2
    resultado = importar_bytes(cur, importacao_id, caminho_do_lote(lote_id), conteudo)
    assert resultado["geracao"] == "a1"
    assert bytes(_snapshot(cur, lote_id)[3]) == conteudo


# ============================================================
# Passo 9 - preservacao (itens 8 e 9)
# ============================================================

@pytest.mark.parametrize("construtor,classificacao", [
    (doc_anterior_a1, "legado_sem_identidade_tecnica"),
    (doc_a1, "legado_identificado_nao_promovido"),
    (doc_a2, "legado_promovido"),
    (doc_a3, "legado_promovido"),
])
def test_preservacao_integral_do_lote_e_de_cada_registro(cur, construtor, classificacao):
    importacao_id = iniciar(cur)
    documento = construtor()
    conteudo = serializar(documento)
    resultado = importar_bytes(cur, importacao_id, caminho_do_lote(documento["lote_id"]), conteudo)

    (snapshot_lote_id, importacao_gravada, caminho, documento_bruto, documento_sha256, geracao, status_legado,
     criado_em_bruto, destino, motivo, lote_id_promovido) = _snapshot(cur, documento["lote_id"])
    assert str(importacao_gravada) == importacao_id
    assert caminho == caminho_do_lote(documento["lote_id"])
    assert bytes(documento_bruto) == conteudo, "Os bytes exatos do arquivo, sem normalizacao."
    assert documento_sha256 == sha256_hex(conteudo)
    assert geracao == resultado["geracao"]
    assert status_legado == {"status": documento["status"], "status_pipeline": documento["status_pipeline"]}
    assert criado_em_bruto == documento["criado_em"]
    assert (destino, motivo) == (resultado["destino"], resultado["motivo"])
    assert (str(lote_id_promovido) if lote_id_promovido else None) == resultado["lote_id_promovido"]

    cur.execute(
        "SELECT lista, posicao, conteudo_bruto, conteudo_sha256, registro_coleta_id::text, classificacao, "
        "       encode(sha256(convert_to(conteudo_bruto::text, 'UTF8')), 'hex') "
        "  FROM nsi_operacional.registros_legado WHERE snapshot_lote_id = %s ORDER BY lista, posicao",
        (snapshot_lote_id,))
    linhas = cur.fetchall()
    esperado = [(lista, posicao, registro)
                for lista in ("clientes", "clientes_invalidos")
                for posicao, registro in enumerate(documento.get(lista, []))]
    assert len(linhas) == len(esperado), "Uma linha por registro, das duas listas."
    for (lista, posicao, conteudo_bruto, conteudo_sha256, registro_id, classe, sha_recalculado), \
            (lista_esperada, posicao_esperada, registro) in zip(linhas, esperado):
        assert (lista, posicao) == (lista_esperada, posicao_esperada)
        assert conteudo_bruto == registro, "O objeto do registro, sem alterar nem completar valores."
        assert conteudo_sha256 == sha_recalculado
        assert registro_id == registro.get("registro_coleta_id")
        assert classe == classificacao


def test_status_legado_usa_null_para_chave_ausente(cur):
    importacao_id = iniciar(cur)
    documento = doc_a1()
    del documento["status"], documento["status_pipeline"]
    importar(cur, importacao_id, documento)
    assert _snapshot(cur, documento["lote_id"])[6] == {"status": None, "status_pipeline": None}


def test_historico_e_demais_campos_permanecem_dentro_do_documento_bruto(cur):
    importacao_id = iniciar(cur)
    documento = doc_a3()
    conteudo = serializar(documento)
    importar_bytes(cur, importacao_id, caminho_do_lote(documento["lote_id"]), conteudo)
    cur.execute(
        "SELECT convert_from(documento_bruto, 'UTF8')::jsonb -> 'historico_versoes' "
        "  FROM nsi_operacional.lotes_legado WHERE lote_id_legado = %s", (documento["lote_id"],))
    assert cur.fetchone()[0] == documento["historico_versoes"]


def test_preservacao_nao_normaliza_valores(cur):
    """Espacos, caixa e formato do telefone ficam exatamente como estavam."""
    importacao_id = iniciar(cur)
    documento = doc_a1()
    documento["clientes"][0].update({"nome": "  pessoa SINTETICA legado  ", "telefone": "(11) 98765-0001"})
    importar(cur, importacao_id, documento)
    cur.execute(
        "SELECT r.conteudo_bruto ->> 'nome', r.conteudo_bruto ->> 'telefone' "
        "  FROM nsi_operacional.registros_legado r JOIN nsi_operacional.lotes_legado g USING (snapshot_lote_id) "
        " WHERE g.lote_id_legado = %s AND r.lista = 'clientes' AND r.posicao = 0", (documento["lote_id"],))
    assert cur.fetchone() == ("  pessoa SINTETICA legado  ", "(11) 98765-0001")


# ============================================================
# Passos 10 e 11 - promocao (item 10)
# ============================================================

@pytest.mark.parametrize("construtor", [doc_a2, doc_a3])
def test_promocao_bem_sucedida(cur, construtor):
    importacao_id = iniciar(cur)
    documento = construtor()
    antes = _linhas_escritas(cur)
    resultado = importar(cur, importacao_id, documento)
    depois = _linhas_escritas(cur)

    n_validos, n_invalidos = len(documento["clientes"]), len(documento["clientes_invalidos"])
    assert resultado["destino"] == "promovido"
    assert resultado["motivo"] is None and resultado["constraint_violada"] is None
    assert depois[2] == antes[2] + 1
    assert depois[3] == antes[3] + n_validos + n_invalidos
    assert depois[5:] == antes[5:], "Nenhum evento e nenhum recibo gravados pela importacao (item 10.4)."

    cur.execute(
        "SELECT lote_id_legado, status, total_recebido, total_valido, total_invalido, versao_eventos_atual, "
        "       total_valido_congelado, horario_real_congelamento, disparo_confirmado_em, "
        "       recebido_em = timezone(%s, %s::timestamp), "
        "       horario_conceitual_congelamento = recebido_em + interval '192 hours' "
        "  FROM nsi_operacional.lotes WHERE lote_id = %s",
        (FUSO_PADRAO, documento["criado_em"].replace("T", " "), resultado["lote_id_promovido"]))
    assert cur.fetchone() == (documento["lote_id"], "aguardando_d8", n_validos + n_invalidos, n_validos,
                              n_invalidos, 1, None, None, None, True, True)

    assert contar(cur, "eventos_lote", "aggregate_id = %s", (resultado["lote_id_promovido"],)) == 0, (
        "Ausencia deliberada de lote_criado (ADR-009, Secao 22)."
    )
    cur.execute("SELECT destino, lote_id_promovido::text FROM nsi_operacional.importacoes_legado_arquivos "
                "WHERE importacao_id = %s", (importacao_id,))
    assert cur.fetchone() == ("promovido", resultado["lote_id_promovido"])


def test_mapeamento_exato_da_projecao(cur):
    """Item 10.3: valido <- clientes; invalido <- clientes_invalidos, com o
    campo do motivo '*_ausente' nulo; numero_versao_dados pelo historico;
    versao_eventos_atual 0."""
    importacao_id = iniciar(cur)
    documento = doc_a3()
    documento["clientes_invalidos"] += [
        cliente_invalido(7, ("nome_ausente",)),
        cliente_invalido(8, ("produto_ausente", "whatsapp_ausente")),
    ]
    documento["total_recebido"] += 2
    documento["total_invalido"] += 2
    resultado = importar(cur, importacao_id, documento)
    assert resultado["destino"] == "promovido", resultado["constraint_violada"]

    cur.execute(
        "SELECT registro_coleta_id::text, nome, whatsapp, produto, valido, motivos_invalidez, "
        "       numero_versao_dados, versao_eventos_atual "
        "  FROM nsi_operacional.registros_coleta WHERE lote_id = %s", (resultado["lote_id_promovido"],))
    projecao = {linha[0]: linha[1:] for linha in cur.fetchall()}

    historico = documento["historico_versoes"]
    esperado = {}
    for c in documento["clientes"]:
        esperado[c["registro_coleta_id"]] = (
            c["nome"], c["telefone"], c["produto"], True, None, len(historico.get(c["registro_coleta_id"], [1])), 0)
    for c in documento["clientes_invalidos"]:
        motivos = c["motivos"]
        esperado[c["registro_coleta_id"]] = (
            None if "nome_ausente" in motivos else c["nome_bruto"],
            None if "whatsapp_ausente" in motivos else c["whatsapp_bruto"],
            None if "produto_ausente" in motivos else c["produto_bruto"],
            False, motivos, len(historico.get(c["registro_coleta_id"], [1])), 0)
    assert projecao == esperado
    assert sorted(v[5] for v in projecao.values()) == [1, 1, 1, 1, 2, 3]


def test_promocao_preserva_fracoes_de_segundo_e_aceita_m0_sem_fracao(cur):
    importacao_id = iniciar(cur)
    for criado_em, esperado in (("2026-01-05T10:30:00.123456", "2026-01-05 10:30:00.123456"),
                                ("2026-01-05T10:30:00.5", "2026-01-05 10:30:00.500000"),
                                ("2026-01-05T10:30:00", "2026-01-05 10:30:00.000000")):
        documento = doc_a2(criado_em=criado_em)
        resultado = importar(cur, importacao_id, documento)
        assert resultado["destino"] == "promovido"
        cur.execute(
            "SELECT to_char(timezone(%s, recebido_em), 'YYYY-MM-DD HH24:MI:SS.US') "
            "  FROM nsi_operacional.lotes WHERE lote_id = %s", (FUSO_PADRAO, resultado["lote_id_promovido"]))
        assert cur.fetchone()[0] == esperado


def test_m0_e_interpretado_no_fuso_declarado_e_nao_no_da_sessao(cur):
    """ADR-010, Secao 13.2: o fuso nunca vem da maquina ou da sessao que
    executa a importacao."""
    cur.execute("SET LOCAL TIME ZONE 'Asia/Tokyo'")
    importacao_id = iniciar(cur, "Europe/Lisbon")
    documento = doc_a2(criado_em="2026-01-05T10:30:00")
    resultado = importar(cur, importacao_id, documento)
    cur.execute("SELECT recebido_em = '2026-01-05 10:30:00+00'::timestamptz FROM nsi_operacional.lotes "
                "WHERE lote_id = %s", (resultado["lote_id_promovido"],))
    assert cur.fetchone()[0] is True


def test_data_disparo_sozinha_nao_impede_a_promocao(cur):
    """Item 6.3: data_disparo e a data PLANEJADA, gravada ja no upload."""
    importacao_id = iniciar(cur)
    documento = doc_a2()
    assert documento["data_disparo"]
    assert importar(cur, importacao_id, documento)["destino"] == "promovido"


def test_lote_a2_sem_nenhum_registro_valido_e_promovido(cur):
    importacao_id = iniciar(cur)
    documento = doc_a2(validos=0, invalidos=2)
    documento["status"] = "sem_registros_validos"
    resultado = importar(cur, importacao_id, documento)
    assert resultado["destino"] == "promovido"
    cur.execute("SELECT status, total_valido FROM nsi_operacional.lotes WHERE lote_id = %s",
                (resultado["lote_id_promovido"],))
    assert cur.fetchone() == ("aguardando_d8", 0), "Status inicial sempre aguardando_d8 (ADR-010, Secao 11.1)."


# ---------- motivos de nao promocao (item 10.1) ----------

@pytest.mark.parametrize("construtor,geracao", [(doc_anterior_a1, "anterior_a1"), (doc_a1, "a1")])
def test_geracao_anterior_a_a2_nunca_e_promovida(cur, construtor, geracao):
    importacao_id = iniciar(cur)
    _assert_nao_promovido(cur, importacao_id, construtor(), "geracao_nao_promovivel", geracao)


def test_execucao_sem_fuso_nao_promove_nenhum_lote(cur):
    importacao_id = iniciar(cur, None)
    _assert_nao_promovido(cur, importacao_id, doc_a2(), "fuso_nao_declarado", "a2")
    _assert_nao_promovido(cur, importacao_id, doc_a3(), "fuso_nao_declarado", "a3")
    _assert_nao_promovido(cur, importacao_id, doc_a1(), "geracao_nao_promovivel", "a1")


_EVIDENCIAS_DE_DISPARO = {
    "status_disparado": lambda d: d.update({"status": "disparado"}),
    "pipeline_disparo_whatsapp": lambda d: d["status_pipeline"].update({"disparo_whatsapp": True}),
    "pipeline_webhook": lambda d: d["status_pipeline"].update({"webhook": True}),
    "pipeline_analise_ia": lambda d: d["status_pipeline"].update({"analise_ia": True}),
    "pipeline_dashboard": lambda d: d["status_pipeline"].update({"dashboard": True}),
    "pipeline_pdf": lambda d: d["status_pipeline"].update({"pdf": True}),
    "registro_com_data_envio_mensagem":
        lambda d: d["clientes"][1].update({"data_envio_mensagem": "2026-01-13T10:31:00"}),
    "registro_com_status_entrega": lambda d: d["clientes"][0].update({"status_entrega": "sent"}),
    "registro_com_data_resposta": lambda d: d["clientes"][0].update({"data_resposta": "2026-01-14T08:00:00"}),
    "registro_com_resposta": lambda d: d["clientes"][0].update({"resposta": "Gostei"}),
}


@pytest.mark.parametrize("evidencia", sorted(_EVIDENCIAS_DE_DISPARO))
def test_evidencia_de_disparo_impede_a_promocao(cur, evidencia):
    importacao_id = iniciar(cur)
    documento = doc_a2()
    _EVIDENCIAS_DE_DISPARO[evidencia](documento)
    _assert_nao_promovido(cur, importacao_id, documento, "evidencia_de_disparo")


def test_campos_de_envio_nulos_ou_vazios_nao_sao_evidencia(cur):
    importacao_id = iniciar(cur)
    documento = doc_a2()
    documento["clientes"][0].update(
        {"data_envio_mensagem": None, "status_entrega": None, "data_resposta": None, "resposta": ""})
    documento["clientes"][1].update({"resposta": None})
    assert importar(cur, importacao_id, documento)["destino"] == "promovido"


def test_status_legado_nunca_vira_status_da_projecao(cur):
    """ADR-010, Secao 14: preservado literalmente, nunca convertido."""
    importacao_id = iniciar(cur)
    documento = doc_a2()
    documento["status"] = "pronto_disparo"
    documento["status_pipeline"]["aguardando_d8"] = True
    resultado = importar(cur, importacao_id, documento)
    assert resultado["destino"] == "promovido"
    cur.execute("SELECT status FROM nsi_operacional.lotes WHERE lote_id = %s", (resultado["lote_id_promovido"],))
    assert cur.fetchone()[0] == "aguardando_d8"
    assert _snapshot(cur, documento["lote_id"])[6]["status"] == "pronto_disparo"


@pytest.mark.parametrize("lote_id_legado", ["LOTE-1", "NSI-20260105-abcdef", "NSI-2026010-ABCDEF", "nsi-20260105-ABCDEF"])
def test_lote_id_legado_fora_do_formato_nao_e_promovido(cur, lote_id_legado):
    importacao_id = iniciar(cur)
    documento = doc_a2(lote_id_legado + "-" + uuid_texto()[:8])
    _assert_nao_promovido(cur, importacao_id, documento, "lote_id_legado_invalido")


def test_lote_id_legado_ja_usado_por_lote_da_projecao_nao_e_promovido(cur):
    importacao_id = iniciar(cur)
    documento = doc_a2()
    cur.execute(
        "INSERT INTO nsi_operacional.lotes (lote_id, lote_id_legado, recebido_em, total_recebido, total_valido, "
        "total_invalido, status, horario_conceitual_congelamento) "
        "VALUES (%s, %s, now(), 0, 0, 0, 'aguardando_d8', now() + interval '192 hours')",
        (uuid_texto(), documento["lote_id"]))
    _assert_nao_promovido(cur, importacao_id, documento, "lote_id_legado_em_uso")


@pytest.mark.parametrize("criado_em", [
    "", "2026-01-05", "2026-01-05 10:30:00", "2026-01-05T10:30", "05/01/2026 10:30:00",
    "2026-01-05T10:30:00Z", "2026-01-05T10:30:00-03:00", "2026-01-05T10:30:00+00:00",
    "2026-01-05T10:30:00 America/Sao_Paulo", "2026-01-05T10:30:00.1234567", "2026-01-05T10:30:00.",
    "2026-02-30T10:30:00", "2026-13-01T10:30:00", "2026-01-05T24:00:00", "2026-01-05T10:60:00",
    "2026-01-05T10:30:60", "0000-01-01T00:00:00", " 2026-01-05T10:30:00", "2026-01-05T10:30:00\n",
])
def test_m0_fora_do_formato_ou_invalido_nao_e_promovido(cur, criado_em):
    importacao_id = iniciar(cur)
    documento = doc_a2(criado_em=criado_em)
    _assert_nao_promovido(cur, importacao_id, documento, "m0_invalido")
    assert _snapshot(cur, documento["lote_id"])[7] == criado_em, "O texto bruto do M0 permanece intacto."


@pytest.mark.parametrize("fuso,criado_em", [
    # America/Sao_Paulo: 2018-11-04 00:00 -> 01:00 (lacuna); 2018-02-18 00:00 -> 23:00 do dia 17 (repeticao).
    ("America/Sao_Paulo", "2018-11-04T00:00:00"),
    ("America/Sao_Paulo", "2018-11-04T00:30:00.5"),
    ("America/Sao_Paulo", "2018-11-04T00:59:59.999999"),
    ("America/Sao_Paulo", "2018-02-17T23:00:00"),
    ("America/Sao_Paulo", "2018-02-17T23:30:00"),
    ("America/Sao_Paulo", "2018-02-17T23:59:59.999999"),
    # Europe/Lisbon: 2025-03-30 01:00 -> 02:00 (lacuna); 2025-10-26 02:00 -> 01:00 (repeticao).
    ("Europe/Lisbon", "2025-03-30T01:30:00"),
    ("Europe/Lisbon", "2025-10-26T01:30:00"),
    # Australia/Lord_Howe: horario de verao de 30 minutos.
    ("Australia/Lord_Howe", "2025-10-05T02:15:00"),
    ("Australia/Lord_Howe", "2025-04-06T01:45:00"),
])
def test_m0_inexistente_ou_ambiguo_no_fuso_declarado_nao_e_promovido(cur, fuso, criado_em):
    importacao_id = iniciar(cur, fuso)
    _assert_nao_promovido(cur, importacao_id, doc_a2(criado_em=criado_em), "m0_inexistente_ou_ambiguo")


@pytest.mark.parametrize("fuso,criado_em", [
    ("America/Sao_Paulo", "2018-11-03T23:59:59.999999"),
    ("America/Sao_Paulo", "2018-11-04T01:00:00"),
    ("America/Sao_Paulo", "2018-02-17T22:59:59.999999"),
    ("America/Sao_Paulo", "2018-02-18T00:00:00"),
    ("Europe/Lisbon", "2025-03-30T02:00:00"),
    ("Europe/Lisbon", "2025-10-26T02:00:00"),
    ("Australia/Lord_Howe", "2025-10-05T02:30:00"),
    ("Australia/Lord_Howe", "2025-04-06T02:00:00"),
    ("UTC", "2018-11-04T00:30:00"),
])
def test_m0_nas_bordas_do_horario_de_verao_e_interpretavel(cur, fuso, criado_em):
    importacao_id = iniciar(cur, fuso)
    documento = doc_a2(criado_em=criado_em)
    resultado = importar(cur, importacao_id, documento)
    assert resultado["destino"] == "promovido", resultado["motivo"]
    cur.execute("SELECT timezone(%s, recebido_em) = %s::timestamp FROM nsi_operacional.lotes WHERE lote_id = %s",
                (fuso, criado_em.replace("T", " "), resultado["lote_id_promovido"]))
    assert cur.fetchone()[0] is True


def test_registro_coleta_id_repetido_no_lote_nao_e_promovido(cur):
    importacao_id = iniciar(cur)
    documento = doc_a2()
    documento["clientes_invalidos"][0]["registro_coleta_id"] = documento["clientes"][0]["registro_coleta_id"].upper()
    _assert_nao_promovido(cur, importacao_id, documento, "identidade_repetida")


def test_colisao_com_registro_da_projecao_nao_e_promovido(cur):
    importacao_id = iniciar(cur)
    anterior = doc_a2()
    assert importar(cur, importacao_id, anterior)["destino"] == "promovido"
    documento = doc_a2()
    documento["clientes"][0]["registro_coleta_id"] = anterior["clientes"][0]["registro_coleta_id"]
    _assert_nao_promovido(cur, importacao_id, documento, "colisao_de_identidade")


def test_colisao_com_registro_do_snapshot_de_outro_lote_nao_e_promovido(cur):
    importacao_id = iniciar(cur)
    anterior = doc_a1()
    importar(cur, importacao_id, anterior)
    documento = doc_a2()
    documento["clientes_invalidos"][0]["registro_coleta_id"] = anterior["clientes"][0]["registro_coleta_id"]
    _assert_nao_promovido(cur, importacao_id, documento, "colisao_de_identidade")


@pytest.mark.parametrize("total_recebido", [0, 2, 4, "3", None, 3.5])
def test_total_recebido_diferente_da_soma_das_listas_nao_e_promovido(cur, total_recebido):
    importacao_id = iniciar(cur)
    documento = doc_a2()
    documento["total_recebido"] = total_recebido
    _assert_nao_promovido(cur, importacao_id, documento, "totais_incoerentes")


def _historico_corrente_divergente(d):
    d["historico_versoes"][d["clientes"][0]["registro_coleta_id"]][-1]["status_versao"] = "invalida"


def _historico_invalido_marcado_valido(d):
    d["historico_versoes"][d["clientes_invalidos"][0]["registro_coleta_id"]][-1]["status_versao"] = "valida"


_HISTORICOS_INCOERENTES = {
    "corrente_invalida_em_clientes": _historico_corrente_divergente,
    "corrente_valida_em_clientes_invalidos": _historico_invalido_marcado_valido,
    "chave_sem_registro_correspondente":
        lambda d: d["historico_versoes"].update({uuid_texto(): [versao_historico(1, "invalida")]}),
    "lista_de_versoes_vazia":
        lambda d: d["historico_versoes"].update({d["clientes"][1]["registro_coleta_id"]: []}),
    "versao_corrente_sem_status":
        lambda d: d["historico_versoes"][d["clientes"][0]["registro_coleta_id"]][-1].pop("status_versao"),
}


@pytest.mark.parametrize("caso", sorted(_HISTORICOS_INCOERENTES))
def test_historico_incoerente_nao_e_promovido(cur, caso):
    importacao_id = iniciar(cur)
    documento = doc_a3()
    _HISTORICOS_INCOERENTES[caso](documento)
    _assert_nao_promovido(cur, importacao_id, documento, "historico_incoerente", "a3")


@pytest.mark.parametrize("alteracao,constraint", [
    (lambda d: d["clientes"][0].update({"telefone": "11987650001"}), "ck_registros_coleta_coerencia"),
    (lambda d: d["clientes"][0].update({"nome": "   "}), "ck_registros_coleta_nome_nao_vazio"),
    (lambda d: d["clientes_invalidos"][0].update({"motivos": ["motivo_fora_do_vocabulario"]}),
     "ck_registros_coleta_motivos_vocabulario"),
    (lambda d: d["clientes_invalidos"][0].update({"motivos": []}), "ck_registros_coleta_coerencia"),
    (lambda d: d["clientes_invalidos"][0].update({"nome_bruto": ""}), "ck_registros_coleta_nome_nao_vazio"),
])
def test_projecao_incompativel_desfaz_a_promocao_e_mantem_o_lote_preservado(cur, alteracao, constraint):
    importacao_id = iniciar(cur)
    documento = doc_a2()
    alteracao(documento)
    resultado = _assert_nao_promovido(cur, importacao_id, documento, "projecao_incompativel")
    assert resultado["constraint_violada"] == constraint, "Somente o NOME da constraint e registrado."
    assert contar(cur, "lotes", "lote_id_legado = %s", (documento["lote_id"],)) == 0, (
        "A promocao e desfeita por inteiro, inclusive a linha de lotes."
    )
    cur.execute("SELECT constraint_violada FROM nsi_operacional.importacoes_legado_arquivos "
                "WHERE importacao_id = %s", (importacao_id,))
    assert cur.fetchone()[0] == constraint
    assert_sem_valor_pessoal(str(resultado), "retorno da nao promocao")


def test_criterios_sao_avaliados_na_ordem_do_item_10_1(cur):
    """O primeiro criterio que falha e o motivo registrado."""
    documento = doc_a3(criado_em="nao-e-data")
    documento["status"] = "disparado"
    documento["total_recebido"] = 99
    documento["historico_versoes"][uuid_texto()] = []

    sem_fuso = iniciar(cur, None)
    assert importar(cur, sem_fuso, documento)["motivo"] == "fuso_nao_declarado"

    for alteracao, motivo in (
        (lambda d: None, "evidencia_de_disparo"),
        (lambda d: d.update({"status": "aguardando_d8"}), "m0_invalido"),
        (lambda d: d.update({"criado_em": "2018-11-04T00:30:00"}), "m0_inexistente_ou_ambiguo"),
        (lambda d: d.update({"criado_em": "2026-01-05T10:30:00"}), "totais_incoerentes"),
        (lambda d: d.update({"total_recebido": 4}), "historico_incoerente"),
    ):
        alteracao(documento)
        copia = dict(documento, lote_id=novo_lote_id_legado())
        copia["clientes"] = [dict(c, registro_coleta_id=uuid_texto()) for c in documento["clientes"]]
        copia["clientes_invalidos"] = [dict(c, registro_coleta_id=uuid_texto())
                                       for c in documento["clientes_invalidos"]]
        copia["historico_versoes"] = {uuid_texto(): []}
        assert importar(cur, iniciar(cur), copia)["motivo"] == motivo


# ============================================================
# Fluxo novo sobre lote promovido (item 17)
# ============================================================

def test_congelamento_de_lote_promovido_com_fronteira_vencida_e_atrasado(cur):
    """ADR-010, Secao 11.1: se a fronteira ja passou, o congelamento ocorre
    depois, pelo fluxo normal, e e registrado como atrasado - o primeiro
    evento do lote tem versao 2."""
    importacao_id = iniciar(cur)
    documento = doc_a2(criado_em="2026-01-05T10:30:00")
    lote_id = importar(cur, importacao_id, documento)["lote_id_promovido"]

    cur.execute("SELECT now() > horario_conceitual_congelamento FROM nsi_operacional.lotes WHERE lote_id = %s",
                (lote_id,))
    assert cur.fetchone()[0] is True, "O M0 sintetico esta a mais de 192 horas no passado."

    cur.execute("SELECT nsi_operacional.fn_registrar_congelamento(%s)", (lote_id,))
    resultado = cur.fetchone()[0]
    assert resultado["sucesso"] is True
    assert resultado["atrasado"] is True
    assert resultado["status"] == "aguardando_confirmacao_disparo"
    assert resultado["total_valido_congelado"] == 2
    assert resultado["versao_eventos"] == 2

    cur.execute("SELECT tipo, aggregate_version FROM nsi_operacional.eventos_lote WHERE aggregate_id = %s",
                (lote_id,))
    assert cur.fetchall() == [("lote_congelado_d8", 2)]


def test_correcao_antes_da_fronteira_e_aceita_em_lote_promovido(cur):
    importacao_id = iniciar(cur)
    documento = doc_a2()
    lote_id = importar(cur, importacao_id, documento)["lote_id_promovido"]
    registro_id = documento["clientes_invalidos"][0]["registro_coleta_id"]
    posicionar_fronteira(cur, lote_id, "1 hour")

    valores = ("Pessoa Corrigida", "5511987650099", "Produto Corrigido", True, None)
    cur.execute(
        "SELECT nsi_operacional.fn_registrar_correcao(%s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (lote_id, registro_id, *valores, "chave-correcao-legado",
         hash_registrar_correcao(lote_id, registro_id, *valores)))
    resultado = cur.fetchone()[0]
    assert resultado["sucesso"] is True
    assert resultado["resultado"] == "aplicada_valida"
    assert resultado["numero_versao_dados"] == 2
    assert resultado["versao_eventos"] == 1, "Registro promovido nasce com versao_eventos_atual 0."

    cur.execute("SELECT total_valido, total_invalido, status FROM nsi_operacional.lotes WHERE lote_id = %s",
                (lote_id,))
    assert cur.fetchone() == (3, 0, "aguardando_d8")


def test_correcao_depois_da_fronteira_e_tardia_em_lote_promovido(cur):
    importacao_id = iniciar(cur)
    documento = doc_a2(criado_em="2026-01-05T10:30:00")
    lote_id = importar(cur, importacao_id, documento)["lote_id_promovido"]
    registro_id = documento["clientes_invalidos"][0]["registro_coleta_id"]
    valores = ("Pessoa Corrigida", "5511987650099", "Produto Corrigido", True, None)
    cur.execute(
        "SELECT nsi_operacional.fn_registrar_correcao(%s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (lote_id, registro_id, *valores, "chave-correcao-tardia",
         hash_registrar_correcao(lote_id, registro_id, *valores)))
    assert cur.fetchone()[0]["resultado"] == "recusada_tardia"


# ============================================================
# Reimportacao e idempotencia (itens 11 e 12)
# ============================================================

@pytest.mark.parametrize("construtor,destino_original", [(doc_a1, "preservado"), (doc_a2, "promovido")])
def test_reimportacao_do_mesmo_arquivo_em_outra_execucao_e_ja_importado(cur, construtor, destino_original):
    documento = construtor()
    primeira = iniciar(cur)
    original = importar(cur, primeira, documento)

    segunda = iniciar(cur)
    antes = _linhas_escritas(cur)
    resultado = importar(cur, segunda, documento)
    depois = _linhas_escritas(cur)

    assert set(resultado) == CHAVES_DO_RETORNO | {"destino_original"}
    assert resultado["destino"] == "ja_importado"
    assert resultado["destino_original"] == destino_original == original["destino"]
    assert resultado["lote_id_promovido"] == original["lote_id_promovido"]
    assert resultado["geracao"] == original["geracao"]
    assert resultado["motivo"] is None
    assert depois[4] == antes[4] + 1, "So a linha do registro tecnico da nova execucao."
    assert depois[:4] + depois[5:] == antes[:4] + antes[5:], "Nenhuma linha nova no snapshot nem na projecao."


def test_reimportacao_com_sha256_diferente_e_recusa_registrada(cur):
    documento = doc_a2()
    primeira = iniciar(cur)
    original = importar(cur, primeira, documento)
    conteudo_original = bytes(_snapshot(cur, documento["lote_id"])[3])

    alterado = dict(documento, nome_lote="Lote Sintetico Alterado")
    segunda = iniciar(cur)
    antes = _linhas_escritas(cur)
    resultado = importar(cur, segunda, alterado)
    depois = _linhas_escritas(cur)

    assert resultado["destino"] == "recusado"
    assert resultado["motivo"] == "conflito_de_reimportacao"
    assert resultado["lote_id_promovido"] is None
    assert "destino_original" not in resultado
    assert depois[4] == antes[4] + 1
    assert depois[:4] + depois[5:] == antes[:4] + antes[5:], "Nunca sobrescrita (ADR-010, Secao 17)."
    assert bytes(_snapshot(cur, documento["lote_id"])[3]) == conteudo_original

    # Reapresentado, recebe a mesma recusa - na mesma execucao (replay) e em outra.
    assert importar(cur, segunda, alterado) == resultado
    assert importar(cur, iniciar(cur), alterado) == resultado
    assert original["destino"] == "promovido"


def test_documento_recusado_e_reapresentado_recebe_a_mesma_recusa(cur):
    documento = doc_a2()
    documento["campo_nao_previsto"] = 1
    primeiro = importar(cur, iniciar(cur), documento)
    segundo = importar(cur, iniciar(cur), documento)
    assert primeiro == segundo
    assert primeiro["motivo"] == "formato_desconhecido"


@pytest.mark.parametrize("construtor", [doc_a1, doc_a2, lambda: {"lote_id": novo_lote_id_legado(), "x": 1}])
def test_mesmo_caminho_com_o_mesmo_sha256_na_mesma_execucao_e_replay(cur, construtor):
    importacao_id = iniciar(cur)
    documento = construtor()
    primeiro = importar(cur, importacao_id, documento)
    antes = _linhas_escritas(cur)
    segundo = importar(cur, importacao_id, documento)
    assert segundo == primeiro, "O replay devolve o resultado ja registrado."
    assert "destino_original" not in segundo
    assert _linhas_escritas(cur) == antes, "Nenhuma escrita no replay."


def test_mesmo_caminho_com_sha256_diferente_na_mesma_execucao_e_conflito(cur):
    """Item 12: o arquivo mudou durante a execucao - 22023, sem escrita, e a
    execucao permanece aberta."""
    importacao_id = iniciar(cur)
    documento = doc_a2()
    importar(cur, importacao_id, documento)
    antes = _linhas_escritas(cur)

    alterado = dict(documento, nome_lote="Lote Sintetico Alterado")
    cur.execute("SAVEPOINT sp")
    with pytest.raises(psycopg.errors.InvalidParameterValue) as exc_info:
        importar(cur, importacao_id, alterado)
    _assert_erro_fixo(exc_info, "22023", "conflito_de_idempotencia")
    assert sha256_hex(serializar(alterado)) not in str(exc_info.value)
    cur.execute("ROLLBACK TO SAVEPOINT sp")

    assert _linhas_escritas(cur) == antes
    assert contar(cur, "importacoes_legado_conclusoes", "importacao_id = %s", (importacao_id,)) == 0
    assert importar(cur, importacao_id, doc_a1())["destino"] == "preservado", "A execucao continua aberta."


def test_conflito_na_mesma_execucao_vale_tambem_para_documento_recusado(cur):
    importacao_id = iniciar(cur)
    assert importar_bytes(cur, importacao_id, "lotes/X/lote.json", b"{")["motivo"] == "documento_ilegivel"
    with pytest.raises(psycopg.errors.InvalidParameterValue) as exc_info:
        importar_bytes(cur, importacao_id, "lotes/X/lote.json", b"{{")
    _assert_erro_fixo(exc_info, "22023", "conflito_de_idempotencia")


def test_linha_do_registro_tecnico_e_imutavel_inclusive_para_o_owner(cur):
    importacao_id = iniciar(cur)
    importar(cur, importacao_id, doc_a1())
    for comando in ("UPDATE nsi_operacional.importacoes_legado_arquivos SET destino = 'recusado' WHERE importacao_id = %s",
                    "DELETE FROM nsi_operacional.importacoes_legado_arquivos WHERE importacao_id = %s"):
        cur.execute("SAVEPOINT sp")
        with pytest.raises(psycopg.errors.RaiseException) as exc_info:
            cur.execute(comando, (importacao_id,))
        assert "registro tecnico imutavel" in exc_info.value.diag.message_primary
        cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_snapshot_nao_tem_trigger_de_imutabilidade(cur):
    """ADR-010, Secao 9.3: o snapshot contem dado pessoal e nao e tornado
    indelevel - e mutavel por ato privilegiado, de forma detectavel."""
    importacao_id = iniciar(cur)
    documento = doc_a1()
    importar(cur, importacao_id, documento)
    cur.execute("UPDATE nsi_operacional.registros_legado SET conteudo_bruto = '{}'::jsonb "
                "WHERE snapshot_lote_id = (SELECT snapshot_lote_id FROM nsi_operacional.lotes_legado "
                "                           WHERE lote_id_legado = %s)", (documento["lote_id"],))
    assert cur.rowcount == 2
    cur.execute(
        "SELECT count(*) FROM pg_catalog.pg_trigger t JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid "
        "  JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
        " WHERE n.nspname = 'nsi_operacional' AND c.relname IN ('lotes_legado', 'registros_legado') "
        "   AND NOT t.tgisinternal")
    assert cur.fetchone()[0] == 0


# ============================================================
# Concorrencia real (item 12) - COMMIT real, somente lotes nao promoviveis
# ============================================================

def _importar_em_thread(url, importacao_id, caminho, conteudo, saida: dict, pid_pronto: threading.Event):
    conn = conectar_como_owner(url)
    try:
        cur = conn.cursor()
        cur.execute("SELECT pg_backend_pid()")
        saida["pid"] = cur.fetchone()[0]
        pid_pronto.set()
        saida["resultado"] = importar_bytes(cur, importacao_id, caminho, conteudo)
        conn.commit()
    except Exception as exc:  # reportada pelo teste, na thread principal
        saida["erro"] = exc
        conn.rollback()
    finally:
        pid_pronto.set()
        conn.close()


def _duas_importacoes_concorrentes(url, conteudo_a: bytes, conteudo_b: bytes, lote_id_legado: str) -> tuple:
    """Conexao A importa e fica com a transacao aberta; a conexao B, em
    outra execucao, importa o mesmo lote e e observada em espera pelo
    bloqueio; A confirma, B termina."""
    caminho = caminho_do_lote(lote_id_legado)
    conn_a = conectar_como_owner(url)
    try:
        cur_a = conn_a.cursor()
        importacao_a = iniciar(cur_a)
        importacao_b = iniciar(cur_a)
        conn_a.commit()

        cur_a.execute("SET LOCAL ROLE nsi_eventos_owner")
        resultado_a = importar_bytes(cur_a, importacao_a, caminho, conteudo_a)

        saida, pid_pronto = {}, threading.Event()
        thread = threading.Thread(
            target=_importar_em_thread, args=(url, importacao_b, caminho, conteudo_b, saida, pid_pronto))
        thread.start()
        try:
            assert pid_pronto.wait(10), "A conexao concorrente nao chegou a iniciar."
            observador = psycopg.connect(url)
            try:
                aguardar_bloqueio(observador, saida["pid"])
            finally:
                observador.close()
            conn_a.commit()
        finally:
            conn_a.rollback()
            thread.join(30)
        assert not thread.is_alive(), "A importacao concorrente nao terminou depois do commit da primeira."
        if "erro" in saida:
            raise saida["erro"]
        return resultado_a, saida["resultado"]
    finally:
        conn_a.close()


def test_duas_importacoes_concorrentes_do_mesmo_arquivo(request):
    """Uma gravacao e um ja_importado, serializadas pela unicidade de
    lote_id_legado e pelo bloqueio de claims."""
    url = request.getfixturevalue("url_banco_teste")
    documento = doc_a1()
    conteudo = serializar(documento)
    resultado_a, resultado_b = _duas_importacoes_concorrentes(url, conteudo, conteudo, documento["lote_id"])

    assert resultado_a["destino"] == "preservado"
    assert resultado_b["destino"] == "ja_importado"
    assert resultado_b["destino_original"] == "preservado"

    with psycopg.connect(url) as conn:
        cur = conn.cursor()
        cur.execute("SET LOCAL ROLE nsi_eventos_owner")
        assert contar(cur, "lotes_legado", "lote_id_legado = %s", (documento["lote_id"],)) == 1
        assert contar(cur, "registros_legado r JOIN nsi_operacional.lotes_legado g USING (snapshot_lote_id)",
                      "g.lote_id_legado = %s", (documento["lote_id"],)) == 2
        assert contar(cur, "importacoes_legado_arquivos", "lote_id_legado = %s", (documento["lote_id"],)) == 2
        conn.rollback()


def test_duas_importacoes_concorrentes_com_sha256_diferente(request):
    """Uma gravacao e uma recusa conflito_de_reimportacao."""
    url = request.getfixturevalue("url_banco_teste")
    documento = doc_a1()
    alterado = dict(documento, nome_lote="Lote Sintetico Alterado")
    resultado_a, resultado_b = _duas_importacoes_concorrentes(
        url, serializar(documento), serializar(alterado), documento["lote_id"])

    assert resultado_a["destino"] == "preservado"
    assert (resultado_b["destino"], resultado_b["motivo"]) == ("recusado", "conflito_de_reimportacao")

    with psycopg.connect(url) as conn:
        cur = conn.cursor()
        cur.execute("SET LOCAL ROLE nsi_eventos_owner")
        cur.execute("SELECT documento_sha256 FROM nsi_operacional.lotes_legado WHERE lote_id_legado = %s",
                    (documento["lote_id"],))
        assert cur.fetchall() == [(sha256_hex(serializar(documento)),)]
        conn.rollback()


# ============================================================
# Privacidade (item 17)
# ============================================================

def test_nenhum_valor_pessoal_em_retorno_nem_no_registro_tecnico(cur):
    importacao_id = iniciar(cur)
    invalido_json = serializar(doc_a2())[:-40]
    retornos = [
        importar(cur, importacao_id, doc_anterior_a1()),
        importar(cur, importacao_id, doc_a1()),
        importar(cur, importacao_id, doc_a2()),
        importar(cur, importacao_id, doc_a3()),
        importar(cur, importacao_id, _mutar(doc_a2(), lambda d: d["clientes"][0].update({"telefone": "x"}))),
        importar(cur, importacao_id, _mutar(doc_a2(), lambda d: d.update({"campo_nao_previsto": 1}))),
        importar_bytes(cur, importacao_id, "lotes/ILEGIVEL/lote.json", invalido_json),
    ]
    assert {r["destino"] for r in retornos} == {"preservado", "promovido", "recusado"}
    assert_sem_valor_pessoal(repr(retornos), "retornos de fn_importar_lote_legado")

    cur.execute("SELECT to_jsonb(i)::text FROM nsi_operacional.importacoes_legado i WHERE importacao_id = %s",
                (importacao_id,))
    assert_sem_valor_pessoal(repr(cur.fetchall()), "importacoes_legado")
    cur.execute("SELECT to_jsonb(a)::text FROM nsi_operacional.importacoes_legado_arquivos a "
                "WHERE importacao_id = %s", (importacao_id,))
    linhas = cur.fetchall()
    assert len(linhas) == 7
    assert_sem_valor_pessoal(repr(linhas), "importacoes_legado_arquivos")


def test_violacao_de_constraint_fora_da_promocao_nao_expoe_o_documento(cur):
    """Item 15: classe 23 com mensagem fixa, sem DETAIL e com o NOME da
    constraint. Nenhum documento sintetico valido viola as constraints do
    snapshot; por isso o teste acrescenta, na propria transacao (revertida
    ao final), uma CHECK temporaria que sempre falha. O detalhe nativo
    traria a linha inteira, com os valores pessoais do registro."""
    importacao_id = iniciar(cur)
    documento = doc_a1()
    cur.execute("ALTER TABLE nsi_operacional.registros_legado "
                "ADD CONSTRAINT ck_teste_sempre_falha CHECK (posicao < 0) NOT VALID")
    with pytest.raises(psycopg.errors.CheckViolation) as exc_info:
        importar(cur, importacao_id, documento)
    assert exc_info.value.sqlstate == "23514"
    assert exc_info.value.diag.message_primary == "violacao_de_constraint"
    assert exc_info.value.diag.message_detail is None
    assert exc_info.value.diag.constraint_name == "ck_teste_sempre_falha"
    assert_sem_valor_pessoal(str(exc_info.value) + repr(exc_info.value), "violacao de constraint")
    for registro_id in ids_do_documento(documento):
        assert registro_id not in str(exc_info.value)
