-- =============================================================
-- scripts/postgres_local/provisionar_c3_roles_envio.sql
-- Sprint C (C3) - ADR-011 (Secao 11) / SPRINT-C-ESPECIFICACAO-TECNICA.md
-- (Secao 3).
--
-- APENAS PARA DESENVOLVIMENTO/TESTE LOCAL. NUNCA PRODUCAO.
--
-- Execute conectado ao banco de manutencao "postgres":
--
--     psql -U postgres -d postgres -f scripts/postgres_local/provisionar_c3_roles_envio.sql
--
-- Pre-requisitos: provisionamentos da B3.1, da B4.3 e da B5.3 ja executados
-- (as oito roles existem na forma aprovada); nsi_dev e nsi_test na MESMA
-- revisao, 0006 ou 0007; o banco descartavel nsi_ensaio NAO existe. Este
-- script NUNCA recria nem altera esses objetos.
--
-- O QUE ESTE SCRIPT FAZ (e nada alem disso):
--   1. cria as roles nsi_envio e nsi_webhook (LOGIN, atributos de seguranca
--      explicitos, sem senha), cada uma de proposito unico;
--   2. concede a cada uma CONNECT em nsi_dev e em nsi_test;
--   3. concede a cada uma USAGE no schema "nsi_operacional" dos dois bancos.
--
-- O QUE ESTE SCRIPT NUNCA FAZ: nao concede EXECUTE em funcao (isso e a
-- migration 0007); nao concede privilegio em tabela; nao concede CREATE;
-- nao cria membership de nenhuma das duas roles, em nenhum sentido (ADR-011,
-- Secao 11 - a excecao unica da ADR-009, Secao 21, continua unica); nao
-- altera atributo, senha ou membership de nenhuma role existente; nao
-- define senha; nunca corrige um estado divergente.
--
-- NAO CONTEM SENHA. As duas roles sao criadas SEM senha; o operador as
-- define interativamente, fora deste script, e configura as variaveis de
-- conexao no .env local (ver LEMBRETES no fim).
--
-- ESTE SCRIPT NAO E EXECUTADO AUTOMATICAMENTE por nenhum teste, por
-- migrations/env.py ou por qualquer codigo de aplicacao. Toda execucao e
-- um procedimento MANUAL autorizado.
--
-- ---------------------------------------------------------------
-- DESENHO DE TRES FASES
-- ---------------------------------------------------------------
-- FASE 1 (preflight): barreira global, somente leitura. Cada role nova
--   pode estar AUSENTE ou PRESENTE na forma exata; as concessoes dela podem
--   estar ausentes ou presentes, nunca diferentes das especificadas.
--   Qualquer outro estado ABORTA aqui.
--
-- FASE 2 (convergencia): unica fase que escreve. Le o estado de novo: cria
--   somente a role que faltar; as concessoes sao GRANT, que nao tem efeito
--   quando o privilegio ja existe. Reexecutar este script e seguro e nunca
--   toca senha.
--
-- FASE 3 (pos-validacao): reconfirma, a partir do zero e somente leitura,
--   TODO o estado final esperado.
--
-- GARANTIA - READ ONLY NAS FASES 1 E 3: o modo somente leitura e ligado no
--   inicio de cada fase e NOVAMENTE depois de cada \c (que abre uma sessao
--   nova, em modo normal); logo apos ligar, o script le o modo efetivo e
--   aborta se nao estiver ativo. A escrita so e liberada em UM ponto: o
--   marcador da Fase 2.
--
-- CADA FASE E AUTOSSUFICIENTE: nenhuma fase transmite estado para outra.
--   Variaveis de cliente do psql sao prefixadas pela fase (f2_) e nunca
--   cruzam fases.
--
-- EFEITO SOBRE OS DEMAIS SCRIPTS (limitacao aceita, no mesmo padrao da
--   B5.2, item 4, e da especificacao da B6, Secao 15): depois deste
--   provisionamento, os scripts da B3.1, da B4.3, da B5.3 e da B6 nao sao
--   reexecutaveis sem adaptacao, porque nao conhecem as duas roles novas.
--   Eles nao sao alterados.
-- =============================================================

