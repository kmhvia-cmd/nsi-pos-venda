# -*- coding: utf-8 -*-
"""
NSI - tests/integration/test_schema_b4_constraints.py
(Sprint B, B4.2 - ADR-009)

Testes de integracao REAIS contra PostgreSQL, exclusivamente contra
nsi_test, das CHECK constraints das quatro tabelas criadas pela
migration 0004 (nsi_operacional.lotes, registros_coleta, eventos_lote,
eventos_registro_coleta) - cada uma testada nos dois sentidos (valor
valido aceito, valor invalido rejeitado com CheckViolation / SQLSTATE
23514).

Mesma disciplina de test_schema_b3_constraints.py: como nenhuma role
funcional tem privilegio DML direto (REVOKE ALL explicito na propria
migration 0004) e nenhuma funcao SECURITY DEFINER existe ainda (B4.3),
todo INSERT deste arquivo roda com a conexao do migrator apos 'SET
LOCAL ROLE nsi_eventos_owner' - nunca commitado: cada tentativa roda
dentro de um SAVEPOINT proprio, revertido logo em seguida, e a
transacao externa e sempre revertida ao final do teste (fixture).
nsi_test nunca fica com residuo de dados de teste.

Pressupoe a migration 0004 ja aplicada em nsi_test - roda como parte do
ciclo de testes descrito em test_migration_0004_upgrade_downgrade.py,
nunca isoladamente contra um banco ainda em 0003.

Nenhum teste deste arquivo chama pytest nem executa a suite completa
internamente.
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
    """Conexao real contra nsi_test, com 'SET LOCAL ROLE nsi_eventos_owner'
    ja ativo - a transacao externa e sempre revertida no teardown, nunca
    commitada. A URL e obtida internamente via request.getfixturevalue(),
    nunca como parametro nomeado desta fixture."""
    url = request.getfixturevalue("url_banco_teste")
    conn = psycopg.connect(url)
    try:
        cursor = conn.cursor()
        cursor.execute("SET LOCAL ROLE nsi_eventos_owner")
        yield cursor
    finally:
        conn.rollback()
        conn.close()


def _aceita(cur, sql: str, params: dict) -> None:
    cur.execute("SAVEPOINT sp_teste")
    try:
        cur.execute(sql, params)
    except Exception as exc:
        cur.execute("ROLLBACK TO SAVEPOINT sp_teste")
        pytest.fail(f"Esperado sucesso, mas falhou: {exc!r}")
    else:
        cur.execute("ROLLBACK TO SAVEPOINT sp_teste")


def _rejeita(cur, sql: str, params: dict, sqlstate_esperado: str = "23514") -> None:
    cur.execute("SAVEPOINT sp_teste")
    try:
        with pytest.raises(psycopg.errors.CheckViolation) as exc_info:
            cur.execute(sql, params)
        assert exc_info.value.sqlstate == sqlstate_esperado
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp_teste")


# ============================================================
# nsi_operacional.lotes
# ============================================================

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


def _params_lote_aguardando_d8(**overrides) -> dict:
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
    return base


def _params_lote_sem_registros_validos(**overrides) -> dict:
    base = _params_lote_aguardando_d8(
        status="sem_registros_validos",
        total_valido_congelado=0,
        horario_real_congelamento=_HORARIO_CONCEITUAL_BASE,
        congelamento_atrasado=False,
    )
    base.update(overrides)
    return base


def _params_lote_aguardando_confirmacao(**overrides) -> dict:
    base = _params_lote_aguardando_d8(
        status="aguardando_confirmacao_disparo",
        total_recebido=7,
        total_valido=5,
        total_invalido=2,
        total_valido_congelado=5,
        horario_real_congelamento=_HORARIO_CONCEITUAL_BASE,
        congelamento_atrasado=False,
    )
    base.update(overrides)
    return base


def _params_lote_disparo_confirmado(**overrides) -> dict:
    base = _params_lote_aguardando_confirmacao(
        status="disparo_confirmado",
        disparo_confirmado_em=_HORARIO_CONCEITUAL_BASE + timedelta(hours=1),
        disparo_confirmado_por_login="nsi_operador_restrito",
        total_confirmado_para_disparo=5,
    )
    base.update(overrides)
    return base


def test_lotes_aguardando_d8_com_total_valido_zero_aceito(cur):
    """Achado central da rodada de correcao: um lote pode nascer
    'aguardando_d8' com total_valido = 0 - nunca 'sem_registros_validos'
    na criacao (ADR-007 SS9.3/SS12)."""
    _aceita(cur, _SQL_INSERT_LOTE, _params_lote_aguardando_d8(total_valido=0, total_invalido=0, total_recebido=0))


def test_lotes_aguardando_d8_com_total_valido_positivo_aceito(cur):
    _aceita(cur, _SQL_INSERT_LOTE, _params_lote_aguardando_d8(total_valido=3, total_invalido=1, total_recebido=4))


def test_lotes_sem_registros_validos_congelado_aceito(cur):
    _aceita(cur, _SQL_INSERT_LOTE, _params_lote_sem_registros_validos())


def test_lotes_sem_registros_validos_na_criacao_rejeitado(cur):
    """sem_registros_validos exige campos de congelamento preenchidos -
    nunca alcancavel na criacao."""
    _rejeita(cur, _SQL_INSERT_LOTE, _params_lote_aguardando_d8(
        status="sem_registros_validos", total_valido_congelado=0,
    ))


def test_lotes_aguardando_confirmacao_disparo_aceito(cur):
    _aceita(cur, _SQL_INSERT_LOTE, _params_lote_aguardando_confirmacao())


def test_lotes_disparo_confirmado_aceito(cur):
    _aceita(cur, _SQL_INSERT_LOTE, _params_lote_disparo_confirmado())


def test_lotes_totais_incoerentes_rejeitado(cur):
    _rejeita(cur, _SQL_INSERT_LOTE, _params_lote_aguardando_d8(
        total_recebido=10, total_valido=3, total_invalido=3,
    ))


def test_lotes_total_valido_negativo_rejeitado(cur):
    _rejeita(cur, _SQL_INSERT_LOTE, _params_lote_aguardando_d8(
        total_valido=-1, total_recebido=-1, total_invalido=0,
    ))


def test_lotes_lote_id_legado_formato_valido_aceito(cur):
    _aceita(cur, _SQL_INSERT_LOTE, _params_lote_aguardando_d8(lote_id_legado="NSI-20260515-A7DCB1"))


def test_lotes_lote_id_legado_formato_invalido_rejeitado(cur):
    _rejeita(cur, _SQL_INSERT_LOTE, _params_lote_aguardando_d8(lote_id_legado="lote-qualquer"))


def test_lotes_horario_conceitual_correto_aceito(cur):
    _aceita(cur, _SQL_INSERT_LOTE, _params_lote_aguardando_d8(
        horario_conceitual_congelamento=_RECEBIDO_EM_BASE + timedelta(hours=192),
    ))


def test_lotes_horario_conceitual_incorreto_rejeitado(cur):
    _rejeita(cur, _SQL_INSERT_LOTE, _params_lote_aguardando_d8(
        horario_conceitual_congelamento=_RECEBIDO_EM_BASE + timedelta(hours=191),
    ))


def test_lotes_congelamento_parcial_rejeitado(cur):
    _rejeita(cur, _SQL_INSERT_LOTE, _params_lote_aguardando_confirmacao(
        congelamento_atrasado=None,
    ))


def test_lotes_atrasado_incoerente_rejeitado(cur):
    _rejeita(cur, _SQL_INSERT_LOTE, _params_lote_aguardando_confirmacao(
        congelamento_atrasado=True,  # horario_real == horario_conceitual, nao e atrasado
    ))


def test_lotes_horario_congelamento_exato_aceito(cur):
    """horario_real_congelamento exatamente igual ao conceitual -
    aceito, congelamento_atrasado FALSE."""
    _aceita(cur, _SQL_INSERT_LOTE, _params_lote_aguardando_confirmacao(
        horario_real_congelamento=_HORARIO_CONCEITUAL_BASE, congelamento_atrasado=False,
    ))


def test_lotes_horario_congelamento_tardio_aceito(cur):
    """horario_real_congelamento posterior ao conceitual - aceito,
    congelamento_atrasado TRUE."""
    _aceita(cur, _SQL_INSERT_LOTE, _params_lote_aguardando_confirmacao(
        horario_real_congelamento=_HORARIO_CONCEITUAL_BASE + timedelta(hours=2),
        congelamento_atrasado=True,
    ))


def test_lotes_horario_congelamento_antecipado_rejeitado(cur):
    """horario_real_congelamento ANTERIOR ao conceitual - deve ser
    rejeitado por ck_lotes_congelamento_nunca_antecipado, mesmo com a
    flag congelamento_atrasado coerente (FALSE, ja que antecipado nao
    e '>')."""
    _rejeita(cur, _SQL_INSERT_LOTE, _params_lote_aguardando_confirmacao(
        horario_real_congelamento=_HORARIO_CONCEITUAL_BASE - timedelta(hours=1),
        congelamento_atrasado=False,
    ))


def test_lotes_flag_atrasado_incoerente_com_horario_tardio_rejeitado(cur):
    """Horario realmente tardio, mas a flag diz que nao foi - recusado
    por ck_lotes_atrasado_correto."""
    _rejeita(cur, _SQL_INSERT_LOTE, _params_lote_aguardando_confirmacao(
        horario_real_congelamento=_HORARIO_CONCEITUAL_BASE + timedelta(hours=2),
        congelamento_atrasado=False,
    ))


def test_lotes_versao_eventos_zero_rejeitado(cur):
    _rejeita(cur, _SQL_INSERT_LOTE, _params_lote_aguardando_d8(versao_eventos_atual=0))


def test_lotes_status_invalido_rejeitado(cur):
    _rejeita(cur, _SQL_INSERT_LOTE, _params_lote_aguardando_d8(status="cancelado"))


def test_lotes_disparo_confirmado_sem_congelamento_rejeitado(cur):
    _rejeita(cur, _SQL_INSERT_LOTE, _params_lote_aguardando_d8(
        status="disparo_confirmado", total_valido=5, total_recebido=5,
        disparo_confirmado_em=_HORARIO_CONCEITUAL_BASE,
        disparo_confirmado_por_login="nsi_operador_restrito",
        total_confirmado_para_disparo=5,
    ))


def test_lotes_total_confirmado_divergente_do_congelado_rejeitado(cur):
    _rejeita(cur, _SQL_INSERT_LOTE, _params_lote_disparo_confirmado(total_confirmado_para_disparo=99))


def test_lotes_aguardando_confirmacao_com_total_valido_zero_rejeitado(cur):
    _rejeita(cur, _SQL_INSERT_LOTE, _params_lote_aguardando_confirmacao(
        total_valido=0, total_valido_congelado=0, total_recebido=2, total_invalido=2,
    ))


# ============================================================
# nsi_operacional.registros_coleta
# ============================================================

_SQL_INSERT_REGISTRO = """
    INSERT INTO nsi_operacional.registros_coleta
        (registro_coleta_id, lote_id, nome, produto, whatsapp, valido, motivos_invalidez,
         numero_versao_dados, versao_eventos_atual)
    VALUES
        (%(registro_coleta_id)s, %(lote_id)s, %(nome)s, %(produto)s, %(whatsapp)s, %(valido)s,
         %(motivos_invalidez)s, %(numero_versao_dados)s, %(versao_eventos_atual)s)
