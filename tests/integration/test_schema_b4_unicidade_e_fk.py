# -*- coding: utf-8 -*-
"""
NSI - tests/integration/test_schema_b4_unicidade_e_fk.py
(Sprint B, B4.2 - ADR-009)

Testes de integracao REAIS contra PostgreSQL, exclusivamente contra
nsi_test, das restricoes de unicidade e das FKs criadas pela migration
0004:

- uq_eventos_lote_aggregate_versao: UNIQUE (aggregate_id, aggregate_version).
- eventos_lote_criado_unico / eventos_lote_congelado_unico /
  eventos_lote_disparo_confirmado_unico: UNIQUE parcial (aggregate_id)
  por tipo - cada um dos tres so pode ocorrer uma vez por lote.
- uq_eventos_registro_coleta_aggregate_versao: UNIQUE (aggregate_id, aggregate_version).
- registros_coleta.lote_id -> lotes.lote_id.
- eventos_lote.aggregate_id -> lotes.lote_id.
- eventos_registro_coleta.aggregate_id -> registros_coleta.registro_coleta_id.
- lotes.lote_id_legado: UNIQUE parcial (WHERE NOT NULL).

Mesma disciplina de test_schema_b3_unicidade_e_fk.py: conexao do
migrator com 'SET LOCAL ROLE nsi_eventos_owner', cada tentativa isolada
num SAVEPOINT proprio, a transacao externa sempre revertida no
teardown - nenhum residuo em nsi_test.

Pressupoe a migration 0004 ja aplicada em nsi_test. Nenhum teste deste
arquivo chama pytest nem executa a suite completa internamente.
"""
import uuid
from datetime import datetime, timedelta, timezone

import psycopg
import pytest

pytestmark = pytest.mark.pg_integration

_RECEBIDO_EM_BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)
_HORARIO_CONCEITUAL_BASE = _RECEBIDO_EM_BASE + timedelta(hours=192)


def _uuid() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def cur(request):
    """A URL e obtida internamente via request.getfixturevalue(), nunca
    como parametro nomeado desta fixture."""
    url = request.getfixturevalue("url_banco_teste")
    conn = psycopg.connect(url)
    try:
        cursor = conn.cursor()
        cursor.execute("SET LOCAL ROLE nsi_eventos_owner")
        yield cursor
    finally:
        conn.rollback()
        conn.close()


_SQL_INSERT_LOTE = """
    INSERT INTO nsi_operacional.lotes
        (lote_id, lote_id_legado, recebido_em, total_recebido, total_valido, total_invalido,
         total_valido_congelado, status, horario_conceitual_congelamento, horario_real_congelamento,
         congelamento_atrasado, disparo_confirmado_em, disparo_confirmado_por_login,
         total_confirmado_para_disparo, versao_eventos_atual)
    VALUES
        (%(lote_id)s, %(lote_id_legado)s, %(recebido_em)s, %(total_recebido)s, %(total_valido)s, %(total_invalido)s,
         %(total_valido_congelado)s, %(status)s, %(horario_conceitual_congelamento)s, %(horario_real_congelamento)s,
         %(congelamento_atrasado)s, %(disparo_confirmado_em)s, %(disparo_confirmado_por_login)s,
         %(total_confirmado_para_disparo)s, %(versao_eventos_atual)s)
"""

_SQL_INSERT_REGISTRO = """
    INSERT INTO nsi_operacional.registros_coleta
        (registro_coleta_id, lote_id, nome, produto, whatsapp, valido, motivos_invalidez,
         numero_versao_dados, versao_eventos_atual)
    VALUES
        (%(registro_coleta_id)s, %(lote_id)s, %(nome)s, %(produto)s, %(whatsapp)s, %(valido)s,
         %(motivos_invalidez)s, %(numero_versao_dados)s, %(versao_eventos_atual)s)
"""

_SQL_INSERT_EVENTO_LOTE = """
    INSERT INTO nsi_operacional.eventos_lote
        (evento_id, aggregate_type, aggregate_id, aggregate_version, tipo, executado_por_login,
         recebido_em, total_recebido, total_valido, total_invalido,
         horario_conceitual, horario_real_execucao, atrasado,
         operador_humano_id, total_confirmado, motivo, codigo_tecnico_normalizado)
    VALUES
        (%(evento_id)s, 'lote', %(aggregate_id)s, %(aggregate_version)s, %(tipo)s,
         %(executado_por_login)s, %(recebido_em)s, %(total_recebido)s, %(total_valido)s, %(total_invalido)s,
         %(horario_conceitual)s, %(horario_real_execucao)s, %(atrasado)s,
         %(operador_humano_id)s, %(total_confirmado)s, %(motivo)s, %(codigo_tecnico_normalizado)s)
"""

