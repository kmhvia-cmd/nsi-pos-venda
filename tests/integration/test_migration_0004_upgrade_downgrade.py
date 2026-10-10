# -*- coding: utf-8 -*-
"""
NSI - tests/integration/test_migration_0004_upgrade_downgrade.py
(Sprint B, B4.2 - ADR-009)

Testes de integracao REAIS contra PostgreSQL - nunca SQLite, nunca mock -
do ciclo completo de downgrade/upgrade da migration 0004, exclusivamente
contra nsi_test (nunca nsi_dev), mesma disciplina ja corrigida na B3.4
para a migration 0003. Desde a B5.4 o head e 0006: o ciclo parte de
0006 e volta a 0006, atravessando o downgrade da 0004 - o Alembic roda
o downgrade inteiro numa unica transacao (migrations/env.py), entao um
downgrade recusado pelo preflight da 0004 desfaz tambem os da 0006 e da 0005.

Revisoes EXPLICITAS em toda chamada ao Alembic (`upgrade 0006`,
`downgrade 0003`) - nunca `head`.

GATE DE IDENTIDADE OBRIGATORIO antes de qualquer downgrade: current_
database() = 'nsi_test', servidor local, porta 5432, current_user =
'nsi_test_migrator' - qualquer divergencia aborta o teste antes de a
chamada ao Alembic ocorrer. Repetido antes de CADA acao destrutiva.

Cobre dois cenarios:

1. Ciclo limpo: 0006 -> (gate) -> downgrade 0003 -> confirma inventario
   identico ao de 0003 original (incluindo o CHECK de 5 comandos
   restaurado em comandos_idempotentes, sem nenhuma das quatro tabelas
   da B4) -> upgrade 0006 -> confirma inventario completo de volta.

2. Downgrade bloqueado por recibo residual: insere e COMMITA um recibo
   sintetico de comando da B4 em comandos_idempotentes -> tenta
   downgrade 0003 -> confirma falha explicita e permanencia integral em
   0006 -> remove SOMENTE o recibo sintetico -> downgrade 0003 (sucesso)
   -> confirma 0003 -> upgrade 0006 novamente -> confirma ausencia de
   qualquer residuo permanente das duas tentativas.

pg_catalog.pg_tables - nunca information_schema.tables - mesmo motivo
ja documentado em test_migration_0002_upgrade_downgrade.py (o migrator
nao tem DML direto nas tabelas de negocio; information_schema.tables
filtra por privilegio).

Marcado 'pg_integration' - pulado em execucao comum de desenvolvimento
quando TEST_DATABASE_URL esta ausente; falha explicitamente quando
NSI_REQUIRE_PG_TESTS=1.
"""
import os
import subprocess
import sys
import uuid

import psycopg
import pytest

from config import mascarar_dsn

pytestmark = pytest.mark.pg_integration

NOME_SCHEMA = "nsi_operacional"
USUARIO_MIGRATOR_ESPERADO = "nsi_test_migrator"

TABELAS_B3 = {"claims", "eventos_claim", "comandos_idempotentes"}
TABELAS_B4 = {"lotes", "registros_coleta", "eventos_lote", "eventos_registro_coleta"}
# Head 0006 (B5.4): registro tecnico de importacao e snapshot legado.
TABELAS_B5 = {"importacoes_legado", "importacoes_legado_arquivos", "importacoes_legado_conclusoes",
              "lotes_legado", "registros_legado"}

COMANDOS_B4 = (
    "registrar_lote", "registrar_congelamento", "confirmar_disparo",
    "registrar_correcao", "registrar_tentativa_nao_resolvida",
)

_CHAVE_SINTETICA = "chave-sintetica-teste-downgrade-0004"


def _uuid() -> str:
    return str(uuid.uuid4())


def _executar_alembic(*args: str, env: dict) -> "subprocess.CompletedProcess[str]":
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        capture_output=True,
        text=True,
        env=env,
    )


