"""claims, eventos_claim, comandos_idempotentes - Sprint B (B3.2, ADR-008)

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-13

Cria as tres tabelas de negocio aprovadas na Parte 1 da B3, a trigger
defensiva de imutabilidade de eventos_claim e os dois indices unicos
parciais - exatamente na ordem fixa aprovada (Parte 1 da B3, Secao 5),
com as correcoes de seguranca aprovadas nesta sessao de planejamento
(REVOKE explicito de DML apos cada CREATE TABLE; RESET ROLE obrigatorio
no caminho de sucesso; autoverificacao de current_user). Nomes de FK,
trigger e indices sao os nomes definitivos ja congelados fora desta
migration - nunca os prefixos fk_/trg_/uq_ usados em rascunhos anteriores
desta sessao de planejamento.

Nao cria nenhuma das seis funcoes SECURITY DEFINER - isso pertence
exclusivamente a migration 0003 (B3.3, "nao fundir 0002 e 0003").

Pre-requisito: scripts/postgres_local/provisionar_b3_roles.sql (B3.1) ja
executado - esta migration falha se a role "nsi_eventos_owner" nao
existir ou se o migrator conectado nao puder executar SET ROLE para ela.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Passo 1 (Parte 1 da B3, Secao 5) - toda a migration roda como o
    # owner das tabelas/funcoes de negocio, nunca como o migrator. No
    # caminho de SUCESSO, o RESET ROLE explicito ao final (ver ultimo
    # passo) e obrigatorio - devolve a sessao ao migrator ANTES de o
    # proprio Alembic gravar o carimbo de versao em alembic_version
    # (tabela de propriedade do migrator). So no caminho de ERRO o
    # rollback da transacao desfaz o SET LOCAL automaticamente - isso
    # nunca substitui o RESET ROLE explicito do caminho de sucesso.
    op.execute("SET LOCAL ROLE nsi_eventos_owner")

    # Passo 2 - claims, sem a FK composta da revisao (adicionada no passo
    # 6, depois que eventos_claim existir).
    op.execute("""
        CREATE TABLE nsi_operacional.claims (
            registro_coleta_id    UUID        NOT NULL PRIMARY KEY,
            claim_id              UUID        NOT NULL UNIQUE,
            token_hash             TEXT        NOT NULL,
            estado                 TEXT        NOT NULL,
            criado_em               TIMESTAMPTZ NOT NULL,
            expira_em               TIMESTAMPTZ NOT NULL,
            ultimo_heartbeat_em     TIMESTAMPTZ,
            versao_atual            BIGINT      NOT NULL DEFAULT 1,
            revisao_atual_id        UUID,
            revisao_decisao         TEXT,
            revisao_registrada_em   TIMESTAMPTZ,

            CONSTRAINT ck_claims_token_hash_sha256
                CHECK (token_hash ~ '^[0-9a-f]{64}$'),
            CONSTRAINT ck_claims_estado
                CHECK (estado IN ('ativo', 'liberado', 'expirado_pendente_revisao')),
            CONSTRAINT ck_claims_versao_atual_positiva
                CHECK (versao_atual > 0),
            CONSTRAINT ck_claims_revisao_decisao
                CHECK (revisao_decisao IS NULL OR revisao_decisao IN ('reatribuir', 'nao_reatribuir')),
            CONSTRAINT ck_claims_expira_apos_criado
                CHECK (expira_em > criado_em),
            CONSTRAINT ck_claims_heartbeat_dentro_da_janela
                CHECK (
                    ultimo_heartbeat_em IS NULL
                    OR (ultimo_heartbeat_em >= criado_em AND ultimo_heartbeat_em < expira_em)
                ),
            CONSTRAINT ck_claims_revisao_completa_ou_vazia
                CHECK (
                    (revisao_atual_id IS NULL AND revisao_decisao IS NULL AND revisao_registrada_em IS NULL)
                    OR (revisao_atual_id IS NOT NULL AND revisao_decisao IS NOT NULL AND revisao_registrada_em IS NOT NULL)
                ),
            CONSTRAINT ck_claims_revisao_somente_em_pendente_revisao
                CHECK (revisao_atual_id IS NULL OR estado = 'expirado_pendente_revisao')
        )
    """)

    # Passo 3 [correcao aprovada] - nenhuma role funcional, nem PUBLIC,
    # recebe DML direto - so as seis funcoes SECURITY DEFINER de B3.3 (via
    # GRANT EXECUTE) poderao inserir eventos ou alterar a projecao.
    op.execute("REVOKE ALL ON TABLE nsi_operacional.claims FROM PUBLIC")
    op.execute(
        "REVOKE ALL ON TABLE nsi_operacional.claims "
        "FROM nsi_aplicacao, nsi_expiracao, nsi_operador_restrito"
    )

    # Passo 4 - eventos_claim, com FK simples para claims e as UNIQUEs
    # normais (a UNIQUE composta que a FK diferivel do passo 6 vai exigir).
    op.execute("""
        CREATE TABLE nsi_operacional.eventos_claim (
            evento_id          UUID        NOT NULL PRIMARY KEY,
            aggregate_type      TEXT        NOT NULL,
            aggregate_id         UUID        NOT NULL REFERENCES nsi_operacional.claims (registro_coleta_id),
            aggregate_version    BIGINT      NOT NULL,
            tipo                 TEXT        NOT NULL,
            claim_id             UUID        NOT NULL,
            occurred_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            executado_por        JSONB       NOT NULL,
            payload              JSONB       NOT NULL DEFAULT '{}'::jsonb,

            CONSTRAINT ck_eventos_claim_aggregate_type
                CHECK (aggregate_type = 'claim'),
            CONSTRAINT ck_eventos_claim_aggregate_version_positiva
                CHECK (aggregate_version > 0),
            CONSTRAINT ck_eventos_claim_tipo
                CHECK (tipo IN (
                    'claim_criado', 'heartbeat_registrado', 'claim_liberado',
                    'claim_expirado', 'revisao_de_abandono_registrada', 'claim_reatribuido'
                )),
            CONSTRAINT uq_eventos_claim_evento_aggregate
                UNIQUE (evento_id, aggregate_id),
            CONSTRAINT uq_eventos_claim_aggregate_versao
                UNIQUE (aggregate_id, aggregate_version)
        )
    """)

    # Passo 5 [correcao aprovada] - REVOKE identico, para eventos_claim.
    op.execute("REVOKE ALL ON TABLE nsi_operacional.eventos_claim FROM PUBLIC")
    op.execute(
        "REVOKE ALL ON TABLE nsi_operacional.eventos_claim "
        "FROM nsi_aplicacao, nsi_expiracao, nsi_operador_restrito"
    )

    # Passo 6 - FK composta diferivel da revisao, agora que eventos_claim
    # existe. DEFERRABLE INITIALLY DEFERRED (Parte 1 da B3, Secao 4).
    # Nome definitivo: claims_revisao_atual_fk (nunca fk_claims_revisao_atual).
    op.execute("""
        ALTER TABLE nsi_operacional.claims
            ADD CONSTRAINT claims_revisao_atual_fk
            FOREIGN KEY (revisao_atual_id, registro_coleta_id)
            REFERENCES nsi_operacional.eventos_claim (evento_id, aggregate_id)
            DEFERRABLE INITIALLY DEFERRED
    """)

    # Passo 7 - comandos_idempotentes. Sem FK para claims (Parte 1 da B3,
    # Secao 7, item 9 - criar_claim e recusas podem ocorrer sem claim
    # existente).
    op.execute("""
        CREATE TABLE nsi_operacional.comandos_idempotentes (
            comando                TEXT        NOT NULL,
            aggregate_id            UUID        NOT NULL,
            chave_idempotencia      TEXT        NOT NULL,
            payload_hash            TEXT        NOT NULL,
            estado_processamento    TEXT        NOT NULL DEFAULT 'processando',
            resultado               JSONB,
            criado_em                TIMESTAMPTZ NOT NULL DEFAULT now(),
            concluido_em             TIMESTAMPTZ,

            CONSTRAINT pk_comandos_idempotentes
                PRIMARY KEY (comando, aggregate_id, chave_idempotencia),
            CONSTRAINT ck_comandos_idempotentes_comando
                CHECK (comando IN (
                    'criar_claim', 'registrar_heartbeat', 'liberar_claim',
                    'registrar_revisao_abandono', 'reatribuir_claim'
                )),
            CONSTRAINT ck_comandos_idempotentes_chave_tamanho
                CHECK (char_length(chave_idempotencia) BETWEEN 1 AND 200),
            CONSTRAINT ck_comandos_idempotentes_payload_hash_sha256
                CHECK (payload_hash ~ '^[0-9a-f]{64}$'),
            CONSTRAINT ck_comandos_idempotentes_estado_processamento
                CHECK (estado_processamento IN ('processando', 'concluido')),
            CONSTRAINT ck_comandos_idempotentes_processando_sem_resultado
                CHECK (
                    (estado_processamento = 'processando' AND resultado IS NULL AND concluido_em IS NULL)
                    OR (estado_processamento = 'concluido' AND resultado IS NOT NULL AND concluido_em IS NOT NULL)
                ),
            CONSTRAINT ck_comandos_idempotentes_concluido_apos_criado
                CHECK (concluido_em IS NULL OR concluido_em >= criado_em)
        )
    """)

    # Passo 8 [correcao aprovada] - REVOKE identico, para comandos_idempotentes.
    op.execute("REVOKE ALL ON TABLE nsi_operacional.comandos_idempotentes FROM PUBLIC")
    op.execute(
        "REVOKE ALL ON TABLE nsi_operacional.comandos_idempotentes "
        "FROM nsi_aplicacao, nsi_expiracao, nsi_operador_restrito"
    )

    # Passo 9 e 10 - os dois indices unicos parciais (Parte 1 da B3, Secao
    # 4). Nomes definitivos: eventos_claim_expirado_unico e
    # eventos_claim_origem_claim_id_unica (nunca o prefixo uq_).
    op.execute("""
        CREATE UNIQUE INDEX eventos_claim_expirado_unico
            ON nsi_operacional.eventos_claim (claim_id)
            WHERE tipo = 'claim_expirado'
    """)
    op.execute("""
        CREATE UNIQUE INDEX eventos_claim_origem_claim_id_unica
            ON nsi_operacional.eventos_claim (claim_id)
            WHERE tipo IN ('claim_criado', 'claim_reatribuido')
    """)

    # Passo 11 - funcao da trigger defensiva. search_path fixo (Parte 1 da
    # B3, Secao 10), qualificacao completa por schema. Nome definitivo
    # (ja literal na Parte 1 da B3, Secao 5, item 7):
    # fn_bloquear_alteracao_eventos_claim.
    op.execute("""
        CREATE FUNCTION nsi_operacional.fn_bloquear_alteracao_eventos_claim()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, nsi_operacional, pg_temp
        AS $trigger$
        BEGIN
            RAISE EXCEPTION
                'nsi_operacional.eventos_claim e um log imutavel - % em % nao e permitido, inclusive para o owner.',
                TG_OP, TG_TABLE_NAME;
        END;
        $trigger$
    """)

    # Passo 12 - trigger BEFORE UPDATE OR DELETE. INSERT legitimo nunca e
    # bloqueado (Parte 1 da B3, Secao 6). Nome definitivo:
    # eventos_claim_bloqueia_alteracao (nunca trg_bloquear_alteracao_eventos_claim).
    op.execute("""
        CREATE TRIGGER eventos_claim_bloqueia_alteracao
            BEFORE UPDATE OR DELETE ON nsi_operacional.eventos_claim
            FOR EACH ROW
            EXECUTE FUNCTION nsi_operacional.fn_bloquear_alteracao_eventos_claim()
    """)

    # Passo 13 - REVOKE ALL da funcao da trigger para PUBLIC (Postgres
    # concede EXECUTE a PUBLIC por padrao em funcoes novas - nunca
    # presumido, sempre explicito).
    op.execute(
        "REVOKE ALL ON FUNCTION nsi_operacional.fn_bloquear_alteracao_eventos_claim() FROM PUBLIC"
    )

    # Passo 14 - devolve a sessao ao migrator antes de retornar ao Alembic
    # (que ainda precisa gravar o carimbo de versao em alembic_version,
    # de propriedade do migrator, nunca do owner). Obrigatorio no caminho
    # de sucesso - ver comentario do passo 1.
    op.execute("RESET ROLE")

    # Passo 15 [correcao aprovada] - autoverificacao: current_user precisa
    # ter voltado a session_user (o migrator) antes do Alembic gravar o
    # carimbo de 0002 - se RESET ROLE tivesse falhado silenciosamente,
    # esta checagem aborta a migration inteira em vez de deixar o carimbo
    # ser gravado sob identidade errada.
    op.execute("""
        DO $$
        BEGIN
            IF current_user <> session_user THEN
                RAISE EXCEPTION 'RESET ROLE falhou - current_user (%) diverge de session_user (%)', current_user, session_user;
            END IF;
        END $$
    """)


def downgrade() -> None:
    # Ordem inversa exata (Parte 1 da B3, Secao 5): trigger, funcao
    # defensiva, comandos_idempotentes, FK composta, eventos_claim,
    # claims. Os dois indices parciais nao precisam de DROP INDEX
    # separado - sao removidos automaticamente junto com eventos_claim.
    op.execute("SET LOCAL ROLE nsi_eventos_owner")

    op.execute(
        "DROP TRIGGER eventos_claim_bloqueia_alteracao ON nsi_operacional.eventos_claim"
    )
    op.execute("DROP FUNCTION nsi_operacional.fn_bloquear_alteracao_eventos_claim()")
    op.execute("DROP TABLE nsi_operacional.comandos_idempotentes")
    op.execute("ALTER TABLE nsi_operacional.claims DROP CONSTRAINT claims_revisao_atual_fk")
    op.execute("DROP TABLE nsi_operacional.eventos_claim")
    op.execute("DROP TABLE nsi_operacional.claims")

    op.execute("RESET ROLE")

    op.execute("""
        DO $$
        BEGIN
            IF current_user <> session_user THEN
                RAISE EXCEPTION 'RESET ROLE falhou - current_user (%) diverge de session_user (%)', current_user, session_user;
            END IF;
        END $$
    """)
