-- =============================================================
-- scripts/postgres_local/provisionar_b3_roles.sql
-- Sprint B (B3.1) - ADR-008 / Especificacao Tecnica da Sprint B,
-- Parte 1 da B3 (APROVADA E ENCERRADA) e correcoes de seguranca da
-- PARTE 2A (APROVADA).
--
-- APENAS PARA DESENVOLVIMENTO/TESTE LOCAL. NUNCA PRODUCAO.
--
-- Execute conectado ao banco de manutencao "postgres":
--
--     psql -U postgres -d postgres -f scripts/postgres_local/provisionar_b3_roles.sql
--
-- Pre-requisito: scripts/postgres_local/provisionar_dev_teste.sql (B2.2/
-- B2.3) ja executado - roles nsi_dev_migrator/nsi_test_migrator e os
-- bancos nsi_dev/nsi_test com o schema "nsi_operacional" ja existem. Este
-- script NUNCA recria esses objetos - trata apenas os passos
-- administrativos proprios da B3.1.
--
-- Cria as quatro roles funcionais aprovadas (nsi_eventos_owner,
-- nsi_aplicacao, nsi_expiracao, nsi_operador_restrito), com TODOS os
-- atributos de seguranca explicitos (nunca apenas o default do
-- PostgreSQL); concede a nsi_dev_migrator/nsi_test_migrator a capacidade
-- de SET ROLE nsi_eventos_owner sem heranca automatica e sem ADMIN
-- OPTION; transfere a propriedade do schema "nsi_operacional" para
-- nsi_eventos_owner nos dois bancos; aplica isolamento de CONNECT por
-- banco (nunca depende apenas de propriedade implicita de banco).
--
-- Requer privilegio de superusuario (ou CREATEROLE, mais ALTER em cada
-- schema) - nesta maquina, o usuario "postgres" da instalacao local.
--
-- NAO CONTEM SENHA. As tres roles LOGIN (nsi_aplicacao, nsi_expiracao,
-- nsi_operador_restrito) sao criadas SEM senha - definida DEPOIS,
-- interativamente, via \password (fora deste arquivo - ver bloco
-- "PROXIMOS PASSOS" ao final). nsi_eventos_owner e NOLOGIN - nunca
-- recebe senha, nunca e usada para conexao de aplicacao.
--
-- ESTE SCRIPT NAO E EXECUTADO AUTOMATICAMENTE por nenhum teste, por
-- migrations/env.py ou por qualquer codigo de aplicacao. Execucao manual,
-- uma unica vez por convergencia desejada, mediante autorizacao
-- especifica e separada - mesma disciplina ja usada em B2.2/B2.3. Uma
-- segunda execucao (idempotente, ver desenho de tres fases abaixo) e
-- tambem sempre um procedimento MANUAL autorizado, nunca disparada por
-- nenhum teste automatizado.
--
-- ---------------------------------------------------------------
-- DESENHO DE TRES FASES (convergencia segura, nunca correcao silenciosa)
-- ---------------------------------------------------------------
-- FASE 1 (leitura): valida CADA uma das quatro roles (se ja existir: os
--   seis atributos de seguranca + ausencia de membership inesperada),
--   as duas memberships dos migrators (se ja existirem: INHERIT FALSE,
--   SET TRUE, ADMIN FALSE) e a propriedade do schema nos dois bancos.
--   Qualquer estado inesperado ABORTA aqui - nenhuma escrita ainda
--   ocorreu em lugar nenhum. Cada decisao de convergencia (precisa
--   criar? precisa conceder membership? precisa alterar owner?) e
--   capturada em uma variavel de CLIENTE do psql (\gset) - essas
--   variaveis SAO preservadas atraves de \c (\c reinicia apenas a
--   sessao/conexao do SERVIDOR; variaveis do psql sao locais ao proprio
--   cliente psql, nunca ao backend).
--
-- FASE 2 (escrita): so executa CREATE ROLE/GRANT/ALTER ja autorizados
--   pela Fase 1, via os comandos de cliente \if - nunca recalcula a
--   decisao aqui. GRANT/REVOKE de CONNECT e USAGE sao ACLs declarativas,
--   naturalmente idempotentes no PostgreSQL (reaplicar nao e erro nem
--   ambiguidade) - por isso ficam fora do padrao \if, sempre reaplicadas.
--
-- FASE 3 (pos-validacao completa): reconfirma, a partir do zero, TODO o
--   estado esperado - nao so o owner do schema: atributos das quatro
--   roles, ausencia de membership inesperada, as duas memberships dos
--   migrators com as tres opcoes corretas, PUBLIC sem CONNECT nos dois
--   bancos, cada migrator com CONNECT somente no seu proprio banco, as
--   tres roles funcionais com CONNECT nos dois bancos, owner do schema
--   nos dois bancos, USAGE correto, e alembic_version ainda pertencendo
--   ao migrator correspondente (nunca ao owner).
--
-- LIMITE ESTRUTURAL DE \c: o PostgreSQL nao tem transacao distribuida
--   nativa entre bancos diferentes do mesmo cluster, e \c fecha a
--   conexao/transacao anterior. A Fase 1 global NAO cria atomicidade
--   entre nsi_dev e nsi_test - ela elimina a classe de falha "ja
--   escrevi X, descobri que Y esta incompativel, X fica orfao", porque
--   TODAS as validacoes (dos tres contextos de conexao) rodam antes de
--   qualquer escrita em qualquer lugar. O risco remanescente e
--   estritamente: uma falha NOVA em tempo de execucao (rede, disco) na
--   Fase 2 de nsi_test, depois que a Fase 2 de nsi_dev ja comitou - nao
--   eliminavel sem transacao distribuida. A resposta a esse residual e
--   reexecutar este mesmo script (idempotente por desenho), nunca
--   desprovisionar como "conserto".
-- =============================================================