_SQL_INSERT_EVENTO_REGISTRO = """
    INSERT INTO nsi_operacional.eventos_registro_coleta
        (evento_id, aggregate_type, aggregate_id, aggregate_version, tipo, executado_por_login,
         resultado, numero_versao_dados)
    VALUES
        (%(evento_id)s, 'registro_coleta', %(aggregate_id)s, %(aggregate_version)s, 'correcao_registrada',
         %(executado_por_login)s, %(resultado)s, %(numero_versao_dados)s)
"""


def _inserir_lote(cur, **overrides) -> str:
    base = dict(
        lote_id=_uuid(),
        lote_id_legado=None,
        recebido_em=_RECEBIDO_EM_BASE,
        total_recebido=0,
        total_valido=0,
        total_invalido=0,
        total_valido_congelado=None,
        status="aguardando_d8",
        horario_conceitual_congelamento=_HORARIO_CONCEITUAL_BASE,
        horario_real_congelamento=None,
        congelamento_atrasado=None,
        disparo_confirmado_em=None,
        disparo_confirmado_por_login=None,
        total_confirmado_para_disparo=None,
        versao_eventos_atual=1,
    )
    base.update(overrides)
    cur.execute(_SQL_INSERT_LOTE, base)
    return base["lote_id"]


def _inserir_registro(cur, lote_id: str, **overrides) -> str:
    base = dict(
        registro_coleta_id=_uuid(),
        lote_id=lote_id,
        nome="Cliente de Teste",
        produto="Produto de Teste",
        whatsapp="5511987654321",
        valido=True,
        motivos_invalidez=None,
        numero_versao_dados=1,
        versao_eventos_atual=0,
    )
    base.update(overrides)
    cur.execute(_SQL_INSERT_REGISTRO, base)
    return base["registro_coleta_id"]


def _inserir_evento_lote(cur, lote_id: str, aggregate_version: int, tipo: str, **overrides) -> str:
    evento_id = overrides.pop("evento_id", _uuid())
    base = dict(
        evento_id=evento_id,
        aggregate_id=lote_id,
        aggregate_version=aggregate_version,
        tipo=tipo,
        executado_por_login="nsi_aplicacao",
        recebido_em=None, total_recebido=None, total_valido=None, total_invalido=None,
        horario_conceitual=None, horario_real_execucao=None, atrasado=None,
        operador_humano_id=None, total_confirmado=None, motivo=None, codigo_tecnico_normalizado=None,
    )
    if tipo == "lote_criado":
        base.update(recebido_em=_RECEBIDO_EM_BASE, total_recebido=0, total_valido=0, total_invalido=0)
    elif tipo == "lote_congelado_d8":
        base.update(horario_conceitual=_HORARIO_CONCEITUAL_BASE, horario_real_execucao=_HORARIO_CONCEITUAL_BASE,
                     atrasado=False)
    elif tipo == "disparo_confirmado":
        base.update(executado_por_login="nsi_operador_restrito", total_confirmado=5)
    elif tipo == "tentativa_correcao_nao_resolvida":
        base.update(motivo="codigo_inexistente")
    base.update(overrides)
    cur.execute(_SQL_INSERT_EVENTO_LOTE, base)
    return evento_id


def _inserir_evento_registro(cur, registro_coleta_id: str, aggregate_version: int,
                              resultado: str = "aplicada_valida", **overrides) -> str:
    evento_id = overrides.pop("evento_id", _uuid())
    base = dict(
        evento_id=evento_id,
        aggregate_id=registro_coleta_id,
        aggregate_version=aggregate_version,
        executado_por_login="nsi_aplicacao",
        resultado=resultado,
        numero_versao_dados=2 if resultado in ("aplicada_valida", "aplicada_ainda_invalida") else None,
    )
    base.update(overrides)
    cur.execute(_SQL_INSERT_EVENTO_REGISTRO, base)
    return evento_id


# ============================================================
# lotes.lote_id_legado - UNIQUE parcial
# ============================================================