def _consultar_estado(url: str) -> dict:
    """Le, numa unica conexao, o carimbo de revisao, o inventario de
    tabelas de nsi_operacional e a definicao atual do CHECK de `comando`
    em comandos_idempotentes - usado apos cada chamada ao Alembic para
    confirmar o estado real do banco, nunca presumido a partir da saida
    do comando."""
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT version_num FROM nsi_operacional.alembic_version")
            linha = cur.fetchone()
            versao = linha[0] if linha else None

            cur.execute(
                "SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname = %s",
                (NOME_SCHEMA,),
            )
            tabelas = {r[0] for r in cur.fetchall()}

            cur.execute("""
                SELECT pg_get_constraintdef(oid)
                  FROM pg_constraint
                 WHERE conname = 'ck_comandos_idempotentes_comando'
                   AND conrelid = 'nsi_operacional.comandos_idempotentes'::regclass
            """)
            linha_check = cur.fetchone()
            check_comando_def = linha_check[0] if linha_check else None

            cur.execute(
                "SELECT tablename, tableowner FROM pg_catalog.pg_tables WHERE schemaname = %s",
                (NOME_SCHEMA,),
            )
            owners_tabelas = {r[0]: r[1] for r in cur.fetchall()}

            cur.execute("""
                SELECT p.proname, pg_get_userbyid(p.proowner)
                  FROM pg_proc p
                  JOIN pg_namespace n ON n.oid = p.pronamespace
                 WHERE n.nspname = %s
                   AND p.proname IN (
                       'fn_bloquear_alteracao_eventos_lote',
                       'fn_bloquear_alteracao_eventos_registro_coleta'
                   )
            """, (NOME_SCHEMA,))
            owners_funcoes = {r[0]: r[1] for r in cur.fetchall()}

    return {
        "versao": versao,
        "tabelas": tabelas,
        "check_comando_def": check_comando_def,
        "owners_tabelas": owners_tabelas,
        "owners_funcoes": owners_funcoes,
    }


def _comprovar_identidade_antes_de_destrutivo(url: str) -> None:
    """GATE OBRIGATORIO antes de qualquer 'alembic downgrade' - mesmo
    mecanismo ja validado em test_migration_0002_upgrade_downgrade.py."""
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT current_database(), inet_server_addr(), inet_server_port(), current_user"
            )
            banco_real, endereco_servidor, porta_real, usuario_real = cur.fetchone()

    assert banco_real == "nsi_test", (
        f"Identidade do banco nao comprovada: current_database()={banco_real!r}, "
        "esperado 'nsi_test'. Nenhuma acao adicional e executada."
    )
    assert endereco_servidor is None or str(endereco_servidor) in ("127.0.0.1", "::1"), (
        f"Servidor remoto detectado (inet_server_addr()={endereco_servidor!r}). "
        "Este teste e exclusivo de PostgreSQL LOCAL. Nenhuma acao adicional e executada."
    )
    assert porta_real == 5432, (
        f"Porta inesperada (inet_server_port()={porta_real!r}), esperado 5432. "
        "Nenhuma acao adicional e executada."
    )
    assert usuario_real == USUARIO_MIGRATOR_ESPERADO, (
        f"Usuario de conexao inesperado (current_user={usuario_real!r}), esperado "
        f"{USUARIO_MIGRATOR_ESPERADO!r}. Nenhuma acao adicional e executada."
    )


def _assert_saida_alembic_sem_dsn(url: str, saida: str, rotulo: str) -> None:
    if url in saida:
        pytest.fail(
            f"Vazamento de DSN detectado na saida do Alembic ({rotulo}) - "
            "a DSN de conexao apareceu na saida capturada. Mensagem fixa: "
            "nem a DSN nem a saida sao exibidas aqui."
        )


def _inserir_recibo_sintetico_b4(url: str) -> None:
    """INSERT real, COMMITADO de verdade (nunca SAVEPOINT) - proposital,
    para provar que o downgrade recusa reverter o CHECK/derrubar as
    tabelas enquanto esse recibo existir. Roda como owner (unica role
    com DML direto)."""
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL ROLE nsi_eventos_owner")
            cur.execute("""
                INSERT INTO nsi_operacional.comandos_idempotentes
                    (comando, aggregate_id, chave_idempotencia, payload_hash,
                     estado_processamento, resultado, concluido_em)
                VALUES
                    ('registrar_lote', %(aggregate_id)s, %(chave)s, %(hash)s,
                     'concluido', %(resultado)s, now())
            """, dict(
                aggregate_id=_uuid(),
                chave=_CHAVE_SINTETICA,
                hash="0" * 64,
                resultado=psycopg.types.json.Jsonb({"teste": "residuo-sintetico"}),
            ))
        conn.commit()


