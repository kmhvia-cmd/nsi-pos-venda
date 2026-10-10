# -*- coding: utf-8 -*-
"""
NSI - tests/integration/test_fn_concluir_importacao_legado.py
(Sprint B, B5.4 - ADR-010, Secao 18; Especificacao Tecnica, B5.2, itens 5,
7, 12, 13, 15 e 16)

Testes de integracao REAIS contra PostgreSQL, exclusivamente contra
nsi_test, de fn_concluir_importacao_legado: gravacao do manifesto canonico,
SHA-256 recalculado no banco, conferencia do total de arquivos, replay,
conflito, execucao concluida fechada a novos lotes e concorrencia real
entre importacao e conclusao.

SOMENTE DADOS SINTETICOS. Os testes rodam sob SET LOCAL ROLE
nsi_eventos_owner e terminam em ROLLBACK, com uma excecao divulgada:

DIVULGACAO DE RESIDUO INTENCIONAL: test_conclusao_espera_a_importacao_em_
andamento exige COMMIT real e usa somente um lote NAO promovivel (geracao
a1). A execucao, sua conclusao, o snapshot e a linha do registro tecnico
ficam como residuo sintetico em nsi_test, nunca em nsi_dev, ate o downgrade
da 0006 remover as tabelas.
"""
import threading

import psycopg
import pytest

from tests.apoio_b4_3 import aguardar_bloqueio
from tests.apoio_b5 import (
    FUSO_PADRAO,
    assert_sem_valor_pessoal,
    caminho_do_lote,
    concluir,
    conectar_como_owner,
    contar,
    doc_a1,
    doc_a2,
    entrada_de_lote,
    entrada_de_tentativa_recusada,
    importar,
    importar_bytes,
    iniciar,
    ler_fixture,
    manifesto_canonico,
    serializar,
    sha256_hex,
    uuid_texto,
)

pytestmark = pytest.mark.pg_integration


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


def _execucao_com_lotes(cur, documentos, fuso=FUSO_PADRAO) -> tuple:
    """Abre a execucao, importa os documentos e devolve (importacao_id,
    manifesto) - sem concluir."""
    importacao_id = iniciar(cur, fuso)
    entradas = []
    for documento in documentos:
        conteudo = serializar(documento)
        resultado = importar_bytes(cur, importacao_id, caminho_do_lote(documento["lote_id"]), conteudo)
        entradas.append(entrada_de_lote(caminho_do_lote(documento["lote_id"]), conteudo, resultado))
    return importacao_id, manifesto_canonico(importacao_id, fuso, entradas)


# ============================================================
# Conclusao
# ============================================================

def test_conclusao_grava_os_bytes_canonicos_do_manifesto(cur):
    importacao_id, manifesto = _execucao_com_lotes(cur, [doc_a1(), doc_a2()])
    resultado = concluir(cur, importacao_id, manifesto, 2)

    assert set(resultado) == {"importacao_id", "concluida_em", "manifesto_sha256"}
    assert resultado["importacao_id"] == importacao_id
    assert resultado["manifesto_sha256"] == sha256_hex(manifesto)

    cur.execute(
        "SELECT manifesto_canonico, manifesto_sha256, total_arquivos, concluida_em = now(), "
        "       encode(sha256(manifesto_canonico), 'hex') "
        "  FROM nsi_operacional.importacoes_legado_conclusoes WHERE importacao_id = %s", (importacao_id,))
    bytes_gravados, sha_gravado, total, concluida_agora, sha_recalculado = cur.fetchone()
    assert bytes(bytes_gravados) == manifesto
    assert sha_gravado == sha_recalculado == sha256_hex(manifesto)
    assert total == 2
    assert concluida_agora is True


def test_manifesto_nao_contem_valor_pessoal(cur):
    importacao_id, manifesto = _execucao_com_lotes(cur, [doc_a1(), doc_a2()])
    concluir(cur, importacao_id, manifesto, 2)
    cur.execute("SELECT convert_from(manifesto_canonico, 'UTF8') FROM nsi_operacional.importacoes_legado_conclusoes "
                "WHERE importacao_id = %s", (importacao_id,))
    assert_sem_valor_pessoal(cur.fetchone()[0], "manifesto gravado")