def test_lote_id_legado_duplicado_rejeitado(cur):
    cur.execute("SAVEPOINT sp1")
    try:
        legado = "NSI-20260515-A7DCB1"
        _inserir_lote(cur, lote_id_legado=legado)
        with pytest.raises(psycopg.errors.UniqueViolation) as exc_info:
            _inserir_lote(cur, lote_id_legado=legado)
        assert exc_info.value.sqlstate == "23505"
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp1")


def test_lote_id_legado_nulo_nao_colide(cur):
    cur.execute("SAVEPOINT sp2")
    try:
        _inserir_lote(cur, lote_id_legado=None)
        _inserir_lote(cur, lote_id_legado=None)
    except Exception as exc:
        cur.execute("ROLLBACK TO SAVEPOINT sp2")
        pytest.fail(f"Esperado sucesso, mas falhou: {exc!r}")
    else:
        cur.execute("ROLLBACK TO SAVEPOINT sp2")


# ============================================================
# registros_coleta.lote_id -> lotes.lote_id
# ============================================================

def test_registro_coleta_orfao_rejeitado(cur):
    cur.execute("SAVEPOINT sp3")
    try:
        with pytest.raises(psycopg.errors.ForeignKeyViolation) as exc_info:
            _inserir_registro(cur, lote_id=_uuid())
        assert exc_info.value.sqlstate == "23503"
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp3")


def test_registro_coleta_com_lote_existente_aceito(cur):
    cur.execute("SAVEPOINT sp4")
    try:
        lote_id = _inserir_lote(cur)
        _inserir_registro(cur, lote_id)
    except Exception as exc:
        cur.execute("ROLLBACK TO SAVEPOINT sp4")
        pytest.fail(f"Esperado sucesso, mas falhou: {exc!r}")
    else:
        cur.execute("ROLLBACK TO SAVEPOINT sp4")


# ============================================================
# eventos_lote.aggregate_id -> lotes.lote_id (impede evento orfao)
# ============================================================

def test_evento_lote_orfao_rejeitado(cur):
    cur.execute("SAVEPOINT sp5")
    try:
        with pytest.raises(psycopg.errors.ForeignKeyViolation) as exc_info:
            _inserir_evento_lote(cur, _uuid(), 1, "lote_criado")
        assert exc_info.value.sqlstate == "23503"
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp5")


# ============================================================
# eventos_registro_coleta.aggregate_id -> registros_coleta.registro_coleta_id
# ============================================================

def test_evento_registro_coleta_orfao_rejeitado(cur):
    cur.execute("SAVEPOINT sp6")
    try:
        with pytest.raises(psycopg.errors.ForeignKeyViolation) as exc_info:
            _inserir_evento_registro(cur, _uuid(), 1)
        assert exc_info.value.sqlstate == "23503"
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp6")


# ============================================================
# uq_eventos_lote_aggregate_versao
# ============================================================

def test_eventos_lote_versao_duplicada_rejeitada(cur):
    cur.execute("SAVEPOINT sp7")
    try:
        lote_id = _inserir_lote(cur)
        _inserir_evento_lote(cur, lote_id, 1, "lote_criado")
        with pytest.raises(psycopg.errors.UniqueViolation) as exc_info:
            _inserir_evento_lote(cur, lote_id, 1, "tentativa_correcao_nao_resolvida")
        assert exc_info.value.sqlstate == "23505"
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp7")


def test_eventos_lote_versoes_distintas_aceitas(cur):
    cur.execute("SAVEPOINT sp8")
    try:
        lote_id = _inserir_lote(cur)
        _inserir_evento_lote(cur, lote_id, 1, "lote_criado")
        _inserir_evento_lote(cur, lote_id, 2, "lote_congelado_d8")
    except Exception as exc:
        cur.execute("ROLLBACK TO SAVEPOINT sp8")
        pytest.fail(f"Esperado sucesso, mas falhou: {exc!r}")
    else:
        cur.execute("ROLLBACK TO SAVEPOINT sp8")


# ============================================================
# eventos_lote_criado_unico / _congelado_unico / _disparo_confirmado_unico
# ============================================================

