# -*- coding: utf-8 -*-
"""
NSI - tests/apoio_b4_3.py

Apoio compartilhado pelos testes de integracao das cinco funcoes da
migration 0005 (Sprint B, B4.3 - ADR-009) - implementacao UNICA, em vez de
uma copia por arquivo:

    tests/integration/test_fn_registrar_lote.py
    tests/integration/test_fn_registrar_congelamento.py
    tests/integration/test_fn_confirmar_disparo.py
    tests/integration/test_fn_registrar_correcao.py
    tests/integration/test_fn_registrar_tentativa_nao_resolvida.py
    tests/integration/test_idempotencia_e_permissoes_b4_3.py
    tests/integration/test_migration_0005_upgrade_downgrade.py

Mesmo padrao de tests/regra_membership_b3_1.py: este modulo nao e um
arquivo de teste (nao comeca com 'test_') - nunca e coletado pelo pytest.
Nao abre conexao propria: toda funcao recebe o cursor ou a conexao do
teste. Nenhuma funcao interpola valor pessoal em mensagem.
"""
import time
import uuid

import pytest
from psycopg.types.json import Jsonb

from core.payload_hash import hash_registrar_lote


def uuid_texto() -> str:
    return str(uuid.uuid4())


def registro_valido(n: int = 1) -> dict:
    """Registro valido, coerente com ck_registros_coleta_coerencia."""
    return {
        "registro_coleta_id": uuid_texto(), "nome": f"Pessoa Teste {n}", "whatsapp": f"55119{n:08d}",
        "produto": "Produto Teste", "valido": True, "motivos_invalidez": None,
    }


def registro_invalido() -> dict:
    """Registro invalido (nome ausente), coerente com ck_registros_coleta_coerencia."""
    return {
        "registro_coleta_id": uuid_texto(), "nome": None, "whatsapp": "5511988887777",
        "produto": "Produto Teste", "valido": False, "motivos_invalidez": ["nome_ausente"],
    }


def criar_lote(cur, registros) -> str:
    """Cria o lote pela propria fn_registrar_lote (com o hash canonico de
    core/payload_hash.py) e devolve o lote_id. Exige um cursor com EXECUTE
    na funcao - em geral o do owner."""
    lote_id = uuid_texto()
    cur.execute(
        "SELECT nsi_operacional.fn_registrar_lote(%s, NULL, %s, %s, %s)",
        (lote_id, Jsonb(registros), "chave-criacao-" + lote_id, hash_registrar_lote(lote_id, None, registros)),
    )
    resultado = cur.fetchone()[0]
    assert resultado["sucesso"] is True
    return lote_id


def posicionar_fronteira(cur, lote_id, deslocamento: str) -> None:
    """horario_conceitual_congelamento = now() + deslocamento, movendo
    recebido_em junto (M0 + 192h exatas, ck_lotes_horario_conceitual).
    Usado na MESMA transacao da chamada testada: now() e o instante de
    inicio da transacao, identico para o deslocamento e para a funcao -
    fronteira temporal exata, sem espera real. Exige o cursor do owner."""
    cur.execute(
        "UPDATE nsi_operacional.lotes "
        "   SET horario_conceitual_congelamento = now() + %s::interval, "
        "       recebido_em = now() + %s::interval - interval '192 hours' "
        " WHERE lote_id = %s",
        (deslocamento, deslocamento, lote_id),
    )


def aguardar_bloqueio(conn_observador, pid: int, limite_s: float = 10.0) -> None:
    """Espera ate a conexao 'pid' estar bloqueada aguardando um lock
    (pg_locks e visivel a qualquer role). Falha - nunca espera
    indefinidamente - se isso nao ocorrer dentro do limite."""
    fim = time.monotonic() + limite_s
    with conn_observador.cursor() as c:
        while time.monotonic() < fim:
            c.execute("SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_locks WHERE pid = %s AND NOT granted)", (pid,))
            if c.fetchone()[0]:
                return
            conn_observador.rollback()
            time.sleep(0.05)
    pytest.fail("A conexao concorrente nunca chegou a esperar pelo bloqueio da primeira.")