"""


def _inserir_lote_base(cur, **overrides) -> str:
    params = _params_lote_aguardando_d8(**overrides)
    cur.execute(_SQL_INSERT_LOTE, params)
    return params["lote_id"]


def _params_registro_valido(lote_id: str, **overrides) -> dict:
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
    return base


def _params_registro_invalido(lote_id: str, motivos: list, **overrides) -> dict:
    base = dict(
        registro_coleta_id=_uuid(),
        lote_id=lote_id,
        nome="Cliente de Teste",
        produto="Produto de Teste",
        whatsapp="5511987654321",
        valido=False,
        motivos_invalidez=motivos,
        numero_versao_dados=1,
        versao_eventos_atual=0,
    )
    if "nome_ausente" in motivos:
        base["nome"] = None
    if "produto_ausente" in motivos:
        base["produto"] = None
    if any(m.startswith("whatsapp") for m in motivos):
        base["whatsapp"] = None if "whatsapp_ausente" in motivos else "abc-invalido"
    base.update(overrides)
    return base


def test_registros_coleta_valido_completo_aceito(cur):
    cur.execute("SAVEPOINT sp_lote")
    try:
        lote_id = _inserir_lote_base(cur)
        _aceita(cur, _SQL_INSERT_REGISTRO, _params_registro_valido(lote_id))
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp_lote")


def test_registros_coleta_valido_com_motivos_preenchidos_rejeitado(cur):
    cur.execute("SAVEPOINT sp_lote")
    try:
        lote_id = _inserir_lote_base(cur)
        _rejeita(cur, _SQL_INSERT_REGISTRO, _params_registro_valido(lote_id, motivos_invalidez=["nome_ausente"]))
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp_lote")


def test_registros_coleta_valido_com_whatsapp_fora_do_formato_rejeitado(cur):
    cur.execute("SAVEPOINT sp_lote")
    try:
        lote_id = _inserir_lote_base(cur)
        _rejeita(cur, _SQL_INSERT_REGISTRO, _params_registro_valido(lote_id, whatsapp="123"))
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp_lote")


def test_registros_coleta_nome_ausente_aceito(cur):
    cur.execute("SAVEPOINT sp_lote")
    try:
        lote_id = _inserir_lote_base(cur)
        _aceita(cur, _SQL_INSERT_REGISTRO, _params_registro_invalido(lote_id, ["nome_ausente"]))
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp_lote")


def test_registros_coleta_produto_ausente_aceito(cur):
    cur.execute("SAVEPOINT sp_lote")
    try:
        lote_id = _inserir_lote_base(cur)
        _aceita(cur, _SQL_INSERT_REGISTRO, _params_registro_invalido(lote_id, ["produto_ausente"]))
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp_lote")


@pytest.mark.parametrize("motivo", [
    "whatsapp_ausente", "whatsapp_caracteres_invalidos",
    "whatsapp_comprimento_invalido", "whatsapp_codigo_pais_invalido", "whatsapp_ddd_invalido",
])
def test_registros_coleta_whatsapp_invalido_aceito(cur, motivo):
    cur.execute("SAVEPOINT sp_lote")
    try:
        lote_id = _inserir_lote_base(cur)
        _aceita(cur, _SQL_INSERT_REGISTRO, _params_registro_invalido(lote_id, [motivo]))
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp_lote")


def test_registros_coleta_multiplos_motivos_aceito(cur):
    cur.execute("SAVEPOINT sp_lote")
    try:
        lote_id = _inserir_lote_base(cur)
        _aceita(cur, _SQL_INSERT_REGISTRO, _params_registro_invalido(
            lote_id, ["nome_ausente", "produto_ausente", "whatsapp_ausente"],
        ))
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp_lote")


def test_registros_coleta_motivo_fora_do_vocabulario_rejeitado(cur):
    cur.execute("SAVEPOINT sp_lote")
    try:
        lote_id = _inserir_lote_base(cur)
        _rejeita(cur, _SQL_INSERT_REGISTRO, _params_registro_invalido(lote_id, ["motivo_inventado"]))
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp_lote")


def test_registros_coleta_dois_motivos_diferentes_aceito(cur):
    cur.execute("SAVEPOINT sp_lote")
    try:
        lote_id = _inserir_lote_base(cur)
        _aceita(cur, _SQL_INSERT_REGISTRO, _params_registro_invalido(
            lote_id, ["nome_ausente", "produto_ausente"],
        ))
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp_lote")


def test_registros_coleta_motivo_duplicado_rejeitado(cur):
    """Mesmo motivo repetido no array - rejeitado por
    ck_registros_coleta_motivos_sem_duplicata, mesmo pertencendo
    inteiramente ao vocabulario fechado."""
    cur.execute("SAVEPOINT sp_lote")
    try:
        lote_id = _inserir_lote_base(cur)
        _rejeita(cur, _SQL_INSERT_REGISTRO, _params_registro_invalido(
            lote_id, ["nome_ausente", "nome_ausente"],
        ))
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp_lote")


def test_registros_coleta_invalido_sem_motivos_rejeitado(cur):
    cur.execute("SAVEPOINT sp_lote")
    try:
        lote_id = _inserir_lote_base(cur)
        _rejeita(cur, _SQL_INSERT_REGISTRO, _params_registro_invalido(lote_id, []))
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp_lote")


def test_registros_coleta_motivo_incoerente_com_campo_rejeitado(cur):
    """motivo diz nome_ausente, mas nome esta preenchido - incoerencia
    que o CHECK precisa recusar."""
    cur.execute("SAVEPOINT sp_lote")
    try:
        lote_id = _inserir_lote_base(cur)
        params = _params_registro_invalido(lote_id, ["nome_ausente"])
        params["nome"] = "Nome Presente Por Engano"
        _rejeita(cur, _SQL_INSERT_REGISTRO, params)
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp_lote")


def test_registros_coleta_versao_dados_zero_rejeitado(cur):
    cur.execute("SAVEPOINT sp_lote")
    try:
        lote_id = _inserir_lote_base(cur)
        _rejeita(cur, _SQL_INSERT_REGISTRO, _params_registro_valido(lote_id, numero_versao_dados=0))
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp_lote")


def test_registros_coleta_versao_eventos_negativa_rejeitado(cur):
    cur.execute("SAVEPOINT sp_lote")
    try:
        lote_id = _inserir_lote_base(cur)
        _rejeita(cur, _SQL_INSERT_REGISTRO, _params_registro_valido(lote_id, versao_eventos_atual=-1))
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp_lote")


# ============================================================
# nsi_operacional.eventos_lote - depende de um lote existente (FK)
# ============================================================

_SQL_INSERT_EVENTO_LOTE = """
    INSERT INTO nsi_operacional.eventos_lote
        (evento_id, aggregate_type, aggregate_id, aggregate_version, tipo, executado_por_login,
         recebido_em, total_recebido, total_valido, total_invalido,
         horario_conceitual, horario_real_execucao, atrasado,
         operador_humano_id, total_confirmado, motivo, codigo_tecnico_normalizado)
    VALUES
        (%(evento_id)s, %(aggregate_type)s, %(aggregate_id)s, %(aggregate_version)s, %(tipo)s,
         %(executado_por_login)s, %(recebido_em)s, %(total_recebido)s, %(total_valido)s, %(total_invalido)s,
         %(horario_conceitual)s, %(horario_real_execucao)s, %(atrasado)s,
         %(operador_humano_id)s, %(total_confirmado)s, %(motivo)s, %(codigo_tecnico_normalizado)s)