\set ON_ERROR_STOP on

-- Verificacao de identidade do servidor - identica ao padrao ja usado em
-- provisionar_dev_teste.sql (B2.2).
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

-- Pre-requisitos de B2 (leitura, abort-only) - os dois migrators e os
-- dois bancos precisam ja existir; este script nunca os cria.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nsi_dev_migrator') THEN
        RAISE EXCEPTION 'nsi_dev_migrator nao existe - execute provisionar_dev_teste.sql (B2.2) antes deste script.';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nsi_test_migrator') THEN
        RAISE EXCEPTION 'nsi_test_migrator nao existe - execute provisionar_dev_teste.sql (B2.2) antes deste script.';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'nsi_dev') THEN
        RAISE EXCEPTION 'Banco nsi_dev nao existe - execute provisionar_dev_teste.sql (B2.2) antes deste script.';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'nsi_test') THEN
        RAISE EXCEPTION 'Banco nsi_test nao existe - execute provisionar_dev_teste.sql (B2.2) antes deste script.';
    END IF;
END $$;

-- =============================================================
-- FASE 1 - SOMENTE LEITURA. Nenhum CREATE/ALTER/GRANT/REVOKE ocorre a
-- partir daqui ate o marcador "FASE 2" abaixo.
-- =============================================================

-- 1.1 - nsi_eventos_owner: existencia + seis atributos de seguranca +
-- ausencia de membership inesperada (nao pode herdar/pertencer a
-- nenhuma outra role). rolinherit nao foi listado nos atributos exigidos
-- pela correcao aprovada - mantido no default do PostgreSQL (true); como
-- esta role nao pertence a nenhuma outra (verificado a seguir), o valor
-- de rolinherit e irrelevante em efeito pratico nesta sprint, mas e
-- validado mesmo assim por completude e para detectar alteracao manual
-- futura.
SELECT CASE WHEN NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nsi_eventos_owner')
            THEN 'true' ELSE 'false' END AS precisa_criar_owner
\gset

DO $$
DECLARE
    canlogin_atual boolean; super_atual boolean; createdb_atual boolean;
    createrole_atual boolean; replication_atual boolean; bypassrls_atual boolean;
    inherit_atual boolean; total_memberships integer;
BEGIN
    SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls, rolinherit
      INTO canlogin_atual, super_atual, createdb_atual, createrole_atual, replication_atual, bypassrls_atual, inherit_atual
      FROM pg_roles WHERE rolname = 'nsi_eventos_owner';
    IF FOUND THEN
        IF canlogin_atual IS DISTINCT FROM false OR super_atual IS DISTINCT FROM false
           OR createdb_atual IS DISTINCT FROM false OR createrole_atual IS DISTINCT FROM false
           OR replication_atual IS DISTINCT FROM false OR bypassrls_atual IS DISTINCT FROM false
           OR inherit_atual IS DISTINCT FROM true THEN
            RAISE EXCEPTION 'Role nsi_eventos_owner ja existe com atributos incompativeis (canlogin=%, super=%, createdb=%, createrole=%, replication=%, bypassrls=%, inherit=%; esperado false/false/false/false/false/false/true). Abortando na preflight, sem nenhuma alteracao.',
                canlogin_atual, super_atual, createdb_atual, createrole_atual, replication_atual, bypassrls_atual, inherit_atual;
        END IF;
    END IF;

    SELECT count(*) INTO total_memberships
      FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.member
     WHERE r.rolname = 'nsi_eventos_owner';
    IF total_memberships <> 0 THEN
        RAISE EXCEPTION 'Role nsi_eventos_owner ja pertence a % outra(s) role(s) - esperado zero (nao pode herdar nem pertencer a role privilegiada). Abortando na preflight, sem nenhuma alteracao.', total_memberships;
    END IF;
END $$;

-- 1.2 - nsi_aplicacao / nsi_expiracao / nsi_operador_restrito: mesmo
-- padrao (canlogin esperado TRUE), repetido explicitamente por role.
SELECT CASE WHEN NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nsi_aplicacao')
            THEN 'true' ELSE 'false' END AS precisa_criar_aplicacao
\gset
DO $$
DECLARE
    canlogin_atual boolean; super_atual boolean; createdb_atual boolean;
    createrole_atual boolean; replication_atual boolean; bypassrls_atual boolean;
    inherit_atual boolean; total_memberships integer;
