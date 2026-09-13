# -*- coding: utf-8 -*-
"""
NSI - tests/integration/test_schema_b3_unicidade_e_fk.py
(Sprint B, B3.2 - ADR-008, Parte 1 da B3)

Testes de integracao REAIS contra PostgreSQL, exclusivamente contra
nsi_test, das restricoes de unicidade e da FK composta diferivel criadas
pela migration 0002:

- uq_eventos_claim_aggregate_versao: UNIQUE (aggregate_id, aggregate_version).
- eventos_claim_expirado_unico: UNIQUE parcial (claim_id) WHERE tipo = 'claim_expirado'.
- eventos_claim_origem_claim_id_unica: UNIQUE parcial (claim_id) WHERE tipo
  IN ('claim_criado', 'claim_reatribuido').
- claims_revisao_atual_fk: FK composta (revisao_atual_id, registro_coleta_id)
  -> eventos_claim (evento_id, aggregate_id), DEFERRABLE INITIALLY DEFERRED.

Mesma disciplina de test_schema_b3_constraints.py: conexao do migrator com
'SET LOCAL ROLE nsi_eventos_owner', cada tentativa isolada em um
SAVEPOINT proprio, a transacao externa sempre revertida no teardown -
nenhum residuo em nsi_test. A natureza DIFERIVEL da FK e comprovada sem
nenhum COMMIT real: 'SET CONSTRAINTS nsi_operacional.claims_revisao_atual_fk IMMEDIATE'
forca a checagem antecipadamente, dentro da mesma transacao, exatamente
o mecanismo que um COMMIT real dispararia - sem exigir persistir nada.

IMPORTANTE: ao contrario de 'DROP TRIGGER x ON schema.tabela' (cujo
escopo vem da propria tabela qualificada), 'SET CONSTRAINTS <nome>' com
nome NAO qualificado e resolvido pelo search_path da sessao - nunca pelo
schema da tabela dona da constraint. Como a conexao do migrator nao tem
'nsi_operacional' no search_path (padrao "$user", public), a forma sem
qualificacao nunca encontra a constraint, mesmo ela existindo de fato -
por isso todo 'SET CONSTRAINTS' deste arquivo qualifica explicitamente
'nsi_operacional.claims_revisao_atual_fk'.

Pressupoe a migration 0002 ja aplicada em nsi_test. Nenhum teste deste
arquivo chama pytest nem executa a suite completa internamente.
"""
import hashlib
import uuid

import psycopg
import pytest

pytestmark = pytest.mark.pg_integration


def _hash_valido(rotulo: str = "valor-de-teste") -> str:
    return hashlib.sha256(rotulo.encode()).hexdigest()


def _uuid() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def cur(request):
    """A URL e obtida internamente via request.getfixturevalue(), nunca
    como parametro nomeado desta fixture - protege contra a DSN aparecer
    no cabecalho de um eventual erro de setup do pytest."""
    url = request.getfixturevalue("url_banco_teste")
    conn = psycopg.connect(url)
    try:
        cursor = conn.cursor()
        cursor.execute("SET LOCAL ROLE nsi_eventos_owner")
        yield cursor
    finally:
        conn.rollback()
        conn.close()


_SQL_INSERT_CLAIM = """
    INSERT INTO nsi_operacional.claims
        (registro_coleta_id, claim_id, token_hash, estado, criado_em, expira_em,
         versao_atual, revisao_atual_id, revisao_decisao, revisao_registrada_em)
    VALUES
        (%(registro_coleta_id)s, %(claim_id)s, %(token_hash)s, %(estado)s,
         now(), now() + interval '5 minutes', %(versao_atual)s,
         %(revisao_atual_id)s, %(revisao_decisao)s, %(revisao_registrada_em)s)
"""

_SQL_INSERT_EVENTO = """
    INSERT INTO nsi_operacional.eventos_claim
        (evento_id, aggregate_type, aggregate_id, aggregate_version, tipo, claim_id, executado_por, payload)
    VALUES
        (%(evento_id)s, 'claim', %(aggregate_id)s, %(aggregate_version)s, %(tipo)s,
         %(claim_id)s, %(executado_por)s, %(payload)s)
"""

_EXECUTADO_POR = psycopg.types.json.Jsonb({"role": "nsi_test_migrator"})
_PAYLOAD_VAZIO = psycopg.types.json.Jsonb({})


def _inserir_claim_simples(cur, **overrides) -> str:
    registro_coleta_id = overrides.pop("registro_coleta_id", _uuid())
    params = dict(
        registro_coleta_id=registro_coleta_id,
        claim_id=_uuid(),
        token_hash=_hash_valido(),
        estado="ativo",
        versao_atual=1,
        revisao_atual_id=None,
        revisao_decisao=None,
        revisao_registrada_em=None,
    )
    params.update(overrides)
    cur.execute(_SQL_INSERT_CLAIM, params)
    return registro_coleta_id


