# -*- coding: utf-8 -*-
"""cinco funcoes SECURITY DEFINER do catalogo de eventos operacionais - Sprint B (B4.3, ADR-009)

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-03

Cria EXATAMENTE as cinco funcoes SECURITY DEFINER do catalogo fechado da
ADR-009 (Secao 6), detalhadas na Especificacao Tecnica da Sprint B
(Secao 18, B4.3), sobre as tabelas ja criadas pela 0004:

  1. fn_registrar_lote                     -> lote_criado
  2. fn_registrar_congelamento             -> lote_congelado_d8
  3. fn_confirmar_disparo                  -> disparo_confirmado
  4. fn_registrar_correcao                 -> correcao_registrada
  5. fn_registrar_tentativa_nao_resolvida  -> tentativa_correcao_nao_resolvida

Nenhuma sexta funcao, nenhum helper auxiliar, nenhuma tabela, coluna,
constraint, indice ou trigger. Todas: LANGUAGE plpgsql, SECURITY DEFINER,
dona nsi_eventos_owner, search_path fixo (pg_catalog, nsi_operacional,
pg_temp), toda referencia interna qualificada por schema, retorno JSONB.
evento_id sempre gerado dentro da funcao (gen_random_uuid()); tempo
sempre now() - nenhuma funcao aceita parametro de relogio.
executado_por_login = session_user, sempre - nunca current_user.

Versao de evento: UPDATE ... SET versao_eventos_atual =
versao_eventos_atual + 1 RETURNING, na linha do agregado - nunca
MAX(aggregate_version) + 1. Evento e projecao na mesma transacao;
nenhuma funcao executa UPDATE/DELETE em evento.

Bloqueio: toda funcao que toca lotes e registros_coleta adquire primeiro
a linha do lote (FOR UPDATE), depois a do registro.

Idempotencia: envelope identico ao da 0003 (reserva com INSERT ... ON
CONFLICT DO NOTHING; mesma chave e mesmo payload_hash -> replay; payload_
hash divergente -> 'conflito_de_idempotencia', SQLSTATE 22023, mensagem
fixa). As quatro funcoes com chave fornecida reservam o recibo antes de
qualquer efeito, e suas recusas tambem gravam recibo. O congelamento e a
excecao: chave deterministica (o proprio lote_id em texto), payload_hash
calculado dentro da funcao, pre-condicoes verificadas com o lote
bloqueado ANTES da reserva - recusa e estado impossivel nao deixam
recibo.

payload_hash do congelamento (formato canonico aprovado, D3): SHA-256 em
hexadecimal minusculo de
    {"comando":"registrar_congelamento","lote_id":"<uuid minusculo>"}
- JSON com chaves ordenadas, sem espacos, UTF-8. Identico ao que o modulo
Python de producao produzira para o mesmo lote_id.

Erros (D1/D2) - recusa de negocio e sempre retorno estruturado
(sucesso=false, motivo de vocabulario fechado), nunca excecao:
  - conflito de idempotencia: 'conflito_de_idempotencia', SQLSTATE 22023;
  - entrada estruturalmente invalida: 'entrada_estrutural_invalida',
    SQLSTATE 22000 - inclui chave de idempotencia fora de 1..200
    caracteres e payload_hash fora do formato (validados ANTES da reserva,
    para que o CHECK de comandos_idempotentes, cujo DETAIL nativo expoe a
    linha com o hash, nunca seja alcancado), lista de registros vazia, e
    registro_coleta_id ja gravado por outro lote concorrente;
  - violacao de constraint em lotes/registros_coleta: capturada e
    relancada como 'violacao_de_constraint' com o SQLSTATE nativo (classe
    23) e o NOME da constraint, sem DETAIL - o detalhe nativo incluiria a
    linha com nome e WhatsApp;
  - estado impossivel da arquitetura: 'invariante_violada', SQLSTATE
    proprio NS001.
Nenhuma mensagem interpola chave, hash, valor pessoal ou DSN.

Ordem de avaliacao em fn_registrar_lote: o PostgreSQL avalia as CHECKs de
lotes ANTES do teste de conflito do ON CONFLICT (lote_id). Por isso um
segundo upload do mesmo lote_id cujo lote_id_legado esteja fora do formato
recebe 'violacao_de_constraint' (23514), e nao a recusa 'lote_ja_existe'.

Nivel de isolamento (contrato do chamador): as cinco funcoes exigem
READ COMMITTED, o padrao do PostgreSQL e do projeto. A serializacao
correta - replay do congelamento concorrente, correcao tardia pela regra
do status, segunda confirmacao recusada - depende de o FOR UPDATE reler a
linha ja commitada pela transacao concorrente. Sob REPEATABLE READ ou
SERIALIZABLE, esses mesmos cenarios terminariam em falha de serializacao
(SQLSTATE 40001), e nao em replay ou recusa.

Matriz de EXECUTE (ADR-009, Secao 11), com REVOKE explicito de PUBLIC:
  fn_registrar_lote                    -> nsi_aplicacao
  fn_registrar_congelamento            -> nsi_congelamento
  fn_confirmar_disparo                 -> nsi_operador_restrito
  fn_registrar_correcao                -> nsi_aplicacao
  fn_registrar_tentativa_nao_resolvida -> nsi_aplicacao
nsi_expiracao em nenhuma. Nenhuma DML ou leitura direta e concedida.

Pre-requisitos: 0004 aplicada; B3.1 provisionada; role nsi_congelamento
provisionada administrativamente (provisionar_b4_role_congelamento.sql).
Esta migration nunca cria, altera ou remove a role - se ela nao existir,
falha antes de criar qualquer objeto.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Pre-requisito administrativo (ADR-009, Secao 11): a role
    # nsi_congelamento e criada exclusivamente pelo script de
    # provisionamento - nunca por esta migration. Sem ela, falha aqui,
    # antes de criar qualquer objeto.
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'nsi_congelamento') THEN
                RAISE EXCEPTION 'Role nsi_congelamento nao existe - provisione-a administrativamente antes desta migration (ADR-009, Secao 11).';
            END IF;
        END $$
    """)

    # Mesmo padrao de 0002/0003/0004: toda a migration roda como o owner
    # das funcoes de negocio, nunca como o migrator.
    op.execute("SET LOCAL ROLE nsi_eventos_owner")

    # =========================================================
    # 1) fn_registrar_lote - lote_criado
    # =========================================================
    op.execute("""
        CREATE FUNCTION nsi_operacional.fn_registrar_lote(
            p_lote_id             UUID,
            p_lote_id_legado      TEXT,
            p_registros           JSONB,
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
            v_resultado           JSONB;
            v_item                JSONB;
            v_chaves              TEXT[];
            v_total_recebido      INTEGER;
            v_total_valido        INTEGER;
            v_recebido_em         TIMESTAMPTZ;
            v_horario_conceitual  TIMESTAMPTZ;
            v_inserido            UUID;
            v_constraint          TEXT;
        BEGIN
            -- Chave e hash validados ANTES da reserva: fora do formato, o
            -- INSERT em comandos_idempotentes violaria um CHECK cujo DETAIL
            -- nativo expoe a linha inteira - inclusive o payload_hash,
            -- correlacionavel (ADR-009, Secao 9).
            IF p_lote_id IS NULL OR p_chave_idempotencia IS NULL OR p_payload_hash IS NULL
               OR char_length(p_chave_idempotencia) NOT BETWEEN 1 AND 200
               OR p_payload_hash !~ '^[0-9a-f]{64}$' THEN
                RAISE EXCEPTION 'entrada_estrutural_invalida' USING ERRCODE = '22000';
            END IF;

            INSERT INTO nsi_operacional.comandos_idempotentes
                (comando, aggregate_id, chave_idempotencia, payload_hash, estado_processamento)
            VALUES ('registrar_lote', p_lote_id, p_chave_idempotencia, p_payload_hash, 'processando')
            ON CONFLICT (comando, aggregate_id, chave_idempotencia) DO NOTHING
            RETURNING payload_hash INTO v_payload_existente;

            IF NOT FOUND THEN
                SELECT payload_hash, resultado INTO v_payload_existente, v_resultado_existente
                  FROM nsi_operacional.comandos_idempotentes
                 WHERE comando = 'registrar_lote' AND aggregate_id = p_lote_id
                   AND chave_idempotencia = p_chave_idempotencia;

                IF v_payload_existente IS DISTINCT FROM p_payload_hash THEN
                    RAISE EXCEPTION 'conflito_de_idempotencia' USING ERRCODE = '22023';
                END IF;

                RETURN v_resultado_existente;
            END IF;

            -- Estrutura da entrada: lista de objetos com exatamente os seis
            -- campos, cada um do tipo esperado. Qualquer desvio aborta a
            -- transacao inteira (inclusive a reserva acima), sem recibo.
            IF p_registros IS NULL OR jsonb_typeof(p_registros) <> 'array' THEN
                RAISE EXCEPTION 'entrada_estrutural_invalida' USING ERRCODE = '22000';
            END IF;
            -- Lista vazia e entrada estruturalmente invalida (decisao da B4.3):
            -- um lote sem nenhum registro nao e criado. IF separado do
            -- anterior: jsonb_array_length exige array, e o OR do SQL nao
            -- garante curto-circuito.
            IF jsonb_array_length(p_registros) = 0 THEN
                RAISE EXCEPTION 'entrada_estrutural_invalida' USING ERRCODE = '22000';
            END IF;

            FOR v_item IN SELECT value FROM jsonb_array_elements(p_registros) LOOP
                IF jsonb_typeof(v_item) <> 'object' THEN
                    RAISE EXCEPTION 'entrada_estrutural_invalida' USING ERRCODE = '22000';
                END IF;

                -- COALESCE: um objeto vazio daria array_agg nulo, e a condicao
                -- inteira ficaria nula - nunca verdadeira - deixando-o passar.
                SELECT COALESCE(array_agg(k), ARRAY[]::TEXT[]) INTO v_chaves FROM jsonb_object_keys(v_item) AS k;
                IF NOT (v_chaves @> ARRAY['registro_coleta_id', 'nome', 'whatsapp', 'produto', 'valido', 'motivos_invalidez']
                        AND v_chaves <@ ARRAY['registro_coleta_id', 'nome', 'whatsapp', 'produto', 'valido', 'motivos_invalidez'])
                   OR jsonb_typeof(v_item -> 'registro_coleta_id') <> 'string'
                   OR (v_item ->> 'registro_coleta_id') !~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
                   OR jsonb_typeof(v_item -> 'valido') <> 'boolean'
                   OR jsonb_typeof(v_item -> 'nome') NOT IN ('string', 'null')
                   OR jsonb_typeof(v_item -> 'whatsapp') NOT IN ('string', 'null')
                   OR jsonb_typeof(v_item -> 'produto') NOT IN ('string', 'null')
                   OR jsonb_typeof(v_item -> 'motivos_invalidez') NOT IN ('array', 'null')
                   OR (jsonb_typeof(v_item -> 'motivos_invalidez') = 'array'
                       AND EXISTS (SELECT 1 FROM jsonb_array_elements(v_item -> 'motivos_invalidez') AS m
                                    WHERE jsonb_typeof(m) <> 'string')) THEN
                    RAISE EXCEPTION 'entrada_estrutural_invalida' USING ERRCODE = '22000';
                END IF;
            END LOOP;

            -- registro_coleta_id repetido na propria lista: violacao estrutural.
            IF (SELECT count(*) <> count(DISTINCT lower(e ->> 'registro_coleta_id'))
                  FROM jsonb_array_elements(p_registros) AS e) THEN
                RAISE EXCEPTION 'entrada_estrutural_invalida' USING ERRCODE = '22000';
            END IF;

            -- Totais contados pela funcao, nunca informados pelo chamador.
            SELECT count(*), count(*) FILTER (WHERE (e ->> 'valido')::BOOLEAN)
              INTO v_total_recebido, v_total_valido
              FROM jsonb_array_elements(p_registros) AS e;

            v_recebido_em := now();
            -- M0 + 192h exatas (691200 s, ck_lotes_horario_conceitual) - nunca
            -- '8 days', que dependeria do fuso da sessao.
            v_horario_conceitual := v_recebido_em + interval '192 hours';

            -- Segundo upload do mesmo lote (chave nova) e recusa de negocio,
            -- nunca segundo evento - ON CONFLICT tambem resolve a corrida entre
            -- dois uploads concorrentes do mesmo lote_id. As CHECKs de lotes
            -- sao avaliadas ANTES do teste de conflito (ver cabecalho).
            BEGIN
                INSERT INTO nsi_operacional.lotes
                    (lote_id, lote_id_legado, recebido_em, total_recebido, total_valido, total_invalido,
                     status, horario_conceitual_congelamento, versao_eventos_atual)
                VALUES (p_lote_id, p_lote_id_legado, v_recebido_em, v_total_recebido, v_total_valido,
                        v_total_recebido - v_total_valido, 'aguardando_d8', v_horario_conceitual, 1)
                ON CONFLICT (lote_id) DO NOTHING
                RETURNING lote_id INTO v_inserido;
            EXCEPTION WHEN integrity_constraint_violation THEN
                -- Mensagem fixa e sem DETAIL (o nativo traria a linha inteira);
                -- so o NOME da constraint e repassado, para diagnostico.
                GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
                IF COALESCE(v_constraint, '') = '' THEN
                    RAISE EXCEPTION 'violacao_de_constraint' USING ERRCODE = SQLSTATE;
                END IF;
                RAISE EXCEPTION 'violacao_de_constraint' USING ERRCODE = SQLSTATE, CONSTRAINT = v_constraint;
            END;

            IF v_inserido IS NULL THEN
                v_resultado := jsonb_build_object('sucesso', false, 'motivo', 'lote_ja_existe');
            ELSE
                -- registro_coleta_id ja existente (em qualquer lote): violacao
                -- estrutural - so verificada depois de o lote ser novo, para
                -- que a repeticao de um upload ja aceito seja a recusa acima.
                IF EXISTS (SELECT 1 FROM nsi_operacional.registros_coleta r
                            WHERE r.registro_coleta_id IN (
                                SELECT (e ->> 'registro_coleta_id')::UUID FROM jsonb_array_elements(p_registros) AS e)) THEN
                    RAISE EXCEPTION 'entrada_estrutural_invalida' USING ERRCODE = '22000';
                END IF;

                BEGIN
                    INSERT INTO nsi_operacional.registros_coleta
                        (registro_coleta_id, lote_id, nome, produto, whatsapp, valido, motivos_invalidez)
                    SELECT (e ->> 'registro_coleta_id')::UUID, p_lote_id,
                           e ->> 'nome', e ->> 'produto', e ->> 'whatsapp', (e ->> 'valido')::BOOLEAN,
                           CASE WHEN jsonb_typeof(e -> 'motivos_invalidez') = 'array'
                                THEN ARRAY(SELECT jsonb_array_elements_text(e -> 'motivos_invalidez'))
                           END
                      FROM jsonb_array_elements(p_registros) AS e;
                EXCEPTION
                    WHEN unique_violation THEN
                        -- registro_coleta_id ja gravado por outro lote concorrente,
                        -- depois da verificacao acima: violacao estrutural, nao de
                        -- constraint (registros_coleta so tem a PK como unicidade).
                        RAISE EXCEPTION 'entrada_estrutural_invalida' USING ERRCODE = '22000';
                    WHEN integrity_constraint_violation THEN
                        -- Mensagem fixa e sem DETAIL (o nativo traria a linha inteira);
                        -- so o NOME da constraint e repassado, para diagnostico.
                        GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
                        IF COALESCE(v_constraint, '') = '' THEN
                            RAISE EXCEPTION 'violacao_de_constraint' USING ERRCODE = SQLSTATE;
                        END IF;
                        RAISE EXCEPTION 'violacao_de_constraint' USING ERRCODE = SQLSTATE, CONSTRAINT = v_constraint;
                END;

                INSERT INTO nsi_operacional.eventos_lote
                    (evento_id, aggregate_type, aggregate_id, aggregate_version, tipo, occurred_at,
                     executado_por_login, recebido_em, total_recebido, total_valido, total_invalido)
                VALUES (gen_random_uuid(), 'lote', p_lote_id, 1, 'lote_criado', v_recebido_em,
                        session_user, v_recebido_em, v_total_recebido, v_total_valido,
                        v_total_recebido - v_total_valido);

                v_resultado := jsonb_build_object(
                    'sucesso', true,
                    'lote_id', p_lote_id,
                    'recebido_em', v_recebido_em,
                    'horario_conceitual_congelamento', v_horario_conceitual,
                    'total_recebido', v_total_recebido,
                    'total_valido', v_total_valido,
                    'total_invalido', v_total_recebido - v_total_valido,
                    'status', 'aguardando_d8',
                    'versao_eventos', 1);
            END IF;

            UPDATE nsi_operacional.comandos_idempotentes
               SET estado_processamento = 'concluido', resultado = v_resultado, concluido_em = now()
             WHERE comando = 'registrar_lote' AND aggregate_id = p_lote_id
               AND chave_idempotencia = p_chave_idempotencia;

            RETURN v_resultado;
        END;
        $fn$
    """)
    op.execute(
        "REVOKE ALL ON FUNCTION nsi_operacional.fn_registrar_lote(UUID, TEXT, JSONB, TEXT, TEXT) FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION nsi_operacional.fn_registrar_lote(UUID, TEXT, JSONB, TEXT, TEXT) TO nsi_aplicacao"
    )

    # =========================================================
    # 2) fn_registrar_congelamento - lote_congelado_d8
    # =========================================================
    op.execute("""
        CREATE FUNCTION nsi_operacional.fn_registrar_congelamento(
            p_lote_id UUID
        ) RETURNS JSONB
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, nsi_operacional, pg_temp
        AS $fn$
        DECLARE
            v_chave               TEXT;
            v_payload_hash        TEXT;
            v_payload_existente   TEXT;
            v_resultado_existente JSONB;
            v_resultado           JSONB;
            v_status              TEXT;
            v_total_valido        INTEGER;
            v_horario_conceitual  TIMESTAMPTZ;
            v_contagem_real       INTEGER;
            v_novo_status         TEXT;
            v_atrasado            BOOLEAN;
            v_versao              BIGINT;
            v_constraint          TEXT;
        BEGIN
            IF p_lote_id IS NULL THEN
                RAISE EXCEPTION 'entrada_estrutural_invalida' USING ERRCODE = '22000';
            END IF;

            -- Chave deterministica e payload_hash calculado aqui (ADR-009,
            -- Secao 12; formato canonico D3).
            v_chave := p_lote_id::TEXT;
            v_payload_hash := encode(sha256(convert_to(
                '{"comando":"registrar_congelamento","lote_id":"' || p_lote_id::TEXT || '"}', 'UTF8')), 'hex');

            -- Linha do lote bloqueada ANTES de qualquer verificacao.
            SELECT status, total_valido, horario_conceitual_congelamento
              INTO v_status, v_total_valido, v_horario_conceitual
              FROM nsi_operacional.lotes
             WHERE lote_id = p_lote_id
               FOR UPDATE;

            IF NOT FOUND THEN
                -- Recusa sem evento e sem recibo.
                RETURN jsonb_build_object('sucesso', false, 'motivo', 'lote_inexistente');
            END IF;

            IF v_status <> 'aguardando_d8' THEN
                -- Lote ja congelado: devolve o resultado gravado na primeira
                -- execucao (replay). Sem esse recibo, o estado e impossivel.
                SELECT payload_hash, resultado INTO v_payload_existente, v_resultado_existente
                  FROM nsi_operacional.comandos_idempotentes
                 WHERE comando = 'registrar_congelamento' AND aggregate_id = p_lote_id
                   AND chave_idempotencia = v_chave;

                IF NOT FOUND THEN
                    RAISE EXCEPTION 'invariante_violada' USING ERRCODE = 'NS001';
                END IF;
                IF v_payload_existente IS DISTINCT FROM v_payload_hash THEN
                    RAISE EXCEPTION 'conflito_de_idempotencia' USING ERRCODE = '22023';
                END IF;

                RETURN v_resultado_existente;
            END IF;

            IF now() < v_horario_conceitual THEN
                -- Recusa sem evento e sem recibo: um recibo de recusa tornaria
                -- a recusa permanente e impediria o congelamento legitimo.
                RETURN jsonb_build_object('sucesso', false, 'motivo', 'instante_nao_atingido');
            END IF;

            -- Contagem real do instante, com o lote bloqueado.
            SELECT count(*) INTO v_contagem_real
              FROM nsi_operacional.registros_coleta
             WHERE lote_id = p_lote_id AND valido;

            -- Estado impossivel da arquitetura: aborta tudo, sem evento, sem
            -- recibo e sem alterar o lote - nunca corrige, nunca escolhe.
            IF v_contagem_real IS DISTINCT FROM v_total_valido THEN
                RAISE EXCEPTION 'invariante_violada' USING ERRCODE = 'NS001';
            END IF;

            INSERT INTO nsi_operacional.comandos_idempotentes
                (comando, aggregate_id, chave_idempotencia, payload_hash, estado_processamento)
            VALUES ('registrar_congelamento', p_lote_id, v_chave, v_payload_hash, 'processando')
            ON CONFLICT (comando, aggregate_id, chave_idempotencia) DO NOTHING;

            IF NOT FOUND THEN
                -- Recibo existente com o lote ainda em aguardando_d8, e com a
                -- linha do lote bloqueada: estado impossivel.
                RAISE EXCEPTION 'invariante_violada' USING ERRCODE = 'NS001';
            END IF;

            v_atrasado := now() > v_horario_conceitual;
            v_novo_status := CASE WHEN v_contagem_real = 0 THEN 'sem_registros_validos'
                                  ELSE 'aguardando_confirmacao_disparo' END;

            BEGIN
                UPDATE nsi_operacional.lotes
                   SET total_valido_congelado    = v_contagem_real,
                       horario_real_congelamento = now(),
                       congelamento_atrasado     = v_atrasado,
                       status                    = v_novo_status,
                       versao_eventos_atual      = versao_eventos_atual + 1
                 WHERE lote_id = p_lote_id
                RETURNING versao_eventos_atual INTO v_versao;
            EXCEPTION WHEN integrity_constraint_violation THEN
                -- Mensagem fixa e sem DETAIL (o nativo traria a linha inteira);
                -- so o NOME da constraint e repassado, para diagnostico.
                GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
                IF COALESCE(v_constraint, '') = '' THEN
                    RAISE EXCEPTION 'violacao_de_constraint' USING ERRCODE = SQLSTATE;
                END IF;
                RAISE EXCEPTION 'violacao_de_constraint' USING ERRCODE = SQLSTATE, CONSTRAINT = v_constraint;
            END;

            INSERT INTO nsi_operacional.eventos_lote
                (evento_id, aggregate_type, aggregate_id, aggregate_version, tipo, occurred_at,
                 executado_por_login, horario_conceitual, horario_real_execucao, atrasado)
            VALUES (gen_random_uuid(), 'lote', p_lote_id, v_versao, 'lote_congelado_d8', now(),
                    session_user, v_horario_conceitual, now(), v_atrasado);

            v_resultado := jsonb_build_object(
                'sucesso', true,
                'status', v_novo_status,
                'total_valido_congelado', v_contagem_real,
                'horario_conceitual', v_horario_conceitual,
                'horario_real_execucao', now(),
                'atrasado', v_atrasado,
                'versao_eventos', v_versao);

            UPDATE nsi_operacional.comandos_idempotentes
               SET estado_processamento = 'concluido', resultado = v_resultado, concluido_em = now()
             WHERE comando = 'registrar_congelamento' AND aggregate_id = p_lote_id
               AND chave_idempotencia = v_chave;

            RETURN v_resultado;
        END;
        $fn$
    """)
    op.execute(
        "REVOKE ALL ON FUNCTION nsi_operacional.fn_registrar_congelamento(UUID) FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION nsi_operacional.fn_registrar_congelamento(UUID) TO nsi_congelamento"
    )

    # =========================================================
    # 3) fn_confirmar_disparo - disparo_confirmado
    # =========================================================
    op.execute("""
        CREATE FUNCTION nsi_operacional.fn_confirmar_disparo(
            p_lote_id             UUID,
            p_total_esperado      INTEGER,
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
            v_resultado           JSONB;
            v_status              TEXT;
            v_total_congelado     INTEGER;
            v_versao              BIGINT;
            v_constraint          TEXT;
        BEGIN
            -- Chave e hash validados ANTES da reserva (ver fn_registrar_lote).
            IF p_lote_id IS NULL OR p_total_esperado IS NULL
               OR p_chave_idempotencia IS NULL OR p_payload_hash IS NULL
               OR char_length(p_chave_idempotencia) NOT BETWEEN 1 AND 200
               OR p_payload_hash !~ '^[0-9a-f]{64}$' THEN
                RAISE EXCEPTION 'entrada_estrutural_invalida' USING ERRCODE = '22000';
            END IF;

            INSERT INTO nsi_operacional.comandos_idempotentes
                (comando, aggregate_id, chave_idempotencia, payload_hash, estado_processamento)
            VALUES ('confirmar_disparo', p_lote_id, p_chave_idempotencia, p_payload_hash, 'processando')
            ON CONFLICT (comando, aggregate_id, chave_idempotencia) DO NOTHING
            RETURNING payload_hash INTO v_payload_existente;

            IF NOT FOUND THEN
                SELECT payload_hash, resultado INTO v_payload_existente, v_resultado_existente
                  FROM nsi_operacional.comandos_idempotentes
                 WHERE comando = 'confirmar_disparo' AND aggregate_id = p_lote_id
                   AND chave_idempotencia = p_chave_idempotencia;

                IF v_payload_existente IS DISTINCT FROM p_payload_hash THEN
                    RAISE EXCEPTION 'conflito_de_idempotencia' USING ERRCODE = '22023';
                END IF;

                RETURN v_resultado_existente;
            END IF;

            SELECT status, total_valido_congelado INTO v_status, v_total_congelado
              FROM nsi_operacional.lotes
             WHERE lote_id = p_lote_id
               FOR UPDATE;

            IF NOT FOUND THEN
                v_resultado := jsonb_build_object('sucesso', false, 'motivo', 'lote_inexistente');
            ELSIF v_status = 'aguardando_d8' THEN
                v_resultado := jsonb_build_object('sucesso', false, 'motivo', 'lote_nao_congelado');
            ELSIF v_status = 'sem_registros_validos' THEN
                v_resultado := jsonb_build_object('sucesso', false, 'motivo', 'sem_registros_validos');
            ELSIF v_status = 'disparo_confirmado' THEN
                v_resultado := jsonb_build_object('sucesso', false, 'motivo', 'disparo_ja_confirmado');
            ELSIF p_total_esperado IS DISTINCT FROM v_total_congelado THEN
                v_resultado := jsonb_build_object('sucesso', false, 'motivo', 'total_divergente');
            ELSE
                BEGIN
                    UPDATE nsi_operacional.lotes
                       SET status                        = 'disparo_confirmado',
                           disparo_confirmado_em         = now(),
                           disparo_confirmado_por_login  = session_user,
                           total_confirmado_para_disparo = v_total_congelado,
                           versao_eventos_atual          = versao_eventos_atual + 1
                     WHERE lote_id = p_lote_id
                    RETURNING versao_eventos_atual INTO v_versao;
                EXCEPTION WHEN integrity_constraint_violation THEN
                    -- Mensagem fixa e sem DETAIL (o nativo traria a linha inteira);
                    -- so o NOME da constraint e repassado, para diagnostico.
                    GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
                    IF COALESCE(v_constraint, '') = '' THEN
                        RAISE EXCEPTION 'violacao_de_constraint' USING ERRCODE = SQLSTATE;
                    END IF;
                    RAISE EXCEPTION 'violacao_de_constraint' USING ERRCODE = SQLSTATE, CONSTRAINT = v_constraint;
                END;

                -- occurred_at deste evento e o T0 da Coleta (ADR-005,
                -- Principio 1). operador_humano_id nulo ate a Sprint D.
                INSERT INTO nsi_operacional.eventos_lote
                    (evento_id, aggregate_type, aggregate_id, aggregate_version, tipo, occurred_at,
                     executado_por_login, operador_humano_id, total_confirmado)
                VALUES (gen_random_uuid(), 'lote', p_lote_id, v_versao, 'disparo_confirmado', now(),
                        session_user, NULL, v_total_congelado);

                v_resultado := jsonb_build_object(
                    'sucesso', true,
                    'lote_id', p_lote_id,
                    'disparo_confirmado_em', now(),
                    'total_confirmado', v_total_congelado,
                    'versao_eventos', v_versao);
            END IF;

            UPDATE nsi_operacional.comandos_idempotentes
               SET estado_processamento = 'concluido', resultado = v_resultado, concluido_em = now()
             WHERE comando = 'confirmar_disparo' AND aggregate_id = p_lote_id
               AND chave_idempotencia = p_chave_idempotencia;

            RETURN v_resultado;
        END;
        $fn$
    """)
    op.execute(
        "REVOKE ALL ON FUNCTION nsi_operacional.fn_confirmar_disparo(UUID, INTEGER, TEXT, TEXT) FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION nsi_operacional.fn_confirmar_disparo(UUID, INTEGER, TEXT, TEXT) "
        "TO nsi_operador_restrito"
    )

    # =========================================================
    # 4) fn_registrar_correcao - correcao_registrada
    # =========================================================
    op.execute("""
        CREATE FUNCTION nsi_operacional.fn_registrar_correcao(
            p_lote_id             UUID,
            p_registro_coleta_id  UUID,
            p_nome                TEXT,
            p_whatsapp            TEXT,
            p_produto             TEXT,
            p_valido              BOOLEAN,
            p_motivos_invalidez   TEXT[],
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
            v_resultado           JSONB;
            v_lote_status         TEXT;
            v_horario_conceitual  TIMESTAMPTZ;
            v_registro_valido     BOOLEAN;
            v_resultado_correcao  TEXT;
            v_numero_versao_dados BIGINT;
            v_versao              BIGINT;
            v_constraint          TEXT;
        BEGIN
            -- Chave e hash validados ANTES da reserva (ver fn_registrar_lote).
            IF p_lote_id IS NULL OR p_registro_coleta_id IS NULL OR p_valido IS NULL
               OR p_chave_idempotencia IS NULL OR p_payload_hash IS NULL
               OR char_length(p_chave_idempotencia) NOT BETWEEN 1 AND 200
               OR p_payload_hash !~ '^[0-9a-f]{64}$' THEN
                RAISE EXCEPTION 'entrada_estrutural_invalida' USING ERRCODE = '22000';
            END IF;

            -- Escopo da chave: (registrar_correcao, registro_coleta_id, chave
            -- da tentativa) - nunca o proprio registro_coleta_id como chave.
            INSERT INTO nsi_operacional.comandos_idempotentes
                (comando, aggregate_id, chave_idempotencia, payload_hash, estado_processamento)
            VALUES ('registrar_correcao', p_registro_coleta_id, p_chave_idempotencia, p_payload_hash, 'processando')
            ON CONFLICT (comando, aggregate_id, chave_idempotencia) DO NOTHING
            RETURNING payload_hash INTO v_payload_existente;

            IF NOT FOUND THEN
                SELECT payload_hash, resultado INTO v_payload_existente, v_resultado_existente
                  FROM nsi_operacional.comandos_idempotentes
                 WHERE comando = 'registrar_correcao' AND aggregate_id = p_registro_coleta_id
                   AND chave_idempotencia = p_chave_idempotencia;

                IF v_payload_existente IS DISTINCT FROM p_payload_hash THEN
                    RAISE EXCEPTION 'conflito_de_idempotencia' USING ERRCODE = '22023';
                END IF;

                RETURN v_resultado_existente;
            END IF;

            -- Bloqueio explicito da linha do lote no inicio: serializa esta
            -- correcao contra o congelamento (e contra outras correcoes).
            SELECT status, horario_conceitual_congelamento INTO v_lote_status, v_horario_conceitual
              FROM nsi_operacional.lotes
             WHERE lote_id = p_lote_id
               FOR UPDATE;

            -- Resolucao restrita ao lote informado (Sprint A3); depois do lote,
            -- a linha do registro.
            SELECT valido INTO v_registro_valido
              FROM nsi_operacional.registros_coleta
             WHERE registro_coleta_id = p_registro_coleta_id AND lote_id = p_lote_id
               FOR UPDATE;

            IF NOT FOUND THEN
                -- Nao resolvido neste lote: sem evento; diagnostico feito pelo
                -- banco, porque a aplicacao nao tem leitura direta.
                v_resultado := jsonb_build_object(
                    'sucesso', false,
                    'motivo', 'registro_nao_resolvido_neste_lote',
                    'diagnostico',
                    CASE WHEN EXISTS (SELECT 1 FROM nsi_operacional.registros_coleta
                                       WHERE registro_coleta_id = p_registro_coleta_id)
                         THEN 'registro_de_outra_operacao'
                         ELSE 'codigo_inexistente' END);
            ELSE
                -- Ordem de decisao da Sprint A3 (processar_uma_correcao).
                IF v_registro_valido THEN
                    v_resultado_correcao := 'recusada_ja_valido';
                ELSIF now() >= v_horario_conceitual OR v_lote_status <> 'aguardando_d8' THEN
                    v_resultado_correcao := 'recusada_tardia';
                ELSIF p_valido THEN
                    v_resultado_correcao := 'aplicada_valida';
                ELSE
                    v_resultado_correcao := 'aplicada_ainda_invalida';
                END IF;

                IF v_resultado_correcao IN ('aplicada_valida', 'aplicada_ainda_invalida') THEN
                    -- Sobrescreve o valor anterior (nenhum historico - ADR-009,
                    -- Secao 5); totais do lote ajustados na mesma transacao, sem
                    -- evento de lote e sem mudanca de status.
                    BEGIN
                        UPDATE nsi_operacional.registros_coleta
                           SET nome                 = p_nome,
                               whatsapp             = p_whatsapp,
                               produto              = p_produto,
                               valido               = p_valido,
                               motivos_invalidez    = p_motivos_invalidez,
                               numero_versao_dados  = numero_versao_dados + 1,
                               versao_eventos_atual = versao_eventos_atual + 1
                         WHERE registro_coleta_id = p_registro_coleta_id
                        RETURNING numero_versao_dados, versao_eventos_atual INTO v_numero_versao_dados, v_versao;

                        IF p_valido THEN
                            UPDATE nsi_operacional.lotes
                               SET total_valido   = total_valido + 1,
                                   total_invalido = total_invalido - 1
                             WHERE lote_id = p_lote_id;
                        END IF;
                    EXCEPTION WHEN integrity_constraint_violation THEN
                        -- Mensagem fixa e sem DETAIL (o nativo traria a linha inteira);
                        -- so o NOME da constraint e repassado, para diagnostico.
                        GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
                        IF COALESCE(v_constraint, '') = '' THEN
                            RAISE EXCEPTION 'violacao_de_constraint' USING ERRCODE = SQLSTATE;
                        END IF;
                        RAISE EXCEPTION 'violacao_de_constraint' USING ERRCODE = SQLSTATE, CONSTRAINT = v_constraint;
                    END;
                ELSE
                    -- Recusa com evento: nenhum valor pessoal, total ou
                    -- numero_versao_dados muda; so a versao de eventos avanca.
                    UPDATE nsi_operacional.registros_coleta
                       SET versao_eventos_atual = versao_eventos_atual + 1
                     WHERE registro_coleta_id = p_registro_coleta_id
                    RETURNING versao_eventos_atual INTO v_versao;
                END IF;

                -- codigo_tecnico da ADR-009 = o proprio registro_coleta_id,
                -- representado em aggregate_id.
                INSERT INTO nsi_operacional.eventos_registro_coleta
                    (evento_id, aggregate_type, aggregate_id, aggregate_version, tipo, occurred_at,
                     executado_por_login, resultado, numero_versao_dados)
                VALUES (gen_random_uuid(), 'registro_coleta', p_registro_coleta_id, v_versao,
                        'correcao_registrada', now(), session_user, v_resultado_correcao, v_numero_versao_dados);

                IF v_numero_versao_dados IS NOT NULL THEN
                    v_resultado := jsonb_build_object(
                        'sucesso', true,
                        'resultado', v_resultado_correcao,
                        'numero_versao_dados', v_numero_versao_dados,
                        'versao_eventos', v_versao);
                ELSE
                    v_resultado := jsonb_build_object(
                        'sucesso', false,
                        'motivo', v_resultado_correcao,
                        'resultado', v_resultado_correcao,
                        'versao_eventos', v_versao);
                END IF;
            END IF;

            UPDATE nsi_operacional.comandos_idempotentes
               SET estado_processamento = 'concluido', resultado = v_resultado, concluido_em = now()
             WHERE comando = 'registrar_correcao' AND aggregate_id = p_registro_coleta_id
               AND chave_idempotencia = p_chave_idempotencia;

            RETURN v_resultado;
        END;
        $fn$
    """)
    op.execute(
        "REVOKE ALL ON FUNCTION nsi_operacional.fn_registrar_correcao("
        "UUID, UUID, TEXT, TEXT, TEXT, BOOLEAN, TEXT[], TEXT, TEXT) FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION nsi_operacional.fn_registrar_correcao("
        "UUID, UUID, TEXT, TEXT, TEXT, BOOLEAN, TEXT[], TEXT, TEXT) TO nsi_aplicacao"
    )

    # =========================================================
    # 5) fn_registrar_tentativa_nao_resolvida - tentativa_correcao_nao_resolvida
    # =========================================================
    op.execute("""
        CREATE FUNCTION nsi_operacional.fn_registrar_tentativa_nao_resolvida(
            p_lote_id                     UUID,
            p_motivo                      TEXT,
            p_codigo_tecnico_normalizado  UUID,
            p_chave_idempotencia          TEXT,
            p_payload_hash                TEXT
        ) RETURNS JSONB
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, nsi_operacional, pg_temp
        AS $fn$
        DECLARE
            v_payload_existente   TEXT;
            v_resultado_existente JSONB;
            v_resultado           JSONB;
            v_evento_id           UUID;
            v_versao              BIGINT;
            v_existe_em_algum     BOOLEAN;
        BEGIN
            -- Chave e hash validados ANTES da reserva (ver fn_registrar_lote).
            IF p_lote_id IS NULL OR p_chave_idempotencia IS NULL OR p_payload_hash IS NULL
               OR char_length(p_chave_idempotencia) NOT BETWEEN 1 AND 200
               OR p_payload_hash !~ '^[0-9a-f]{64}$' THEN
                RAISE EXCEPTION 'entrada_estrutural_invalida' USING ERRCODE = '22000';
            END IF;

            INSERT INTO nsi_operacional.comandos_idempotentes
                (comando, aggregate_id, chave_idempotencia, payload_hash, estado_processamento)
            VALUES ('registrar_tentativa_nao_resolvida', p_lote_id, p_chave_idempotencia, p_payload_hash, 'processando')
            ON CONFLICT (comando, aggregate_id, chave_idempotencia) DO NOTHING
            RETURNING payload_hash INTO v_payload_existente;

            IF NOT FOUND THEN
                SELECT payload_hash, resultado INTO v_payload_existente, v_resultado_existente
                  FROM nsi_operacional.comandos_idempotentes
                 WHERE comando = 'registrar_tentativa_nao_resolvida' AND aggregate_id = p_lote_id
                   AND chave_idempotencia = p_chave_idempotencia;

                IF v_payload_existente IS DISTINCT FROM p_payload_hash THEN
                    RAISE EXCEPTION 'conflito_de_idempotencia' USING ERRCODE = '22023';
                END IF;

                RETURN v_resultado_existente;
            END IF;

            -- Aceita em qualquer status do lote; a linha do lote e bloqueada
            -- porque a versao de eventos do lote avanca.
            PERFORM 1 FROM nsi_operacional.lotes WHERE lote_id = p_lote_id FOR UPDATE;

            IF NOT FOUND THEN
                v_resultado := jsonb_build_object('sucesso', false, 'motivo', 'lote_inexistente');
            ELSIF p_motivo IS NULL OR p_motivo NOT IN (
                      'codigo_ausente', 'codigo_invalido', 'codigo_inexistente', 'registro_de_outra_operacao') THEN
                v_resultado := jsonb_build_object('sucesso', false, 'motivo', 'motivo_invalido');
            -- Coerencia motivo/codigo imposta aqui (a CHECK da tabela nao a
            -- impoe): codigo nulo se e somente se o motivo nao tem codigo
            -- sintaticamente valido (ADR-009, Secao 8).
            ELSIF (p_codigo_tecnico_normalizado IS NULL) <> (p_motivo IN ('codigo_ausente', 'codigo_invalido')) THEN
                v_resultado := jsonb_build_object('sucesso', false, 'motivo', 'motivo_incoerente_com_codigo');
            ELSIF p_codigo_tecnico_normalizado IS NOT NULL
                  AND EXISTS (SELECT 1 FROM nsi_operacional.registros_coleta
                               WHERE registro_coleta_id = p_codigo_tecnico_normalizado AND lote_id = p_lote_id) THEN
                v_resultado := jsonb_build_object('sucesso', false, 'motivo', 'codigo_resolve_neste_lote');
            ELSE
                -- Motivo conferido contra o banco.
                v_existe_em_algum := p_codigo_tecnico_normalizado IS NOT NULL
                    AND EXISTS (SELECT 1 FROM nsi_operacional.registros_coleta
                                 WHERE registro_coleta_id = p_codigo_tecnico_normalizado);

                IF (p_motivo = 'codigo_inexistente' AND v_existe_em_algum)
                   OR (p_motivo = 'registro_de_outra_operacao' AND NOT v_existe_em_algum) THEN
                    v_resultado := jsonb_build_object('sucesso', false, 'motivo', 'motivo_diverge_do_estado');
                ELSE
                    UPDATE nsi_operacional.lotes
                       SET versao_eventos_atual = versao_eventos_atual + 1
                     WHERE lote_id = p_lote_id
                    RETURNING versao_eventos_atual INTO v_versao;

                    v_evento_id := gen_random_uuid();

                    INSERT INTO nsi_operacional.eventos_lote
                        (evento_id, aggregate_type, aggregate_id, aggregate_version, tipo, occurred_at,
                         executado_por_login, motivo, codigo_tecnico_normalizado)
                    VALUES (v_evento_id, 'lote', p_lote_id, v_versao, 'tentativa_correcao_nao_resolvida', now(),
                            session_user, p_motivo, p_codigo_tecnico_normalizado);

                    v_resultado := jsonb_build_object(
                        'sucesso', true,
                        'evento_id', v_evento_id,
                        'versao_eventos', v_versao);
                END IF;
            END IF;

            UPDATE nsi_operacional.comandos_idempotentes
               SET estado_processamento = 'concluido', resultado = v_resultado, concluido_em = now()
             WHERE comando = 'registrar_tentativa_nao_resolvida' AND aggregate_id = p_lote_id
               AND chave_idempotencia = p_chave_idempotencia;

            RETURN v_resultado;
        END;
        $fn$
    """)
    op.execute(
        "REVOKE ALL ON FUNCTION nsi_operacional.fn_registrar_tentativa_nao_resolvida(UUID, TEXT, UUID, TEXT, TEXT) "
        "FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION nsi_operacional.fn_registrar_tentativa_nao_resolvida(UUID, TEXT, UUID, TEXT, TEXT) "
        "TO nsi_aplicacao"
    )

    # Devolve a sessao ao migrator antes de o Alembic gravar o carimbo de
    # versao - mesmo padrao obrigatorio de 0002/0003/0004.
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
    # Remove exatamente as cinco funcoes, na ordem inversa da criacao. Nao
    # toca tabelas, dados, eventos, recibos nem a role nsi_congelamento -
    # retira a capacidade de gravar novos eventos, nunca apaga os ja
    # gravados. Com as funcoes, desaparecem tambem os seus GRANT EXECUTE.
    op.execute("SET LOCAL ROLE nsi_eventos_owner")

    op.execute(
        "DROP FUNCTION nsi_operacional.fn_registrar_tentativa_nao_resolvida(UUID, TEXT, UUID, TEXT, TEXT)"
    )
    op.execute(
        "DROP FUNCTION nsi_operacional.fn_registrar_correcao("
        "UUID, UUID, TEXT, TEXT, TEXT, BOOLEAN, TEXT[], TEXT, TEXT)"
    )
    op.execute("DROP FUNCTION nsi_operacional.fn_confirmar_disparo(UUID, INTEGER, TEXT, TEXT)")
    op.execute("DROP FUNCTION nsi_operacional.fn_registrar_congelamento(UUID)")
    op.execute("DROP FUNCTION nsi_operacional.fn_registrar_lote(UUID, TEXT, JSONB, TEXT, TEXT)")

    # Autoverificacao: nenhuma das cinco funcoes pode restar, em nenhuma
    # assinatura.
    op.execute("""
        DO $$
        DECLARE restantes INTEGER;
        BEGIN
            SELECT count(*) INTO restantes
              FROM pg_catalog.pg_proc p
              JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
             WHERE n.nspname = 'nsi_operacional'
               AND p.proname IN ('fn_registrar_lote', 'fn_registrar_congelamento', 'fn_confirmar_disparo',
                                 'fn_registrar_correcao', 'fn_registrar_tentativa_nao_resolvida');
            IF restantes <> 0 THEN
                RAISE EXCEPTION 'Downgrade de 0005 incompleto: % funcao(oes) da B4.3 ainda existem.', restantes;
            END IF;
        END $$
    """)

    op.execute("RESET ROLE")
    op.execute("""
        DO $$
        BEGIN
            IF current_user <> session_user THEN
                RAISE EXCEPTION 'RESET ROLE falhou - current_user (%) diverge de session_user (%)', current_user, session_user;
            END IF;
        END $$
    """)