BEGIN
    SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls, rolinherit
      INTO canlogin_atual, super_atual, createdb_atual, createrole_atual, replication_atual, bypassrls_atual, inherit_atual
      FROM pg_roles WHERE rolname = 'nsi_aplicacao';
    IF FOUND THEN
        IF canlogin_atual IS DISTINCT FROM true OR super_atual IS DISTINCT FROM false
           OR createdb_atual IS DISTINCT FROM false OR createrole_atual IS DISTINCT FROM false
           OR replication_atual IS DISTINCT FROM false OR bypassrls_atual IS DISTINCT FROM false
           OR inherit_atual IS DISTINCT FROM true THEN
            RAISE EXCEPTION 'Role nsi_aplicacao ja existe com atributos incompativeis (canlogin=%, super=%, createdb=%, createrole=%, replication=%, bypassrls=%, inherit=%; esperado true/false/false/false/false/false/true). Abortando na preflight, sem nenhuma alteracao.',
                canlogin_atual, super_atual, createdb_atual, createrole_atual, replication_atual, bypassrls_atual, inherit_atual;
        END IF;
    END IF;

    SELECT count(*) INTO total_memberships
      FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.member
     WHERE r.rolname = 'nsi_aplicacao';
    IF total_memberships <> 0 THEN
        RAISE EXCEPTION 'Role nsi_aplicacao ja pertence a % outra(s) role(s) - esperado zero. Abortando na preflight, sem nenhuma alteracao.', total_memberships;
    END IF;
END $$;

SELECT CASE WHEN NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nsi_expiracao')
            THEN 'true' ELSE 'false' END AS precisa_criar_expiracao
\gset
DO $$
DECLARE
    canlogin_atual boolean; super_atual boolean; createdb_atual boolean;
    createrole_atual boolean; replication_atual boolean; bypassrls_atual boolean;
    inherit_atual boolean; total_memberships integer;
BEGIN
    SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls, rolinherit
      INTO canlogin_atual, super_atual, createdb_atual, createrole_atual, replication_atual, bypassrls_atual, inherit_atual
      FROM pg_roles WHERE rolname = 'nsi_expiracao';
    IF FOUND THEN
        IF canlogin_atual IS DISTINCT FROM true OR super_atual IS DISTINCT FROM false
           OR createdb_atual IS DISTINCT FROM false OR createrole_atual IS DISTINCT FROM false
           OR replication_atual IS DISTINCT FROM false OR bypassrls_atual IS DISTINCT FROM false
           OR inherit_atual IS DISTINCT FROM true THEN
            RAISE EXCEPTION 'Role nsi_expiracao ja existe com atributos incompativeis (canlogin=%, super=%, createdb=%, createrole=%, replication=%, bypassrls=%, inherit=%; esperado true/false/false/false/false/false/true). Abortando na preflight, sem nenhuma alteracao.',
                canlogin_atual, super_atual, createdb_atual, createrole_atual, replication_atual, bypassrls_atual, inherit_atual;
        END IF;
    END IF;

    SELECT count(*) INTO total_memberships
      FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.member
     WHERE r.rolname = 'nsi_expiracao';
    IF total_memberships <> 0 THEN
        RAISE EXCEPTION 'Role nsi_expiracao ja pertence a % outra(s) role(s) - esperado zero. Abortando na preflight, sem nenhuma alteracao.', total_memberships;
    END IF;
END $$;

SELECT CASE WHEN NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nsi_operador_restrito')
            THEN 'true' ELSE 'false' END AS precisa_criar_operador
\gset
DO $$
DECLARE
    canlogin_atual boolean; super_atual boolean; createdb_atual boolean;
    createrole_atual boolean; replication_atual boolean; bypassrls_atual boolean;
    inherit_atual boolean; total_memberships integer;
BEGIN
    SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls, rolinherit
      INTO canlogin_atual, super_atual, createdb_atual, createrole_atual, replication_atual, bypassrls_atual, inherit_atual
      FROM pg_roles WHERE rolname = 'nsi_operador_restrito';
    IF FOUND THEN
        IF canlogin_atual IS DISTINCT FROM true OR super_atual IS DISTINCT FROM false
           OR createdb_atual IS DISTINCT FROM false OR createrole_atual IS DISTINCT FROM false
           OR replication_atual IS DISTINCT FROM false OR bypassrls_atual IS DISTINCT FROM false
           OR inherit_atual IS DISTINCT FROM true THEN
            RAISE EXCEPTION 'Role nsi_operador_restrito ja existe com atributos incompativeis (canlogin=%, super=%, createdb=%, createrole=%, replication=%, bypassrls=%, inherit=%; esperado true/false/false/false/false/false/true). Abortando na preflight, sem nenhuma alteracao.',
                canlogin_atual, super_atual, createdb_atual, createrole_atual, replication_atual, bypassrls_atual, inherit_atual;
        END IF;
    END IF;

    SELECT count(*) INTO total_memberships
      FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.member
     WHERE r.rolname = 'nsi_operador_restrito';
    IF total_memberships <> 0 THEN
        RAISE EXCEPTION 'Role nsi_operador_restrito ja pertence a % outra(s) role(s) - esperado zero. Abortando na preflight, sem nenhuma alteracao.', total_memberships;
    END IF;