\set ON_ERROR_STOP on

-- =============================================================
-- PROTECOES INICIAIS. Somente leitura - o modo e ligado antes de qualquer
-- outra consulta.
-- =============================================================
SET default_transaction_read_only = on;
DO $$
BEGIN
    IF current_setting('transaction_read_only') <> 'on' THEN
        RAISE EXCEPTION 'Modo somente leitura NAO esta ativo nas protecoes iniciais. Abortando sem nenhuma alteracao.';
    END IF;
END $$;

-- Verificacao de identidade do servidor - identica ao padrao da B3.1 a B6.
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

-- Privilegio de superusuario (CREATE ROLE exige).
DO $$
BEGIN
    IF current_setting('is_superuser') <> 'on' THEN
        RAISE EXCEPTION 'Sessao sem privilegio de superusuario (session_user=%). Abortando sem nenhuma alteracao.', session_user;
    END IF;
END $$;

-- Os dois bancos permanentes precisam existir; o de ensaio, nao.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'nsi_dev')
       OR NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'nsi_test') THEN
        RAISE EXCEPTION 'Bancos nsi_dev e nsi_test precisam existir. Abortando sem nenhuma alteracao.';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_database WHERE datname = 'nsi_ensaio')
       OR EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nsi_ensaio_migrator') THEN
        RAISE EXCEPTION 'O ambiente de ensaio da B6 existe. Descarte-o (desprovisionar_b6_ensaio.sql) antes deste provisionamento. Abortando sem nenhuma alteracao.';
    END IF;
END $$;

-- =============================================================
-- FASE 1 - PREFLIGHT. READ ONLY obrigatorio: nenhuma escrita ocorre a
-- partir daqui ate o marcador "FASE 2" abaixo.
-- =============================================================
\echo 'FASE 1 - preflight (somente leitura).'
SET default_transaction_read_only = on;
DO $$
BEGIN
    IF current_setting('transaction_read_only') <> 'on' THEN
        RAISE EXCEPTION 'Modo somente leitura NAO esta ativo na Fase 1 (postgres). Abortando na preflight, sem nenhuma alteracao.';
    END IF;
END $$;

-- 1.1 - as oito roles existentes, com os atributos aprovados.
DO $$
DECLARE
    nome_role text; canlogin_esperado boolean; total integer;
BEGIN
    FOREACH nome_role IN ARRAY ARRAY['nsi_eventos_owner', 'nsi_aplicacao', 'nsi_expiracao', 'nsi_operador_restrito',
                                     'nsi_congelamento', 'nsi_importacao', 'nsi_dev_migrator', 'nsi_test_migrator'] LOOP
        canlogin_esperado := nome_role NOT IN ('nsi_eventos_owner', 'nsi_congelamento');
        SELECT count(*) INTO total FROM pg_roles
         WHERE rolname = nome_role AND rolcanlogin = canlogin_esperado AND NOT rolsuper AND NOT rolcreatedb
           AND NOT rolcreaterole AND NOT rolreplication AND NOT rolbypassrls;
        IF total <> 1 THEN
            RAISE EXCEPTION 'Role % ausente ou com atributos diferentes dos aprovados (B3.1, B4.3, B5.3). Abortando na preflight, sem nenhuma alteracao.', nome_role;
        END IF;
    END LOOP;
END $$;

-- 1.2 - cada role nova: ausente, ou presente na forma exata; nunca com
-- membership, em nenhum sentido; nunca com concessao de banco diferente de
-- CONNECT em nsi_dev ou nsi_test; nunca dona de objeto.
DO $$
DECLARE
    nome_role text; total integer;
