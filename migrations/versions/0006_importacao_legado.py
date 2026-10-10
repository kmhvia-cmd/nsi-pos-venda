# -*- coding: utf-8 -*-
"""importacao do legado operacional - Sprint B (B5.4, ADR-010)

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-10

Implementa a Especificacao Tecnica da Sprint B (Secao 18, B5.2), subordinada
a ADR-010 e a ADR-009 (Secao 22). Cria EXATAMENTE:

  Registro tecnico de importacao (item 16) - sem valor pessoal, imutavel
  inclusive para o owner (trigger BEFORE UPDATE OR DELETE):
    - importacoes_legado
    - importacoes_legado_arquivos
    - importacoes_legado_conclusoes
    - fn_bloquear_alteracao_importacoes_legado
    - fn_bloquear_alteracao_importacoes_legado_arquivos
    - fn_bloquear_alteracao_importacoes_legado_conclusoes

  Snapshot legado (item 8) - contem dado pessoal e, por isso, NAO tem
  trigger de imutabilidade (ADR-010, Secao 9.3); a integridade e
  verificavel pelo SHA-256 guardado no registro tecnico imutavel:
    - lotes_legado
    - registros_legado (com indice em registro_coleta_id)

  Quatro funcoes SECURITY DEFINER de importacao (item 5.1):
    1. fn_iniciar_importacao_legado
    2. fn_importar_lote_legado
    3. fn_concluir_importacao_legado
    4. fn_verificar_paridade_legado

  Nova definicao de fn_criar_claim (item 10.5), com a mesma assinatura,
  owner, SECURITY DEFINER, search_path, matriz de EXECUTE e envelope de
  idempotencia da 0003. Unica mudanca: a recusa
  'registro_legado_nao_promovido'.

Nenhum evento novo, nenhuma escrita em eventos_lote, em
eventos_registro_coleta ou em comandos_idempotentes pelas funcoes de
importacao (ADR-010, Principio 1; item 10.4): elas nao referenciam
nenhuma dessas tres tabelas para escrita - a paridade apenas LE os dois
logs de evento.

Regras comuns as quatro funcoes: LANGUAGE plpgsql, SECURITY DEFINER, dona
nsi_eventos_owner, search_path fixo (pg_catalog, nsi_operacional, pg_temp),
toda referencia interna qualificada por schema, retorno JSONB, identidade
tecnica session_user - nunca current_user. Nenhum retorno contem valor
pessoal.

Erros (item 15) - mensagens fixas, sem DETAIL, sem valor pessoal, hash,
chave ou documento:
  - 'conflito_de_idempotencia', SQLSTATE 22023;
  - 'entrada_estrutural_invalida', SQLSTATE 22000;
  - 'violacao_de_constraint', SQLSTATE nativo da classe 23, com o NOME da
    constraint (fora do bloco de promocao);
  - 'invariante_violada', SQLSTATE proprio NS001.
Recusa de lote e nao promocao NUNCA sao excecao: sao retornos
estruturados, gravados no registro tecnico.

Ordem de avaliacao de fn_importar_lote_legado: a do item 5.1. Os passos 9
a 11 (preservacao, criterios e promocao) sao gravados na ordem
criterios -> promocao -> snapshot, na mesma transacao: lotes_legado
referencia lotes por chave estrangeira e tem CHECK de coerencia entre
destino, motivo e lote promovido, de modo que a linha do snapshot so pode
ser gravada com o destino ja conhecido. O resultado e identico ao da
ordem logica do item 5.1 - a preservacao nunca depende da promocao, e uma
promocao desfeita ('projecao_incompativel') deixa o lote preservado.

Concorrencia (itens 10.5 e 12):
  - fn_importar_lote_legado bloqueia a linha da execucao FOR SHARE;
    fn_concluir_importacao_legado, FOR UPDATE - a conclusao espera as
    importacoes em andamento, e nenhuma importacao grava depois de a
    conclusao ter contado;
  - antes da verificacao de claim pre-existente, fn_importar_lote_legado
    bloqueia claims em SHARE ROW EXCLUSIVE ate o fim da transacao. O modo
    conflita com a gravacao de claims e consigo mesmo: importacoes de lote
    ficam serializadas entre si a partir desse ponto, e a reimportacao
    (passo 7) e reavaliada depois do bloqueio;
  - em fn_criar_claim, a consulta a registros_legado esta no MESMO comando
    SQL que grava o claim: o comando so obtem o seu snapshot depois de
    adquirir o bloqueio de claims, e portanto depois do commit de uma
    importacao concorrente.
Nivel de isolamento exigido: READ COMMITTED, o mesmo contrato da 0005.

Matriz de EXECUTE (item 4), com REVOKE explicito de PUBLIC:
  as quatro funcoes de importacao -> nsi_importacao, somente;
  fn_criar_claim                  -> nsi_aplicacao (inalterada).
Nenhuma role funcional - inclusive nsi_importacao - recebe leitura ou DML
em nenhuma das cinco tabelas novas.

Downgrade: aborta, sem remover nada, se existir linha de
importacoes_legado_arquivos com destino 'promovido' (o lote promovido
perderia a prova de origem exigida pela ADR-009, Secao 22). Sem lote
promovido, remove as funcoes e tabelas desta migration e restaura
fn_criar_claim com os comandos lidos do proprio arquivo da 0003 - nunca
copiados a mao.

Pre-requisitos: 0005 aplicada; role nsi_importacao provisionada
administrativamente (provisionar_b5_role_importacao.sql). Esta migration
nunca cria, altera ou remove a role - se ela nao existir, falha antes de
criar qualquer objeto.
"""
import ast
from pathlib import Path
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ARQUIVO_0003 = "0003_seis_funcoes_claim.py"
_ASSINATURA_FN_CRIAR_CLAIM = "nsi_operacional.fn_criar_claim(UUID, TEXT, TEXT, TEXT)"


def _comandos_fn_criar_claim_da_0003() -> list:
    """Le, do proprio arquivo da 0003, os tres comandos que definem
    fn_criar_claim (CREATE FUNCTION, REVOKE e GRANT), na ordem em que
    aparecem. O arquivo e apenas analisado (ast) - nunca importado nem
    executado. Falha se a 0003 nao tiver exatamente esses tres comandos."""
    fonte = Path(__file__).with_name(_ARQUIVO_0003).read_text(encoding="utf-8")
    upgrade_0003 = next(
        no for no in ast.parse(fonte).body
        if isinstance(no, ast.FunctionDef) and no.name == "upgrade"
    )

    comandos = []
    for no in upgrade_0003.body:
        if not (isinstance(no, ast.Expr) and isinstance(no.value, ast.Call) and len(no.value.args) == 1):
            continue
        argumento = no.value.args[0]
        if not (isinstance(argumento, ast.Constant) and isinstance(argumento.value, str)):
            continue
        sql = argumento.value
        if "CREATE FUNCTION nsi_operacional.fn_criar_claim(" in sql or _ASSINATURA_FN_CRIAR_CLAIM in sql:
            comandos.append(sql)

    prefixos = [comando.strip().split("(")[0].split(" ON ")[0] for comando in comandos]
    if prefixos != ["CREATE FUNCTION nsi_operacional.fn_criar_claim", "REVOKE ALL", "GRANT EXECUTE"]:
        raise RuntimeError(
            "A definicao de fn_criar_claim nao foi localizada no arquivo da 0003 na forma esperada "
            "(CREATE FUNCTION, REVOKE ALL, GRANT EXECUTE) - downgrade da 0006 abortado."
        )
    return comandos