END $$;

-- 1.3 - memberships dos dois migrators (validar-ou-criar na Fase 2,
-- nunca REVOKE+GRANT cego, que seria "corrigir silenciosamente").
SELECT CASE WHEN NOT EXISTS (
    SELECT 1 FROM pg_auth_members m
    JOIN pg_roles r_role ON r_role.oid = m.roleid
    JOIN pg_roles r_member ON r_member.oid = m.member
    WHERE r_role.rolname = 'nsi_eventos_owner' AND r_member.rolname = 'nsi_dev_migrator'
) THEN 'true' ELSE 'false' END AS precisa_grant_membership_dev
\gset
DO $$
DECLARE inherit_atual boolean; set_atual boolean; admin_atual boolean;
BEGIN
    SELECT m.inherit_option, m.set_option, m.admin_option
      INTO inherit_atual, set_atual, admin_atual
      FROM pg_auth_members m
      JOIN pg_roles r_role ON r_role.oid = m.roleid
      JOIN pg_roles r_member ON r_member.oid = m.member
     WHERE r_role.rolname = 'nsi_eventos_owner' AND r_member.rolname = 'nsi_dev_migrator';
    IF FOUND THEN
        IF inherit_atual IS DISTINCT FROM false OR set_atual IS DISTINCT FROM true OR admin_atual IS DISTINCT FROM false THEN
            RAISE EXCEPTION 'Membership nsi_dev_migrator em nsi_eventos_owner ja existe com opcoes incompativeis (inherit=%, set=%, admin=%; esperado false/true/false). Abortando na preflight, sem nenhuma alteracao.', inherit_atual, set_atual, admin_atual;
        END IF;
    END IF;
END $$;

SELECT CASE WHEN NOT EXISTS (
    SELECT 1 FROM pg_auth_members m
    JOIN pg_roles r_role ON r_role.oid = m.roleid
    JOIN pg_roles r_member ON r_member.oid = m.member
    WHERE r_role.rolname = 'nsi_eventos_owner' AND r_member.rolname = 'nsi_test_migrator'
) THEN 'true' ELSE 'false' END AS precisa_grant_membership_test
\gset
DO $$
DECLARE inherit_atual boolean; set_atual boolean; admin_atual boolean;
BEGIN
    SELECT m.inherit_option, m.set_option, m.admin_option
      INTO inherit_atual, set_atual, admin_atual
      FROM pg_auth_members m
      JOIN pg_roles r_role ON r_role.oid = m.roleid
      JOIN pg_roles r_member ON r_member.oid = m.member
     WHERE r_role.rolname = 'nsi_eventos_owner' AND r_member.rolname = 'nsi_test_migrator';
    IF FOUND THEN
        IF inherit_atual IS DISTINCT FROM false OR set_atual IS DISTINCT FROM true OR admin_atual IS DISTINCT FROM false THEN
            RAISE EXCEPTION 'Membership nsi_test_migrator em nsi_eventos_owner ja existe com opcoes incompativeis (inherit=%, set=%, admin=%; esperado false/true/false). Abortando na preflight, sem nenhuma alteracao.', inherit_atual, set_atual, admin_atual;
        END IF;
    END IF;
END $$;

-- 1.4 - propriedade do schema em nsi_dev.
\c nsi_dev
DO $$
DECLARE dono_atual name;
BEGIN
    SELECT rolname INTO dono_atual
      FROM pg_namespace n JOIN pg_roles r ON r.oid = n.nspowner
     WHERE n.nspname = 'nsi_operacional';
    IF dono_atual IS NULL THEN
        RAISE EXCEPTION 'Schema nsi_operacional nao existe em nsi_dev - execute provisionar_dev_teste.sql (B2.2) antes deste script.';
    END IF;
    IF dono_atual NOT IN ('nsi_dev_migrator', 'nsi_eventos_owner') THEN
        RAISE EXCEPTION 'Schema nsi_operacional em nsi_dev tem dono inesperado (%) - esperado nsi_dev_migrator (1a execucao) ou nsi_eventos_owner (execucao repetida). Abortando na preflight, sem nenhuma alteracao.', dono_atual;
    END IF;
END $$;
SELECT CASE WHEN (SELECT rolname FROM pg_namespace n JOIN pg_roles r ON r.oid = n.nspowner WHERE n.nspname = 'nsi_operacional') = 'nsi_dev_migrator'
            THEN 'true' ELSE 'false' END AS precisa_alter_owner_dev
\gset