BEGIN
    FOREACH nome_role IN ARRAY ARRAY['nsi_envio', 'nsi_webhook'] LOOP
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = nome_role) THEN
            CONTINUE;
        END IF;
        SELECT count(*) INTO total FROM pg_roles
         WHERE rolname = nome_role AND rolcanlogin AND rolinherit AND NOT rolsuper AND NOT rolcreatedb
           AND NOT rolcreaterole AND NOT rolreplication AND NOT rolbypassrls;
        IF total <> 1 THEN
            RAISE EXCEPTION 'Role % existe com atributos diferentes dos especificados. Abortando na preflight, sem nenhuma alteracao.', nome_role;
        END IF;
        SELECT count(*) INTO total
          FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.member JOIN pg_roles g ON g.oid = m.roleid
         WHERE r.rolname = nome_role OR g.rolname = nome_role;
        IF total <> 0 THEN
            RAISE EXCEPTION 'Role % possui % membership(s); o especificado e nenhuma, em nenhum sentido. Abortando na preflight, sem nenhuma alteracao.', nome_role, total;
        END IF;
        SELECT count(*) INTO total
          FROM pg_database d CROSS JOIN LATERAL aclexplode(d.datacl) a JOIN pg_roles g ON g.oid = a.grantee
         WHERE g.rolname = nome_role
           AND NOT (d.datname IN ('nsi_dev', 'nsi_test') AND a.privilege_type = 'CONNECT' AND NOT a.is_grantable);
        IF total <> 0 THEN
            RAISE EXCEPTION 'Role % possui % concessao(oes) de banco fora do especificado. Abortando na preflight, sem nenhuma alteracao.', nome_role, total;
        END IF;
        SELECT count(*) INTO total
          FROM pg_shdepend s JOIN pg_roles r ON r.oid = s.refobjid
         WHERE s.refclassid = 'pg_authid'::regclass AND r.rolname = nome_role AND s.deptype = 'o';
        IF total <> 0 THEN
            RAISE EXCEPTION 'Role % e dona de % objeto(s). Abortando na preflight, sem nenhuma alteracao.', nome_role, total;
        END IF;
    END LOOP;
END $$;

-- 1.3 - a excecao unica de membership da ADR-009 (Secao 21) continua unica.
DO $$
DECLARE total integer; total_exatas integer;
BEGIN
    SELECT count(*),
           count(*) FILTER (WHERE (g.rolname = 'nsi_eventos_owner' AND r.rolname IN ('nsi_dev_migrator', 'nsi_test_migrator')
                                   OR g.rolname = 'nsi_congelamento' AND r.rolname = 'nsi_aplicacao')
                              AND NOT m.inherit_option AND m.set_option AND NOT m.admin_option)
      INTO total, total_exatas
      FROM pg_auth_members m JOIN pg_roles g ON g.oid = m.roleid JOIN pg_roles r ON r.oid = m.member
     WHERE g.rolname LIKE 'nsi\_%' OR r.rolname LIKE 'nsi\_%';
    IF total <> 3 OR total_exatas <> 3 THEN
        RAISE EXCEPTION 'Memberships das roles do projeto fora do aprovado (linhas=%, exatas=%; esperado 3 e 3). Abortando na preflight, sem nenhuma alteracao.', total, total_exatas;
    END IF;
END $$;

-- 1.4 - dentro de cada banco: revisao 0006 ou 0007, e nenhuma concessao de
-- schema as roles novas diferente de USAGE.
\c nsi_dev
SET default_transaction_read_only = on;
DO $$
DECLARE total integer;
BEGIN
    IF current_setting('transaction_read_only') <> 'on' THEN
        RAISE EXCEPTION 'Modo somente leitura NAO esta ativo na Fase 1 (%). Abortando na preflight, sem nenhuma alteracao.', current_database();
    END IF;
    IF (SELECT version_num FROM nsi_operacional.alembic_version) NOT IN ('0006', '0007') THEN
        RAISE EXCEPTION 'Banco % fora das revisoes 0006 e 0007. Abortando na preflight, sem nenhuma alteracao.', current_database();
    END IF;
    SELECT count(*) INTO total
      FROM pg_namespace n CROSS JOIN LATERAL aclexplode(n.nspacl) a JOIN pg_roles g ON g.oid = a.grantee
     WHERE g.rolname IN ('nsi_envio', 'nsi_webhook')
       AND NOT (n.nspname = 'nsi_operacional' AND a.privilege_type = 'USAGE' AND NOT a.is_grantable);
    IF total <> 0 THEN
        RAISE EXCEPTION 'Concessao de schema fora do especificado para as roles novas em % (%). Abortando na preflight, sem nenhuma alteracao.', current_database(), total;
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
    IF (SELECT version_num FROM nsi_operacional.alembic_version) NOT IN ('0006', '0007') THEN
        RAISE EXCEPTION 'Banco % fora das revisoes 0006 e 0007. Abortando na preflight, sem nenhuma alteracao.', current_database();
    END IF;
    SELECT count(*) INTO total
      FROM pg_namespace n CROSS JOIN LATERAL aclexplode(n.nspacl) a JOIN pg_roles g ON g.oid = a.grantee
     WHERE g.rolname IN ('nsi_envio', 'nsi_webhook')
       AND NOT (n.nspname = 'nsi_operacional' AND a.privilege_type = 'USAGE' AND NOT a.is_grantable);
    IF total <> 0 THEN
        RAISE EXCEPTION 'Concessao de schema fora do especificado para as roles novas em % (%). Abortando na preflight, sem nenhuma alteracao.', current_database(), total;
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

