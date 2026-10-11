-- =============================================================
-- scripts/postgres_local/desprovisionar_c3_roles_envio.sql
-- Sprint C (C3) - ADR-011 (Secao 11) / SPRINT-C-ESPECIFICACAO-TECNICA.md
-- (Secao 3). Reversao de provisionar_c3_roles_envio.sql.
--
-- APENAS PARA DESENVOLVIMENTO/TESTE LOCAL. NUNCA PRODUCAO.
--
-- Execute conectado ao banco de manutencao "postgres":
--
--     psql -U postgres -d postgres -f scripts/postgres_local/desprovisionar_c3_roles_envio.sql
--
-- O QUE ESTE SCRIPT FAZ (e nada alem disso): revoga de nsi_envio e de
-- nsi_webhook o USAGE no schema "nsi_operacional" de nsi_dev e de nsi_test
-- e o CONNECT nos dois bancos, e remove as duas roles.
--
-- O QUE ESTE SCRIPT NUNCA FAZ: nao reverte migration; nao remove funcao,
-- tabela ou evento; nao altera nenhuma outra role; nunca derruba sessao;
-- nunca usa remocao em cascata.
--
-- BLOQUEIO PELA MIGRATION 0007: a 0007 concede EXECUTE as duas roles. Com a
-- 0007 aplicada em nsi_dev ou em nsi_test, este script ABORTA na preflight:
-- a reversao da migration e um passo anterior, feito pelo Alembic, somente
-- em nsi_test - e, como nenhum downgrade e permitido em nsi_dev, este
-- script so e executavel enquanto nsi_dev estiver na revisao 0006.
--
-- NAO CONTEM SENHA.
--
-- ESTE SCRIPT NAO E EXECUTADO AUTOMATICAMENTE por nenhum teste nem por
-- qualquer codigo de aplicacao. Toda execucao e um procedimento MANUAL
-- autorizado, com confirmacao textual exata.
--
-- DESENHO: Fase 1 (preflight, somente leitura) -> gate de confirmacao ->
-- Fase 2 (unica que escreve) -> Fase 3 (pos-validacao, somente leitura).
-- O modo somente leitura e religado e conferido depois de cada \c fora da
-- Fase 2. Variaveis de cliente sao prefixadas (conf_, f2_) e nunca cruzam
-- para a Fase 3. Cada role pode estar ausente ou presente: o que existir e
-- removido.
-- =============================================================

\set ON_ERROR_STOP on

-- =============================================================
-- PROTECOES INICIAIS. Somente leitura.
-- =============================================================
SET default_transaction_read_only = on;
DO $$
BEGIN
    IF current_setting('transaction_read_only') <> 'on' THEN
        RAISE EXCEPTION 'Modo somente leitura NAO esta ativo nas protecoes iniciais. Abortando sem nenhuma alteracao.';
    END IF;
END $$;

DO $$
BEGIN
    IF current_database() <> 'postgres' THEN
        RAISE EXCEPTION 'Conectado ao banco "%", esperado "postgres". Abortando sem nenhuma alteracao.', current_database();
    END IF;
    IF inet_server_addr() IS NOT NULL AND host(inet_server_addr()) NOT IN ('127.0.0.1', '::1') THEN
        RAISE EXCEPTION 'Servidor remoto detectado (inet_server_addr()=%). Este script e exclusivo de PostgreSQL LOCAL. Abortando.', inet_server_addr();
    END IF;
    IF inet_server_port() <> 5432 THEN
        RAISE EXCEPTION 'Porta inesperada (%), esperado 5432. Abortando.', inet_server_port();
    END IF;
    IF version() NOT LIKE '%PostgreSQL 17%' THEN
        RAISE EXCEPTION 'Versao inesperada do servidor (%), esperado PostgreSQL 17. Abortando.', version();
    END IF;
END $$;

DO $$
BEGIN
    IF current_setting('is_superuser') <> 'on' THEN
        RAISE EXCEPTION 'Sessao sem privilegio de superusuario (session_user=%). Abortando sem nenhuma alteracao.', session_user;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'nsi_dev')
       OR NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'nsi_test') THEN
        RAISE EXCEPTION 'Bancos nsi_dev e nsi_test precisam existir. Abortando sem nenhuma alteracao.';
    END IF;