def _remover_recibo_sintetico_b4(url: str) -> None:
    """DELETE explicito, exclusivamente da linha sintetica criada por
    este teste - nunca um TRUNCATE nem remocao mais ampla."""
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL ROLE nsi_eventos_owner")
            cur.execute(
                "DELETE FROM nsi_operacional.comandos_idempotentes "
                "WHERE comando = 'registrar_lote' AND chave_idempotencia = %(chave)s",
                {"chave": _CHAVE_SINTETICA},
            )
        conn.commit()


def test_identidade_do_banco_de_teste_e_comprovada(request):
    url = request.getfixturevalue("url_banco_teste")
    _comprovar_identidade_antes_de_destrutivo(url)


def test_ciclo_downgrade_0003_upgrade_0004(request):
    """Estado inicial 0006 (aplicado manualmente pelo operador antes
    desta suite rodar) -> (gate) -> downgrade 0003 -> confirma
    inventario identico ao de 0003 original -> upgrade 0006 -> confirma
    inventario completo de volta, terminando OBRIGATORIAMENTE em 0006."""
    url = request.getfixturevalue("url_banco_teste")
    env = {**os.environ, "NSI_DATABASE_ENV": "test"}

    estado_inicial = _consultar_estado(url)
    assert estado_inicial["versao"] == "0006", (
        f"Estado inicial inesperado: alembic_version={estado_inicial['versao']!r}, "
        "esperado '0006' antes deste teste rodar - o fluxo aprovado exige "
        "'alembic upgrade 0006' aplicado manualmente antes da suite."
    )
    assert estado_inicial["tabelas"] == ({"alembic_version"} | TABELAS_B3 | TABELAS_B4 | TABELAS_B5)
    assert "registrar_lote" in estado_inicial["check_comando_def"]

    _comprovar_identidade_antes_de_destrutivo(url)

    resultado_downgrade = _executar_alembic("downgrade", "0003", env=env)
    assert resultado_downgrade.returncode == 0, resultado_downgrade.stderr
    _assert_saida_alembic_sem_dsn(url, resultado_downgrade.stdout, "downgrade 0003 - stdout")
    _assert_saida_alembic_sem_dsn(url, resultado_downgrade.stderr, "downgrade 0003 - stderr")

    estado_pos_downgrade = _consultar_estado(url)
    assert estado_pos_downgrade["versao"] == "0003"
    assert estado_pos_downgrade["tabelas"] == ({"alembic_version"} | TABELAS_B3), (
        "Downgrade precisa remover exatamente as quatro tabelas da B4.2, "
        f"sem residuo - encontrado: {estado_pos_downgrade['tabelas']}"
    )
    assert "registrar_lote" not in estado_pos_downgrade["check_comando_def"], (
        "CHECK de comando precisa voltar aos 5 valores originais de claims apos o downgrade."
    )

    resultado_upgrade = _executar_alembic("upgrade", "0006", env=env)
    assert resultado_upgrade.returncode == 0, resultado_upgrade.stderr
    _assert_saida_alembic_sem_dsn(url, resultado_upgrade.stdout, "upgrade 0006 - stdout")
    _assert_saida_alembic_sem_dsn(url, resultado_upgrade.stderr, "upgrade 0006 - stderr")

    estado_final = _consultar_estado(url)
    assert estado_final["versao"] == "0006", (
        "O ciclo de testes precisa terminar com nsi_test novamente em 0006 - "
        f"estado final encontrado: {estado_final['versao']!r}"
    )
    assert estado_final["tabelas"] == ({"alembic_version"} | TABELAS_B3 | TABELAS_B4 | TABELAS_B5)
    assert "registrar_lote" in estado_final["check_comando_def"]

    # Verificacao explicita de ownership, por pg_catalog, apos o upgrade
    # para 0006 - nunca presumida a partir de como a migration foi
    # escrita. alembic_version nunca e tocada por esta migration -
    # permanece do migrator, nunca do owner.
    owners_tabelas = estado_final["owners_tabelas"]
    assert owners_tabelas["lotes"] == "nsi_eventos_owner"
    assert owners_tabelas["registros_coleta"] == "nsi_eventos_owner"
    assert owners_tabelas["eventos_lote"] == "nsi_eventos_owner"
    assert owners_tabelas["eventos_registro_coleta"] == "nsi_eventos_owner"
    assert owners_tabelas["alembic_version"] == USUARIO_MIGRATOR_ESPERADO, (
        "alembic_version nunca deveria mudar de dono por causa da migration 0004."
    )

    owners_funcoes = estado_final["owners_funcoes"]
    assert owners_funcoes["fn_bloquear_alteracao_eventos_lote"] == "nsi_eventos_owner"
    assert owners_funcoes["fn_bloquear_alteracao_eventos_registro_coleta"] == "nsi_eventos_owner"