def test_tentativas_recusadas_entram_so_no_manifesto_e_nao_contam_no_total(cur):
    """Item 16: total_arquivos e conferido contra as linhas registradas, sem
    contar as tentativas recusadas da A3."""
    importacao_id = iniciar(cur)
    documento = doc_a1()
    conteudo = serializar(documento)
    resultado = importar_bytes(cur, importacao_id, caminho_do_lote(documento["lote_id"]), conteudo)
    caminho_tentativa = "correcoes_rejeitadas/2026-01-09/3f0c1b7e-5a44-4c0e-9d0a-6f6f1f0a9b01.json"
    manifesto = manifesto_canonico(importacao_id, FUSO_PADRAO, [
        entrada_de_lote(caminho_do_lote(documento["lote_id"]), conteudo, resultado),
        entrada_de_tentativa_recusada(caminho_tentativa, ler_fixture(caminho_tentativa)),
    ])
    concluir(cur, importacao_id, manifesto, 1)
    assert contar(cur, "importacoes_legado_arquivos", "importacao_id = %s", (importacao_id,)) == 1


def test_execucao_sem_nenhum_lote_pode_ser_concluida(cur):
    importacao_id = iniciar(cur, None)
    manifesto = manifesto_canonico(importacao_id, None, [])
    assert concluir(cur, importacao_id, manifesto, 0)["manifesto_sha256"] == sha256_hex(manifesto)


def test_execucao_com_recusa_de_reimportacao_e_concluida_normalmente(cur):
    """Item 11: o conflito de reimportacao e recusa registrada, e nao
    impede a conclusao."""
    documento = doc_a1()
    importar(cur, iniciar(cur), documento)
    alterado = dict(documento, nome_lote="Lote Sintetico Alterado")
    importacao_id, manifesto = _execucao_com_lotes(cur, [alterado])
    assert b'"motivo":"conflito_de_reimportacao"' in manifesto
    concluir(cur, importacao_id, manifesto, 1)
    assert contar(cur, "importacoes_legado_conclusoes", "importacao_id = %s", (importacao_id,)) == 1


# ============================================================
# Entrada estruturalmente invalida (22000)
# ============================================================

@pytest.mark.parametrize("indice_nulo", [0, 1, 2, 3])
def test_parametro_nulo_e_recusado(cur, indice_nulo):
    importacao_id, manifesto = _execucao_com_lotes(cur, [doc_a1()])
    parametros = [importacao_id, manifesto, sha256_hex(manifesto), 1]
    parametros[indice_nulo] = None
    with pytest.raises(psycopg.errors.DataException) as exc_info:
        cur.execute("SELECT nsi_operacional.fn_concluir_importacao_legado(%s, %s, %s, %s)", parametros)
    _assert_erro_fixo(exc_info, "22000", "entrada_estrutural_invalida")


@pytest.mark.parametrize("sha256", ["", "abc", "A" * 64, "g" * 64, "a" * 63])
def test_sha256_do_manifesto_fora_do_formato_e_recusado(cur, sha256):
    importacao_id, manifesto = _execucao_com_lotes(cur, [doc_a1()])
    with pytest.raises(psycopg.errors.DataException) as exc_info:
        concluir(cur, importacao_id, manifesto, 1, sha256)
    _assert_erro_fixo(exc_info, "22000", "entrada_estrutural_invalida")


def test_bytes_do_manifesto_divergentes_do_hash_informado_sao_recusados(cur):
    """Item 13: SHA-256 recalculado no banco sobre os bytes gravados."""
    importacao_id, manifesto = _execucao_com_lotes(cur, [doc_a1()])
    cur.execute("SAVEPOINT sp")
    with pytest.raises(psycopg.errors.DataException) as exc_info:
        concluir(cur, importacao_id, manifesto + b" ", 1, sha256_hex(manifesto))
    _assert_erro_fixo(exc_info, "22000", "entrada_estrutural_invalida")
    assert sha256_hex(manifesto) not in str(exc_info.value)
    cur.execute("ROLLBACK TO SAVEPOINT sp")
    assert contar(cur, "importacoes_legado_conclusoes", "importacao_id = %s", (importacao_id,)) == 0


@pytest.mark.parametrize("total", [0, 2, 3, -1])
def test_total_de_arquivos_diferente_das_linhas_registradas_e_recusado(cur, total):
    importacao_id, manifesto = _execucao_com_lotes(cur, [doc_a1()])
    cur.execute("SAVEPOINT sp")
    with pytest.raises(psycopg.errors.DataException) as exc_info:
        concluir(cur, importacao_id, manifesto, total)
    _assert_erro_fixo(exc_info, "22000", "entrada_estrutural_invalida")
    cur.execute("ROLLBACK TO SAVEPOINT sp")
    assert contar(cur, "importacoes_legado_conclusoes", "importacao_id = %s", (importacao_id,)) == 0
    assert concluir(cur, importacao_id, manifesto, 1)["importacao_id"] == importacao_id