END $$;

-- =============================================================
-- FASE 1 - PREFLIGHT. READ ONLY obrigatorio.
-- =============================================================
\echo 'FASE 1 - preflight (somente leitura).'
SET default_transaction_read_only = on;
DO $$
BEGIN
    IF current_setting('transaction_read_only') <> 'on' THEN
        RAISE EXCEPTION 'Modo somente leitura NAO esta ativo na Fase 1 (postgres). Abortando na preflight, sem nenhuma alteracao.';
    END IF;
END $$;

-- 1.1 - nenhuma sessao das duas roles pode estar aberta: este script nunca
-- derruba sessao.
DO $$
DECLARE total integer;
BEGIN
    SELECT count(*) INTO total FROM pg_stat_activity WHERE usename IN ('nsi_envio', 'nsi_webhook');
    IF total <> 0 THEN
        RAISE EXCEPTION 'Existem % sessao(oes) abertas de nsi_envio ou nsi_webhook. Encerre-as e execute de novo. Abortando na preflight, sem nenhuma alteracao.', total;
    END IF;
END $$;

-- 1.2 - nenhuma das duas roles e dona de objeto nem participa de membership.
DO $$
DECLARE total integer;
BEGIN
    SELECT count(*) INTO total
      FROM pg_shdepend s JOIN pg_roles r ON r.oid = s.refobjid
     WHERE s.refclassid = 'pg_authid'::regclass AND r.rolname IN ('nsi_envio', 'nsi_webhook') AND s.deptype = 'o';
    IF total <> 0 THEN
        RAISE EXCEPTION 'As roles a remover sao donas de % objeto(s). Abortando na preflight, sem nenhuma alteracao.', total;
    END IF;
    SELECT count(*) INTO total
      FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.member JOIN pg_roles g ON g.oid = m.roleid
     WHERE r.rolname IN ('nsi_envio', 'nsi_webhook') OR g.rolname IN ('nsi_envio', 'nsi_webhook');
    IF total <> 0 THEN
        RAISE EXCEPTION 'As roles a remover possuem % membership(s) inesperada(s). Abortando na preflight, sem nenhuma alteracao.', total;
    END IF;
END $$;

-- 1.3 - dentro de cada banco: a 0007 nao pode estar aplicada, e as duas
-- roles nao podem ter nenhum EXECUTE nem privilegio em tabela.
\c nsi_dev
SET default_transaction_read_only = on;
DO $$
DECLARE total integer;
BEGIN
    IF current_setting('transaction_read_only') <> 'on' THEN
        RAISE EXCEPTION 'Modo somente leitura NAO esta ativo na Fase 1 (%). Abortando na preflight, sem nenhuma alteracao.', current_database();
    END IF;
    IF (SELECT version_num FROM nsi_operacional.alembic_version) IS DISTINCT FROM '0006' THEN
        RAISE EXCEPTION 'Banco % fora da revisao 0006: a migration 0007 depende das roles. Abortando na preflight, sem nenhuma alteracao.', current_database();
    END IF;
    SELECT count(*) INTO total
      FROM pg_roles r, pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
     WHERE r.rolname IN ('nsi_envio', 'nsi_webhook') AND n.nspname = 'nsi_operacional'
       AND has_function_privilege(r.oid, p.oid, 'EXECUTE');
    IF total <> 0 THEN
        RAISE EXCEPTION 'As roles a remover ainda tem EXECUTE em % funcao(oes) de %. Abortando na preflight, sem nenhuma alteracao.', total, current_database();
    END IF;
END $$;