\echo 'FASE 1 concluida - estado previsto; nenhuma escrita ocorreu.'

-- =============================================================
-- FASE 2 - CONVERGENCIA. UNICO ponto do script em que a escrita e
-- liberada. Le o estado de novo: cria somente a role que faltar.
-- =============================================================
\echo 'FASE 2 - convergencia (escrita liberada).'
SET default_transaction_read_only = off;

SELECT NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nsi_envio') AS f2_falta_envio,
       NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nsi_webhook') AS f2_falta_webhook
\gset

-- Acao 1 - role de envio, sem senha.
\if :f2_falta_envio
    CREATE ROLE nsi_envio LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
    \echo 'FASE 2: role nsi_envio criada.'
\else
    \echo 'FASE 2: role nsi_envio ja presente, nada a fazer.'
\endif

-- Acao 2 - role de webhook, sem senha.
\if :f2_falta_webhook
    CREATE ROLE nsi_webhook LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
    \echo 'FASE 2: role nsi_webhook criada.'
\else
    \echo 'FASE 2: role nsi_webhook ja presente, nada a fazer.'
\endif

-- Acao 3 - CONNECT nos dois bancos permanentes (sem efeito se ja existir).
GRANT CONNECT ON DATABASE nsi_dev TO nsi_envio;
GRANT CONNECT ON DATABASE nsi_test TO nsi_envio;
GRANT CONNECT ON DATABASE nsi_dev TO nsi_webhook;
GRANT CONNECT ON DATABASE nsi_test TO nsi_webhook;

-- Acao 4 - USAGE no schema, dentro de cada banco (sem efeito se ja existir).
\c nsi_dev
GRANT USAGE ON SCHEMA nsi_operacional TO nsi_envio;
GRANT USAGE ON SCHEMA nsi_operacional TO nsi_webhook;
\c nsi_test
GRANT USAGE ON SCHEMA nsi_operacional TO nsi_envio;
GRANT USAGE ON SCHEMA nsi_operacional TO nsi_webhook;
\c postgres

\echo 'FASE 2 concluida.'

-- =============================================================
-- FASE 3 - POS-VALIDACAO COMPLETA. READ ONLY obrigatorio. Reconfirma, a
-- partir do zero, TODO o estado final.
-- =============================================================
\echo 'FASE 3 - pos-validacao completa (somente leitura).'
SET default_transaction_read_only = on;
DO $$
BEGIN
    IF current_setting('transaction_read_only') <> 'on' THEN
        RAISE EXCEPTION 'Modo somente leitura NAO esta ativo na Fase 3 (postgres).';
    END IF;
END $$;

-- 3.1 - as oito roles existentes continuam na forma aprovada.
DO $$
DECLARE
    nome_role text; canlogin_esperado boolean; total integer;
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
END $$;

-- 3.2 - as duas roles novas: atributos exatos, nenhuma membership, CONNECT
-- exatamente em nsi_dev e nsi_test, nenhum objeto proprio.
DO $$
DECLARE
    nome_role text; total integer; total_esperadas integer;
