"""seis funcoes SECURITY DEFINER do ciclo de vida do claim - Sprint B (B3.3, ADR-008)

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-13

Cria EXATAMENTE as seis funcoes SECURITY DEFINER aprovadas na Parte 1 da
B3 e detalhadas na Especificacao Tecnica da Sprint B (Secao 15), com as
correcoes finais aprovadas na rodada de planejamento da B3.3:

  1. fn_criar_claim
  2. fn_registrar_heartbeat
  3. fn_liberar_claim
  4. fn_materializar_expiracao
  5. fn_registrar_revisao_abandono
  6. fn_reatribuir_claim

Nenhuma setima funcao (nenhum helper auxiliar) - a expressao de
'executado_por' e inline, repetida, em cada uma das seis. Todas:
LANGUAGE plpgsql, SECURITY DEFINER, dona nsi_eventos_owner, search_path
fixo (pg_catalog, nsi_operacional, pg_temp), toda referencia interna
qualificada por schema. claim_id/evento_id sempre gerados dentro da
funcao via gen_random_uuid() (nativo do PostgreSQL 13+, sem extensao) -
nunca recebidos como parametro. Nenhuma DML direta e concedida a
nenhuma role funcional - apenas EXECUTE, na matriz minima abaixo.

Idempotencia persistente (cinco funcoes externas; fn_materializar_
expiracao dispensa chave, idempotente por desenho via UPDATE
condicional): reserva com
  INSERT ... ON CONFLICT (comando, aggregate_id, chave_idempotencia)
  DO NOTHING RETURNING payload_hash
antes de qualquer efeito; payload_hash divergente na mesma chave ->
RAISE EXCEPTION 'conflito_de_idempotencia' USING ERRCODE = '22023' -
SQLSTATE padrao SQL (invalid_parameter_value), mensagem fixa, nunca
interpolando chave/hash/DSN/token/payload; o recibo original nunca e
tocado (a excecao aborta antes de qualquer escrita adicional). payload_
hash cobre TODOS os campos semanticamente relevantes, incluindo
token_hash/token_hash_novo - uma tentativa legitima repete o mesmo
token (ainda em memoria) e produz o mesmo hash; uma tentativa com token
novo (resposta e token originais perdidos) diverge e produz conflito,
nunca um resultado combinando token novo com recibo antigo.

Pre-requisito: migrations 0001/0002 ja aplicadas (nao alteradas por
este arquivo) e B3.1 (roles) ja provisionada.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Mesmo padrao da 0002: toda a migration roda como o owner das
    # funcoes de negocio, nunca como o migrator. RESET ROLE explicito e
    # obrigatorio no caminho de sucesso, antes de o Alembic gravar o
    # carimbo em alembic_version (tabela do migrator).
    op.execute("SET LOCAL ROLE nsi_eventos_owner")

    # =========================================================
    # 1) fn_criar_claim
    # =========================================================
    op.execute("""
        CREATE FUNCTION nsi_operacional.fn_criar_claim(
            p_registro_coleta_id  UUID,
            p_token_hash          TEXT,
            p_chave_idempotencia  TEXT,
            p_payload_hash        TEXT
        ) RETURNS JSONB
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, nsi_operacional, pg_temp
        AS $fn$
        DECLARE
            v_payload_existente   TEXT;
            v_resultado_existente JSONB;
            v_novo_claim_id       UUID;
            v_versao              BIGINT;
            v_resultado           JSONB;
            v_executado_por       JSONB;
        BEGIN
            v_executado_por := jsonb_build_object(
                'role', session_user, 'worker_id', current_setting('app.worker_id', true));

            INSERT INTO nsi_operacional.comandos_idempotentes
                (comando, aggregate_id, chave_idempotencia, payload_hash, estado_processamento)
            VALUES ('criar_claim', p_registro_coleta_id, p_chave_idempotencia, p_payload_hash, 'processando')
            ON CONFLICT (comando, aggregate_id, chave_idempotencia) DO NOTHING
            RETURNING payload_hash INTO v_payload_existente;

            IF NOT FOUND THEN
                SELECT payload_hash, resultado INTO v_payload_existente, v_resultado_existente
                  FROM nsi_operacional.comandos_idempotentes
                 WHERE comando = 'criar_claim' AND aggregate_id = p_registro_coleta_id
                   AND chave_idempotencia = p_chave_idempotencia;

                IF v_payload_existente IS DISTINCT FROM p_payload_hash THEN
                    RAISE EXCEPTION 'conflito_de_idempotencia' USING ERRCODE = '22023';
                END IF;

                RETURN v_resultado_existente;
            END IF;

            v_novo_claim_id := gen_random_uuid();

            INSERT INTO nsi_operacional.claims
                   (registro_coleta_id, claim_id, token_hash, estado, criado_em, expira_em,
                    versao_atual, ultimo_heartbeat_em, revisao_atual_id, revisao_decisao, revisao_registrada_em)
            VALUES (p_registro_coleta_id, v_novo_claim_id, p_token_hash, 'ativo', now(), now() + interval '5 minutes',
                    1, NULL, NULL, NULL, NULL)
            ON CONFLICT (registro_coleta_id) DO UPDATE
               SET claim_id              = EXCLUDED.claim_id,
                   token_hash            = EXCLUDED.token_hash,
                   estado                = 'ativo',
                   criado_em             = now(),
                   expira_em             = now() + interval '5 minutes',
                   versao_atual          = nsi_operacional.claims.versao_atual + 1,
                   ultimo_heartbeat_em   = NULL,
                   revisao_atual_id      = NULL,
                   revisao_decisao       = NULL,
                   revisao_registrada_em = NULL
             WHERE nsi_operacional.claims.estado = 'liberado'
            RETURNING versao_atual INTO v_versao;

            IF FOUND THEN
                INSERT INTO nsi_operacional.eventos_claim
                    (evento_id, aggregate_type, aggregate_id, aggregate_version, tipo, claim_id, executado_por, payload)
                VALUES (gen_random_uuid(), 'claim', p_registro_coleta_id, v_versao, 'claim_criado', v_novo_claim_id,
                        v_executado_por, '{}'::jsonb);

                v_resultado := jsonb_build_object(
                    'sucesso', true, 'claim_id', v_novo_claim_id,
                    'expira_em', (now() + interval '5 minutes'), 'versao_atual', v_versao);
            ELSE
                v_resultado := jsonb_build_object('sucesso', false, 'motivo', 'registro_ocupado');
            END IF;

            UPDATE nsi_operacional.comandos_idempotentes
               SET estado_processamento = 'concluido', resultado = v_resultado, concluido_em = now()
             WHERE comando = 'criar_claim' AND aggregate_id = p_registro_coleta_id
               AND chave_idempotencia = p_chave_idempotencia;

            RETURN v_resultado;
        END;
        $fn$
    """)
    op.execute("REVOKE ALL ON FUNCTION nsi_operacional.fn_criar_claim(UUID, TEXT, TEXT, TEXT) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION nsi_operacional.fn_criar_claim(UUID, TEXT, TEXT, TEXT) TO nsi_aplicacao")

    # =========================================================
    # 2) fn_registrar_heartbeat
    # =========================================================
    op.execute("""
        CREATE FUNCTION nsi_operacional.fn_registrar_heartbeat(
            p_registro_coleta_id  UUID,
            p_claim_id            UUID,
            p_token_hash          TEXT,
            p_chave_idempotencia  TEXT,
            p_payload_hash        TEXT
        ) RETURNS JSONB
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, nsi_operacional, pg_temp
        AS $fn$
        DECLARE
            v_payload_existente   TEXT;
            v_resultado_existente JSONB;
            v_versao              BIGINT;
            v_nova_expira_em      TIMESTAMPTZ;
            v_resultado           JSONB;
            v_executado_por       JSONB;
            v_pode_materializar   BOOLEAN;
        BEGIN
            v_executado_por := jsonb_build_object(
                'role', session_user, 'worker_id', current_setting('app.worker_id', true));

            INSERT INTO nsi_operacional.comandos_idempotentes
                (comando, aggregate_id, chave_idempotencia, payload_hash, estado_processamento)
            VALUES ('registrar_heartbeat', p_registro_coleta_id, p_chave_idempotencia, p_payload_hash, 'processando')
            ON CONFLICT (comando, aggregate_id, chave_idempotencia) DO NOTHING
            RETURNING payload_hash INTO v_payload_existente;

            IF NOT FOUND THEN
                SELECT payload_hash, resultado INTO v_payload_existente, v_resultado_existente
                  FROM nsi_operacional.comandos_idempotentes
                 WHERE comando = 'registrar_heartbeat' AND aggregate_id = p_registro_coleta_id
                   AND chave_idempotencia = p_chave_idempotencia;

                IF v_payload_existente IS DISTINCT FROM p_payload_hash THEN
                    RAISE EXCEPTION 'conflito_de_idempotencia' USING ERRCODE = '22023';
                END IF;

                RETURN v_resultado_existente;
            END IF;

            v_nova_expira_em := now() + interval '5 minutes';

            UPDATE nsi_operacional.claims
               SET expira_em = v_nova_expira_em, ultimo_heartbeat_em = now(), versao_atual = versao_atual + 1
             WHERE registro_coleta_id = p_registro_coleta_id
               AND claim_id = p_claim_id
               AND token_hash = p_token_hash
               AND estado = 'ativo'
               AND now() < expira_em
            RETURNING versao_atual INTO v_versao;

            IF FOUND THEN
                INSERT INTO nsi_operacional.eventos_claim
                    (evento_id, aggregate_type, aggregate_id, aggregate_version, tipo, claim_id, executado_por, payload)
                VALUES (gen_random_uuid(), 'claim', p_registro_coleta_id, v_versao, 'heartbeat_registrado', p_claim_id,
                        v_executado_por, '{}'::jsonb);

                v_resultado := jsonb_build_object('sucesso', true, 'expira_em', v_nova_expira_em, 'versao_atual', v_versao);
            ELSE
                SELECT EXISTS (
                    SELECT 1 FROM nsi_operacional.claims
                     WHERE registro_coleta_id = p_registro_coleta_id
                       AND claim_id = p_claim_id
                       AND token_hash = p_token_hash
                       AND estado = 'ativo'
                       AND now() >= expira_em
                ) INTO v_pode_materializar;

                IF v_pode_materializar THEN
                    UPDATE nsi_operacional.claims
                       SET estado = 'expirado_pendente_revisao', versao_atual = versao_atual + 1
                     WHERE registro_coleta_id = p_registro_coleta_id AND estado = 'ativo' AND expira_em <= now()
                    RETURNING versao_atual INTO v_versao;

                    IF FOUND THEN
                        INSERT INTO nsi_operacional.eventos_claim
                            (evento_id, aggregate_type, aggregate_id, aggregate_version, tipo, claim_id, executado_por, payload)
                        VALUES (gen_random_uuid(), 'claim', p_registro_coleta_id, v_versao, 'claim_expirado', p_claim_id,
                                v_executado_por, '{}'::jsonb);
                    END IF;

                    v_resultado := jsonb_build_object('sucesso', false, 'motivo', 'expirado_materializado_nesta_chamada');
                ELSE
                    v_resultado := jsonb_build_object('sucesso', false, 'motivo', 'token_claim_ou_estado_invalido');
                END IF;
            END IF;

            UPDATE nsi_operacional.comandos_idempotentes
               SET estado_processamento = 'concluido', resultado = v_resultado, concluido_em = now()
             WHERE comando = 'registrar_heartbeat' AND aggregate_id = p_registro_coleta_id
               AND chave_idempotencia = p_chave_idempotencia;

            RETURN v_resultado;
        END;
        $fn$
    """)
    op.execute(
        "REVOKE ALL ON FUNCTION nsi_operacional.fn_registrar_heartbeat(UUID, UUID, TEXT, TEXT, TEXT) FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION nsi_operacional.fn_registrar_heartbeat(UUID, UUID, TEXT, TEXT, TEXT) TO nsi_aplicacao"
    )

    # =========================================================
    # 3) fn_liberar_claim
    # =========================================================
    op.execute("""
        CREATE FUNCTION nsi_operacional.fn_liberar_claim(
            p_registro_coleta_id  UUID,
            p_claim_id            UUID,
            p_token_hash          TEXT,
            p_chave_idempotencia  TEXT,
            p_payload_hash        TEXT
        ) RETURNS JSONB
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, nsi_operacional, pg_temp
        AS $fn$
        DECLARE
            v_payload_existente   TEXT;
            v_resultado_existente JSONB;
            v_versao              BIGINT;
            v_resultado           JSONB;
            v_executado_por       JSONB;
            v_pode_materializar   BOOLEAN;
        BEGIN
            v_executado_por := jsonb_build_object(
                'role', session_user, 'worker_id', current_setting('app.worker_id', true));

            INSERT INTO nsi_operacional.comandos_idempotentes
                (comando, aggregate_id, chave_idempotencia, payload_hash, estado_processamento)
            VALUES ('liberar_claim', p_registro_coleta_id, p_chave_idempotencia, p_payload_hash, 'processando')
            ON CONFLICT (comando, aggregate_id, chave_idempotencia) DO NOTHING
            RETURNING payload_hash INTO v_payload_existente;

            IF NOT FOUND THEN
                SELECT payload_hash, resultado INTO v_payload_existente, v_resultado_existente
                  FROM nsi_operacional.comandos_idempotentes
                 WHERE comando = 'liberar_claim' AND aggregate_id = p_registro_coleta_id
                   AND chave_idempotencia = p_chave_idempotencia;

                IF v_payload_existente IS DISTINCT FROM p_payload_hash THEN
                    RAISE EXCEPTION 'conflito_de_idempotencia' USING ERRCODE = '22023';
                END IF;

                RETURN v_resultado_existente;
            END IF;

            UPDATE nsi_operacional.claims
               SET estado = 'liberado', versao_atual = versao_atual + 1
             WHERE registro_coleta_id = p_registro_coleta_id
               AND claim_id = p_claim_id
               AND token_hash = p_token_hash
               AND estado = 'ativo'
               AND now() < expira_em
            RETURNING versao_atual INTO v_versao;

            IF FOUND THEN
                INSERT INTO nsi_operacional.eventos_claim
                    (evento_id, aggregate_type, aggregate_id, aggregate_version, tipo, claim_id, executado_por, payload)
                VALUES (gen_random_uuid(), 'claim', p_registro_coleta_id, v_versao, 'claim_liberado', p_claim_id,
                        v_executado_por, '{}'::jsonb);

                v_resultado := jsonb_build_object('sucesso', true, 'versao_atual', v_versao);
            ELSE
                SELECT EXISTS (
                    SELECT 1 FROM nsi_operacional.claims
                     WHERE registro_coleta_id = p_registro_coleta_id
                       AND claim_id = p_claim_id
                       AND token_hash = p_token_hash
                       AND estado = 'ativo'
                       AND now() >= expira_em
                ) INTO v_pode_materializar;

                IF v_pode_materializar THEN
                    UPDATE nsi_operacional.claims
                       SET estado = 'expirado_pendente_revisao', versao_atual = versao_atual + 1
                     WHERE registro_coleta_id = p_registro_coleta_id AND estado = 'ativo' AND expira_em <= now()
                    RETURNING versao_atual INTO v_versao;

                    IF FOUND THEN
                        INSERT INTO nsi_operacional.eventos_claim
                            (evento_id, aggregate_type, aggregate_id, aggregate_version, tipo, claim_id, executado_por, payload)
                        VALUES (gen_random_uuid(), 'claim', p_registro_coleta_id, v_versao, 'claim_expirado', p_claim_id,
                                v_executado_por, '{}'::jsonb);
                    END IF;

                    v_resultado := jsonb_build_object('sucesso', false, 'motivo', 'expirado_materializado_nesta_chamada');
                ELSE
                    v_resultado := jsonb_build_object('sucesso', false, 'motivo', 'token_claim_ou_estado_invalido');
                END IF;
            END IF;

            UPDATE nsi_operacional.comandos_idempotentes
               SET estado_processamento = 'concluido', resultado = v_resultado, concluido_em = now()
             WHERE comando = 'liberar_claim' AND aggregate_id = p_registro_coleta_id
               AND chave_idempotencia = p_chave_idempotencia;

            RETURN v_resultado;
        END;
        $fn$
    """)
    op.execute(
        "REVOKE ALL ON FUNCTION nsi_operacional.fn_liberar_claim(UUID, UUID, TEXT, TEXT, TEXT) FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION nsi_operacional.fn_liberar_claim(UUID, UUID, TEXT, TEXT, TEXT) TO nsi_aplicacao"
    )

    # =========================================================
    # 4) fn_materializar_expiracao - unica sem chave de idempotencia
    # =========================================================
    op.execute("""
        CREATE FUNCTION nsi_operacional.fn_materializar_expiracao(
            p_registro_coleta_id UUID
        ) RETURNS JSONB
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, nsi_operacional, pg_temp
        AS $fn$
        DECLARE
            v_versao        BIGINT;
            v_claim_id      UUID;
            v_resultado     JSONB;
            v_executado_por JSONB;
        BEGIN
            v_executado_por := jsonb_build_object(
                'role', session_user, 'worker_id', current_setting('app.worker_id', true));

            UPDATE nsi_operacional.claims
               SET estado = 'expirado_pendente_revisao', versao_atual = versao_atual + 1
             WHERE registro_coleta_id = p_registro_coleta_id AND estado = 'ativo' AND expira_em <= now()
            RETURNING versao_atual, claim_id INTO v_versao, v_claim_id;

            IF FOUND THEN
                INSERT INTO nsi_operacional.eventos_claim
                    (evento_id, aggregate_type, aggregate_id, aggregate_version, tipo, claim_id, executado_por, payload)
                VALUES (gen_random_uuid(), 'claim', p_registro_coleta_id, v_versao, 'claim_expirado', v_claim_id,
                        v_executado_por, '{}'::jsonb);

                v_resultado := jsonb_build_object('materializado', true, 'claim_id', v_claim_id, 'versao_atual', v_versao);
            ELSE
                v_resultado := jsonb_build_object('materializado', false);
            END IF;

            RETURN v_resultado;
        END;
        $fn$
    """)
    op.execute(
        "REVOKE ALL ON FUNCTION nsi_operacional.fn_materializar_expiracao(UUID) FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION nsi_operacional.fn_materializar_expiracao(UUID) TO nsi_aplicacao, nsi_expiracao"
    )

    # =========================================================
    # 5) fn_registrar_revisao_abandono
    # =========================================================
    op.execute("""
        CREATE FUNCTION nsi_operacional.fn_registrar_revisao_abandono(
            p_registro_coleta_id  UUID,
            p_decisao             TEXT,
            p_justificativa       TEXT,
            p_chave_idempotencia  TEXT,
            p_payload_hash        TEXT
        ) RETURNS JSONB
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, nsi_operacional, pg_temp
        AS $fn$
        DECLARE
            v_payload_existente   TEXT;
            v_resultado_existente JSONB;
            v_evento_id           UUID;
            v_claim_id            UUID;
            v_versao              BIGINT;
            v_resultado           JSONB;
            v_executado_por       JSONB;
        BEGIN
            v_executado_por := jsonb_build_object(
                'role', session_user, 'worker_id', current_setting('app.worker_id', true));

            INSERT INTO nsi_operacional.comandos_idempotentes
                (comando, aggregate_id, chave_idempotencia, payload_hash, estado_processamento)
            VALUES ('registrar_revisao_abandono', p_registro_coleta_id, p_chave_idempotencia, p_payload_hash, 'processando')
            ON CONFLICT (comando, aggregate_id, chave_idempotencia) DO NOTHING
            RETURNING payload_hash INTO v_payload_existente;

            IF NOT FOUND THEN
                SELECT payload_hash, resultado INTO v_payload_existente, v_resultado_existente
                  FROM nsi_operacional.comandos_idempotentes
                 WHERE comando = 'registrar_revisao_abandono' AND aggregate_id = p_registro_coleta_id
                   AND chave_idempotencia = p_chave_idempotencia;

                IF v_payload_existente IS DISTINCT FROM p_payload_hash THEN
                    RAISE EXCEPTION 'conflito_de_idempotencia' USING ERRCODE = '22023';
                END IF;

                RETURN v_resultado_existente;
            END IF;

            v_evento_id := gen_random_uuid();

            UPDATE nsi_operacional.claims
               SET versao_atual = versao_atual + 1,
                   revisao_atual_id = v_evento_id,
                   revisao_decisao = p_decisao,
                   revisao_registrada_em = now()
             WHERE registro_coleta_id = p_registro_coleta_id AND estado = 'expirado_pendente_revisao'
            RETURNING claim_id, versao_atual INTO v_claim_id, v_versao;

            IF FOUND THEN
                INSERT INTO nsi_operacional.eventos_claim
                    (evento_id, aggregate_type, aggregate_id, aggregate_version, tipo, claim_id, executado_por, payload)
                VALUES (v_evento_id, 'claim', p_registro_coleta_id, v_versao, 'revisao_de_abandono_registrada', v_claim_id,
                        v_executado_por,
                        jsonb_build_object('claim_id_revisado', v_claim_id, 'decisao', p_decisao, 'justificativa', p_justificativa));

                v_resultado := jsonb_build_object('sucesso', true, 'evento_id', v_evento_id, 'decisao', p_decisao);
            ELSE
                v_resultado := jsonb_build_object('sucesso', false, 'motivo', 'claim_nao_esta_pendente_de_revisao');
            END IF;

            UPDATE nsi_operacional.comandos_idempotentes
               SET estado_processamento = 'concluido', resultado = v_resultado, concluido_em = now()
             WHERE comando = 'registrar_revisao_abandono' AND aggregate_id = p_registro_coleta_id
               AND chave_idempotencia = p_chave_idempotencia;

            RETURN v_resultado;
        END;
        $fn$
    """)
    op.execute(
        "REVOKE ALL ON FUNCTION nsi_operacional.fn_registrar_revisao_abandono(UUID, TEXT, TEXT, TEXT, TEXT) FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION nsi_operacional.fn_registrar_revisao_abandono(UUID, TEXT, TEXT, TEXT, TEXT) "
        "TO nsi_operador_restrito"
    )

    # =========================================================
    # 6) fn_reatribuir_claim
    # =========================================================
    op.execute("""
        CREATE FUNCTION nsi_operacional.fn_reatribuir_claim(
            p_registro_coleta_id  UUID,
            p_evento_id_revisao   UUID,
            p_token_hash_novo     TEXT,
            p_chave_idempotencia  TEXT,
            p_payload_hash        TEXT
        ) RETURNS JSONB
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, nsi_operacional, pg_temp
        AS $fn$
        DECLARE
            v_payload_existente   TEXT;
            v_resultado_existente JSONB;
            v_novo_claim_id       UUID;
            v_versao              BIGINT;
            v_nova_expira_em      TIMESTAMPTZ;
            v_resultado           JSONB;
            v_executado_por       JSONB;
        BEGIN
            v_executado_por := jsonb_build_object(
                'role', session_user, 'worker_id', current_setting('app.worker_id', true));

            INSERT INTO nsi_operacional.comandos_idempotentes
                (comando, aggregate_id, chave_idempotencia, payload_hash, estado_processamento)
            VALUES ('reatribuir_claim', p_registro_coleta_id, p_chave_idempotencia, p_payload_hash, 'processando')
            ON CONFLICT (comando, aggregate_id, chave_idempotencia) DO NOTHING
            RETURNING payload_hash INTO v_payload_existente;

            IF NOT FOUND THEN
                SELECT payload_hash, resultado INTO v_payload_existente, v_resultado_existente
                  FROM nsi_operacional.comandos_idempotentes
                 WHERE comando = 'reatribuir_claim' AND aggregate_id = p_registro_coleta_id
                   AND chave_idempotencia = p_chave_idempotencia;

                IF v_payload_existente IS DISTINCT FROM p_payload_hash THEN
                    RAISE EXCEPTION 'conflito_de_idempotencia' USING ERRCODE = '22023';
                END IF;

                RETURN v_resultado_existente;
            END IF;

            v_novo_claim_id := gen_random_uuid();
            v_nova_expira_em := now() + interval '5 minutes';

            UPDATE nsi_operacional.claims
               SET claim_id              = v_novo_claim_id,
                   token_hash            = p_token_hash_novo,
                   estado                = 'ativo',
                   criado_em             = now(),
                   expira_em             = v_nova_expira_em,
                   ultimo_heartbeat_em   = NULL,
                   versao_atual          = versao_atual + 1,
                   revisao_atual_id      = NULL,
                   revisao_decisao       = NULL,
                   revisao_registrada_em = NULL
             WHERE registro_coleta_id = p_registro_coleta_id
               AND estado = 'expirado_pendente_revisao'
               AND revisao_atual_id = p_evento_id_revisao
               AND revisao_decisao = 'reatribuir'
               AND EXISTS (
                     SELECT 1 FROM nsi_operacional.eventos_claim ec
                      WHERE ec.evento_id    = p_evento_id_revisao
                        AND ec.aggregate_id = p_registro_coleta_id
                        AND ec.tipo         = 'revisao_de_abandono_registrada'
                        AND ec.claim_id     = claims.claim_id
                   )
            RETURNING versao_atual INTO v_versao;

            IF FOUND THEN
                INSERT INTO nsi_operacional.eventos_claim
                    (evento_id, aggregate_type, aggregate_id, aggregate_version, tipo, claim_id, executado_por, payload)
                VALUES (gen_random_uuid(), 'claim', p_registro_coleta_id, v_versao, 'claim_reatribuido', v_novo_claim_id,
                        v_executado_por, jsonb_build_object('evento_id_revisao', p_evento_id_revisao));

                v_resultado := jsonb_build_object(
                    'sucesso', true, 'claim_id', v_novo_claim_id,
                    'expira_em', v_nova_expira_em, 'versao_atual', v_versao);
            ELSE
                v_resultado := jsonb_build_object('sucesso', false, 'motivo', 'revisao_invalida_ou_ja_consumida');
            END IF;

            UPDATE nsi_operacional.comandos_idempotentes
               SET estado_processamento = 'concluido', resultado = v_resultado, concluido_em = now()
             WHERE comando = 'reatribuir_claim' AND aggregate_id = p_registro_coleta_id
               AND chave_idempotencia = p_chave_idempotencia;

            RETURN v_resultado;
        END;
        $fn$
    """)
    op.execute(
        "REVOKE ALL ON FUNCTION nsi_operacional.fn_reatribuir_claim(UUID, UUID, TEXT, TEXT, TEXT) FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION nsi_operacional.fn_reatribuir_claim(UUID, UUID, TEXT, TEXT, TEXT) "
        "TO nsi_operador_restrito"
    )

    # Devolve a sessao ao migrator antes de retornar ao Alembic.
    op.execute("RESET ROLE")

    op.execute("""
        DO $$
        BEGIN
            IF current_user <> session_user THEN
                RAISE EXCEPTION 'RESET ROLE falhou - current_user (%) diverge de session_user (%)', current_user, session_user;
            END IF;
        END $$
    """)


def downgrade() -> None:
    # Ordem inversa da criacao - sem dependencia real entre as seis
    # funcoes, mas mantida simetrica por clareza.
    op.execute("SET LOCAL ROLE nsi_eventos_owner")

    op.execute("DROP FUNCTION nsi_operacional.fn_reatribuir_claim(UUID, UUID, TEXT, TEXT, TEXT)")
    op.execute("DROP FUNCTION nsi_operacional.fn_registrar_revisao_abandono(UUID, TEXT, TEXT, TEXT, TEXT)")
    op.execute("DROP FUNCTION nsi_operacional.fn_materializar_expiracao(UUID)")
    op.execute("DROP FUNCTION nsi_operacional.fn_liberar_claim(UUID, UUID, TEXT, TEXT, TEXT)")
    op.execute("DROP FUNCTION nsi_operacional.fn_registrar_heartbeat(UUID, UUID, TEXT, TEXT, TEXT)")
    op.execute("DROP FUNCTION nsi_operacional.fn_criar_claim(UUID, TEXT, TEXT, TEXT)")

    op.execute("RESET ROLE")

    op.execute("""
        DO $$
        BEGIN
            IF current_user <> session_user THEN
                RAISE EXCEPTION 'RESET ROLE falhou - current_user (%) diverge de session_user (%)', current_user, session_user;
            END IF;
        END $$
    """)