-- 1.5 - propriedade do schema em nsi_test.
\c nsi_test
DO $$
DECLARE dono_atual name;
BEGIN
    SELECT rolname INTO dono_atual
      FROM pg_namespace n JOIN pg_roles r ON r.oid = n.nspowner
     WHERE n.nspname = 'nsi_operacional';
    IF dono_atual IS NULL THEN
        RAISE EXCEPTION 'Schema nsi_operacional nao existe em nsi_test - execute provisionar_dev_teste.sql (B2.2) antes deste script.';
    END IF;
    IF dono_atual NOT IN ('nsi_test_migrator', 'nsi_eventos_owner') THEN
        RAISE EXCEPTION 'Schema nsi_operacional em nsi_test tem dono inesperado (%) - esperado nsi_test_migrator (1a execucao) ou nsi_eventos_owner (execucao repetida). Abortando na preflight, sem nenhuma alteracao.', dono_atual;
    END IF;
END $$;
SELECT CASE WHEN (SELECT rolname FROM pg_namespace n JOIN pg_roles r ON r.oid = n.nspowner WHERE n.nspname = 'nsi_operacional') = 'nsi_test_migrator'
            THEN 'true' ELSE 'false' END AS precisa_alter_owner_test
\gset

\c postgres
-- Fim da FASE 1: todas as validacoes possiveis (quatro roles, duas
-- memberships, dois owners de schema) ja passaram, ou o script ja
-- abortou. Nenhuma escrita ocorreu ate aqui.

-- =============================================================
-- FASE 2 - CONVERGENCIA. So executa acoes ja autorizadas pela Fase 1
-- (via as variaveis \gset acima). \if e um comando de CLIENTE do psql -
-- nao recalcula nenhuma decisao aqui.
-- =============================================================
BEGIN;

\if :precisa_criar_owner
CREATE ROLE nsi_eventos_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
\endif

\if :precisa_criar_aplicacao
CREATE ROLE nsi_aplicacao LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
\endif

\if :precisa_criar_expiracao
CREATE ROLE nsi_expiracao LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
\endif

\if :precisa_criar_operador
CREATE ROLE nsi_operador_restrito LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
\endif

\if :precisa_grant_membership_dev
GRANT nsi_eventos_owner TO nsi_dev_migrator WITH INHERIT FALSE, SET TRUE, ADMIN FALSE;
\endif

\if :precisa_grant_membership_test
GRANT nsi_eventos_owner TO nsi_test_migrator WITH INHERIT FALSE, SET TRUE, ADMIN FALSE;
\endif

-- CONNECT: ACL declarativa, idempotente por natureza - sempre reaplicada,
-- nunca depende de propriedade implicita de banco. Isolamento de PUBLIC +
-- CONNECT explicito de cada migrator no seu proprio banco + as tres
-- roles funcionais nos dois bancos locais (compartilhadas apenas neste
-- cluster local - Parte 1 da B3, Secao 3; nao decide producao).
REVOKE CONNECT ON DATABASE nsi_dev  FROM PUBLIC;
REVOKE CONNECT ON DATABASE nsi_test FROM PUBLIC;

GRANT CONNECT ON DATABASE nsi_dev  TO nsi_dev_migrator;
GRANT CONNECT ON DATABASE nsi_test TO nsi_test_migrator;

GRANT CONNECT ON DATABASE nsi_dev  TO nsi_aplicacao, nsi_expiracao, nsi_operador_restrito;
GRANT CONNECT ON DATABASE nsi_test TO nsi_aplicacao, nsi_expiracao, nsi_operador_restrito;

COMMIT;

\c nsi_dev
BEGIN;
\if :precisa_alter_owner_dev
ALTER SCHEMA nsi_operacional OWNER TO nsi_eventos_owner;
\endif
GRANT USAGE ON SCHEMA nsi_operacional TO nsi_dev_migrator;
GRANT USAGE ON SCHEMA nsi_operacional TO nsi_aplicacao, nsi_expiracao, nsi_operador_restrito;
COMMIT;

\c nsi_test
BEGIN;
\if :precisa_alter_owner_test
ALTER SCHEMA nsi_operacional OWNER TO nsi_eventos_owner;
\endif
GRANT USAGE ON SCHEMA nsi_operacional TO nsi_test_migrator;
GRANT USAGE ON SCHEMA nsi_operacional TO nsi_aplicacao, nsi_expiracao, nsi_operador_restrito;
COMMIT;

\c postgres

-- =============================================================
-- FASE 3 - POS-VALIDACAO COMPLETA. Reconfirma, a partir do zero (nunca
-- reaproveitando as variaveis da Fase 1), todo o estado exigido.
-- =============================================================

-- 3.1 - atributos das quatro roles + ausencia de membership inesperada
-- (mesma checagem da Fase 1, agora sem ramo condicional - tem que bater
-- exatamente, sempre).
DO $$
DECLARE
    canlogin_atual boolean; super_atual boolean; createdb_atual boolean;
    createrole_atual boolean; replication_atual boolean; bypassrls_atual boolean;
    inherit_atual boolean; total_memberships integer;