BEGIN
    FOREACH nome_role IN ARRAY ARRAY['nsi_envio', 'nsi_webhook'] LOOP
        SELECT count(*) INTO total FROM pg_roles
         WHERE rolname = nome_role AND rolcanlogin AND rolinherit AND NOT rolsuper AND NOT rolcreatedb
           AND NOT rolcreaterole AND NOT rolreplication AND NOT rolbypassrls;
        IF total <> 1 THEN
            RAISE EXCEPTION 'Pos-validacao falhou: role % ausente ou com atributos diferentes dos especificados.', nome_role;
        END IF;
        SELECT count(*) INTO total
          FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.member JOIN pg_roles g ON g.oid = m.roleid
         WHERE r.rolname = nome_role OR g.rolname = nome_role;
        IF total <> 0 THEN
            RAISE EXCEPTION 'Pos-validacao falhou: role % possui % membership(s).', nome_role, total;
        END IF;
        SELECT count(*),
               count(*) FILTER (WHERE d.datname IN ('nsi_dev', 'nsi_test') AND a.privilege_type = 'CONNECT' AND NOT a.is_grantable)
          INTO total, total_esperadas
          FROM pg_database d CROSS JOIN LATERAL aclexplode(d.datacl) a JOIN pg_roles g ON g.oid = a.grantee
         WHERE g.rolname = nome_role;
        IF total <> 2 OR total_esperadas <> 2 THEN
            RAISE EXCEPTION 'Pos-validacao falhou: concessoes de banco de % fora do especificado (linhas=%, esperadas=%; esperado 2 e 2).', nome_role, total, total_esperadas;
        END IF;
        IF has_database_privilege(nome_role, 'postgres', 'CREATE')
           OR has_database_privilege(nome_role, 'nsi_dev', 'CREATE')
           OR has_database_privilege(nome_role, 'nsi_test', 'CREATE') THEN
            RAISE EXCEPTION 'Pos-validacao falhou: role % com CREATE em banco.', nome_role;
        END IF;
        SELECT count(*) INTO total
          FROM pg_shdepend s JOIN pg_roles r ON r.oid = s.refobjid
         WHERE s.refclassid = 'pg_authid'::regclass AND r.rolname = nome_role AND s.deptype = 'o';
        IF total <> 0 THEN
            RAISE EXCEPTION 'Pos-validacao falhou: role % e dona de % objeto(s).', nome_role, total;
        END IF;
    END LOOP;
END $$;

-- 3.3 - memberships das roles do projeto: exatamente as tres aprovadas.
DO $$
DECLARE total integer; total_exatas integer;
BEGIN
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

-- 3.4 - dentro de cada banco: USAGE no schema, sem CREATE, sem privilegio
-- em tabela; EXECUTE em funcao somente se a 0007 ja estiver aplicada.
\c nsi_dev
SET default_transaction_read_only = on;
DO $$
DECLARE
    nome_role text; total integer; revisao text;
BEGIN
    IF current_setting('transaction_read_only') <> 'on' THEN
        RAISE EXCEPTION 'Modo somente leitura NAO esta ativo na Fase 3 (%).', current_database();
    END IF;
    SELECT version_num INTO revisao FROM nsi_operacional.alembic_version;
    IF revisao NOT IN ('0006', '0007') THEN
        RAISE EXCEPTION 'Pos-validacao falhou: banco % fora das revisoes 0006 e 0007.', current_database();
    END IF;
    FOREACH nome_role IN ARRAY ARRAY['nsi_envio', 'nsi_webhook'] LOOP
        SELECT count(*) INTO total
          FROM pg_namespace n CROSS JOIN LATERAL aclexplode(n.nspacl) a JOIN pg_roles g ON g.oid = a.grantee
         WHERE g.rolname = nome_role AND n.nspname = 'nsi_operacional' AND a.privilege_type = 'USAGE' AND NOT a.is_grantable;
        IF total <> 1 OR has_schema_privilege(nome_role, 'nsi_operacional', 'CREATE') THEN
            RAISE EXCEPTION 'Pos-validacao falhou: schema de % fora do especificado para % (USAGE=%).', current_database(), nome_role, total;
        END IF;
        SELECT count(*) INTO total FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = 'nsi_operacional' AND c.relkind IN ('r', 'v', 'm', 'S')
           AND (has_table_privilege(nome_role, c.oid, 'SELECT') OR has_table_privilege(nome_role, c.oid, 'INSERT')
                OR has_table_privilege(nome_role, c.oid, 'UPDATE') OR has_table_privilege(nome_role, c.oid, 'DELETE'));
        IF total <> 0 THEN
            RAISE EXCEPTION 'Pos-validacao falhou: role % com privilegio em % tabela(s) de %.', nome_role, total, current_database();
        END IF;
        SELECT count(*) INTO total FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
         WHERE n.nspname = 'nsi_operacional' AND has_function_privilege(nome_role, p.oid, 'EXECUTE');
        IF revisao = '0006' AND total <> 0 THEN
            RAISE EXCEPTION 'Pos-validacao falhou: role % com EXECUTE em % funcao(oes) de % antes da 0007.', nome_role, total, current_database();
        END IF;
    END LOOP;