"""


def _params_evento_lote_base(lote_id: str, **overrides) -> dict:
    base = dict(
        evento_id=_uuid(),
        aggregate_type="lote",
        aggregate_id=lote_id,
        aggregate_version=1,
        tipo="lote_criado",
        executado_por_login="nsi_aplicacao",
        recebido_em=_RECEBIDO_EM_BASE,
        total_recebido=0,
        total_valido=0,
        total_invalido=0,
        horario_conceitual=None,
        horario_real_execucao=None,
        atrasado=None,
        operador_humano_id=None,
        total_confirmado=None,
        motivo=None,
        codigo_tecnico_normalizado=None,
    )
    base.update(overrides)
    return base


def _params_evento_lote_congelado(lote_id: str, **overrides) -> dict:
    base = _params_evento_lote_base(
        lote_id,
        tipo="lote_congelado_d8",
        recebido_em=None, total_recebido=None, total_valido=None, total_invalido=None,
        horario_conceitual=_HORARIO_CONCEITUAL_BASE,
        horario_real_execucao=_HORARIO_CONCEITUAL_BASE,
        atrasado=False,
    )
    base.update(overrides)
    return base


def _params_evento_disparo(lote_id: str, **overrides) -> dict:
    base = _params_evento_lote_base(
        lote_id,
        tipo="disparo_confirmado",
        executado_por_login="nsi_operador_restrito",
        recebido_em=None, total_recebido=None, total_valido=None, total_invalido=None,
        total_confirmado=5,
    )
    base.update(overrides)
    return base


def _params_evento_tentativa(lote_id: str, **overrides) -> dict:
    base = _params_evento_lote_base(
        lote_id,
        tipo="tentativa_correcao_nao_resolvida",
        recebido_em=None, total_recebido=None, total_valido=None, total_invalido=None,
        motivo="codigo_inexistente",
    )
    base.update(overrides)
    return base


def test_eventos_lote_lote_criado_aceito(cur):
    cur.execute("SAVEPOINT sp_lote")
    try:
        lote_id = _inserir_lote_base(cur)
        _aceita(cur, _SQL_INSERT_EVENTO_LOTE, _params_evento_lote_base(lote_id))
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp_lote")


def test_eventos_lote_congelado_aceito(cur):
    cur.execute("SAVEPOINT sp_lote")
    try:
        lote_id = _inserir_lote_base(cur)
        _aceita(cur, _SQL_INSERT_EVENTO_LOTE, _params_evento_lote_congelado(lote_id))
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp_lote")


def test_eventos_lote_disparo_confirmado_aceito(cur):
    cur.execute("SAVEPOINT sp_lote")
    try:
        lote_id = _inserir_lote_base(cur)
        _aceita(cur, _SQL_INSERT_EVENTO_LOTE, _params_evento_disparo(lote_id))
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp_lote")


def test_eventos_lote_tentativa_nao_resolvida_aceita(cur):
    cur.execute("SAVEPOINT sp_lote")
    try:
        lote_id = _inserir_lote_base(cur)
        _aceita(cur, _SQL_INSERT_EVENTO_LOTE, _params_evento_tentativa(lote_id))
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp_lote")


def test_eventos_lote_aggregate_type_incorreto_rejeitado(cur):
    cur.execute("SAVEPOINT sp_lote")
    try:
        lote_id = _inserir_lote_base(cur)
        _rejeita(cur, _SQL_INSERT_EVENTO_LOTE, _params_evento_lote_base(lote_id, aggregate_type="outro"))
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp_lote")


def test_eventos_lote_tipo_invalido_rejeitado(cur):
    cur.execute("SAVEPOINT sp_lote")
    try:
        lote_id = _inserir_lote_base(cur)
        _rejeita(cur, _SQL_INSERT_EVENTO_LOTE, _params_evento_lote_base(lote_id, tipo="evento_inventado"))
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp_lote")


def test_eventos_lote_aggregate_version_zero_rejeitado(cur):
    cur.execute("SAVEPOINT sp_lote")
    try:
        lote_id = _inserir_lote_base(cur)
        _rejeita(cur, _SQL_INSERT_EVENTO_LOTE, _params_evento_lote_base(lote_id, aggregate_version=0))
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp_lote")


def test_eventos_lote_criado_com_campos_de_congelamento_rejeitado(cur):
    cur.execute("SAVEPOINT sp_lote")
    try:
        lote_id = _inserir_lote_base(cur)
        _rejeita(cur, _SQL_INSERT_EVENTO_LOTE, _params_evento_lote_base(
            lote_id, horario_conceitual=_HORARIO_CONCEITUAL_BASE,
        ))
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp_lote")


def test_eventos_lote_congelado_sem_horario_real_rejeitado(cur):
    cur.execute("SAVEPOINT sp_lote")
    try:
        lote_id = _inserir_lote_base(cur)
        _rejeita(cur, _SQL_INSERT_EVENTO_LOTE, _params_evento_lote_congelado(lote_id, horario_real_execucao=None))
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp_lote")


def test_eventos_lote_congelado_horario_exato_aceito(cur):
    cur.execute("SAVEPOINT sp_lote")
    try:
        lote_id = _inserir_lote_base(cur)
        _aceita(cur, _SQL_INSERT_EVENTO_LOTE, _params_evento_lote_congelado(
            lote_id, horario_real_execucao=_HORARIO_CONCEITUAL_BASE, atrasado=False,
        ))
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp_lote")


def test_eventos_lote_congelado_horario_tardio_aceito(cur):
    cur.execute("SAVEPOINT sp_lote")
    try:
        lote_id = _inserir_lote_base(cur)
        _aceita(cur, _SQL_INSERT_EVENTO_LOTE, _params_evento_lote_congelado(
            lote_id, horario_real_execucao=_HORARIO_CONCEITUAL_BASE + timedelta(hours=3), atrasado=True,
        ))
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp_lote")


def test_eventos_lote_congelado_horario_antecipado_rejeitado(cur):
    """horario_real_execucao ANTERIOR ao conceitual - deve ser
    rejeitado por ck_eventos_lote_congelamento_nunca_antecipado."""
    cur.execute("SAVEPOINT sp_lote")
    try:
        lote_id = _inserir_lote_base(cur)
        _rejeita(cur, _SQL_INSERT_EVENTO_LOTE, _params_evento_lote_congelado(
            lote_id, horario_real_execucao=_HORARIO_CONCEITUAL_BASE - timedelta(hours=1), atrasado=False,
        ))
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp_lote")


def test_eventos_lote_congelado_atrasado_incoerente_rejeitado(cur):
    """Horario realmente tardio, mas atrasado=False - recusado por
    ck_eventos_lote_atrasado_correto."""
    cur.execute("SAVEPOINT sp_lote")
    try:
        lote_id = _inserir_lote_base(cur)
        _rejeita(cur, _SQL_INSERT_EVENTO_LOTE, _params_evento_lote_congelado(
            lote_id, horario_real_execucao=_HORARIO_CONCEITUAL_BASE + timedelta(hours=3), atrasado=False,
        ))
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp_lote")


def test_eventos_lote_disparo_sem_total_confirmado_rejeitado(cur):
    cur.execute("SAVEPOINT sp_lote")
    try:
        lote_id = _inserir_lote_base(cur)
        _rejeita(cur, _SQL_INSERT_EVENTO_LOTE, _params_evento_disparo(lote_id, total_confirmado=None))
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp_lote")


def test_eventos_lote_tentativa_sem_motivo_rejeitada(cur):
    cur.execute("SAVEPOINT sp_lote")
    try:
        lote_id = _inserir_lote_base(cur)
        _rejeita(cur, _SQL_INSERT_EVENTO_LOTE, _params_evento_tentativa(lote_id, motivo=None))
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp_lote")


def test_eventos_lote_motivo_fora_do_vocabulario_rejeitado(cur):
    cur.execute("SAVEPOINT sp_lote")
    try:
        lote_id = _inserir_lote_base(cur)
        _rejeita(cur, _SQL_INSERT_EVENTO_LOTE, _params_evento_tentativa(lote_id, motivo="motivo_inventado"))
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp_lote")


def test_eventos_lote_operador_humano_fora_de_disparo_confirmado_rejeitado(cur):
    cur.execute("SAVEPOINT sp_lote")
    try:
        lote_id = _inserir_lote_base(cur)
        _rejeita(cur, _SQL_INSERT_EVENTO_LOTE, _params_evento_lote_base(lote_id, operador_humano_id=_uuid()))
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp_lote")


def test_eventos_lote_operador_humano_nulo_em_disparo_confirmado_aceito(cur):
    """Hoje operador_humano_id permanece sempre NULL (Sprint D ainda nao
    existe) - o CHECK so proibe fora de disparo_confirmado, nunca exige
    presenca dentro dele."""
    cur.execute("SAVEPOINT sp_lote")
    try:
        lote_id = _inserir_lote_base(cur)
        _aceita(cur, _SQL_INSERT_EVENTO_LOTE, _params_evento_disparo(lote_id, operador_humano_id=None))
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp_lote")


# ============================================================
# nsi_operacional.eventos_registro_coleta - depende de um registro (FK)
# ============================================================

_SQL_INSERT_EVENTO_REGISTRO = """
    INSERT INTO nsi_operacional.eventos_registro_coleta
        (evento_id, aggregate_type, aggregate_id, aggregate_version, tipo, executado_por_login,
         resultado, numero_versao_dados)
    VALUES
        (%(evento_id)s, %(aggregate_type)s, %(aggregate_id)s, %(aggregate_version)s, %(tipo)s,
         %(executado_por_login)s, %(resultado)s, %(numero_versao_dados)s)