def _inserir_evento(cur, aggregate_id: str, aggregate_version: int, tipo: str, **overrides) -> str:
    evento_id = overrides.pop("evento_id", _uuid())
    params = dict(
        evento_id=evento_id,
        aggregate_id=aggregate_id,
        aggregate_version=aggregate_version,
        tipo=tipo,
        claim_id=_uuid(),
        executado_por=_EXECUTADO_POR,
        payload=_PAYLOAD_VAZIO,
    )
    params.update(overrides)
    cur.execute(_SQL_INSERT_EVENTO, params)
    return evento_id


# ============================================================
# UNIQUE (aggregate_id, aggregate_version)
# ============================================================

def test_unique_aggregate_id_aggregate_version_rejeita_duplicata(cur):
    cur.execute("SAVEPOINT sp1")
    try:
        registro_coleta_id = _inserir_claim_simples(cur)
        _inserir_evento(cur, registro_coleta_id, 1, "claim_criado")
        with pytest.raises(psycopg.errors.UniqueViolation) as exc_info:
            _inserir_evento(cur, registro_coleta_id, 1, "heartbeat_registrado")
        assert exc_info.value.sqlstate == "23505"
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp1")


def test_unique_aggregate_id_aggregate_version_aceita_versoes_distintas(cur):
    cur.execute("SAVEPOINT sp2")
    try:
        registro_coleta_id = _inserir_claim_simples(cur)
        _inserir_evento(cur, registro_coleta_id, 1, "claim_criado")
        _inserir_evento(cur, registro_coleta_id, 2, "heartbeat_registrado")
    except Exception as exc:
        cur.execute("ROLLBACK TO SAVEPOINT sp2")
        pytest.fail(f"Esperado sucesso, mas falhou: {exc!r}")
    else:
        cur.execute("ROLLBACK TO SAVEPOINT sp2")


# ============================================================
# eventos_claim_expirado_unico - claim_id unico onde tipo = claim_expirado
# ============================================================

def test_indice_expirado_rejeita_segundo_evento_para_mesmo_claim_id(cur):
    cur.execute("SAVEPOINT sp3")
    try:
        registro_coleta_id = _inserir_claim_simples(cur)
        claim_id_compartilhado = _uuid()
        _inserir_evento(cur, registro_coleta_id, 1, "claim_expirado", claim_id=claim_id_compartilhado)
        with pytest.raises(psycopg.errors.UniqueViolation) as exc_info:
            _inserir_evento(cur, registro_coleta_id, 2, "claim_expirado", claim_id=claim_id_compartilhado)
        assert exc_info.value.sqlstate == "23505"
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp3")


def test_indice_expirado_nao_colide_entre_claim_ids_distintos(cur):
    cur.execute("SAVEPOINT sp4")
    try:
        registro_coleta_id = _inserir_claim_simples(cur)
        _inserir_evento(cur, registro_coleta_id, 1, "claim_expirado", claim_id=_uuid())
        _inserir_evento(cur, registro_coleta_id, 2, "claim_expirado", claim_id=_uuid())
    except Exception as exc:
        cur.execute("ROLLBACK TO SAVEPOINT sp4")
        pytest.fail(f"Esperado sucesso, mas falhou: {exc!r}")
    else:
        cur.execute("ROLLBACK TO SAVEPOINT sp4")


# ============================================================
# eventos_claim_origem_claim_id_unica - claim_id unico como origem entre
# claim_criado e claim_reatribuido
# ============================================================

def test_indice_origem_rejeita_claim_id_reaproveitado_entre_criado_e_reatribuido(cur):
    cur.execute("SAVEPOINT sp5")
    try:
        registro_coleta_id = _inserir_claim_simples(cur)
        claim_id_compartilhado = _uuid()
        _inserir_evento(cur, registro_coleta_id, 1, "claim_criado", claim_id=claim_id_compartilhado)
        with pytest.raises(psycopg.errors.UniqueViolation) as exc_info:
            _inserir_evento(cur, registro_coleta_id, 2, "claim_reatribuido", claim_id=claim_id_compartilhado)
        assert exc_info.value.sqlstate == "23505"
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp5")