END $$;

\c nsi_test
SET default_transaction_read_only = on;
DO $$
DECLARE
    nome_role text; total integer; revisao text;
BEGIN
    IF current_setting('transaction_read_only') <> 'on' THEN
        RAISE EXCEPTION 'Modo somente leitura NAO esta ativo na Fase 3 (%).', current_database();
    END IF;
    SELECT version_num INTO revisao FROM nsi_operacional.alembic_version;
    IF revisao NOT IN ('0006', '0007') THEN
        RAISE EXCEPTION 'Pos-validacao falhou: banco % fora das revisoes 0006 e 0007.', current_database();
    END IF;
    FOREACH nome_role IN ARRAY ARRAY['nsi_envio', 'nsi_webhook'] LOOP
        SELECT count(*) INTO total
          FROM pg_namespace n CROSS JOIN LATERAL aclexplode(n.nspacl) a JOIN pg_roles g ON g.oid = a.grantee
         WHERE g.rolname = nome_role AND n.nspname = 'nsi_operacional' AND a.privilege_type = 'USAGE' AND NOT a.is_grantable;
        IF total <> 1 OR has_schema_privilege(nome_role, 'nsi_operacional', 'CREATE') THEN
            RAISE EXCEPTION 'Pos-validacao falhou: schema de % fora do especificado para % (USAGE=%).', current_database(), nome_role, total;
        END IF;
        SELECT count(*) INTO total FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = 'nsi_operacional' AND c.relkind IN ('r', 'v', 'm', 'S')
           AND (has_table_privilege(nome_role, c.oid, 'SELECT') OR has_table_privilege(nome_role, c.oid, 'INSERT')
                OR has_table_privilege(nome_role, c.oid, 'UPDATE') OR has_table_privilege(nome_role, c.oid, 'DELETE'));
        IF total <> 0 THEN
            RAISE EXCEPTION 'Pos-validacao falhou: role % com privilegio em % tabela(s) de %.', nome_role, total, current_database();
        END IF;
        SELECT count(*) INTO total FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
         WHERE n.nspname = 'nsi_operacional' AND has_function_privilege(nome_role, p.oid, 'EXECUTE');
        IF revisao = '0006' AND total <> 0 THEN
            RAISE EXCEPTION 'Pos-validacao falhou: role % com EXECUTE em % funcao(oes) de % antes da 0007.', nome_role, total, current_database();
        END IF;
    END LOOP;
END $$;

\c postgres
SET default_transaction_read_only = on;

-- =============================================================
-- ENCERRAMENTO
-- =============================================================
\echo 'provisionar_c3_roles_envio.sql concluido - Fase 3 (pos-validacao completa) passou integralmente.'
\echo ''
\echo 'LEMBRETES (manuais, fora deste script):'
\echo '  1. Definir as senhas:  \\password nsi_envio   e   \\password nsi_webhook'
\echo '  2. Configurar no .env local, fora do versionamento, no formato postgresql://'
\echo '       DATABASE_URL_NSI_ENVIO      e TEST_DATABASE_URL_NSI_ENVIO'
\echo '       DATABASE_URL_NSI_WEBHOOK    e TEST_DATABASE_URL_NSI_WEBHOOK'
\echo '  3. EXECUTE em funcao so e concedido pela migration 0007.'
