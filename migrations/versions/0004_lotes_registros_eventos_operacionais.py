# -*- coding: utf-8 -*-
"""lotes, registros_coleta, eventos_lote, eventos_registro_coleta - Sprint B (B4.2, ADR-009)

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-16

Cria as quatro tabelas do catalogo fechado de eventos operacionais de
lote, registro de coleta e correcao aprovado pela ADR-009
(docs/architecture/ADR-009-catalogo-eventos-operacionais.md) - modelo
HIBRIDO, nunca event sourcing integral: `lotes`/`registros_coleta` sao a
fonte dos valores pessoais e operacionais ATUAIS; `eventos_lote`/
`eventos_registro_coleta` sao o log imutavel de transicoes e auditoria,
nunca carregando nome/WhatsApp/produto/valores corrigidos brutos
(ADR-009, Principio 2).

Nao cria nenhuma funcao SECURITY DEFINER - isso pertence exclusivamente
a B4.3. Nao referencia nem concede nada a `nsi_congelamento` - essa role
ainda nao existe neste ponto (sua criacao e administrativa, posterior a
esta migration, nunca automatica por ela - ADR-009, Secao 11). O `REVOKE`
desta migration atinge somente roles ja existentes desde a B3.1
(`nsi_aplicacao`, `nsi_operador_restrito`, `nsi_expiracao`).

Maquina de estados definitiva de `lotes.status` (corrigida apos
verificacao direta de ADR-007 SS9.3/SS12 e do comportamento real de
`adapters/storage.py::_recalcular_contagens_e_status` - nenhum lote
nasce terminal; `sem_registros_validos` so existe a partir do
congelamento):

    CRIACAO -> sempre 'aguardando_d8', inclusive com total_valido = 0.
    ANTES DE D+8 -> correcoes alteram registros_coleta e os totais do
        lote, sem mudar status.
    CONGELAMENTO (contagem REAL no instante, nunca a do upload) ->
        total_valido = 0  => 'sem_registros_validos' (terminal)
        total_valido > 0  => 'aguardando_confirmacao_disparo'
    CONFIRMACAO -> 'aguardando_confirmacao_disparo' -> 'disparo_confirmado'.

Depois do congelamento, nenhuma correcao altera dado pessoal, dado de
negocio ou total - uma tentativa tardia so gera o evento
`correcao_registrada` (resultado='recusada_tardia') e avanca
`versao_eventos_atual`, nunca `numero_versao_dados` nem os totais.

`numero_versao_dados` (dado de negocio, so avanca em correcao aplicada)
e `aggregate_version`/`versao_eventos_atual` (posicao no fluxo de
eventos, avanca inclusive em recusa) sao contadores independentes,
nunca derivados um do outro - a versao e obtida por
`UPDATE ... SET versao_eventos_atual = versao_eventos_atual + 1
RETURNING versao_eventos_atual` (mesmo padrao ja validado por
`claims.versao_atual` na B3.3), nunca por MAX(aggregate_version)+1.

Ampliacao aditiva e controlada de `comandos_idempotentes`
(migration 0002): o CHECK de `comando` ganha os cinco comandos novos
da B4, sem remover nenhum dos cinco ja existentes de claims - nenhuma
outra coluna dessa tabela e alterada.

Nenhuma coluna de checksum. Nenhum payload JSONB generico - todo evento
usa colunas relacionais tipadas com CHECK condicional por tipo.

Pre-requisito: scripts/postgres_local/provisionar_b3_roles.sql (B3.1)
ja executado - esta migration falha se a role "nsi_eventos_owner" nao
existir ou se o migrator conectado nao puder executar SET ROLE para ela
(mesmo pre-requisito de 0002/0003).
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Toda a migration roda como o owner das tabelas/funcoes de negocio,
    # nunca como o migrator - mesmo padrao de 0002/0003.
    op.execute("SET LOCAL ROLE nsi_eventos_owner")

    # ------------------------------------------------------------------
    # lotes
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE nsi_operacional.lotes (
            lote_id                         UUID        NOT NULL PRIMARY KEY,
            lote_id_legado                  TEXT,
            recebido_em                     TIMESTAMPTZ NOT NULL,
            total_recebido                  INTEGER     NOT NULL,
            total_valido                    INTEGER     NOT NULL,
            total_invalido                  INTEGER     NOT NULL,
            total_valido_congelado          INTEGER,
            status                          TEXT        NOT NULL,
            horario_conceitual_congelamento TIMESTAMPTZ NOT NULL,
            horario_real_congelamento       TIMESTAMPTZ,
            congelamento_atrasado           BOOLEAN,
            disparo_confirmado_em           TIMESTAMPTZ,
            disparo_confirmado_por_login    TEXT,
            total_confirmado_para_disparo   INTEGER,
            versao_eventos_atual            BIGINT      NOT NULL DEFAULT 1,

            CONSTRAINT ck_lotes_lote_id_legado_formato
                CHECK (lote_id_legado IS NULL OR lote_id_legado ~ '^NSI-[0-9]{8}-[0-9A-F]{6}$'),
            CONSTRAINT ck_lotes_totais
                CHECK (total_recebido >= 0 AND total_valido >= 0 AND total_invalido >= 0
                       AND total_recebido = total_valido + total_invalido),
            CONSTRAINT ck_lotes_horario_conceitual
                CHECK (EXTRACT(EPOCH FROM (horario_conceitual_congelamento - recebido_em)) = 691200),
            CONSTRAINT ck_lotes_congelamento_junto
                CHECK ((horario_real_congelamento IS NULL AND congelamento_atrasado IS NULL)
                       OR (horario_real_congelamento IS NOT NULL AND congelamento_atrasado IS NOT NULL)),
            CONSTRAINT ck_lotes_congelamento_nunca_antecipado
                CHECK (horario_real_congelamento IS NULL
                       OR horario_real_congelamento >= horario_conceitual_congelamento),
            CONSTRAINT ck_lotes_atrasado_correto
                CHECK (horario_real_congelamento IS NULL
                       OR congelamento_atrasado = (horario_real_congelamento > horario_conceitual_congelamento)),
            CONSTRAINT ck_lotes_versao_eventos_positiva
                CHECK (versao_eventos_atual > 0),
            CONSTRAINT ck_lotes_status
                CHECK (status IN ('aguardando_d8', 'sem_registros_validos',
                                   'aguardando_confirmacao_disparo', 'disparo_confirmado')),
            CONSTRAINT ck_lotes_status_coerente
                CHECK (
                     (status = 'aguardando_d8'
                        AND total_valido >= 0
                        AND total_valido_congelado IS NULL
                        AND horario_real_congelamento IS NULL AND congelamento_atrasado IS NULL
                        AND disparo_confirmado_em IS NULL AND disparo_confirmado_por_login IS NULL
                        AND total_confirmado_para_disparo IS NULL)
                  OR (status = 'sem_registros_validos'
                        AND total_valido = 0
                        AND total_valido_congelado = 0
                        AND horario_real_congelamento IS NOT NULL AND congelamento_atrasado IS NOT NULL
                        AND disparo_confirmado_em IS NULL AND disparo_confirmado_por_login IS NULL
                        AND total_confirmado_para_disparo IS NULL)
                  OR (status = 'aguardando_confirmacao_disparo'
                        AND total_valido > 0
                        AND total_valido_congelado IS NOT NULL AND total_valido_congelado >= 0
                        AND total_valido_congelado = total_valido
                        AND horario_real_congelamento IS NOT NULL AND congelamento_atrasado IS NOT NULL
                        AND disparo_confirmado_em IS NULL AND disparo_confirmado_por_login IS NULL
                        AND total_confirmado_para_disparo IS NULL)
                  OR (status = 'disparo_confirmado'
                        AND total_valido > 0
                        AND total_valido_congelado IS NOT NULL AND total_valido_congelado >= 0
                        AND total_valido_congelado = total_valido
                        AND horario_real_congelamento IS NOT NULL AND congelamento_atrasado IS NOT NULL
                        AND disparo_confirmado_em IS NOT NULL AND disparo_confirmado_por_login IS NOT NULL
                        AND total_confirmado_para_disparo IS NOT NULL AND total_confirmado_para_disparo >= 0
                        AND total_confirmado_para_disparo = total_valido_congelado)
                )
        )
    """)

    op.execute(
        "CREATE UNIQUE INDEX lotes_lote_id_legado_unico ON nsi_operacional.lotes (lote_id_legado) "
        "WHERE lote_id_legado IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX lotes_aguardando_congelamento ON nsi_operacional.lotes (horario_conceitual_congelamento) "
        "WHERE status = 'aguardando_d8'"
    )

    op.execute("REVOKE ALL ON TABLE nsi_operacional.lotes FROM PUBLIC")
    op.execute(
        "REVOKE ALL ON TABLE nsi_operacional.lotes FROM nsi_aplicacao, nsi_expiracao, nsi_operador_restrito"
    )

    # ------------------------------------------------------------------
    # registros_coleta
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE nsi_operacional.registros_coleta (
            registro_coleta_id  UUID    NOT NULL PRIMARY KEY,
            lote_id             UUID    NOT NULL REFERENCES nsi_operacional.lotes (lote_id),
            nome                TEXT,
            produto             TEXT,
            whatsapp            TEXT,
            valido              BOOLEAN NOT NULL,
            motivos_invalidez   TEXT[],
            numero_versao_dados BIGINT  NOT NULL DEFAULT 1,
            versao_eventos_atual BIGINT NOT NULL DEFAULT 0,

            CONSTRAINT ck_registros_coleta_nome_nao_vazio
                CHECK (nome IS NULL OR btrim(nome) <> ''),
            CONSTRAINT ck_registros_coleta_produto_nao_vazio
                CHECK (produto IS NULL OR btrim(produto) <> ''),
            CONSTRAINT ck_registros_coleta_whatsapp_nao_vazio
                CHECK (whatsapp IS NULL OR btrim(whatsapp) <> ''),
            CONSTRAINT ck_registros_coleta_versao_dados_positiva
                CHECK (numero_versao_dados > 0),
            CONSTRAINT ck_registros_coleta_versao_eventos_nao_negativa
                CHECK (versao_eventos_atual >= 0),
            CONSTRAINT ck_registros_coleta_motivos_vocabulario
                CHECK (
                    motivos_invalidez IS NULL
                    OR motivos_invalidez <@ ARRAY[
                         'nome_ausente', 'produto_ausente', 'whatsapp_ausente',
                         'whatsapp_caracteres_invalidos', 'whatsapp_comprimento_invalido',
                         'whatsapp_codigo_pais_invalido', 'whatsapp_ddd_invalido'
                       ]::TEXT[]
                ),
            CONSTRAINT ck_registros_coleta_motivos_sem_duplicata
                CHECK (
                    motivos_invalidez IS NULL
                    OR (
                        cardinality(array_positions(motivos_invalidez, 'nome_ausente')) <= 1
                        AND cardinality(array_positions(motivos_invalidez, 'produto_ausente')) <= 1
                        AND cardinality(array_positions(motivos_invalidez, 'whatsapp_ausente')) <= 1
                        AND cardinality(array_positions(motivos_invalidez, 'whatsapp_caracteres_invalidos')) <= 1
                        AND cardinality(array_positions(motivos_invalidez, 'whatsapp_comprimento_invalido')) <= 1
                        AND cardinality(array_positions(motivos_invalidez, 'whatsapp_codigo_pais_invalido')) <= 1
                        AND cardinality(array_positions(motivos_invalidez, 'whatsapp_ddd_invalido')) <= 1
                    )
                ),
            CONSTRAINT ck_registros_coleta_coerencia
                CHECK (
                     (valido = TRUE
                        AND nome IS NOT NULL AND produto IS NOT NULL
                        AND whatsapp IS NOT NULL AND whatsapp ~ '^55[0-9]{10,11}$'
                        AND motivos_invalidez IS NULL)
                  OR (valido = FALSE
                        AND motivos_invalidez IS NOT NULL AND cardinality(motivos_invalidez) > 0
                        AND (nome IS NULL)     = ('nome_ausente'     = ANY(motivos_invalidez))
                        AND (produto IS NULL)  = ('produto_ausente'  = ANY(motivos_invalidez))
                        AND (whatsapp IS NULL) = ('whatsapp_ausente' = ANY(motivos_invalidez)))
                )
        )
    """)

    op.execute("CREATE INDEX registros_coleta_lote_id ON nsi_operacional.registros_coleta (lote_id)")
    op.execute(
        "CREATE INDEX registros_coleta_invalidos_por_lote ON nsi_operacional.registros_coleta (lote_id) "
        "WHERE valido = false"
    )

    op.execute("REVOKE ALL ON TABLE nsi_operacional.registros_coleta FROM PUBLIC")
    op.execute(
        "REVOKE ALL ON TABLE nsi_operacional.registros_coleta "
        "FROM nsi_aplicacao, nsi_expiracao, nsi_operador_restrito"
    )

    # ------------------------------------------------------------------
    # eventos_lote
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE nsi_operacional.eventos_lote (
            evento_id             UUID        NOT NULL PRIMARY KEY,
            aggregate_type        TEXT        NOT NULL,
            aggregate_id          UUID        NOT NULL REFERENCES nsi_operacional.lotes (lote_id),
            aggregate_version     BIGINT      NOT NULL,
            tipo                  TEXT        NOT NULL,
            occurred_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
            executado_por_login   TEXT        NOT NULL,
            recebido_em           TIMESTAMPTZ,
            total_recebido        INTEGER,
            total_valido          INTEGER,
            total_invalido        INTEGER,
            horario_conceitual    TIMESTAMPTZ,
            horario_real_execucao TIMESTAMPTZ,
            atrasado              BOOLEAN,
            operador_humano_id    UUID,
            total_confirmado      INTEGER,
            motivo                TEXT,
            codigo_tecnico_normalizado UUID,

            CONSTRAINT ck_eventos_lote_aggregate_type
                CHECK (aggregate_type = 'lote'),
            CONSTRAINT ck_eventos_lote_aggregate_version_positiva
                CHECK (aggregate_version > 0),
            CONSTRAINT ck_eventos_lote_tipo
                CHECK (tipo IN ('lote_criado', 'lote_congelado_d8', 'disparo_confirmado',
                                 'tentativa_correcao_nao_resolvida')),
            CONSTRAINT ck_eventos_lote_motivo
                CHECK (motivo IS NULL OR motivo IN (
                    'codigo_ausente', 'codigo_invalido', 'codigo_inexistente', 'registro_de_outra_operacao'
                )),
            CONSTRAINT ck_eventos_lote_operador_humano
                CHECK (operador_humano_id IS NULL OR tipo = 'disparo_confirmado'),
            CONSTRAINT ck_eventos_lote_congelamento_nunca_antecipado
                CHECK (tipo <> 'lote_congelado_d8' OR horario_real_execucao >= horario_conceitual),
            CONSTRAINT ck_eventos_lote_atrasado_correto
                CHECK (tipo <> 'lote_congelado_d8' OR atrasado = (horario_real_execucao > horario_conceitual)),
            CONSTRAINT ck_eventos_lote_payload_por_tipo
                CHECK (
                     (tipo = 'lote_criado'
                        AND recebido_em IS NOT NULL AND total_recebido IS NOT NULL
                        AND total_valido IS NOT NULL AND total_invalido IS NOT NULL
                        AND horario_conceitual IS NULL AND horario_real_execucao IS NULL AND atrasado IS NULL
                        AND total_confirmado IS NULL AND motivo IS NULL AND codigo_tecnico_normalizado IS NULL)
                  OR (tipo = 'lote_congelado_d8'
                        AND horario_conceitual IS NOT NULL AND horario_real_execucao IS NOT NULL
                        AND atrasado IS NOT NULL
                        AND recebido_em IS NULL AND total_recebido IS NULL
                        AND total_valido IS NULL AND total_invalido IS NULL
                        AND total_confirmado IS NULL AND motivo IS NULL AND codigo_tecnico_normalizado IS NULL)
                  OR (tipo = 'disparo_confirmado'
                        AND total_confirmado IS NOT NULL
                        AND recebido_em IS NULL AND total_recebido IS NULL
                        AND total_valido IS NULL AND total_invalido IS NULL
                        AND horario_conceitual IS NULL AND horario_real_execucao IS NULL AND atrasado IS NULL
                        AND motivo IS NULL AND codigo_tecnico_normalizado IS NULL)
                  OR (tipo = 'tentativa_correcao_nao_resolvida'
                        AND motivo IS NOT NULL
                        AND recebido_em IS NULL AND total_recebido IS NULL
                        AND total_valido IS NULL AND total_invalido IS NULL
                        AND horario_conceitual IS NULL AND horario_real_execucao IS NULL AND atrasado IS NULL
                        AND operador_humano_id IS NULL AND total_confirmado IS NULL)
                ),
            CONSTRAINT uq_eventos_lote_aggregate_versao
                UNIQUE (aggregate_id, aggregate_version)
        )
    """)

    op.execute(
        "CREATE UNIQUE INDEX eventos_lote_criado_unico ON nsi_operacional.eventos_lote (aggregate_id) "
        "WHERE tipo = 'lote_criado'"
    )
    op.execute(
        "CREATE UNIQUE INDEX eventos_lote_congelado_unico ON nsi_operacional.eventos_lote (aggregate_id) "
        "WHERE tipo = 'lote_congelado_d8'"
    )
    op.execute(
        "CREATE UNIQUE INDEX eventos_lote_disparo_confirmado_unico ON nsi_operacional.eventos_lote (aggregate_id) "
        "WHERE tipo = 'disparo_confirmado'"
    )

    op.execute("REVOKE ALL ON TABLE nsi_operacional.eventos_lote FROM PUBLIC")
    op.execute(
        "REVOKE ALL ON TABLE nsi_operacional.eventos_lote FROM nsi_aplicacao, nsi_expiracao, nsi_operador_restrito"
    )

    op.execute("""
        CREATE FUNCTION nsi_operacional.fn_bloquear_alteracao_eventos_lote()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, nsi_operacional, pg_temp
        AS $trigger$
        BEGIN
            RAISE EXCEPTION
                'nsi_operacional.eventos_lote e um log imutavel - % em % nao e permitido, inclusive para o owner.',
                TG_OP, TG_TABLE_NAME;
        END;
        $trigger$
    """)
    op.execute("""
        CREATE TRIGGER eventos_lote_bloqueia_alteracao
            BEFORE UPDATE OR DELETE ON nsi_operacional.eventos_lote
            FOR EACH ROW
            EXECUTE FUNCTION nsi_operacional.fn_bloquear_alteracao_eventos_lote()
    """)
    op.execute(
        "REVOKE ALL ON FUNCTION nsi_operacional.fn_bloquear_alteracao_eventos_lote() FROM PUBLIC"
    )

    # ------------------------------------------------------------------
    # eventos_registro_coleta
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE nsi_operacional.eventos_registro_coleta (
            evento_id           UUID        NOT NULL PRIMARY KEY,
            aggregate_type      TEXT        NOT NULL,
            aggregate_id        UUID        NOT NULL REFERENCES nsi_operacional.registros_coleta (registro_coleta_id),
            aggregate_version   BIGINT      NOT NULL,
            tipo                TEXT        NOT NULL,
            occurred_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            executado_por_login TEXT        NOT NULL,
            resultado           TEXT        NOT NULL,
            numero_versao_dados BIGINT,

            CONSTRAINT ck_eventos_registro_coleta_aggregate_type
                CHECK (aggregate_type = 'registro_coleta'),
            CONSTRAINT ck_eventos_registro_coleta_aggregate_version_positiva
                CHECK (aggregate_version > 0),
            CONSTRAINT ck_eventos_registro_coleta_tipo
                CHECK (tipo = 'correcao_registrada'),
            CONSTRAINT ck_eventos_registro_coleta_resultado
                CHECK (resultado IN ('aplicada_valida', 'aplicada_ainda_invalida',
                                      'recusada_ja_valido', 'recusada_tardia')),
            CONSTRAINT ck_eventos_registro_coleta_versao_dados_por_resultado
                CHECK (
                     (resultado IN ('aplicada_valida', 'aplicada_ainda_invalida')
                        AND numero_versao_dados IS NOT NULL AND numero_versao_dados > 0)
                  OR (resultado IN ('recusada_ja_valido', 'recusada_tardia')
                        AND numero_versao_dados IS NULL)
                ),
            CONSTRAINT uq_eventos_registro_coleta_aggregate_versao
                UNIQUE (aggregate_id, aggregate_version)
        )
    """)

    op.execute("REVOKE ALL ON TABLE nsi_operacional.eventos_registro_coleta FROM PUBLIC")
    op.execute(
        "REVOKE ALL ON TABLE nsi_operacional.eventos_registro_coleta "
        "FROM nsi_aplicacao, nsi_expiracao, nsi_operador_restrito"
    )

    op.execute("""
        CREATE FUNCTION nsi_operacional.fn_bloquear_alteracao_eventos_registro_coleta()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, nsi_operacional, pg_temp
        AS $trigger$
        BEGIN
            RAISE EXCEPTION
                'nsi_operacional.eventos_registro_coleta e um log imutavel - % em % nao e permitido, inclusive para o owner.',
                TG_OP, TG_TABLE_NAME;
        END;
        $trigger$
    """)
    op.execute("""
        CREATE TRIGGER eventos_registro_coleta_bloqueia_alteracao
            BEFORE UPDATE OR DELETE ON nsi_operacional.eventos_registro_coleta
            FOR EACH ROW
            EXECUTE FUNCTION nsi_operacional.fn_bloquear_alteracao_eventos_registro_coleta()
    """)
    op.execute(
        "REVOKE ALL ON FUNCTION nsi_operacional.fn_bloquear_alteracao_eventos_registro_coleta() FROM PUBLIC"
    )

    # ------------------------------------------------------------------
    # comandos_idempotentes - ampliacao aditiva e controlada (0002)
    # ------------------------------------------------------------------
    op.execute(
        "ALTER TABLE nsi_operacional.comandos_idempotentes DROP CONSTRAINT ck_comandos_idempotentes_comando"
    )
    op.execute("""
        ALTER TABLE nsi_operacional.comandos_idempotentes
            ADD CONSTRAINT ck_comandos_idempotentes_comando
            CHECK (comando IN (
                'criar_claim', 'registrar_heartbeat', 'liberar_claim',
                'registrar_revisao_abandono', 'reatribuir_claim',
                'registrar_lote', 'registrar_congelamento', 'confirmar_disparo',
                'registrar_correcao', 'registrar_tentativa_nao_resolvida'
            ))
    """)

    # Devolve a sessao ao migrator antes de o Alembic gravar o carimbo de
    # versao - mesmo padrao obrigatorio de 0002/0003.
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
    # Ordem inversa exata da criacao.
    op.execute("SET LOCAL ROLE nsi_eventos_owner")

    # Preflight OBRIGATORIO - aborta a transacao inteira, sem remover
    # nenhum objeto, se existir qualquer recibo de comando da B4 em
    # comandos_idempotentes. Nunca apaga recibo algum silenciosamente.
    op.execute("""
        DO $$
        DECLARE
            residual BIGINT;
        BEGIN
            SELECT COUNT(*) INTO residual
              FROM nsi_operacional.comandos_idempotentes
             WHERE comando IN (
                 'registrar_lote', 'registrar_congelamento', 'confirmar_disparo',
                 'registrar_correcao', 'registrar_tentativa_nao_resolvida'
             );
            IF residual > 0 THEN
                RAISE EXCEPTION
                    'Downgrade de 0004 abortado: % recibo(s) de comandos da B4 existem em comandos_idempotentes - remova-os explicitamente antes de reverter.',
                    residual;
            END IF;
        END $$
    """)

    # Reverso do ALTER (ultimo passo do upgrade).
    op.execute(
        "ALTER TABLE nsi_operacional.comandos_idempotentes DROP CONSTRAINT ck_comandos_idempotentes_comando"
    )
    op.execute("""
        ALTER TABLE nsi_operacional.comandos_idempotentes
            ADD CONSTRAINT ck_comandos_idempotentes_comando
            CHECK (comando IN (
                'criar_claim', 'registrar_heartbeat', 'liberar_claim',
                'registrar_revisao_abandono', 'reatribuir_claim'
            ))
    """)

    op.execute(
        "DROP TRIGGER eventos_registro_coleta_bloqueia_alteracao ON nsi_operacional.eventos_registro_coleta"
    )
    op.execute("DROP FUNCTION nsi_operacional.fn_bloquear_alteracao_eventos_registro_coleta()")
    op.execute("DROP TABLE nsi_operacional.eventos_registro_coleta")

    op.execute("DROP TRIGGER eventos_lote_bloqueia_alteracao ON nsi_operacional.eventos_lote")
    op.execute("DROP FUNCTION nsi_operacional.fn_bloquear_alteracao_eventos_lote()")
    op.execute("DROP TABLE nsi_operacional.eventos_lote")

    op.execute("DROP TABLE nsi_operacional.registros_coleta")
    op.execute("DROP TABLE nsi_operacional.lotes")

    op.execute("RESET ROLE")
    op.execute("""
        DO $$
        BEGIN
            IF current_user <> session_user THEN
                RAISE EXCEPTION 'RESET ROLE falhou - current_user (%) diverge de session_user (%)', current_user, session_user;
            END IF;
        END $$
    """)