def test_execucao_inexistente_e_recusada(cur):
    manifesto = manifesto_canonico(uuid_texto(), None, [])
    with pytest.raises(psycopg.errors.DataException) as exc_info:
        concluir(cur, uuid_texto(), manifesto, 0)
    _assert_erro_fixo(exc_info, "22000", "entrada_estrutural_invalida")


# ============================================================
# Idempotencia (item 12)
# ============================================================

def test_replay_com_o_mesmo_manifesto_devolve_o_mesmo_resultado(cur):
    importacao_id, manifesto = _execucao_com_lotes(cur, [doc_a1()])
    primeiro = concluir(cur, importacao_id, manifesto, 1)
    segundo = concluir(cur, importacao_id, manifesto, 1)
    assert segundo == primeiro
    assert contar(cur, "importacoes_legado_conclusoes", "importacao_id = %s", (importacao_id,)) == 1


def test_mesmo_importacao_id_com_manifesto_diferente_e_conflito(cur):
    importacao_id, manifesto = _execucao_com_lotes(cur, [doc_a1()])
    concluir(cur, importacao_id, manifesto, 1)

    outro = manifesto_canonico(importacao_id, FUSO_PADRAO, [])
    cur.execute("SAVEPOINT sp")
    with pytest.raises(psycopg.errors.InvalidParameterValue) as exc_info:
        concluir(cur, importacao_id, outro, 1)
    _assert_erro_fixo(exc_info, "22023", "conflito_de_idempotencia")
    for texto in (str(exc_info.value), repr(exc_info.value)):
        assert sha256_hex(outro) not in texto and sha256_hex(manifesto) not in texto
    cur.execute("ROLLBACK TO SAVEPOINT sp")

    cur.execute("SELECT manifesto_sha256 FROM nsi_operacional.importacoes_legado_conclusoes "
                "WHERE importacao_id = %s", (importacao_id,))
    assert cur.fetchone()[0] == sha256_hex(manifesto), "A conclusao original permanece intocada."


def test_execucao_concluida_nao_aceita_novos_lotes(cur):
    importacao_id, manifesto = _execucao_com_lotes(cur, [doc_a1()])
    concluir(cur, importacao_id, manifesto, 1)
    antes = contar(cur, "importacoes_legado_arquivos", "importacao_id = %s", (importacao_id,))

    cur.execute("SAVEPOINT sp")
    with pytest.raises(psycopg.errors.DataException) as exc_info:
        importar(cur, importacao_id, doc_a2())
    _assert_erro_fixo(exc_info, "22000", "entrada_estrutural_invalida")
    cur.execute("ROLLBACK TO SAVEPOINT sp")
    assert contar(cur, "importacoes_legado_arquivos", "importacao_id = %s", (importacao_id,)) == antes


def test_conclusao_e_imutavel_inclusive_para_o_owner(cur):
    importacao_id, manifesto = _execucao_com_lotes(cur, [doc_a1()])
    concluir(cur, importacao_id, manifesto, 1)
    for comando in ("UPDATE nsi_operacional.importacoes_legado_conclusoes SET total_arquivos = 9 WHERE importacao_id = %s",
                    "DELETE FROM nsi_operacional.importacoes_legado_conclusoes WHERE importacao_id = %s"):
        cur.execute("SAVEPOINT sp")
        with pytest.raises(psycopg.errors.RaiseException) as exc_info:
            cur.execute(comando, (importacao_id,))
        assert "registro tecnico imutavel" in exc_info.value.diag.message_primary
        cur.execute("ROLLBACK TO SAVEPOINT sp")


def test_check_da_tabela_exige_o_sha256_dos_bytes_gravados(cur):
    importacao_id = iniciar(cur)
    with pytest.raises(psycopg.errors.CheckViolation) as exc_info:
        cur.execute(
            "INSERT INTO nsi_operacional.importacoes_legado_conclusoes "
            "(importacao_id, manifesto_canonico, manifesto_sha256, total_arquivos) VALUES (%s, %s, %s, 0)",
            (importacao_id, b"{}", "0" * 64))
    assert exc_info.value.diag.constraint_name == "ck_importacoes_legado_conclusoes_sha256_recalculado"


# ============================================================
# Concorrencia real entre importacao e conclusao (item 12)
# ============================================================