BEGIN
    SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls, rolinherit
      INTO canlogin_atual, super_atual, createdb_atual, createrole_atual, replication_atual, bypassrls_atual, inherit_atual
      FROM pg_roles WHERE rolname = 'nsi_eventos_owner';
    IF NOT FOUND OR canlogin_atual IS DISTINCT FROM false OR super_atual IS DISTINCT FROM false
       OR createdb_atual IS DISTINCT FROM false OR createrole_atual IS DISTINCT FROM false
       OR replication_atual IS DISTINCT FROM false OR bypassrls_atual IS DISTINCT FROM false
       OR inherit_atual IS DISTINCT FROM true THEN
        RAISE EXCEPTION 'Pos-validacao falhou: atributos de nsi_eventos_owner incorretos ou role ausente.';
    END IF;
    SELECT count(*) INTO total_memberships FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.member WHERE r.rolname = 'nsi_eventos_owner';
    IF total_memberships <> 0 THEN
        RAISE EXCEPTION 'Pos-validacao falhou: nsi_eventos_owner pertence a % role(s) inesperada(s).', total_memberships;
    END IF;
END $$;

DO $$
DECLARE
    canlogin_atual boolean; super_atual boolean; createdb_atual boolean;
    createrole_atual boolean; replication_atual boolean; bypassrls_atual boolean;
    inherit_atual boolean; total_memberships integer;
BEGIN
    SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls, rolinherit
      INTO canlogin_atual, super_atual, createdb_atual, createrole_atual, replication_atual, bypassrls_atual, inherit_atual
      FROM pg_roles WHERE rolname = 'nsi_aplicacao';
    IF NOT FOUND OR canlogin_atual IS DISTINCT FROM true OR super_atual IS DISTINCT FROM false
       OR createdb_atual IS DISTINCT FROM false OR createrole_atual IS DISTINCT FROM false
       OR replication_atual IS DISTINCT FROM false OR bypassrls_atual IS DISTINCT FROM false
       OR inherit_atual IS DISTINCT FROM true THEN
        RAISE EXCEPTION 'Pos-validacao falhou: atributos de nsi_aplicacao incorretos ou role ausente.';
    END IF;
    SELECT count(*) INTO total_memberships FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.member WHERE r.rolname = 'nsi_aplicacao';
    IF total_memberships <> 0 THEN
        RAISE EXCEPTION 'Pos-validacao falhou: nsi_aplicacao pertence a % role(s) inesperada(s).', total_memberships;
    END IF;
END $$;

DO $$
DECLARE
    canlogin_atual boolean; super_atual boolean; createdb_atual boolean;
    createrole_atual boolean; replication_atual boolean; bypassrls_atual boolean;
    inherit_atual boolean; total_memberships integer;
BEGIN
    SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls, rolinherit
      INTO canlogin_atual, super_atual, createdb_atual, createrole_atual, replication_atual, bypassrls_atual, inherit_atual
      FROM pg_roles WHERE rolname = 'nsi_expiracao';
    IF NOT FOUND OR canlogin_atual IS DISTINCT FROM true OR super_atual IS DISTINCT FROM false
       OR createdb_atual IS DISTINCT FROM false OR createrole_atual IS DISTINCT FROM false
       OR replication_atual IS DISTINCT FROM false OR bypassrls_atual IS DISTINCT FROM false
       OR inherit_atual IS DISTINCT FROM true THEN
        RAISE EXCEPTION 'Pos-validacao falhou: atributos de nsi_expiracao incorretos ou role ausente.';
    END IF;
    SELECT count(*) INTO total_memberships FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.member WHERE r.rolname = 'nsi_expiracao';
    IF total_memberships <> 0 THEN
        RAISE EXCEPTION 'Pos-validacao falhou: nsi_expiracao pertence a % role(s) inesperada(s).', total_memberships;
    END IF;
END $$;

DO $$
DECLARE
    canlogin_atual boolean; super_atual boolean; createdb_atual boolean;
    createrole_atual boolean; replication_atual boolean; bypassrls_atual boolean;
    inherit_atual boolean; total_memberships integer;
BEGIN
    SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls, rolinherit
      INTO canlogin_atual, super_atual, createdb_atual, createrole_atual, replication_atual, bypassrls_atual, inherit_atual
      FROM pg_roles WHERE rolname = 'nsi_operador_restrito';
    IF NOT FOUND OR canlogin_atual IS DISTINCT FROM true OR super_atual IS DISTINCT FROM false
       OR createdb_atual IS DISTINCT FROM false OR createrole_atual IS DISTINCT FROM false
       OR replication_atual IS DISTINCT FROM false OR bypassrls_atual IS DISTINCT FROM false
       OR inherit_atual IS DISTINCT FROM true THEN
        RAISE EXCEPTION 'Pos-validacao falhou: atributos de nsi_operador_restrito incorretos ou role ausente.';
    END IF;
    SELECT count(*) INTO total_memberships FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.member WHERE r.rolname = 'nsi_operador_restrito';
    IF total_memberships <> 0 THEN
        RAISE EXCEPTION 'Pos-validacao falhou: nsi_operador_restrito pertence a % role(s) inesperada(s).', total_memberships;
    END IF;
END $$;