def upgrade() -> None:
    # Pre-requisito administrativo (ADR-010, Secao 16.5; B5.2, item 4): a
    # role nsi_importacao e criada exclusivamente pelo script de
    # provisionamento - nunca por esta migration. Sem ela, falha aqui,
    # antes de criar qualquer objeto.
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'nsi_importacao') THEN
                RAISE EXCEPTION 'Role nsi_importacao nao existe - provisione-a administrativamente antes desta migration (ADR-010, Secao 16).';
            END IF;
        END $$
    """)

    # Mesmo padrao de 0002 a 0005: toda a migration roda como o owner das
    # tabelas e funcoes de negocio, nunca como o migrator.
    op.execute("SET LOCAL ROLE nsi_eventos_owner")

    # ------------------------------------------------------------------
    # Registro tecnico de importacao (item 16)
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE nsi_operacional.importacoes_legado (
            importacao_id       UUID        NOT NULL PRIMARY KEY,
            iniciada_em         TIMESTAMPTZ NOT NULL DEFAULT now(),
            executado_por_login TEXT        NOT NULL,
            fuso_declarado      TEXT,

            CONSTRAINT ck_importacoes_legado_fuso_formato
                CHECK (fuso_declarado IS NULL
                       OR fuso_declarado = 'UTC'
                       OR (fuso_declarado ~ '^[A-Za-z0-9_+-]+(/[A-Za-z0-9_+-]+)+$'
                           AND fuso_declarado !~ '^(Etc|posix|right)/'))
        )
    """)

    op.execute("""
        CREATE TABLE nsi_operacional.importacoes_legado_arquivos (
            importacao_id      UUID        NOT NULL REFERENCES nsi_operacional.importacoes_legado (importacao_id),
            caminho_relativo   TEXT        NOT NULL,
            documento_sha256   TEXT        NOT NULL,
            lote_id_legado     TEXT,
            geracao            TEXT,
            destino            TEXT        NOT NULL,
            motivo             TEXT,
            constraint_violada TEXT,
            lote_id_promovido  UUID,
            registrado_em      TIMESTAMPTZ NOT NULL DEFAULT now(),

            CONSTRAINT uq_importacoes_legado_arquivos_caminho
                UNIQUE (importacao_id, caminho_relativo),
            CONSTRAINT ck_importacoes_legado_arquivos_caminho
                CHECK (caminho_relativo ~ '^lotes/[^/]+/lote[.]json$'),
            CONSTRAINT ck_importacoes_legado_arquivos_sha256
                CHECK (documento_sha256 ~ '^[0-9a-f]{64}$'),
            CONSTRAINT ck_importacoes_legado_arquivos_geracao
                CHECK (geracao IS NULL
                       OR geracao IN ('anterior_a1', 'a1', 'a2', 'a3', 'formato_desconhecido')),
            CONSTRAINT ck_importacoes_legado_arquivos_destino
                CHECK (destino IN ('preservado', 'promovido', 'recusado', 'ja_importado')),
            CONSTRAINT ck_importacoes_legado_arquivos_constraint_violada
                CHECK (constraint_violada IS NULL OR motivo = 'projecao_incompativel'),
            CONSTRAINT ck_importacoes_legado_arquivos_coerencia
                CHECK (
                     (destino = 'promovido'
                        AND motivo IS NULL
                        AND lote_id_promovido IS NOT NULL AND lote_id_legado IS NOT NULL
                        AND geracao IS NOT NULL AND geracao IN ('a2', 'a3'))
                  OR (destino = 'preservado'
                        AND motivo IS NOT NULL AND motivo IN (
                            'geracao_nao_promovivel', 'fuso_nao_declarado', 'evidencia_de_disparo',
                            'lote_id_legado_invalido', 'lote_id_legado_em_uso', 'm0_invalido',
                            'm0_inexistente_ou_ambiguo', 'identidade_repetida', 'colisao_de_identidade',
                            'totais_incoerentes', 'historico_incoerente', 'projecao_incompativel')
                        AND lote_id_promovido IS NULL AND lote_id_legado IS NOT NULL
                        AND geracao IS NOT NULL AND geracao IN ('anterior_a1', 'a1', 'a2', 'a3'))
                  OR (destino = 'recusado'
                        AND motivo IS NOT NULL AND motivo IN (
                            'documento_ilegivel', 'identidade_divergente', 'formato_desconhecido',
                            'conflito_de_reimportacao', 'claim_preexistente')
                        AND lote_id_promovido IS NULL)
                  OR (destino = 'ja_importado'
                        AND motivo IS NULL
                        AND lote_id_legado IS NOT NULL
                        AND geracao IS NOT NULL AND geracao IN ('anterior_a1', 'a1', 'a2', 'a3'))
                )
        )
    """)

    op.execute("""
        CREATE TABLE nsi_operacional.importacoes_legado_conclusoes (
            importacao_id      UUID        NOT NULL PRIMARY KEY
                                           REFERENCES nsi_operacional.importacoes_legado (importacao_id),
            concluida_em       TIMESTAMPTZ NOT NULL DEFAULT now(),
            manifesto_canonico BYTEA       NOT NULL,
            manifesto_sha256   TEXT        NOT NULL,
            total_arquivos     INTEGER     NOT NULL,

            CONSTRAINT ck_importacoes_legado_conclusoes_sha256
                CHECK (manifesto_sha256 ~ '^[0-9a-f]{64}$'),
            CONSTRAINT ck_importacoes_legado_conclusoes_sha256_recalculado
                CHECK (manifesto_sha256 = encode(sha256(manifesto_canonico), 'hex')),
            CONSTRAINT ck_importacoes_legado_conclusoes_total
                CHECK (total_arquivos >= 0)
        )
    """)

    for tabela in ("importacoes_legado", "importacoes_legado_arquivos", "importacoes_legado_conclusoes"):
        op.execute(f"""
            CREATE FUNCTION nsi_operacional.fn_bloquear_alteracao_{tabela}()
            RETURNS trigger
            LANGUAGE plpgsql
            SET search_path = pg_catalog, nsi_operacional, pg_temp
            AS $trigger$
            BEGIN
                RAISE EXCEPTION
                    'nsi_operacional.{tabela} e um registro tecnico imutavel - % em % nao e permitido, inclusive para o owner.',
                    TG_OP, TG_TABLE_NAME;
            END;
            $trigger$
        """)
        op.execute(f"""
            CREATE TRIGGER {tabela}_bloqueia_alteracao
                BEFORE UPDATE OR DELETE ON nsi_operacional.{tabela}
                FOR EACH ROW
                EXECUTE FUNCTION nsi_operacional.fn_bloquear_alteracao_{tabela}()
        """)
        op.execute(f"REVOKE ALL ON FUNCTION nsi_operacional.fn_bloquear_alteracao_{tabela}() FROM PUBLIC")

    # ------------------------------------------------------------------
    # Snapshot legado (item 8) - sem trigger de imutabilidade (ADR-010,
    # Secao 9.3)
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE nsi_operacional.lotes_legado (
            snapshot_lote_id    UUID  NOT NULL PRIMARY KEY,
            importacao_id       UUID  NOT NULL REFERENCES nsi_operacional.importacoes_legado (importacao_id),
            lote_id_legado      TEXT  NOT NULL,
            caminho_relativo    TEXT  NOT NULL,
            documento_bruto     BYTEA NOT NULL,
            documento_sha256    TEXT  NOT NULL,
            geracao             TEXT  NOT NULL,
            status_legado       JSONB NOT NULL,
            criado_em_bruto     TEXT  NOT NULL,
            destino             TEXT  NOT NULL,
            motivo_nao_promocao TEXT,
            lote_id_promovido   UUID  REFERENCES nsi_operacional.lotes (lote_id),

            CONSTRAINT uq_lotes_legado_lote_id_legado
                UNIQUE (lote_id_legado),
            CONSTRAINT ck_lotes_legado_sha256
                CHECK (documento_sha256 ~ '^[0-9a-f]{64}$'),
            CONSTRAINT ck_lotes_legado_geracao
                CHECK (geracao IN ('anterior_a1', 'a1', 'a2', 'a3')),
            CONSTRAINT ck_lotes_legado_status_legado
                CHECK (jsonb_typeof(status_legado) = 'object'
                       AND status_legado ? 'status' AND status_legado ? 'status_pipeline'
                       AND status_legado - 'status' - 'status_pipeline' = '{}'::jsonb),
            CONSTRAINT ck_lotes_legado_destino
                CHECK (destino IN ('preservado', 'promovido')),
            CONSTRAINT ck_lotes_legado_coerencia
                CHECK (
                     (destino = 'promovido'
                        AND motivo_nao_promocao IS NULL AND lote_id_promovido IS NOT NULL)
                  OR (destino = 'preservado'
                        AND motivo_nao_promocao IS NOT NULL AND lote_id_promovido IS NULL)
                )
        )
    """)

    op.execute("""
        CREATE TABLE nsi_operacional.registros_legado (
            snapshot_lote_id   UUID    NOT NULL REFERENCES nsi_operacional.lotes_legado (snapshot_lote_id),
            lista              TEXT    NOT NULL,
            posicao            INTEGER NOT NULL,
            conteudo_bruto     JSONB   NOT NULL,
            conteudo_sha256    TEXT    NOT NULL,
            registro_coleta_id UUID,
            classificacao      TEXT    NOT NULL,

            CONSTRAINT pk_registros_legado
                PRIMARY KEY (snapshot_lote_id, lista, posicao),
            CONSTRAINT ck_registros_legado_lista
                CHECK (lista IN ('clientes', 'clientes_invalidos')),
            CONSTRAINT ck_registros_legado_posicao
                CHECK (posicao >= 0),
            CONSTRAINT ck_registros_legado_conteudo_objeto
                CHECK (jsonb_typeof(conteudo_bruto) = 'object'),
            CONSTRAINT ck_registros_legado_sha256
                CHECK (conteudo_sha256 ~ '^[0-9a-f]{64}$'),
            CONSTRAINT ck_registros_legado_classificacao
                CHECK (classificacao IN ('legado_sem_identidade_tecnica',
                                         'legado_identificado_nao_promovido', 'legado_promovido')),
            CONSTRAINT ck_registros_legado_identidade
                CHECK ((registro_coleta_id IS NULL) = (classificacao = 'legado_sem_identidade_tecnica'))
        )
    """)

    # Usado por fn_criar_claim (item 10.5) e pelo criterio
    # 'colisao_de_identidade' (item 10.1).
    op.execute(
        "CREATE INDEX registros_legado_registro_coleta_id "
        "ON nsi_operacional.registros_legado (registro_coleta_id)"
    )

    # Nenhuma role funcional - inclusive nsi_importacao - le ou escreve
    # diretamente em nenhuma das cinco tabelas (ADR-010, Secoes 9.2 e 16.2).
    for tabela in ("importacoes_legado", "importacoes_legado_arquivos", "importacoes_legado_conclusoes",
                   "lotes_legado", "registros_legado"):
        op.execute(f"REVOKE ALL ON TABLE nsi_operacional.{tabela} FROM PUBLIC")
        op.execute(
            f"REVOKE ALL ON TABLE nsi_operacional.{tabela} "
            "FROM nsi_aplicacao, nsi_expiracao, nsi_operador_restrito, nsi_congelamento, nsi_importacao"
        )

    # =========================================================
    # 1) fn_iniciar_importacao_legado
    # =========================================================
    op.execute("""
        CREATE FUNCTION nsi_operacional.fn_iniciar_importacao_legado(
            p_importacao_id  UUID,
            p_fuso           TEXT
        ) RETURNS JSONB
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, nsi_operacional, pg_temp
        AS $fn$
        DECLARE
            v_iniciada_em  TIMESTAMPTZ;
            v_fuso         TEXT;
        BEGIN
            IF p_importacao_id IS NULL THEN
                RAISE EXCEPTION 'entrada_estrutural_invalida' USING ERRCODE = '22000';
            END IF;

            -- Fuso: nulo, ou identificador IANA com regras proprias (ADR-010,
            -- Secao 13.2) - 'UTC' ou 'Regiao/Local', existente em
            -- pg_timezone_names com a grafia exata. Deslocamentos fixos
            -- (Etc/GMT+3, GMT+0, EST, EST5EDT) e os prefixos posix/ e right/
            -- sao recusados.
            IF p_fuso IS NOT NULL THEN
                IF NOT (p_fuso = 'UTC'
                        OR (p_fuso ~ '^[A-Za-z0-9_+-]+(/[A-Za-z0-9_+-]+)+$'
                            AND p_fuso !~ '^(Etc|posix|right)/'))
                   OR NOT EXISTS (SELECT 1 FROM pg_catalog.pg_timezone_names WHERE name = p_fuso) THEN
                    RAISE EXCEPTION 'entrada_estrutural_invalida' USING ERRCODE = '22000';
                END IF;
            END IF;

            INSERT INTO nsi_operacional.importacoes_legado
                (importacao_id, iniciada_em, executado_por_login, fuso_declarado)
            VALUES (p_importacao_id, now(), session_user, p_fuso)
            ON CONFLICT (importacao_id) DO NOTHING
            RETURNING iniciada_em, fuso_declarado INTO v_iniciada_em, v_fuso;

            IF NOT FOUND THEN
                SELECT iniciada_em, fuso_declarado INTO v_iniciada_em, v_fuso
                  FROM nsi_operacional.importacoes_legado
                 WHERE importacao_id = p_importacao_id;

                IF v_fuso IS DISTINCT FROM p_fuso THEN
                    RAISE EXCEPTION 'conflito_de_idempotencia' USING ERRCODE = '22023';
                END IF;
            END IF;

            -- O retorno e remontado a partir da linha gravada, nunca guardado:
            -- o instante vai em UTC e em formato fixo, para que o replay
            -- devolva o mesmo resultado em qualquer sessao, qualquer que seja
            -- o TimeZone dela.
            RETURN jsonb_build_object(
                'importacao_id', p_importacao_id,
                'iniciada_em', to_char(timezone('UTC', v_iniciada_em), 'YYYY-MM-DD"T"HH24:MI:SS.US"+00:00"'),
                'fuso_declarado', v_fuso);
        END;
        $fn$
    """)
    op.execute(
        "REVOKE ALL ON FUNCTION nsi_operacional.fn_iniciar_importacao_legado(UUID, TEXT) FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION nsi_operacional.fn_iniciar_importacao_legado(UUID, TEXT) TO nsi_importacao"
    )

    # =========================================================
    # 2) fn_importar_lote_legado
    # =========================================================
    op.execute("""
        CREATE FUNCTION nsi_operacional.fn_importar_lote_legado(
            p_importacao_id     UUID,
            p_caminho_relativo  TEXT,
            p_documento         BYTEA,
            p_documento_sha256  TEXT
        ) RETURNS JSONB
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, nsi_operacional, pg_temp
        AS $fn$
        DECLARE
            v_fuso               TEXT;
            v_sha_registrado     TEXT;
            v_doc                JSONB;
            v_estrutura_ok       BOOLEAN;
            v_geracao            TEXT;
            v_destino            TEXT;
            v_motivo             TEXT;
            v_lote_id_legado     TEXT;
            v_lote_id_promovido  UUID;
            v_constraint         TEXT;
            v_n_clientes         INTEGER;
            v_n_invalidos        INTEGER;
            v_n_com_id           INTEGER;
            v_n_clientes_com_id  INTEGER;
            v_id_malformado      BOOLEAN;
            v_chave_extra        BOOLEAN;
            v_n_totais           INTEGER;
            v_ids                UUID[];
            v_sha_snapshot       TEXT;
            v_promovido_original UUID;
            v_criado_em          TEXT;
            v_local              TIMESTAMP;
            v_recebido_em        TIMESTAMPTZ;
            v_ida_e_volta        BOOLEAN;
            v_n_instantes        INTEGER;
            v_snapshot_lote_id   UUID;
            v_gravados           INTEGER;
        BEGIN
            -- ---------------------------------------------------------
            -- Passo 1 - parametros, formato do caminho (item 6.1) e execucao
            -- existente e aberta.
            -- ---------------------------------------------------------
            IF p_importacao_id IS NULL OR p_caminho_relativo IS NULL
               OR p_documento IS NULL OR p_documento_sha256 IS NULL
               OR p_caminho_relativo !~ '^lotes/[^/]+/lote[.]json$'
               OR p_documento_sha256 !~ '^[0-9a-f]{64}$' THEN
                RAISE EXCEPTION 'entrada_estrutural_invalida' USING ERRCODE = '22000';
            END IF;

            -- Bloqueio compartilhado da linha da execucao (item 12): a
            -- conclusao, que a bloqueia FOR UPDATE, espera esta importacao; e
            -- esta importacao, se chegar depois, enxerga a conclusao abaixo.
            -- Bloqueio de linha nao e escrita e nao dispara a trigger.
            SELECT fuso_declarado INTO v_fuso
              FROM nsi_operacional.importacoes_legado
             WHERE importacao_id = p_importacao_id
               FOR SHARE;

            IF NOT FOUND THEN
                RAISE EXCEPTION 'entrada_estrutural_invalida' USING ERRCODE = '22000';
            END IF;

            IF EXISTS (SELECT 1 FROM nsi_operacional.importacoes_legado_conclusoes
                        WHERE importacao_id = p_importacao_id) THEN
                RAISE EXCEPTION 'entrada_estrutural_invalida' USING ERRCODE = '22000';
            END IF;

            -- ---------------------------------------------------------
            -- Passo 2 - SHA-256 recalculado no banco sobre os bytes brutos.
            -- ---------------------------------------------------------
            IF encode(sha256(p_documento), 'hex') <> p_documento_sha256 THEN
                RAISE EXCEPTION 'entrada_estrutural_invalida' USING ERRCODE = '22000';
            END IF;

            -- ---------------------------------------------------------
            -- Passo 3 - mesmo caminho ja registrado nesta execucao: replay ou
            -- conflito, decididos ao final, sobre a linha registrada.
            -- ---------------------------------------------------------
            SELECT documento_sha256 INTO v_sha_registrado
              FROM nsi_operacional.importacoes_legado_arquivos
             WHERE importacao_id = p_importacao_id AND caminho_relativo = p_caminho_relativo;

            IF NOT FOUND THEN
                -- -----------------------------------------------------
                -- Passo 4 - legibilidade: JSON em UTF-8 aceito pelo tipo jsonb.
                -- -----------------------------------------------------
                BEGIN
                    v_doc := convert_from(p_documento, 'UTF8')::JSONB;
                EXCEPTION WHEN data_exception OR program_limit_exceeded THEN
                    v_destino := 'recusado';
                    v_motivo := 'documento_ilegivel';
                END;

                -- -----------------------------------------------------
                -- Passo 5 - lote_id contra o nome do diretorio.
                -- -----------------------------------------------------
                IF v_destino IS NULL AND jsonb_typeof(v_doc -> 'lote_id') = 'string' THEN
                    v_lote_id_legado := v_doc ->> 'lote_id';
                    IF v_lote_id_legado <> split_part(p_caminho_relativo, '/', 2) THEN
                        v_destino := 'recusado';
                        v_motivo := 'identidade_divergente';
                    END IF;
                END IF;

                -- -----------------------------------------------------
                -- Passo 6 - classificacao por geracao (item 6.2), somente pela
                -- estrutura. Cada verificacao so roda depois de a anterior ter
                -- garantido o tipo de que ela depende.
                -- -----------------------------------------------------
                IF v_destino IS NULL THEN
                    v_geracao := 'formato_desconhecido';

                    v_estrutura_ok := jsonb_typeof(v_doc) = 'object';

                    IF v_estrutura_ok THEN
                        v_estrutura_ok := COALESCE(
                            jsonb_typeof(v_doc -> 'lote_id') = 'string'
                            AND jsonb_typeof(v_doc -> 'criado_em') = 'string'
                            AND jsonb_typeof(v_doc -> 'clientes') = 'array'
                            AND COALESCE(jsonb_typeof(v_doc -> 'clientes_invalidos'), 'array') = 'array'
                            AND NOT EXISTS (
                                SELECT 1 FROM jsonb_object_keys(v_doc) AS k
                                 WHERE k <> ALL (ARRAY[
                                     'lote_id', 'empresa', 'nome_lote', 'data_inicial', 'data_final',
                                     'csv_original', 'criado_em', 'total_clientes', 'total_recebido',
                                     'total_valido', 'total_invalido', 'status', 'data_disparo',
                                     'status_pipeline', 'clientes', 'clientes_invalidos', 'historico_versoes'])),
                            false);
                    END IF;

                    IF v_estrutura_ok THEN
                        SELECT count(*) FILTER (WHERE l.lista = 'clientes'),
                               count(*) FILTER (WHERE l.lista = 'clientes_invalidos'),
                               COALESCE(bool_and(jsonb_typeof(e.valor) = 'object'), true)
                          INTO v_n_clientes, v_n_invalidos, v_estrutura_ok
                          FROM (VALUES ('clientes'), ('clientes_invalidos')) AS l(lista)
                         CROSS JOIN LATERAL jsonb_array_elements(COALESCE(v_doc -> l.lista, '[]'::JSONB))
                               AS e(valor);
                    END IF;

                    IF v_estrutura_ok THEN
                        SELECT count(*) FILTER (WHERE e.valor ? 'registro_coleta_id'),
                               count(*) FILTER (WHERE e.valor ? 'registro_coleta_id' AND l.lista = 'clientes'),
                               COALESCE(bool_or(
                                   e.valor ? 'registro_coleta_id'
                                   AND (jsonb_typeof(e.valor -> 'registro_coleta_id') <> 'string'
                                        OR (e.valor ->> 'registro_coleta_id')
                                           !~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')),
                                   false),
                               COALESCE(bool_or(EXISTS (
                                   SELECT 1 FROM jsonb_object_keys(e.valor) AS k
                                    WHERE k <> ALL (CASE l.lista
                                        WHEN 'clientes' THEN ARRAY[
                                            'registro_coleta_id', 'nome', 'telefone', 'produto', 'resposta',
                                            'data_resposta', 'status_entrega', 'data_envio_mensagem']
                                        ELSE ARRAY[
                                            'registro_coleta_id', 'nome_bruto', 'whatsapp_bruto',
                                            'produto_bruto', 'motivos']
                                        END))),
                                   false)
                          INTO v_n_com_id, v_n_clientes_com_id, v_id_malformado, v_chave_extra
                          FROM (VALUES ('clientes'), ('clientes_invalidos')) AS l(lista)
                         CROSS JOIN LATERAL jsonb_array_elements(COALESCE(v_doc -> l.lista, '[]'::JSONB))
                               AS e(valor);

                        v_n_totais := (v_doc ? 'total_recebido')::INTEGER
                                    + (v_doc ? 'total_valido')::INTEGER
                                    + (v_doc ? 'total_invalido')::INTEGER;

                        IF v_id_malformado OR v_chave_extra THEN
                            NULL;
                        ELSIF NOT (v_doc ? 'clientes_invalidos') AND NOT (v_doc ? 'historico_versoes')
                              AND v_n_totais = 0 THEN
                            -- Sem nenhuma marca da A2: a identidade por linha decide.
                            -- Lista vazia nao tem registro com identidade: anterior_a1.
                            IF v_n_com_id = 0 THEN
                                v_geracao := 'anterior_a1';
                            ELSIF v_n_clientes_com_id = v_n_clientes THEN
                                v_geracao := 'a1';
                            END IF;
                        ELSIF (v_doc ? 'clientes_invalidos') AND v_n_totais = 3
                              AND v_n_com_id = v_n_clientes + v_n_invalidos THEN
                            IF NOT (v_doc ? 'historico_versoes') THEN
                                v_geracao := 'a2';
                            ELSIF jsonb_typeof(v_doc -> 'historico_versoes') = 'object' THEN
                                IF NOT EXISTS (SELECT 1 FROM jsonb_each(v_doc -> 'historico_versoes') AS h
                                                WHERE jsonb_typeof(h.value) <> 'array') THEN
                                    v_geracao := 'a3';
                                END IF;
                            END IF;
                        END IF;
                    END IF;

                    IF v_geracao = 'formato_desconhecido' THEN
                        v_destino := 'recusado';
                        v_motivo := 'formato_desconhecido';
                    ELSE
                        SELECT COALESCE(array_agg((e.valor ->> 'registro_coleta_id')::UUID), ARRAY[]::UUID[])
                          INTO v_ids
                          FROM (VALUES ('clientes'), ('clientes_invalidos')) AS l(lista)
                         CROSS JOIN LATERAL jsonb_array_elements(COALESCE(v_doc -> l.lista, '[]'::JSONB))
                               AS e(valor)
                         WHERE e.valor ? 'registro_coleta_id';
                    END IF;
                END IF;

                -- -----------------------------------------------------
                -- Passo 7 - reimportacao pelo lote_id_legado (item 11): avaliada
                -- ANTES do bloqueio de claims, para que um lote ja importado
                -- nunca faca a criacao de claims esperar, e reavaliada DEPOIS
                -- dele, porque o bloqueio serializa as importacoes de lote e
                -- uma importacao concorrente do mesmo lote pode ter terminado
                -- durante a espera.
                -- Passo 8 - bloqueio SHARE ROW EXCLUSIVE de claims, mantido ate
                -- o fim da transacao (item 10.5).
                -- -----------------------------------------------------
                IF v_destino IS NULL THEN
                    FOR v_passagem IN 1..2 LOOP
                        SELECT documento_sha256, lote_id_promovido INTO v_sha_snapshot, v_promovido_original
                          FROM nsi_operacional.lotes_legado
                         WHERE lote_id_legado = v_lote_id_legado;

                        IF FOUND THEN
                            IF v_sha_snapshot = p_documento_sha256 THEN
                                v_destino := 'ja_importado';
                                v_lote_id_promovido := v_promovido_original;
                            ELSE
                                v_destino := 'recusado';
                                v_motivo := 'conflito_de_reimportacao';
                            END IF;
                            EXIT;
                        END IF;

                        EXIT WHEN v_passagem = 2;

                        LOCK TABLE nsi_operacional.claims IN SHARE ROW EXCLUSIVE MODE;
                    END LOOP;
                END IF;

                -- Passo 8 - claim pre-existente em algum registro do documento.
                IF v_destino IS NULL
                   AND EXISTS (SELECT 1 FROM nsi_operacional.claims AS c
                                WHERE c.registro_coleta_id = ANY (v_ids)) THEN
                    v_destino := 'recusado';
                    v_motivo := 'claim_preexistente';
                END IF;

                -- -----------------------------------------------------
                -- Passo 10 - criterios de promocao, na ordem do item 10.1. O
                -- primeiro que falha e o motivo de nao promocao.
                -- -----------------------------------------------------
                IF v_destino IS NULL THEN
                    v_criado_em := v_doc ->> 'criado_em';

                    IF v_geracao IN ('anterior_a1', 'a1') THEN
                        v_motivo := 'geracao_nao_promovivel';
                    ELSIF v_fuso IS NULL THEN
                        v_motivo := 'fuso_nao_declarado';
                    -- Evidencias de disparo (item 6.3). data_disparo NAO e
                    -- evidencia: e a data planejada, gravada no upload.
                    ELSIF (v_doc ->> 'status') = 'disparado'
                          OR EXISTS (SELECT 1
                                       FROM unnest(ARRAY['disparo_whatsapp', 'webhook', 'analise_ia',
                                                         'dashboard', 'pdf']) AS etapa
                                      WHERE v_doc -> 'status_pipeline' -> etapa = 'true'::JSONB)
                          OR EXISTS (SELECT 1
                                       FROM jsonb_array_elements(v_doc -> 'clientes') AS c
                                      WHERE COALESCE(c -> 'data_envio_mensagem', 'null'::JSONB) <> 'null'::JSONB
                                         OR COALESCE(c -> 'status_entrega', 'null'::JSONB) <> 'null'::JSONB
                                         OR COALESCE(c -> 'data_resposta', 'null'::JSONB) <> 'null'::JSONB
                                         OR COALESCE(c -> 'resposta', 'null'::JSONB)
                                            NOT IN ('null'::JSONB, '""'::JSONB)) THEN
                        v_motivo := 'evidencia_de_disparo';
                    ELSIF v_lote_id_legado !~ '^NSI-[0-9]{8}-[0-9A-F]{6}$' THEN
                        v_motivo := 'lote_id_legado_invalido';
                    ELSIF EXISTS (SELECT 1 FROM nsi_operacional.lotes WHERE lote_id_legado = v_lote_id_legado) THEN
                        v_motivo := 'lote_id_legado_em_uso';
                    ELSIF v_criado_em !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}([.][0-9]{1,6})?$' THEN
                        v_motivo := 'm0_invalido';
                    ELSE
                        -- Data e hora validas: a conversao precisa ser aceita e
                        -- reproduzir exatamente o texto (24:00:00 e segundo 60
                        -- seriam aceitos e ajustados pelo PostgreSQL).
                        BEGIN
                            v_local := replace(v_criado_em, 'T', ' ')::TIMESTAMP;
                        EXCEPTION WHEN data_exception THEN
                            v_motivo := 'm0_invalido';
                        END;

                        IF v_motivo IS NULL
                           AND to_char(v_local, 'YYYY-MM-DD"T"HH24:MI:SS') <> left(v_criado_em, 19) THEN
                            v_motivo := 'm0_invalido';
                        END IF;

                        IF v_motivo IS NULL THEN
                            -- Instantes UTC que produzem o horario local no fuso
                            -- declarado: a conversao do PostgreSQL (ord 0) e os
                            -- obtidos com os deslocamentos vigentes 36 horas antes
                            -- e depois. Inexistente: a ida e volta da conversao
                            -- nao reproduz o horario local. Ambiguo: ha mais de
                            -- um instante valido (ADR-010, Secao 13.4).
                            SELECT COALESCE(bool_or(s.ord = 0 AND timezone(v_fuso, s.instante) = v_local), false),
                                   count(DISTINCT s.instante) FILTER (WHERE timezone(v_fuso, s.instante) = v_local)
                              INTO v_ida_e_volta, v_n_instantes
                              FROM (
                                  SELECT 0 AS ord, timezone(v_fuso, v_local) AS instante
                                  UNION ALL
                                  SELECT 1, timezone('UTC', v_local) - make_interval(secs => EXTRACT(EPOCH FROM (
                                             timezone(v_fuso, timezone('UTC', v_local) + d.desvio)
                                             - timezone('UTC', timezone('UTC', v_local) + d.desvio))))
                                    FROM (VALUES (interval '-36 hours'), (interval '36 hours')) AS d(desvio)
                              ) AS s;

                            IF NOT v_ida_e_volta OR v_n_instantes <> 1 THEN
                                v_motivo := 'm0_inexistente_ou_ambiguo';
                            ELSE
                                v_recebido_em := timezone(v_fuso, v_local);
                            END IF;
                        END IF;

                        IF v_motivo IS NULL THEN
                            IF cardinality(v_ids) <> (SELECT count(DISTINCT i) FROM unnest(v_ids) AS i) THEN
                                v_motivo := 'identidade_repetida';
                            ELSIF EXISTS (SELECT 1 FROM nsi_operacional.registros_coleta AS r
                                           WHERE r.registro_coleta_id = ANY (v_ids))
                                  OR EXISTS (SELECT 1 FROM nsi_operacional.registros_legado AS g
                                              WHERE g.registro_coleta_id = ANY (v_ids)) THEN
                                v_motivo := 'colisao_de_identidade';
                            ELSIF jsonb_typeof(v_doc -> 'total_recebido') IS DISTINCT FROM 'number'
                                  OR (v_doc -> 'total_recebido') <> to_jsonb(v_n_clientes + v_n_invalidos) THEN
                                v_motivo := 'totais_incoerentes';
                            -- Em a3: toda chave do historico precisa de um registro
                            -- correspondente, na lista coerente com a versao
                            -- corrente (a ultima); lista de versoes vazia nao tem
                            -- versao corrente.
                            ELSIF v_geracao = 'a3' AND EXISTS (
                                      SELECT 1
                                        FROM jsonb_each(v_doc -> 'historico_versoes') AS h
                                       WHERE NOT EXISTS (
                                                 SELECT 1
                                                   FROM (VALUES ('clientes', 'valida'), ('clientes_invalidos', 'invalida'))
                                                        AS l(lista, status_versao)
                                                  CROSS JOIN LATERAL jsonb_array_elements(v_doc -> l.lista) AS e(valor)
                                                  WHERE e.valor ->> 'registro_coleta_id' = h.key
                                                    AND (h.value -> -1) ->> 'status_versao' = l.status_versao)) THEN
                                v_motivo := 'historico_incoerente';
                            END IF;
                        END IF;
                    END IF;
                END IF;

                -- -----------------------------------------------------
                -- Passo 11 - promocao (itens 10.2 e 10.3), num bloco de excecao
                -- proprio: a violacao de qualquer constraint de lotes ou de
                -- registros_coleta desfaz a promocao, e somente ela; o lote
                -- segue para a preservacao com 'projecao_incompativel' e o
                -- NOME da constraint. Nenhum evento e nenhum recibo.
                -- -----------------------------------------------------
                IF v_destino IS NULL AND v_motivo IS NULL THEN
                    v_lote_id_promovido := gen_random_uuid();

                    BEGIN
                        -- versao_eventos_atual = 1: a posicao 1 corresponde a
                        -- promocao, provada pelo registro tecnico; o primeiro
                        -- evento do fluxo novo tera versao 2 (ADR-009, Secao 22).
                        INSERT INTO nsi_operacional.lotes
                            (lote_id, lote_id_legado, recebido_em, total_recebido, total_valido, total_invalido,
                             status, horario_conceitual_congelamento, versao_eventos_atual)
                        VALUES (v_lote_id_promovido, v_lote_id_legado, v_recebido_em,
                                v_n_clientes + v_n_invalidos, v_n_clientes, v_n_invalidos,
                                'aguardando_d8', v_recebido_em + interval '192 hours', 1);

                        INSERT INTO nsi_operacional.registros_coleta
                            (registro_coleta_id, lote_id, nome, produto, whatsapp, valido, motivos_invalidez,
                             numero_versao_dados, versao_eventos_atual)
                        SELECT (e.valor ->> 'registro_coleta_id')::UUID,
                               v_lote_id_promovido,
                               CASE WHEN l.lista = 'clientes' THEN e.valor ->> 'nome'
                                    WHEN NOT COALESCE(e.valor -> 'motivos' ? 'nome_ausente', false)
                                    THEN e.valor ->> 'nome_bruto' END,
                               CASE WHEN l.lista = 'clientes' THEN e.valor ->> 'produto'
                                    WHEN NOT COALESCE(e.valor -> 'motivos' ? 'produto_ausente', false)
                                    THEN e.valor ->> 'produto_bruto' END,
                               CASE WHEN l.lista = 'clientes' THEN e.valor ->> 'telefone'
                                    WHEN NOT COALESCE(e.valor -> 'motivos' ? 'whatsapp_ausente', false)
                                    THEN e.valor ->> 'whatsapp_bruto' END,
                               l.lista = 'clientes',
                               CASE WHEN l.lista = 'clientes_invalidos'
                                         AND jsonb_typeof(e.valor -> 'motivos') = 'array'
                                    THEN ARRAY(SELECT jsonb_array_elements_text(e.valor -> 'motivos')) END,
                               COALESCE(jsonb_array_length(
                                   v_doc -> 'historico_versoes' -> (e.valor ->> 'registro_coleta_id')), 1),
                               0
                          FROM (VALUES ('clientes'), ('clientes_invalidos')) AS l(lista)
                         CROSS JOIN LATERAL jsonb_array_elements(v_doc -> l.lista) AS e(valor);
                    EXCEPTION WHEN integrity_constraint_violation THEN
                        GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
                        v_constraint := NULLIF(v_constraint, '');
                        v_motivo := 'projecao_incompativel';
                        v_lote_id_promovido := NULL;
                    END;
                END IF;

                -- -----------------------------------------------------
                -- Passo 9 - preservacao (snapshot), e passo 12 - linha do
                -- registro tecnico. Violacao de constraint aqui e relancada com
                -- mensagem fixa e sem DETAIL: o detalhe nativo traria a linha
                -- inteira, com o documento e os valores pessoais.
                -- -----------------------------------------------------
                BEGIN
                    IF v_destino IS NULL THEN
                        v_destino := CASE WHEN v_motivo IS NULL THEN 'promovido' ELSE 'preservado' END;
                        v_snapshot_lote_id := gen_random_uuid();

                        INSERT INTO nsi_operacional.lotes_legado
                            (snapshot_lote_id, importacao_id, lote_id_legado, caminho_relativo, documento_bruto,
                             documento_sha256, geracao, status_legado, criado_em_bruto, destino,
                             motivo_nao_promocao, lote_id_promovido)
                        VALUES (v_snapshot_lote_id, p_importacao_id, v_lote_id_legado, p_caminho_relativo,
                                p_documento, p_documento_sha256, v_geracao,
                                jsonb_build_object('status', v_doc -> 'status',
                                                   'status_pipeline', v_doc -> 'status_pipeline'),
                                v_criado_em, v_destino, v_motivo, v_lote_id_promovido);

                        -- Uma linha por registro, das duas listas, sem alterar,
                        -- normalizar ou completar valor nenhum (item 9).
                        -- conteudo_sha256 calculado somente no banco (item 13).
                        INSERT INTO nsi_operacional.registros_legado
                            (snapshot_lote_id, lista, posicao, conteudo_bruto, conteudo_sha256,
                             registro_coleta_id, classificacao)
                        SELECT v_snapshot_lote_id, l.lista, (e.ord - 1)::INTEGER, e.valor,
                               encode(sha256(convert_to(e.valor::TEXT, 'UTF8')), 'hex'),
                               (e.valor ->> 'registro_coleta_id')::UUID,
                               CASE WHEN NOT (e.valor ? 'registro_coleta_id') THEN 'legado_sem_identidade_tecnica'
                                    WHEN v_destino = 'promovido' THEN 'legado_promovido'
                                    ELSE 'legado_identificado_nao_promovido' END
                          FROM (VALUES ('clientes'), ('clientes_invalidos')) AS l(lista)
                         CROSS JOIN LATERAL jsonb_array_elements(COALESCE(v_doc -> l.lista, '[]'::JSONB))
                               WITH ORDINALITY AS e(valor, ord);

                        GET DIAGNOSTICS v_gravados = ROW_COUNT;
                        IF v_gravados <> v_n_clientes + v_n_invalidos THEN
                            RAISE EXCEPTION 'invariante_violada' USING ERRCODE = 'NS001';
                        END IF;
                    END IF;

                    INSERT INTO nsi_operacional.importacoes_legado_arquivos
                        (importacao_id, caminho_relativo, documento_sha256, lote_id_legado, geracao, destino,
                         motivo, constraint_violada, lote_id_promovido, registrado_em)
                    VALUES (p_importacao_id, p_caminho_relativo, p_documento_sha256, v_lote_id_legado, v_geracao,
                            v_destino, v_motivo, v_constraint, v_lote_id_promovido, now())
                    ON CONFLICT (importacao_id, caminho_relativo) DO NOTHING;

                    IF FOUND THEN
                        v_sha_registrado := p_documento_sha256;
                    ELSE
                        -- O mesmo caminho foi registrado nesta execucao por uma
                        -- chamada concorrente: vale a linha dela (passo 3).
                        SELECT documento_sha256 INTO v_sha_registrado
                          FROM nsi_operacional.importacoes_legado_arquivos
                         WHERE importacao_id = p_importacao_id AND caminho_relativo = p_caminho_relativo;
                    END IF;
                EXCEPTION WHEN integrity_constraint_violation THEN
                    GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
                    IF COALESCE(v_constraint, '') = '' THEN
                        RAISE EXCEPTION 'violacao_de_constraint' USING ERRCODE = SQLSTATE;
                    END IF;
                    RAISE EXCEPTION 'violacao_de_constraint' USING ERRCODE = SQLSTATE, CONSTRAINT = v_constraint;
                END;
            END IF;

            -- Mesmo caminho com SHA-256 diferente na mesma execucao: o arquivo
            -- mudou durante a execucao. A excecao desfaz qualquer escrita
            -- desta chamada (item 12).
            IF v_sha_registrado IS DISTINCT FROM p_documento_sha256 THEN
                RAISE EXCEPTION 'conflito_de_idempotencia' USING ERRCODE = '22023';
            END IF;

            -- Retorno sempre montado a partir da linha registrada: a primeira
            -- execucao e o replay devolvem o mesmo resultado.
            RETURN (
                SELECT jsonb_build_object(
                           'geracao', a.geracao,
                           'destino', a.destino,
                           'motivo', a.motivo,
                           'lote_id_legado', a.lote_id_legado,
                           'lote_id_promovido', a.lote_id_promovido,
                           'constraint_violada', a.constraint_violada)
                       || CASE WHEN a.destino = 'ja_importado'
                               THEN jsonb_build_object(
                                        'destino_original',
                                        CASE WHEN a.lote_id_promovido IS NULL THEN 'preservado' ELSE 'promovido' END)
                               ELSE '{}'::JSONB END
                  FROM nsi_operacional.importacoes_legado_arquivos AS a
                 WHERE a.importacao_id = p_importacao_id AND a.caminho_relativo = p_caminho_relativo);
        END;
        $fn$
    """)
    op.execute(
        "REVOKE ALL ON FUNCTION nsi_operacional.fn_importar_lote_legado(UUID, TEXT, BYTEA, TEXT) FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION nsi_operacional.fn_importar_lote_legado(UUID, TEXT, BYTEA, TEXT) "
        "TO nsi_importacao"
    )

    # =========================================================
    # 3) fn_concluir_importacao_legado
    # =========================================================
    op.execute("""
        CREATE FUNCTION nsi_operacional.fn_concluir_importacao_legado(
            p_importacao_id       UUID,
            p_manifesto_canonico  BYTEA,
            p_manifesto_sha256    TEXT,
            p_total_arquivos      INTEGER
        ) RETURNS JSONB
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, nsi_operacional, pg_temp
        AS $fn$
        DECLARE
            v_concluida_em       TIMESTAMPTZ;
            v_sha_registrado     TEXT;
            v_total_registrado   INTEGER;
            v_constraint         TEXT;
        BEGIN
            IF p_importacao_id IS NULL OR p_manifesto_canonico IS NULL
               OR p_manifesto_sha256 IS NULL OR p_total_arquivos IS NULL
               OR p_manifesto_sha256 !~ '^[0-9a-f]{64}$'
               OR p_total_arquivos < 0 THEN
                RAISE EXCEPTION 'entrada_estrutural_invalida' USING ERRCODE = '22000';
            END IF;

            -- SHA-256 recalculado no banco sobre os bytes do manifesto (item 13).
            IF encode(sha256(p_manifesto_canonico), 'hex') <> p_manifesto_sha256 THEN
                RAISE EXCEPTION 'entrada_estrutural_invalida' USING ERRCODE = '22000';
            END IF;

            -- Bloqueio exclusivo da linha da execucao (item 12): espera as
            -- importacoes de lote em andamento, que a bloqueiam FOR SHARE, e
            -- serializa duas conclusoes da mesma execucao.
            PERFORM 1
               FROM nsi_operacional.importacoes_legado
              WHERE importacao_id = p_importacao_id
                FOR UPDATE;

            IF NOT FOUND THEN
                RAISE EXCEPTION 'entrada_estrutural_invalida' USING ERRCODE = '22000';
            END IF;

            SELECT concluida_em, manifesto_sha256 INTO v_concluida_em, v_sha_registrado
              FROM nsi_operacional.importacoes_legado_conclusoes
             WHERE importacao_id = p_importacao_id;

            IF FOUND THEN
                IF v_sha_registrado <> p_manifesto_sha256 THEN
                    RAISE EXCEPTION 'conflito_de_idempotencia' USING ERRCODE = '22023';
                END IF;
            ELSE
                -- total_arquivos conferido contra as linhas registradas - as
                -- tentativas recusadas so entram no manifesto (item 16).
                SELECT count(*) INTO v_total_registrado
                  FROM nsi_operacional.importacoes_legado_arquivos
                 WHERE importacao_id = p_importacao_id;

                IF v_total_registrado <> p_total_arquivos THEN
                    RAISE EXCEPTION 'entrada_estrutural_invalida' USING ERRCODE = '22000';
                END IF;

                BEGIN
                    INSERT INTO nsi_operacional.importacoes_legado_conclusoes
                        (importacao_id, concluida_em, manifesto_canonico, manifesto_sha256, total_arquivos)
                    VALUES (p_importacao_id, now(), p_manifesto_canonico, p_manifesto_sha256, p_total_arquivos)
                    RETURNING concluida_em INTO v_concluida_em;
                EXCEPTION WHEN integrity_constraint_violation THEN
                    GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
                    IF COALESCE(v_constraint, '') = '' THEN
                        RAISE EXCEPTION 'violacao_de_constraint' USING ERRCODE = SQLSTATE;
                    END IF;
                    RAISE EXCEPTION 'violacao_de_constraint' USING ERRCODE = SQLSTATE, CONSTRAINT = v_constraint;
                END;
            END IF;

            -- Instante em UTC e formato fixo: mesmo resultado no replay, em
            -- qualquer sessao (ver fn_iniciar_importacao_legado).
            RETURN jsonb_build_object(
                'importacao_id', p_importacao_id,
                'concluida_em', to_char(timezone('UTC', v_concluida_em), 'YYYY-MM-DD"T"HH24:MI:SS.US"+00:00"'),
                'manifesto_sha256', p_manifesto_sha256);
        END;
        $fn$
    """)
    op.execute(
        "REVOKE ALL ON FUNCTION nsi_operacional.fn_concluir_importacao_legado(UUID, BYTEA, TEXT, INTEGER) "
        "FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION nsi_operacional.fn_concluir_importacao_legado(UUID, BYTEA, TEXT, INTEGER) "
        "TO nsi_importacao"
    )

    # =========================================================
    # 4) fn_verificar_paridade_legado - somente leitura
    # =========================================================
    op.execute("""
        CREATE FUNCTION nsi_operacional.fn_verificar_paridade_legado(
            p_importacao_id  UUID
        ) RETURNS JSONB
        LANGUAGE plpgsql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, nsi_operacional, pg_temp
        AS $fn$
        DECLARE
            v_fuso_execucao     TEXT;
            v_concluida         BOOLEAN;
            v_manifesto_bytes   BYTEA;
            v_manifesto_sha256  TEXT;
            v_manifesto         JSONB;
            v_m_sha256_ok       BOOLEAN;
            v_m_cabecalho_ok    BOOLEAN;
            v_m_sem_orfao_ok    BOOLEAN;
            v_arq               RECORD;
            v_snap              RECORD;
            v_tem_snapshot      BOOLEAN;
            v_doc               JSONB;
            v_fuso_origem       TEXT;
            v_promovido         UUID;
            v_evoluido          BOOLEAN;
            v_sha256_ok         BOOLEAN;
            v_quantidade_ok     BOOLEAN;
            v_conteudo_ok       BOOLEAN;
            v_projecao_ok       BOOLEAN;
            v_totais_ok         BOOLEAN;
            v_recebido_em_ok    BOOLEAN;
            v_sem_evento_ok     BOOLEAN;
            v_origem_ok         BOOLEAN;
            v_manifesto_ok      BOOLEAN;
            v_lotes             JSONB := '[]'::JSONB;
            v_total             INTEGER := 0;
            v_preservados       INTEGER := 0;
            v_promovidos        INTEGER := 0;
            v_recusados         INTEGER := 0;
            v_ja_importados     INTEGER := 0;
            v_evoluidos         INTEGER := 0;
            v_reprovados        INTEGER := 0;
        BEGIN
            IF p_importacao_id IS NULL THEN
                RAISE EXCEPTION 'entrada_estrutural_invalida' USING ERRCODE = '22000';
            END IF;

            SELECT fuso_declarado INTO v_fuso_execucao
              FROM nsi_operacional.importacoes_legado
             WHERE importacao_id = p_importacao_id;

            IF NOT FOUND THEN
                RAISE EXCEPTION 'entrada_estrutural_invalida' USING ERRCODE = '22000';
            END IF;

            SELECT manifesto_canonico, manifesto_sha256 INTO v_manifesto_bytes, v_manifesto_sha256
              FROM nsi_operacional.importacoes_legado_conclusoes
             WHERE importacao_id = p_importacao_id;

            v_concluida := FOUND;

            -- ---------------------------------------------------------
            -- Registro tecnico: manifesto gravado (item 14). Sem conclusao,
            -- nao ha manifesto - as tres verificacoes ficam nulas.
            -- ---------------------------------------------------------
            IF v_concluida THEN
                v_m_sha256_ok := encode(sha256(v_manifesto_bytes), 'hex') = v_manifesto_sha256;

                BEGIN
                    v_manifesto := convert_from(v_manifesto_bytes, 'UTF8')::JSONB;
                EXCEPTION WHEN data_exception OR program_limit_exceeded THEN
                    v_manifesto := NULL;
                END;

                IF jsonb_typeof(v_manifesto -> 'arquivos') IS DISTINCT FROM 'array' THEN
                    v_manifesto := NULL;
                    v_m_cabecalho_ok := false;
                    v_m_sem_orfao_ok := false;
                ELSE
                    v_m_cabecalho_ok :=
                        (v_manifesto ->> 'importacao_id') IS NOT DISTINCT FROM p_importacao_id::TEXT
                        AND (v_manifesto ->> 'fuso_declarado') IS NOT DISTINCT FROM v_fuso_execucao;

                    -- Toda entrada de tipo 'lote' tem linha no registro tecnico;
                    -- as de tipo 'tentativa_recusada' nao tem linha.
                    v_m_sem_orfao_ok := NOT EXISTS (
                        SELECT 1
                          FROM jsonb_array_elements(v_manifesto -> 'arquivos') AS m
                         WHERE m ->> 'tipo' = 'lote'
                           AND NOT EXISTS (
                                   SELECT 1 FROM nsi_operacional.importacoes_legado_arquivos AS a
                                    WHERE a.importacao_id = p_importacao_id
                                      AND a.caminho_relativo = m ->> 'caminho_relativo'));
                END IF;
            END IF;

            -- ---------------------------------------------------------
            -- Uma entrada por lote apresentado na execucao.
            -- ---------------------------------------------------------
            FOR v_arq IN
                SELECT a.caminho_relativo, a.documento_sha256, a.lote_id_legado, a.geracao, a.destino,
                       a.motivo, a.lote_id_promovido
                  FROM nsi_operacional.importacoes_legado_arquivos AS a
                 WHERE a.importacao_id = p_importacao_id
                 ORDER BY a.caminho_relativo COLLATE "C"
            LOOP
                v_doc := NULL;
                v_promovido := NULL;
                v_evoluido := false;
                v_sha256_ok := NULL;
                v_quantidade_ok := NULL;
                v_conteudo_ok := NULL;
                v_projecao_ok := NULL;
                v_totais_ok := NULL;
                v_recebido_em_ok := NULL;
                v_sem_evento_ok := NULL;
                v_origem_ok := NULL;
                v_manifesto_ok := NULL;

                -- Lote recusado nao tem snapshot proprio. Lote 'ja_importado' e
                -- reverificado por inteiro no snapshot original (item 14).
                IF v_arq.destino <> 'recusado' THEN
                    v_promovido := v_arq.lote_id_promovido;

                    SELECT g.snapshot_lote_id, g.importacao_id, g.documento_bruto, g.documento_sha256,
                           g.criado_em_bruto, g.lote_id_promovido
                      INTO v_snap
                      FROM nsi_operacional.lotes_legado AS g
                     WHERE g.lote_id_legado = v_arq.lote_id_legado;

                    v_tem_snapshot := FOUND;

                    IF NOT v_tem_snapshot THEN
                        v_sha256_ok := false;
                        v_quantidade_ok := false;
                        v_conteudo_ok := false;
                    ELSE
                        v_sha256_ok := encode(sha256(v_snap.documento_bruto), 'hex') = v_snap.documento_sha256
                                       AND v_snap.documento_sha256 = v_arq.documento_sha256;

                        -- Tudo e recalculado a partir de documento_bruto. Um
                        -- documento adulterado que deixe de ser legivel, ou de
                        -- ter a estrutura esperada, reprova as verificacoes.
                        BEGIN
                            v_doc := convert_from(v_snap.documento_bruto, 'UTF8')::JSONB;

                            SELECT NOT EXISTS (
                                       SELECT 1
                                         FROM (VALUES ('clientes'), ('clientes_invalidos')) AS l(lista)
                                        WHERE (SELECT count(*) FROM nsi_operacional.registros_legado AS r
                                                WHERE r.snapshot_lote_id = v_snap.snapshot_lote_id
                                                  AND r.lista = l.lista)
                                              <> jsonb_array_length(COALESCE(v_doc -> l.lista, '[]'::JSONB)))
                              INTO v_quantidade_ok;

                            SELECT NOT EXISTS (
                                       SELECT 1
                                         FROM nsi_operacional.registros_legado AS r
                                        WHERE r.snapshot_lote_id = v_snap.snapshot_lote_id
                                          AND (r.conteudo_bruto IS DISTINCT FROM (v_doc -> r.lista -> r.posicao)
                                               OR r.conteudo_sha256 IS DISTINCT FROM encode(sha256(convert_to(
                                                      (v_doc -> r.lista -> r.posicao)::TEXT, 'UTF8')), 'hex')))
                              INTO v_conteudo_ok;
                        EXCEPTION WHEN data_exception OR program_limit_exceeded THEN
                            v_doc := NULL;
                            v_quantidade_ok := false;
                            v_conteudo_ok := false;
                        END;
                    END IF;
                END IF;

                -- ---------------------------------------------------------
                -- Lote promovido (inclusive o 'ja_importado' cujo original foi
                -- promovido).
                -- ---------------------------------------------------------
                IF v_promovido IS NOT NULL THEN
                    -- Lote evoluido: ja tem evento do fluxo novo. A paridade e
                    -- a prova do momento da importacao - as comparacoes de
                    -- projecao deixam de se aplicar (nulas).
                    v_evoluido :=
                        EXISTS (SELECT 1 FROM nsi_operacional.eventos_lote AS ev
                                 WHERE ev.aggregate_id = v_promovido)
                        OR EXISTS (SELECT 1
                                     FROM nsi_operacional.eventos_registro_coleta AS ev
                                     JOIN nsi_operacional.registros_coleta AS rc
                                       ON rc.registro_coleta_id = ev.aggregate_id
                                    WHERE rc.lote_id = v_promovido);

                    -- Nenhum evento gravado por nsi_importacao para o lote.
                    v_sem_evento_ok :=
                        NOT EXISTS (SELECT 1 FROM nsi_operacional.eventos_lote AS ev
                                     WHERE ev.aggregate_id = v_promovido
                                       AND ev.executado_por_login = 'nsi_importacao')
                        AND NOT EXISTS (SELECT 1
                                          FROM nsi_operacional.eventos_registro_coleta AS ev
                                          JOIN nsi_operacional.registros_coleta AS rc
                                            ON rc.registro_coleta_id = ev.aggregate_id
                                         WHERE rc.lote_id = v_promovido
                                           AND ev.executado_por_login = 'nsi_importacao');

                    -- Prova de origem (ADR-009, Secao 22): o lote da projecao, o
                    -- snapshot e a linha de promocao do registro tecnico
                    -- apontam uns para os outros.
                    v_origem_ok :=
                        v_tem_snapshot
                        AND v_snap.lote_id_promovido IS NOT DISTINCT FROM v_promovido
                        AND EXISTS (SELECT 1 FROM nsi_operacional.lotes AS lo
                                     WHERE lo.lote_id = v_promovido
                                       AND lo.lote_id_legado = v_arq.lote_id_legado)
                        AND EXISTS (SELECT 1 FROM nsi_operacional.importacoes_legado_arquivos AS o
                                     WHERE o.destino = 'promovido'
                                       AND o.lote_id_promovido = v_promovido
                                       AND o.lote_id_legado = v_arq.lote_id_legado);

                    IF NOT v_evoluido THEN
                        IF v_doc IS NULL THEN
                            v_projecao_ok := false;
                            v_totais_ok := false;
                            v_recebido_em_ok := false;
                        ELSE
                            BEGIN
                                -- Cada valor de registros_coleta igual ao
                                -- mapeamento do item 10.3 recalculado do documento.
                                SELECT count(*) = (SELECT count(*) FROM nsi_operacional.registros_coleta AS q
                                                    WHERE q.lote_id = v_promovido)
                                       AND COALESCE(bool_and(
                                               rc.registro_coleta_id IS NOT NULL
                                               AND rc.nome IS NOT DISTINCT FROM m.nome
                                               AND rc.produto IS NOT DISTINCT FROM m.produto
                                               AND rc.whatsapp IS NOT DISTINCT FROM m.whatsapp
                                               AND rc.valido = m.valido
                                               AND rc.motivos_invalidez IS NOT DISTINCT FROM m.motivos_invalidez
                                               AND rc.numero_versao_dados = m.numero_versao_dados
                                               AND rc.versao_eventos_atual = 0), true)
                                  INTO v_projecao_ok
                                  FROM (
                                      SELECT (e.valor ->> 'registro_coleta_id')::UUID AS registro_coleta_id,
                                             CASE WHEN l.lista = 'clientes' THEN e.valor ->> 'nome'
                                                  WHEN NOT COALESCE(e.valor -> 'motivos' ? 'nome_ausente', false)
                                                  THEN e.valor ->> 'nome_bruto' END AS nome,
                                             CASE WHEN l.lista = 'clientes' THEN e.valor ->> 'produto'
                                                  WHEN NOT COALESCE(e.valor -> 'motivos' ? 'produto_ausente', false)
                                                  THEN e.valor ->> 'produto_bruto' END AS produto,
                                             CASE WHEN l.lista = 'clientes' THEN e.valor ->> 'telefone'
                                                  WHEN NOT COALESCE(e.valor -> 'motivos' ? 'whatsapp_ausente', false)
                                                  THEN e.valor ->> 'whatsapp_bruto' END AS whatsapp,
                                             l.lista = 'clientes' AS valido,
                                             CASE WHEN l.lista = 'clientes_invalidos'
                                                       AND jsonb_typeof(e.valor -> 'motivos') = 'array'
                                                  THEN ARRAY(SELECT jsonb_array_elements_text(e.valor -> 'motivos'))
                                                  END AS motivos_invalidez,
                                             COALESCE(jsonb_array_length(
                                                 v_doc -> 'historico_versoes' -> (e.valor ->> 'registro_coleta_id')), 1)
                                                 AS numero_versao_dados
                                        FROM (VALUES ('clientes'), ('clientes_invalidos')) AS l(lista)
                                       CROSS JOIN LATERAL jsonb_array_elements(v_doc -> l.lista) AS e(valor)
                                  ) AS m
                                  LEFT JOIN nsi_operacional.registros_coleta AS rc
                                    ON rc.registro_coleta_id = m.registro_coleta_id AND rc.lote_id = v_promovido;

                                -- Totais iguais a recontagem das duas listas.
                                SELECT lo.total_valido = jsonb_array_length(v_doc -> 'clientes')
                                       AND lo.total_invalido = jsonb_array_length(v_doc -> 'clientes_invalidos')
                                       AND lo.total_recebido = jsonb_array_length(v_doc -> 'clientes')
                                                               + jsonb_array_length(v_doc -> 'clientes_invalidos')
                                  INTO v_totais_ok
                                  FROM nsi_operacional.lotes AS lo
                                 WHERE lo.lote_id = v_promovido;

                                -- recebido_em igual a reinterpretacao de
                                -- criado_em_bruto no fuso gravado pela execucao
                                -- que promoveu o lote (ADR-010, Secao 13.5).
                                SELECT i.fuso_declarado INTO v_fuso_origem
                                  FROM nsi_operacional.importacoes_legado AS i
                                 WHERE i.importacao_id = v_snap.importacao_id;

                                SELECT lo.recebido_em = timezone(
                                           v_fuso_origem, replace(v_snap.criado_em_bruto, 'T', ' ')::TIMESTAMP)
                                  INTO v_recebido_em_ok
                                  FROM nsi_operacional.lotes AS lo
                                 WHERE lo.lote_id = v_promovido;
                            EXCEPTION WHEN data_exception OR program_limit_exceeded THEN
                                NULL;
                            END;

                            -- Verificacao que nao pode ser feita (lote ausente,
                            -- documento adulterado) e verificacao reprovada.
                            v_projecao_ok := COALESCE(v_projecao_ok, false);
                            v_totais_ok := COALESCE(v_totais_ok, false);
                            v_recebido_em_ok := COALESCE(v_recebido_em_ok, false);
                        END IF;
                    END IF;
                END IF;

                -- ---------------------------------------------------------
                -- Linha do registro tecnico contra a entrada correspondente do
                -- manifesto: caminho, SHA-256, geracao, destino e motivo.
                -- ---------------------------------------------------------
                IF v_concluida THEN
                    IF v_manifesto IS NULL THEN
                        v_manifesto_ok := false;
                    ELSE
                        SELECT count(*) = 1
                               AND bool_and(
                                       (m ->> 'sha256') IS NOT DISTINCT FROM v_arq.documento_sha256
                                       AND (m ->> 'geracao') IS NOT DISTINCT FROM v_arq.geracao
                                       AND (m ->> 'destino') IS NOT DISTINCT FROM v_arq.destino
                                       AND (m ->> 'motivo') IS NOT DISTINCT FROM v_arq.motivo)
                          INTO v_manifesto_ok
                          FROM jsonb_array_elements(v_manifesto -> 'arquivos') AS m
                         WHERE m ->> 'tipo' = 'lote'
                           AND m ->> 'caminho_relativo' = v_arq.caminho_relativo;

                        v_manifesto_ok := COALESCE(v_manifesto_ok, false);
                    END IF;
                END IF;

                v_total := v_total + 1;
                v_preservados := v_preservados + (v_arq.destino = 'preservado')::INTEGER;
                v_promovidos := v_promovidos + (v_arq.destino = 'promovido')::INTEGER;
                v_recusados := v_recusados + (v_arq.destino = 'recusado')::INTEGER;
                v_ja_importados := v_ja_importados + (v_arq.destino = 'ja_importado')::INTEGER;
                v_evoluidos := v_evoluidos + v_evoluido::INTEGER;

                -- Verificacao nula nao se aplica; qualquer verificacao falsa
                -- reprova o lote.
                IF NOT (COALESCE(v_sha256_ok, true) AND COALESCE(v_quantidade_ok, true)
                        AND COALESCE(v_conteudo_ok, true) AND COALESCE(v_projecao_ok, true)
                        AND COALESCE(v_totais_ok, true) AND COALESCE(v_recebido_em_ok, true)
                        AND COALESCE(v_sem_evento_ok, true) AND COALESCE(v_origem_ok, true)
                        AND COALESCE(v_manifesto_ok, true)) THEN
                    v_reprovados := v_reprovados + 1;
                END IF;

                v_lotes := v_lotes || jsonb_build_array(jsonb_build_object(
                    'caminho_relativo', v_arq.caminho_relativo,
                    'lote_id_legado', v_arq.lote_id_legado,
                    'destino', v_arq.destino,
                    'evoluido_no_fluxo_novo', v_evoluido,
                    'documento_sha256_confere', v_sha256_ok,
                    'quantidade_registros_confere', v_quantidade_ok,
                    'conteudo_registros_confere', v_conteudo_ok,
                    'projecao_registros_confere', v_projecao_ok,
                    'totais_conferem', v_totais_ok,
                    'recebido_em_confere', v_recebido_em_ok,
                    'sem_evento_da_importacao', v_sem_evento_ok,
                    'prova_de_origem_confere', v_origem_ok,
                    'registro_confere_com_manifesto', v_manifesto_ok));
            END LOOP;

            RETURN jsonb_build_object(
                'aprovada', v_concluida AND v_m_sha256_ok AND v_m_cabecalho_ok AND v_m_sem_orfao_ok
                            AND v_reprovados = 0,
                'concluida', v_concluida,
                'motivo', CASE WHEN v_concluida THEN NULL ELSE 'execucao_nao_concluida' END,
                'registro_tecnico', jsonb_build_object(
                    'manifesto_sha256_confere', v_m_sha256_ok,
                    'manifesto_cabecalho_confere', v_m_cabecalho_ok,
                    'manifesto_sem_lote_orfao', v_m_sem_orfao_ok),
                'lotes', v_lotes,
                'contagens', jsonb_build_object(
                    'lotes', v_total,
                    'preservado', v_preservados,
                    'promovido', v_promovidos,
                    'recusado', v_recusados,
                    'ja_importado', v_ja_importados,
                    'evoluidos_no_fluxo_novo', v_evoluidos,
                    'lotes_reprovados', v_reprovados));
        END;
        $fn$
    """)
    op.execute(
        "REVOKE ALL ON FUNCTION nsi_operacional.fn_verificar_paridade_legado(UUID) FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION nsi_operacional.fn_verificar_paridade_legado(UUID) TO nsi_importacao"
    )

    # =========================================================
    # fn_criar_claim - nova definicao (item 10.5; ADR-010, Secao 15)
    #
    # CREATE OR REPLACE preserva owner e matriz de EXECUTE da 0003. O corpo
    # e o da 0003, com uma unica mudanca: a consulta a registros_legado,
    # feita no MESMO comando SQL que grava o claim, e a recusa
    # 'registro_legado_nao_promovido', gravada no recibo como
    # 'registro_ocupado'.
    # =========================================================
    op.execute("""
        CREATE OR REPLACE FUNCTION nsi_operacional.fn_criar_claim(
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
            v_payload_existente     TEXT;
            v_resultado_existente   JSONB;
            v_novo_claim_id         UUID;
            v_versao                BIGINT;
            v_resultado             JSONB;
            v_executado_por         JSONB;
            v_legado_nao_promovido  BOOLEAN;
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

            -- Um unico comando: le registros_legado e grava o claim sob o
            -- mesmo snapshot, obtido depois do bloqueio de claims. Se uma
            -- importacao de lote estiver em andamento (SHARE ROW EXCLUSIVE em
            -- claims), este comando espera e so entao le o snapshot legado.
            WITH legado AS (
                SELECT EXISTS (
                           SELECT 1 FROM nsi_operacional.registros_legado
                            WHERE registro_coleta_id = p_registro_coleta_id
                              AND classificacao = 'legado_identificado_nao_promovido') AS nao_promovido
            ), gravado AS (
                INSERT INTO nsi_operacional.claims
                       (registro_coleta_id, claim_id, token_hash, estado, criado_em, expira_em,
                        versao_atual, ultimo_heartbeat_em, revisao_atual_id, revisao_decisao, revisao_registrada_em)
                SELECT p_registro_coleta_id, v_novo_claim_id, p_token_hash, 'ativo', now(), now() + interval '5 minutes',
                       1, NULL::TIMESTAMPTZ, NULL::UUID, NULL::TEXT, NULL::TIMESTAMPTZ
                  FROM legado
                 WHERE NOT legado.nao_promovido
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
                RETURNING versao_atual
            )
            SELECT (SELECT nao_promovido FROM legado), (SELECT versao_atual FROM gravado)
              INTO v_legado_nao_promovido, v_versao;

            IF v_legado_nao_promovido THEN
                v_resultado := jsonb_build_object('sucesso', false, 'motivo', 'registro_legado_nao_promovido');
            ELSIF v_versao IS NOT NULL THEN
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

    # Devolve a sessao ao migrator antes de o Alembic gravar o carimbo de
    # versao - mesmo padrao obrigatorio de 0002 a 0005.
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
    # Lidos antes de qualquer acao: se a definicao da 0003 nao puder ser
    # localizada, nada e removido.
    comandos_fn_criar_claim = _comandos_fn_criar_claim_da_0003()

    op.execute("SET LOCAL ROLE nsi_eventos_owner")

    # Preflight OBRIGATORIO - aborta a transacao inteira, sem remover nenhum
    # objeto, se existir lote promovido: ele perderia a prova de origem
    # exigida pela ADR-009, Secao 22.
    op.execute("""
        DO $$
        DECLARE
            promovidos BIGINT;
        BEGIN
            SELECT COUNT(*) INTO promovidos
              FROM nsi_operacional.importacoes_legado_arquivos
             WHERE destino = 'promovido';
            IF promovidos > 0 THEN
                RAISE EXCEPTION
                    'Downgrade de 0006 abortado: % lote(s) promovido(s) existem em importacoes_legado_arquivos - a prova de origem (ADR-009, Secao 22) seria perdida.',
                    promovidos;
            END IF;
        END $$
    """)

    # Ordem inversa da criacao. fn_criar_claim volta a definicao da 0003,
    # com os proprios comandos daquele arquivo (CREATE, REVOKE, GRANT).
    op.execute(f"DROP FUNCTION {_ASSINATURA_FN_CRIAR_CLAIM}")
    for comando in comandos_fn_criar_claim:
        op.execute(comando)

    op.execute("DROP FUNCTION nsi_operacional.fn_verificar_paridade_legado(UUID)")
    op.execute("DROP FUNCTION nsi_operacional.fn_concluir_importacao_legado(UUID, BYTEA, TEXT, INTEGER)")
    op.execute("DROP FUNCTION nsi_operacional.fn_importar_lote_legado(UUID, TEXT, BYTEA, TEXT)")
    op.execute("DROP FUNCTION nsi_operacional.fn_iniciar_importacao_legado(UUID, TEXT)")

    op.execute("DROP TABLE nsi_operacional.registros_legado")
    op.execute("DROP TABLE nsi_operacional.lotes_legado")

    for tabela in ("importacoes_legado_conclusoes", "importacoes_legado_arquivos", "importacoes_legado"):
        op.execute(f"DROP TRIGGER {tabela}_bloqueia_alteracao ON nsi_operacional.{tabela}")
        op.execute(f"DROP FUNCTION nsi_operacional.fn_bloquear_alteracao_{tabela}()")
        op.execute(f"DROP TABLE nsi_operacional.{tabela}")

    # Autoverificacao: nenhum objeto da 0006 pode restar, e fn_criar_claim
    # precisa existir em exatamente uma assinatura.
    op.execute("""
        DO $$
        DECLARE
            funcoes_restantes INTEGER;
            tabelas_restantes INTEGER;
            criar_claim       INTEGER;
        BEGIN
            SELECT count(*) FILTER (WHERE p.proname <> 'fn_criar_claim'),
                   count(*) FILTER (WHERE p.proname = 'fn_criar_claim')
              INTO funcoes_restantes, criar_claim
              FROM pg_catalog.pg_proc p
              JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
             WHERE n.nspname = 'nsi_operacional'
               AND p.proname IN ('fn_iniciar_importacao_legado', 'fn_importar_lote_legado',
                                 'fn_concluir_importacao_legado', 'fn_verificar_paridade_legado',
                                 'fn_bloquear_alteracao_importacoes_legado',
                                 'fn_bloquear_alteracao_importacoes_legado_arquivos',
                                 'fn_bloquear_alteracao_importacoes_legado_conclusoes',
                                 'fn_criar_claim');

            SELECT count(*) INTO tabelas_restantes
              FROM pg_catalog.pg_tables
             WHERE schemaname = 'nsi_operacional'
               AND tablename IN ('importacoes_legado', 'importacoes_legado_arquivos',
                                 'importacoes_legado_conclusoes', 'lotes_legado', 'registros_legado');

            IF funcoes_restantes <> 0 OR tabelas_restantes <> 0 OR criar_claim <> 1 THEN
                RAISE EXCEPTION 'Downgrade de 0006 incompleto: % funcao(oes), % tabela(s) restantes; fn_criar_claim em % assinatura(s).',
                    funcoes_restantes, tabelas_restantes, criar_claim;
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