@pytest.mark.parametrize("tipo", ["lote_criado", "lote_congelado_d8", "disparo_confirmado"])
def test_eventos_lote_tipo_unico_rejeita_segunda_ocorrencia(cur, tipo):
    cur.execute("SAVEPOINT sp9")
    try:
        lote_id = _inserir_lote(cur)
        _inserir_evento_lote(cur, lote_id, 1, tipo)
        with pytest.raises(psycopg.errors.UniqueViolation) as exc_info:
            _inserir_evento_lote(cur, lote_id, 2, tipo)
        assert exc_info.value.sqlstate == "23505"
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp9")


def test_eventos_lote_tentativa_nao_resolvida_aceita_multiplas_ocorrencias(cur):
    """tentativa_correcao_nao_resolvida nao tem UNIQUE parcial - pode
    repetir quantas vezes forem necessarias para o mesmo lote."""
    cur.execute("SAVEPOINT sp10")
    try:
        lote_id = _inserir_lote(cur)
        _inserir_evento_lote(cur, lote_id, 1, "tentativa_correcao_nao_resolvida")
        _inserir_evento_lote(cur, lote_id, 2, "tentativa_correcao_nao_resolvida")
    except Exception as exc:
        cur.execute("ROLLBACK TO SAVEPOINT sp10")
        pytest.fail(f"Esperado sucesso, mas falhou: {exc!r}")
    else:
        cur.execute("ROLLBACK TO SAVEPOINT sp10")


def test_eventos_lote_tipos_distintos_nao_colidem_no_indice_parcial(cur):
    cur.execute("SAVEPOINT sp11")
    try:
        lote_id = _inserir_lote(cur)
        _inserir_evento_lote(cur, lote_id, 1, "lote_criado")
        _inserir_evento_lote(cur, lote_id, 2, "lote_congelado_d8")
        _inserir_evento_lote(cur, lote_id, 3, "disparo_confirmado")
    except Exception as exc:
        cur.execute("ROLLBACK TO SAVEPOINT sp11")
        pytest.fail(f"Esperado sucesso, mas falhou: {exc!r}")
    else:
        cur.execute("ROLLBACK TO SAVEPOINT sp11")


# ============================================================
# uq_eventos_registro_coleta_aggregate_versao
# ============================================================

def test_eventos_registro_coleta_versao_duplicada_rejeitada(cur):
    cur.execute("SAVEPOINT sp12")
    try:
        lote_id = _inserir_lote(cur)
        registro_id = _inserir_registro(cur, lote_id)
        _inserir_evento_registro(cur, registro_id, 1, resultado="aplicada_ainda_invalida")
        with pytest.raises(psycopg.errors.UniqueViolation) as exc_info:
            _inserir_evento_registro(cur, registro_id, 1, resultado="recusada_tardia")
        assert exc_info.value.sqlstate == "23505"
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp12")


def test_eventos_registro_coleta_versoes_distintas_aceitas(cur):
    cur.execute("SAVEPOINT sp13")
    try:
        lote_id = _inserir_lote(cur)
        registro_id = _inserir_registro(cur, lote_id)
        _inserir_evento_registro(cur, registro_id, 1, resultado="aplicada_ainda_invalida")
        _inserir_evento_registro(cur, registro_id, 2, resultado="recusada_tardia")
        _inserir_evento_registro(cur, registro_id, 3, resultado="aplicada_valida")
    except Exception as exc:
        cur.execute("ROLLBACK TO SAVEPOINT sp13")
        pytest.fail(f"Esperado sucesso, mas falhou: {exc!r}")
    else:
        cur.execute("ROLLBACK TO SAVEPOINT sp13")


def test_eventos_registro_coleta_multiplos_registros_mesmo_lote_nao_colidem(cur):
    """aggregate_id diferente (registros distintos) com mesma
    aggregate_version nunca colide - a UNIQUE e por par."""
    cur.execute("SAVEPOINT sp14")
    try:
        lote_id = _inserir_lote(cur)
        registro_a = _inserir_registro(cur, lote_id)
        registro_b = _inserir_registro(cur, lote_id)
        _inserir_evento_registro(cur, registro_a, 1, resultado="aplicada_ainda_invalida")
        _inserir_evento_registro(cur, registro_b, 1, resultado="aplicada_ainda_invalida")
    except Exception as exc:
        cur.execute("ROLLBACK TO SAVEPOINT sp14")
        pytest.fail(f"Esperado sucesso, mas falhou: {exc!r}")
    else:
        cur.execute("ROLLBACK TO SAVEPOINT sp14")