"""


def _inserir_lote_e_registro(cur, **overrides_registro) -> str:
    lote_id = _inserir_lote_base(cur)
    params = _params_registro_valido(lote_id, **overrides_registro)
    cur.execute(_SQL_INSERT_REGISTRO, params)
    return params["registro_coleta_id"]


def _params_evento_registro(registro_coleta_id: str, **overrides) -> dict:
    base = dict(
        evento_id=_uuid(),
        aggregate_type="registro_coleta",
        aggregate_id=registro_coleta_id,
        aggregate_version=1,
        tipo="correcao_registrada",
        executado_por_login="nsi_aplicacao",
        resultado="aplicada_valida",
        numero_versao_dados=2,
    )
    base.update(overrides)
    return base


def test_eventos_registro_coleta_aplicada_valida_aceito(cur):
    cur.execute("SAVEPOINT sp_reg")
    try:
        registro_id = _inserir_lote_e_registro(cur)
        _aceita(cur, _SQL_INSERT_EVENTO_REGISTRO, _params_evento_registro(registro_id, resultado="aplicada_valida"))
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp_reg")


def test_eventos_registro_coleta_aplicada_ainda_invalida_aceito(cur):
    cur.execute("SAVEPOINT sp_reg")
    try:
        registro_id = _inserir_lote_e_registro(cur)
        _aceita(cur, _SQL_INSERT_EVENTO_REGISTRO, _params_evento_registro(
            registro_id, resultado="aplicada_ainda_invalida",
        ))
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp_reg")


def test_eventos_registro_coleta_recusada_ja_valido_aceito(cur):
    cur.execute("SAVEPOINT sp_reg")
    try:
        registro_id = _inserir_lote_e_registro(cur)
        _aceita(cur, _SQL_INSERT_EVENTO_REGISTRO, _params_evento_registro(
            registro_id, resultado="recusada_ja_valido", numero_versao_dados=None,
        ))
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp_reg")


def test_eventos_registro_coleta_recusada_tardia_aceito(cur):
    """Tentativa tardia depois do congelamento so gera este evento -
    numero_versao_dados sempre NULL."""
    cur.execute("SAVEPOINT sp_reg")
    try:
        registro_id = _inserir_lote_e_registro(cur)
        _aceita(cur, _SQL_INSERT_EVENTO_REGISTRO, _params_evento_registro(
            registro_id, resultado="recusada_tardia", numero_versao_dados=None,
        ))
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp_reg")


def test_eventos_registro_coleta_aplicada_sem_versao_dados_rejeitado(cur):
    cur.execute("SAVEPOINT sp_reg")
    try:
        registro_id = _inserir_lote_e_registro(cur)
        _rejeita(cur, _SQL_INSERT_EVENTO_REGISTRO, _params_evento_registro(
            registro_id, resultado="aplicada_valida", numero_versao_dados=None,
        ))
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp_reg")


def test_eventos_registro_coleta_recusada_com_versao_dados_rejeitado(cur):
    cur.execute("SAVEPOINT sp_reg")
    try:
        registro_id = _inserir_lote_e_registro(cur)
        _rejeita(cur, _SQL_INSERT_EVENTO_REGISTRO, _params_evento_registro(
            registro_id, resultado="recusada_tardia", numero_versao_dados=1,
        ))
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp_reg")


def test_eventos_registro_coleta_resultado_invalido_rejeitado(cur):
    cur.execute("SAVEPOINT sp_reg")
    try:
        registro_id = _inserir_lote_e_registro(cur)
        _rejeita(cur, _SQL_INSERT_EVENTO_REGISTRO, _params_evento_registro(
            registro_id, resultado="resultado_inventado", numero_versao_dados=None,
        ))
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp_reg")


def test_eventos_registro_coleta_aggregate_type_incorreto_rejeitado(cur):
    cur.execute("SAVEPOINT sp_reg")
    try:
        registro_id = _inserir_lote_e_registro(cur)
        _rejeita(cur, _SQL_INSERT_EVENTO_REGISTRO, _params_evento_registro(registro_id, aggregate_type="lote"))
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp_reg")


def test_eventos_registro_coleta_tipo_incorreto_rejeitado(cur):
    cur.execute("SAVEPOINT sp_reg")
    try:
        registro_id = _inserir_lote_e_registro(cur)
        _rejeita(cur, _SQL_INSERT_EVENTO_REGISTRO, _params_evento_registro(registro_id, tipo="outro_tipo"))
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp_reg")


def test_eventos_registro_coleta_aggregate_version_zero_rejeitado(cur):
    cur.execute("SAVEPOINT sp_reg")
    try:
        registro_id = _inserir_lote_e_registro(cur)
        _rejeita(cur, _SQL_INSERT_EVENTO_REGISTRO, _params_evento_registro(registro_id, aggregate_version=0))
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp_reg")