def test_indice_origem_nao_colide_com_tipos_fora_do_par(cur):
    """claim_id repetido em tipos fora de {claim_criado, claim_reatribuido}
    (ex.: heartbeat_registrado) nunca colide com este indice parcial."""
    cur.execute("SAVEPOINT sp6")
    try:
        registro_coleta_id = _inserir_claim_simples(cur)
        claim_id_compartilhado = _uuid()
        _inserir_evento(cur, registro_coleta_id, 1, "claim_criado", claim_id=claim_id_compartilhado)
        _inserir_evento(cur, registro_coleta_id, 2, "heartbeat_registrado", claim_id=claim_id_compartilhado)
    except Exception as exc:
        cur.execute("ROLLBACK TO SAVEPOINT sp6")
        pytest.fail(f"Esperado sucesso, mas falhou: {exc!r}")
    else:
        cur.execute("ROLLBACK TO SAVEPOINT sp6")


# ============================================================
# claims_revisao_atual_fk - FK composta DEFERRABLE INITIALLY DEFERRED
# ============================================================

def test_fk_revisao_e_verdadeiramente_diferida_ate_immediate(cur):
    """O INSERT do claim referenciando um evento AINDA NAO inserido tem que
    ter sucesso na hora - a checagem so acontece em SET CONSTRAINTS
    ... IMMEDIATE (ou, em producao, no COMMIT). Comprova o adiamento em
    si, nao apenas o resultado final."""
    cur.execute("SAVEPOINT sp7")
    try:
        registro_coleta_id = _uuid()
        evento_id_futuro = _uuid()
        # INSERT do claim referenciando um evento que ainda nao existe -
        # precisa suceder, exatamente por a FK ser diferida.
        _inserir_claim_simples(
            cur,
            registro_coleta_id=registro_coleta_id,
            estado="expirado_pendente_revisao",
            revisao_atual_id=evento_id_futuro,
            revisao_decisao="reatribuir",
            revisao_registrada_em="2026-01-01T00:00:00+00:00",
        )
        # Neste ponto, o evento referenciado ainda nao existe - forcar a
        # checagem agora precisa falhar, provando que a FK e real.
        with pytest.raises(psycopg.errors.ForeignKeyViolation) as exc_info:
            cur.execute("SET CONSTRAINTS nsi_operacional.claims_revisao_atual_fk IMMEDIATE")
        assert exc_info.value.sqlstate == "23503"
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp7")


def test_fk_revisao_satisfeita_quando_evento_correspondente_existe(cur):
    cur.execute("SAVEPOINT sp8")
    try:
        registro_coleta_id = _uuid()
        evento_id = _uuid()
        _inserir_claim_simples(
            cur,
            registro_coleta_id=registro_coleta_id,
            estado="expirado_pendente_revisao",
            revisao_atual_id=evento_id,
            revisao_decisao="reatribuir",
            revisao_registrada_em="2026-01-01T00:00:00+00:00",
        )
        _inserir_evento(
            cur, registro_coleta_id, 1, "revisao_de_abandono_registrada",
            evento_id=evento_id,
        )
        # Forca a checagem agora - precisa passar, pois (evento_id,
        # registro_coleta_id) == (evento_id, aggregate_id) do evento.
        cur.execute("SET CONSTRAINTS nsi_operacional.claims_revisao_atual_fk IMMEDIATE")
    except Exception as exc:
        cur.execute("ROLLBACK TO SAVEPOINT sp8")
        pytest.fail(f"Esperado sucesso, mas falhou: {exc!r}")
    else:
        cur.execute("ROLLBACK TO SAVEPOINT sp8")


def test_fk_revisao_rejeita_evento_de_agregado_diferente(cur):
    """evento_id existe, mas com aggregate_id de OUTRO claim - a FK
    composta precisa rejeitar mesmo assim, provando que a checagem e pelo
    par inteiro, nunca so pelo evento_id isolado."""
    cur.execute("SAVEPOINT sp9")
    try:
        registro_coleta_id_alvo = _uuid()
        registro_coleta_id_outro = _uuid()
        evento_id = _uuid()

        _inserir_claim_simples(cur, registro_coleta_id=registro_coleta_id_outro)
        _inserir_evento(
            cur, registro_coleta_id_outro, 1, "claim_criado", evento_id=evento_id,
        )

        _inserir_claim_simples(
            cur,
            registro_coleta_id=registro_coleta_id_alvo,
            estado="expirado_pendente_revisao",
            revisao_atual_id=evento_id,
            revisao_decisao="reatribuir",
            revisao_registrada_em="2026-01-01T00:00:00+00:00",
        )

        with pytest.raises(psycopg.errors.ForeignKeyViolation) as exc_info:
            cur.execute("SET CONSTRAINTS nsi_operacional.claims_revisao_atual_fk IMMEDIATE")
        assert exc_info.value.sqlstate == "23503"
    finally:
        cur.execute("ROLLBACK TO SAVEPOINT sp9")