-- 3.2 - as duas memberships dos migrators, com as tres opcoes corretas.
DO $$
DECLARE inherit_atual boolean; set_atual boolean; admin_atual boolean;
BEGIN
    SELECT m.inherit_option, m.set_option, m.admin_option
      INTO inherit_atual, set_atual, admin_atual
      FROM pg_auth_members m
      JOIN pg_roles r_role ON r_role.oid = m.roleid
      JOIN pg_roles r_member ON r_member.oid = m.member
     WHERE r_role.rolname = 'nsi_eventos_owner' AND r_member.rolname = 'nsi_dev_migrator';
    IF NOT FOUND OR inherit_atual IS DISTINCT FROM false OR set_atual IS DISTINCT FROM true OR admin_atual IS DISTINCT FROM false THEN
        RAISE EXCEPTION 'Pos-validacao falhou: membership nsi_dev_migrator em nsi_eventos_owner ausente ou com opcoes incorretas.';
    END IF;
END $$;
DO $$
DECLARE inherit_atual boolean; set_atual boolean; admin_atual boolean;
BEGIN
    SELECT m.inherit_option, m.set_option, m.admin_option
      INTO inherit_atual, set_atual, admin_atual
      FROM pg_auth_members m
      JOIN pg_roles r_role ON r_role.oid = m.roleid
      JOIN pg_roles r_member ON r_member.oid = m.member
     WHERE r_role.rolname = 'nsi_eventos_owner' AND r_member.rolname = 'nsi_test_migrator';
    IF NOT FOUND OR inherit_atual IS DISTINCT FROM false OR set_atual IS DISTINCT FROM true OR admin_atual IS DISTINCT FROM false THEN
        RAISE EXCEPTION 'Pos-validacao falhou: membership nsi_test_migrator em nsi_eventos_owner ausente ou com opcoes incorretas.';
    END IF;
END $$;

-- 3.3 - PUBLIC sem CONNECT nos dois bancos. pg_database e catalogo
-- compartilhado (visivel de qualquer conexao) - nao precisa de \c.
-- NUNCA usa has_database_privilege('public', ...): 'public' seria
-- interpretado como nome de role real (que nao existe) e nao como o
-- pseudo-role PUBLIC. grantee = 0 e o valor documentado do PostgreSQL
-- para representar PUBLIC dentro de aclexplode().
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_database d, aclexplode(coalesce(d.datacl, acldefault('d', d.datdba))) AS acl
        WHERE d.datname = 'nsi_dev' AND acl.grantee = 0 AND acl.privilege_type = 'CONNECT'
    ) THEN
        RAISE EXCEPTION 'Pos-validacao falhou: PUBLIC ainda tem CONNECT em nsi_dev.';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_database d, aclexplode(coalesce(d.datacl, acldefault('d', d.datdba))) AS acl
        WHERE d.datname = 'nsi_test' AND acl.grantee = 0 AND acl.privilege_type = 'CONNECT'
    ) THEN
        RAISE EXCEPTION 'Pos-validacao falhou: PUBLIC ainda tem CONNECT em nsi_test.';
    END IF;
END $$;

-- 3.4 - cada migrator com CONNECT somente no seu proprio banco.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_database d, aclexplode(coalesce(d.datacl, acldefault('d', d.datdba))) AS acl, pg_roles r
        WHERE d.datname = 'nsi_dev' AND r.oid = acl.grantee AND r.rolname = 'nsi_dev_migrator' AND acl.privilege_type = 'CONNECT'
    ) THEN
        RAISE EXCEPTION 'Pos-validacao falhou: nsi_dev_migrator sem CONNECT em nsi_dev.';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_database d, aclexplode(coalesce(d.datacl, acldefault('d', d.datdba))) AS acl, pg_roles r
        WHERE d.datname = 'nsi_test' AND r.oid = acl.grantee AND r.rolname = 'nsi_dev_migrator' AND acl.privilege_type = 'CONNECT'
    ) THEN
        RAISE EXCEPTION 'Pos-validacao falhou: nsi_dev_migrator tem CONNECT indevido em nsi_test.';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_database d, aclexplode(coalesce(d.datacl, acldefault('d', d.datdba))) AS acl, pg_roles r
        WHERE d.datname = 'nsi_test' AND r.oid = acl.grantee AND r.rolname = 'nsi_test_migrator' AND acl.privilege_type = 'CONNECT'
    ) THEN
        RAISE EXCEPTION 'Pos-validacao falhou: nsi_test_migrator sem CONNECT em nsi_test.';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_database d, aclexplode(coalesce(d.datacl, acldefault('d', d.datdba))) AS acl, pg_roles r
        WHERE d.datname = 'nsi_dev' AND r.oid = acl.grantee AND r.rolname = 'nsi_test_migrator' AND acl.privilege_type = 'CONNECT'
    ) THEN
        RAISE EXCEPTION 'Pos-validacao falhou: nsi_test_migrator tem CONNECT indevido em nsi_dev.';
    END IF;
END $$;