def test_conclusao_espera_a_importacao_em_andamento(request):
    """A importacao bloqueia a linha da execucao FOR SHARE; a conclusao, que
    a bloqueia FOR UPDATE, e observada em espera. Depois do commit da
    importacao, a conclusao confere o total JA com a linha concorrente: o
    total 1 e aceito, e uma nova importacao e recusada."""
    url = request.getfixturevalue("url_banco_teste")
    documento = doc_a1()
    conteudo = serializar(documento)
    saida, pid_pronto = {}, threading.Event()

    def _concluir(importacao_id, manifesto):
        conn = conectar_como_owner(url)
        try:
            cur = conn.cursor()
            cur.execute("SELECT pg_backend_pid()")
            saida["pid"] = cur.fetchone()[0]
            pid_pronto.set()
            saida["resultado"] = concluir(cur, importacao_id, manifesto, 1)
            conn.commit()
        except Exception as exc:  # reportada pelo teste, na thread principal
            saida["erro"] = exc
            conn.rollback()
        finally:
            pid_pronto.set()
            conn.close()

    conn_a = conectar_como_owner(url)
    try:
        cur_a = conn_a.cursor()
        importacao_id = iniciar(cur_a)
        conn_a.commit()

        cur_a.execute("SET LOCAL ROLE nsi_eventos_owner")
        resultado = importar_bytes(cur_a, importacao_id, caminho_do_lote(documento["lote_id"]), conteudo)
        manifesto = manifesto_canonico(
            importacao_id, FUSO_PADRAO, [entrada_de_lote(caminho_do_lote(documento["lote_id"]), conteudo, resultado)])

        thread = threading.Thread(target=_concluir, args=(importacao_id, manifesto))
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
        assert not thread.is_alive(), "A conclusao nao terminou depois do commit da importacao."
        if "erro" in saida:
            raise saida["erro"]
        assert saida["resultado"]["manifesto_sha256"] == sha256_hex(manifesto)

        cur_a.execute("SET LOCAL ROLE nsi_eventos_owner")
        assert contar(cur_a, "importacoes_legado_conclusoes",
                      "importacao_id = %s AND total_arquivos = 1", (importacao_id,)) == 1
        with pytest.raises(psycopg.errors.DataException) as exc_info:
            importar(cur_a, importacao_id, doc_a1())
        assert exc_info.value.sqlstate == "22000"
    finally:
        conn_a.rollback()
        conn_a.close()


def test_importacao_que_espera_a_conclusao_e_recusada(request):
    """Sentido inverso: a conclusao esta em andamento; a importacao espera o
    bloqueio da linha da execucao e, depois do commit, encontra a execucao
    concluida (22000), sem gravar nada. Somente a execucao concluida e
    vazia fica como residuo sintetico."""
    url = request.getfixturevalue("url_banco_teste")
    documento = doc_a1()
    saida, pid_pronto = {}, threading.Event()

    def _importar(importacao_id):
        conn = conectar_como_owner(url)
        try:
            cur = conn.cursor()
            cur.execute("SELECT pg_backend_pid()")
            saida["pid"] = cur.fetchone()[0]
            pid_pronto.set()
            saida["resultado"] = importar(cur, importacao_id, documento)
            conn.commit()
        except Exception as exc:  # esperada: 22000
            saida["erro"] = exc
            conn.rollback()
        finally:
            pid_pronto.set()
            conn.close()

    conn_a = conectar_como_owner(url)
    try:
        cur_a = conn_a.cursor()
        importacao_id = iniciar(cur_a, None)
        conn_a.commit()

        cur_a.execute("SET LOCAL ROLE nsi_eventos_owner")
        concluir(cur_a, importacao_id, manifesto_canonico(importacao_id, None, []), 0)

        thread = threading.Thread(target=_importar, args=(importacao_id,))
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
        assert not thread.is_alive()

        assert "resultado" not in saida, "Nenhuma importacao grava depois de a conclusao ter contado."
        assert isinstance(saida.get("erro"), psycopg.errors.DataException)
        assert saida["erro"].sqlstate == "22000"

        cur_a.execute("SET LOCAL ROLE nsi_eventos_owner")
        assert contar(cur_a, "importacoes_legado_arquivos", "importacao_id = %s", (importacao_id,)) == 0
        assert contar(cur_a, "lotes_legado", "lote_id_legado = %s", (documento["lote_id"],)) == 0
    finally:
        conn_a.rollback()
        conn_a.close()