\c nsi_test
SET default_transaction_read_only = on;
DO $$
DECLARE total integer;
BEGIN
    IF current_setting('transaction_read_only') <> 'on' THEN
        RAISE EXCEPTION 'Modo somente leitura NAO esta ativo na Fase 1 (%). Abortando na preflight, sem nenhuma alteracao.', current_database();
    END IF;
    IF (SELECT version_num FROM nsi_operacional.alembic_version) IS DISTINCT FROM '0006' THEN
        RAISE EXCEPTION 'Banco % fora da revisao 0006: a migration 0007 depende das roles. Abortando na preflight, sem nenhuma alteracao.', current_database();
    END IF;
    SELECT count(*) INTO total
      FROM pg_roles r, pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
     WHERE r.rolname IN ('nsi_envio', 'nsi_webhook') AND n.nspname = 'nsi_operacional'
       AND has_function_privilege(r.oid, p.oid, 'EXECUTE');
    IF total <> 0 THEN
        RAISE EXCEPTION 'As roles a remover ainda tem EXECUTE em % funcao(oes) de %. Abortando na preflight, sem nenhuma alteracao.', total, current_database();
    END IF;
END $$;

\c postgres
SET default_transaction_read_only = on;
DO $$
BEGIN
    IF current_setting('transaction_read_only') <> 'on' THEN
        RAISE EXCEPTION 'Modo somente leitura NAO esta ativo na Fase 1 (postgres). Abortando na preflight, sem nenhuma alteracao.';
    END IF;
END $$;

\echo 'FASE 1 concluida - nenhuma escrita ocorreu.'

-- =============================================================
-- GATE DE CONFIRMACAO. Sempre exigido. Somente leitura.
-- =============================================================
\echo ''
\echo 'Este script REMOVE as roles nsi_envio e nsi_webhook e suas concessoes.'
\echo 'Para prosseguir, digite exatamente: CONFIRMO-DESPROVISIONAR-NSI-C3-ROLES-ENVIO'
\prompt 'Confirmacao: ' conf_resposta
SET default_transaction_read_only = on;
SELECT (:'conf_resposta' = 'CONFIRMO-DESPROVISIONAR-NSI-C3-ROLES-ENVIO') AS conf_pode_prosseguir
\gset
\if :conf_pode_prosseguir
    \echo 'Confirmacao aceita.'
\else
    \echo 'Confirmacao NAO conferida. Abortando sem nenhuma alteracao.'
    \quit
\endif

-- =============================================================
-- FASE 2 - REMOCAO. UNICO ponto do script em que a escrita e liberada.
-- Le o estado de novo: remove somente o que existir.
-- =============================================================
\echo 'FASE 2 - remocao (escrita liberada).'
SET default_transaction_read_only = off;

SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nsi_envio') AS f2_existe_envio,
       EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nsi_webhook') AS f2_existe_webhook
\gset

\c nsi_dev
\if :f2_existe_envio
    REVOKE USAGE ON SCHEMA nsi_operacional FROM nsi_envio;
\endif
\if :f2_existe_webhook
    REVOKE USAGE ON SCHEMA nsi_operacional FROM nsi_webhook;
\endif

\c nsi_test
\if :f2_existe_envio
    REVOKE USAGE ON SCHEMA nsi_operacional FROM nsi_envio;
\endif
\if :f2_existe_webhook
    REVOKE USAGE ON SCHEMA nsi_operacional FROM nsi_webhook;
\endif

\c postgres
\if :f2_existe_envio
    REVOKE CONNECT ON DATABASE nsi_dev FROM nsi_envio;
    REVOKE CONNECT ON DATABASE nsi_test FROM nsi_envio;
    DROP ROLE nsi_envio;
    \echo 'FASE 2: role nsi_envio removida.'
\else
    \echo 'FASE 2: role nsi_envio ausente, nada a fazer.'
\endif
\if :f2_existe_webhook
    REVOKE CONNECT ON DATABASE nsi_dev FROM nsi_webhook;
    REVOKE CONNECT ON DATABASE nsi_test FROM nsi_webhook;
    DROP ROLE nsi_webhook;
    \echo 'FASE 2: role nsi_webhook removida.'
\else
    \echo 'FASE 2: role nsi_webhook ausente, nada a fazer.'
\endif

\echo 'FASE 2 concluida.'

-- =============================================================
-- FASE 3 - POS-VALIDACAO COMPLETA. READ ONLY obrigatorio.
-- =============================================================
\echo 'FASE 3 - pos-validacao completa (somente leitura).'
SET default_transaction_read_only = on;
DO $$
BEGIN
    IF current_setting('transaction_read_only') <> 'on' THEN
        RAISE EXCEPTION 'Modo somente leitura NAO esta ativo na Fase 3 (postgres).';
    END IF;