-- 3.5 - as tres roles funcionais com CONNECT nos dois bancos.
DO $$
DECLARE nome_role text;
BEGIN
    FOREACH nome_role IN ARRAY ARRAY['nsi_aplicacao', 'nsi_expiracao', 'nsi_operador_restrito']
    LOOP
        IF NOT EXISTS (
            SELECT 1 FROM pg_database d, aclexplode(coalesce(d.datacl, acldefault('d', d.datdba))) AS acl, pg_roles r
            WHERE d.datname = 'nsi_dev' AND r.oid = acl.grantee AND r.rolname = nome_role AND acl.privilege_type = 'CONNECT'
        ) THEN
            RAISE EXCEPTION 'Pos-validacao falhou: % sem CONNECT em nsi_dev.', nome_role;
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM pg_database d, aclexplode(coalesce(d.datacl, acldefault('d', d.datdba))) AS acl, pg_roles r
            WHERE d.datname = 'nsi_test' AND r.oid = acl.grantee AND r.rolname = nome_role AND acl.privilege_type = 'CONNECT'
        ) THEN
            RAISE EXCEPTION 'Pos-validacao falhou: % sem CONNECT em nsi_test.', nome_role;
        END IF;
    END LOOP;
END $$;

-- 3.6 - owner do schema, USAGE, e alembic_version - por banco (requer
-- \c, ver limite estrutural documentado no cabecalho).
\c nsi_dev
DO $$
BEGIN
    IF (SELECT rolname FROM pg_namespace n JOIN pg_roles r ON r.oid = n.nspowner WHERE n.nspname = 'nsi_operacional') <> 'nsi_eventos_owner' THEN
        RAISE EXCEPTION 'Pos-validacao falhou: schema nsi_operacional em nsi_dev nao pertence a nsi_eventos_owner.';
    END IF;
    IF NOT has_schema_privilege('nsi_dev_migrator', 'nsi_operacional', 'USAGE') THEN
        RAISE EXCEPTION 'Pos-validacao falhou: nsi_dev_migrator sem USAGE em nsi_operacional (nsi_dev).';
    END IF;
    IF NOT has_schema_privilege('nsi_aplicacao', 'nsi_operacional', 'USAGE')
       OR NOT has_schema_privilege('nsi_expiracao', 'nsi_operacional', 'USAGE')
       OR NOT has_schema_privilege('nsi_operador_restrito', 'nsi_operacional', 'USAGE') THEN
        RAISE EXCEPTION 'Pos-validacao falhou: alguma role funcional sem USAGE em nsi_operacional (nsi_dev).';
    END IF;
    IF (SELECT tableowner FROM pg_tables WHERE schemaname = 'nsi_operacional' AND tablename = 'alembic_version') <> 'nsi_dev_migrator' THEN
        RAISE EXCEPTION 'Pos-validacao falhou: alembic_version em nsi_dev nao pertence mais a nsi_dev_migrator.';
    END IF;
END $$;

\c nsi_test
DO $$
BEGIN
    IF (SELECT rolname FROM pg_namespace n JOIN pg_roles r ON r.oid = n.nspowner WHERE n.nspname = 'nsi_operacional') <> 'nsi_eventos_owner' THEN
        RAISE EXCEPTION 'Pos-validacao falhou: schema nsi_operacional em nsi_test nao pertence a nsi_eventos_owner.';
    END IF;
    IF NOT has_schema_privilege('nsi_test_migrator', 'nsi_operacional', 'USAGE') THEN
        RAISE EXCEPTION 'Pos-validacao falhou: nsi_test_migrator sem USAGE em nsi_operacional (nsi_test).';
    END IF;
    IF NOT has_schema_privilege('nsi_aplicacao', 'nsi_operacional', 'USAGE')
       OR NOT has_schema_privilege('nsi_expiracao', 'nsi_operacional', 'USAGE')
       OR NOT has_schema_privilege('nsi_operador_restrito', 'nsi_operacional', 'USAGE') THEN
        RAISE EXCEPTION 'Pos-validacao falhou: alguma role funcional sem USAGE em nsi_operacional (nsi_test).';
    END IF;
    IF (SELECT tableowner FROM pg_tables WHERE schemaname = 'nsi_operacional' AND tablename = 'alembic_version') <> 'nsi_test_migrator' THEN
        RAISE EXCEPTION 'Pos-validacao falhou: alembic_version em nsi_test nao pertence mais a nsi_test_migrator.';
    END IF;
END $$;

\c postgres
\echo 'provisionar_b3_roles.sql concluido - Fase 3 (pos-validacao completa) passou integralmente.'

-- =============================================================
-- PROXIMOS PASSOS (fora deste arquivo, NUNCA automatizados):
--
-- 1) Definir a senha de cada uma das tres roles LOGIN INTERATIVAMENTE
--    (nunca em linha de comando, nunca em variavel -v, nunca gravada em
--    nenhum arquivo versionado):
--
--        psql -U postgres -d postgres
--        \password nsi_aplicacao
--        \password nsi_expiracao
--        \password nsi_operador_restrito
--        \q
--
--    nsi_eventos_owner e NOLOGIN - nunca recebe senha.
--
-- 2) Configurar as seis variaveis DATABASE_URL_NSI_*/TEST_DATABASE_URL_NSI_*
--    SOMENTE no .env local (ja coberto por .gitignore) - nunca em arquivo
--    versionado, log ou historico de shell.
-- =============================================================