def test_downgrade_bloqueado_por_recibo_residual_b4(request):
    """Cenario de seguranca: um recibo de comando da B4, genuinamente
    commitado, precisa impedir o downgrade por completo - nunca ser
    apagado silenciosamente.

    Corrigido nesta rodada: a remocao do recibo sintetico precisa
    acontecer explicitamente DEPOIS de comprovar o bloqueio e ANTES da
    tentativa de downgrade limpo - remove-lo somente no 'finally' e
    tarde demais, pois o 'finally' so roda depois que o corpo inteiro
    (incluindo a propria tentativa 'limpa') ja executou. A remocao e
    confirmada por consulta direta antes de prosseguir.

    Recuperacao obrigatoria em 'finally', independente de qualquer
    falha intermediaria neste teste: repete a remocao do recibo
    sintetico de forma idempotente (garante limpeza mesmo se a remocao
    intermediaria acima nunca tiver sido alcancada por uma falha
    anterior), repete o gate completo de identidade, e forca 'alembic
    upgrade 0006' se nsi_test nao estiver la - nunca contra nsi_dev.
    Se o corpo do teste ja estiver propagando uma falha, o 'finally'
    nunca levanta uma NOVA falha por cima dela (o que a esconderia) -
    só levanta se a recuperacao falhar e nao houver falha original em
    andamento."""
    url = request.getfixturevalue("url_banco_teste")
    env = {**os.environ, "NSI_DATABASE_ENV": "test"}

    estado_inicial = _consultar_estado(url)
    assert estado_inicial["versao"] == "0006", (
        "Este teste tambem exige nsi_test em 0006 antes de rodar."
    )

    _inserir_recibo_sintetico_b4(url)
    try:
        _comprovar_identidade_antes_de_destrutivo(url)

        resultado_bloqueado = _executar_alembic("downgrade", "0003", env=env)
        assert resultado_bloqueado.returncode != 0, (
            "O downgrade deveria falhar com o recibo sintetico da B4 ainda presente."
        )
        assert "recibo" in resultado_bloqueado.stderr.lower() or "b4" in resultado_bloqueado.stderr.lower(), (
            "A falha precisa ser a mensagem explicita do preflight, nao um erro generico."
        )
        _assert_saida_alembic_sem_dsn(url, resultado_bloqueado.stdout, "downgrade bloqueado - stdout")
        _assert_saida_alembic_sem_dsn(url, resultado_bloqueado.stderr, "downgrade bloqueado - stderr")

        estado_apos_bloqueio = _consultar_estado(url)
        assert estado_apos_bloqueio["versao"] == "0006", (
            "nsi_test precisa permanecer integralmente em 0006 apos o downgrade recusado."
        )
        assert estado_apos_bloqueio["tabelas"] == ({"alembic_version"} | TABELAS_B3 | TABELAS_B4 | TABELAS_B5), (
            "Nenhuma tabela pode ter sido removida por um downgrade que falhou no preflight."
        )

        # Remove explicitamente o recibo sintetico ANTES de tentar o
        # downgrade limpo - a remocao so no 'finally' (abaixo) e tarde
        # demais para esta segunda tentativa, que precisa mesmo encontrar
        # o preflight ja desbloqueado. Confirma por consulta direta que
        # o recibo realmente nao existe mais antes de prosseguir.
        _remover_recibo_sintetico_b4(url)
        with psycopg.connect(url) as conn:
            with conn.cursor() as cur:
                cur.execute("SET LOCAL ROLE nsi_eventos_owner")
                cur.execute(
                    "SELECT COUNT(*) FROM nsi_operacional.comandos_idempotentes "
                    "WHERE chave_idempotencia = %(chave)s",
                    {"chave": _CHAVE_SINTETICA},
                )
                (quantidade_apos_remocao,) = cur.fetchone()
        assert quantidade_apos_remocao == 0, (
            "O recibo sintetico precisa estar confirmadamente ausente antes do downgrade limpo - "
            f"encontrado {quantidade_apos_remocao} linha(s)."
        )

        _comprovar_identidade_antes_de_destrutivo(url)
        resultado_downgrade_limpo = _executar_alembic("downgrade", "0003", env=env)
        assert resultado_downgrade_limpo.returncode == 0, resultado_downgrade_limpo.stderr
        _assert_saida_alembic_sem_dsn(url, resultado_downgrade_limpo.stdout, "downgrade limpo - stdout")
        _assert_saida_alembic_sem_dsn(url, resultado_downgrade_limpo.stderr, "downgrade limpo - stderr")

        estado_pos_downgrade_limpo = _consultar_estado(url)
        assert estado_pos_downgrade_limpo["versao"] == "0003"
        assert estado_pos_downgrade_limpo["tabelas"] == ({"alembic_version"} | TABELAS_B3)
    finally:
        excecao_original_em_andamento = sys.exc_info()[0] is not None

        # Remove exclusivamente o recibo sintetico deste teste - nunca
        # depende de o corpo acima ter tido sucesso.
        _remover_recibo_sintetico_b4(url)

        # Gate completo repetido antes de qualquer acao de recuperacao.
        _comprovar_identidade_antes_de_destrutivo(url)

        estado_para_recuperacao = _consultar_estado(url)
        if estado_para_recuperacao["versao"] != "0006":
            resultado_recuperacao = _executar_alembic("upgrade", "0006", env=env)
            _assert_saida_alembic_sem_dsn(url, resultado_recuperacao.stdout, "recuperacao final - stdout")
            _assert_saida_alembic_sem_dsn(url, resultado_recuperacao.stderr, "recuperacao final - stderr")
            if resultado_recuperacao.returncode != 0 and not excecao_original_em_andamento:
                # So levanta uma falha NOVA aqui quando nao ha nenhuma
                # falha original em andamento - nunca mascara a causa
                # raiz de uma falha anterior do proprio corpo do teste.
                pytest.fail(
                    "Falha ao recuperar nsi_test para 0006 apos o teste - stderr: "
                    f"{resultado_recuperacao.stderr[-500:] if resultado_recuperacao.stderr else '(vazio)'}"
                )

    estado_final = _consultar_estado(url)
    assert estado_final["versao"] == "0006", (
        "O ciclo precisa terminar novamente em 0006, sem nenhum residuo permanente "
        "das duas tentativas de downgrade."
    )
    assert estado_final["tabelas"] == ({"alembic_version"} | TABELAS_B3 | TABELAS_B4 | TABELAS_B5)

    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL ROLE nsi_eventos_owner")
            cur.execute(
                "SELECT COUNT(*) FROM nsi_operacional.comandos_idempotentes WHERE chave_idempotencia = %(chave)s",
                {"chave": _CHAVE_SINTETICA},
            )
            (quantidade,) = cur.fetchone()
    assert quantidade == 0, "O recibo sintetico nao pode sobreviver ao final deste teste."


def test_dsn_mascarada_nunca_contem_usuario_ou_senha(request):
    url = request.getfixturevalue("url_banco_teste")
    representacao_segura = mascarar_dsn(url)
    assert "@" not in representacao_segura
    assert "://" not in representacao_segura