END $$;

-- 3.1 - as duas roles nao existem mais.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname IN ('nsi_envio', 'nsi_webhook')) THEN
        RAISE EXCEPTION 'Pos-validacao falhou: nsi_envio ou nsi_webhook ainda existe.';
    END IF;
END $$;

-- 3.2 - as oito roles anteriores continuam na forma aprovada, com as tres
-- memberships aprovadas e nenhuma outra.
DO $$
DECLARE
    nome_role text; canlogin_esperado boolean; total integer; total_exatas integer;
BEGIN
    FOREACH nome_role IN ARRAY ARRAY['nsi_eventos_owner', 'nsi_aplicacao', 'nsi_expiracao', 'nsi_operador_restrito',
                                     'nsi_congelamento', 'nsi_importacao', 'nsi_dev_migrator', 'nsi_test_migrator'] LOOP
        canlogin_esperado := nome_role NOT IN ('nsi_eventos_owner', 'nsi_congelamento');
        SELECT count(*) INTO total FROM pg_roles
         WHERE rolname = nome_role AND rolcanlogin = canlogin_esperado AND NOT rolsuper AND NOT rolcreatedb
           AND NOT rolcreaterole AND NOT rolreplication AND NOT rolbypassrls;
        IF total <> 1 THEN
            RAISE EXCEPTION 'Pos-validacao falhou: role % ausente ou com atributos diferentes dos aprovados.', nome_role;
        END IF;
    END LOOP;
    SELECT count(*),
           count(*) FILTER (WHERE (g.rolname = 'nsi_eventos_owner' AND r.rolname IN ('nsi_dev_migrator', 'nsi_test_migrator')
                                   OR g.rolname = 'nsi_congelamento' AND r.rolname = 'nsi_aplicacao')
                              AND NOT m.inherit_option AND m.set_option AND NOT m.admin_option)
      INTO total, total_exatas
      FROM pg_auth_members m JOIN pg_roles g ON g.oid = m.roleid JOIN pg_roles r ON r.oid = m.member
     WHERE g.rolname LIKE 'nsi\_%' OR r.rolname LIKE 'nsi\_%';
    IF total <> 3 OR total_exatas <> 3 THEN
        RAISE EXCEPTION 'Pos-validacao falhou: memberships das roles do projeto fora do aprovado (linhas=%, exatas=%; esperado 3 e 3).', total, total_exatas;
    END IF;
END $$;

-- 3.3 - os dois bancos continuam na revisao 0006.
\c nsi_dev
SET default_transaction_read_only = on;
DO $$
BEGIN
    IF current_setting('transaction_read_only') <> 'on' THEN
        RAISE EXCEPTION 'Modo somente leitura NAO esta ativo na Fase 3 (%).', current_database();
    END IF;
    IF (SELECT version_num FROM nsi_operacional.alembic_version) IS DISTINCT FROM '0006' THEN
        RAISE EXCEPTION 'Pos-validacao falhou: banco % fora da revisao 0006.', current_database();
    END IF;
END $$;

\c nsi_test
SET default_transaction_read_only = on;
DO $$
BEGIN
    IF current_setting('transaction_read_only') <> 'on' THEN
        RAISE EXCEPTION 'Modo somente leitura NAO esta ativo na Fase 3 (%).', current_database();
    END IF;
    IF (SELECT version_num FROM nsi_operacional.alembic_version) IS DISTINCT FROM '0006' THEN
        RAISE EXCEPTION 'Pos-validacao falhou: banco % fora da revisao 0006.', current_database();
    END IF;
END $$;

\c postgres
SET default_transaction_read_only = on;

-- =============================================================
-- ENCERRAMENTO
-- =============================================================
\echo 'desprovisionar_c3_roles_envio.sql concluido - Fase 3 (pos-validacao completa) passou integralmente.'
\echo ''
\echo 'LEMBRETE: remover do .env local as quatro variaveis de conexao de nsi_envio e nsi_webhook.'
