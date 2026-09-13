-- =============================================================
-- scripts/postgres_local/desprovisionar_b3_roles.sql
-- Sprint B (B3.1) - ADR-008
--
-- *** SCRIPT DESTRUTIVO - APENAS DESENVOLVIMENTO/TESTE LOCAL ***
-- *** NUNCA EXECUTAR CONTRA PRODUCAO - NUNCA EXECUTADO AUTOMATICAMENTE ***
-- *** NENHUM TESTE AUTOMATIZADO CHAMA ESTE ARQUIVO - execucao manual,
--     autorizada e deliberada, sempre. ***
--
-- Reverte EXATAMENTE os efeitos de provisionar_b3_roles.sql: remove as
-- quatro roles funcionais (nsi_eventos_owner, nsi_aplicacao,
-- nsi_expiracao, nsi_operador_restrito), devolve a propriedade do schema
-- "nsi_operacional" aos migrators, e revoga CONNECT apenas das tres roles
-- funcionais.
--
-- NUNCA toca em nsi_dev_migrator, nsi_test_migrator, nsi_dev ou nsi_test -
-- esses permanecem objetos exclusivos de
-- scripts/postgres_local/desprovisionar_dev_teste.sql (B2). Em particular,
-- o CONNECT explicito de cada migrator no seu proprio banco (concedido
-- por provisionar_b3_roles.sql) e PRESERVADO por este script - como
-- PUBLIC permanece sem CONNECT (decisao aprovada, ver bloco final),
-- revogar tambem o dos migrators deixaria B2 inoperante apos uma reversao
-- de B3. O desprovisionamento remove somente: CONNECT das tres roles
-- funcionais; a membership dos migrators em nsi_eventos_owner; USAGE das
-- quatro roles removidas; as quatro roles; a propriedade do schema volta
-- ao migrator.
--
-- GATE OBRIGATORIO: exige que nsi_operacional.alembic_version, nos DOIS
-- bancos, tenha exatamente uma linha com version_num = '0001' - nunca usa
-- "alembic downgrade base" como referencia. Este script SO desprovisiona
-- quando o banco esta exatamente no estado pos-B2 (schema criado, nenhuma
-- tabela de negocio). Qualquer outro estado (tabela ausente, vazia, com
-- multiplas linhas, ou revisao diferente) ABORTA antes de qualquer
-- alteracao destrutiva.
--
-- Execute conectado ao banco de manutencao "postgres":
--
--     psql -U postgres -d postgres -f scripts/postgres_local/desprovisionar_b3_roles.sql
--
-- Execucao manual, uma unica vez por reversao desejada, mediante
-- autorizacao especifica e separada.
--
-- NAO CONTEM SENHA.
-- =============================================================

\set ON_ERROR_STOP on

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

-- =============================================================
-- GATE 1 (automatico, antes de qualquer prompt): revisao exata do
-- Alembic em nsi_dev e nsi_test. NUNCA "alembic downgrade base" - o
-- estado exigido e exatamente a revisao '0001'.
-- =============================================================
\c nsi_dev
DO $$
DECLARE
    total_linhas  integer;
    valor_revisao text;
BEGIN
    IF to_regclass('nsi_operacional.alembic_version') IS NULL THEN
        RAISE EXCEPTION 'nsi_operacional.alembic_version nao existe em nsi_dev - nao e seguro desprovisionar sem essa comprovacao. Abortando.';
    END IF;
    SELECT count(*) INTO total_linhas FROM nsi_operacional.alembic_version;
    IF total_linhas <> 1 THEN
        RAISE EXCEPTION 'nsi_operacional.alembic_version em nsi_dev tem % linha(s), esperado exatamente 1. Abortando sem nenhuma alteracao.', total_linhas;
    END IF;
    SELECT version_num INTO valor_revisao FROM nsi_operacional.alembic_version;
    IF valor_revisao <> '0001' THEN
        RAISE EXCEPTION 'nsi_operacional.alembic_version em nsi_dev esta em revisao % - esperado exatamente ''0001''. Abortando sem nenhuma alteracao.', valor_revisao;
    END IF;
END $$;

\c nsi_test
DO $$
DECLARE
    total_linhas  integer;
    valor_revisao text;
BEGIN
    IF to_regclass('nsi_operacional.alembic_version') IS NULL THEN
        RAISE EXCEPTION 'nsi_operacional.alembic_version nao existe em nsi_test - nao e seguro desprovisionar sem essa comprovacao. Abortando.';
    END IF;
    SELECT count(*) INTO total_linhas FROM nsi_operacional.alembic_version;
    IF total_linhas <> 1 THEN
        RAISE EXCEPTION 'nsi_operacional.alembic_version em nsi_test tem % linha(s), esperado exatamente 1. Abortando sem nenhuma alteracao.', total_linhas;
    END IF;
    SELECT version_num INTO valor_revisao FROM nsi_operacional.alembic_version;
    IF valor_revisao <> '0001' THEN
        RAISE EXCEPTION 'nsi_operacional.alembic_version em nsi_test esta em revisao % - esperado exatamente ''0001''. Abortando sem nenhuma alteracao.', valor_revisao;
    END IF;
END $$;

\c postgres

-- Confirmacao textual obrigatoria - so chega aqui se o GATE 1 passou nos
-- dois bancos.
\prompt 'Digite exatamente CONFIRMO-DESPROVISIONAR-NSI-B3-ROLES para prosseguir com a destruicao: ' confirmacao_desprovisionamento

SELECT CASE WHEN :'confirmacao_desprovisionamento' = 'CONFIRMO-DESPROVISIONAR-NSI-B3-ROLES'
            THEN 'true' ELSE 'false' END AS pode_prosseguir
\gset

\if :pode_prosseguir
    \echo 'Confirmacao recebida - prosseguindo com o desprovisionamento.'
\else
    \echo 'Confirmacao incorreta ou ausente - abortando sem nenhuma alteracao.'
    \quit
\endif

-- =============================================================
-- GATE 2: verificacao de dependencias antes de qualquer DROP ROLE. O
-- schema "nsi_operacional" pertencer a nsi_eventos_owner NESTE MOMENTO e
-- o estado normal esperado (revertido logo abaixo) - NUNCA tratado como
-- objeto residual. O que este gate procura e objeto de NEGOCIO (tabela,
-- indice, sequencia, funcao) que nao deveria existir, dado que o GATE 1
-- ja comprovou revisao 0001 (0002 nunca aplicada).
-- =============================================================
\c nsi_dev
DO $$
DECLARE total_objetos integer;
BEGIN
    SELECT count(*) INTO total_objetos
      FROM pg_class c JOIN pg_roles r ON r.oid = c.relowner
     WHERE r.rolname IN ('nsi_eventos_owner', 'nsi_aplicacao', 'nsi_expiracao', 'nsi_operador_restrito');
    IF total_objetos <> 0 THEN
        RAISE EXCEPTION 'Encontrado(s) % objeto(s) (tabela/indice/sequencia) em nsi_dev pertencente(s) as roles de B3 - inesperado dado revisao 0001 ja confirmada. Abortando - investigue manualmente antes de prosseguir.', total_objetos;
    END IF;

    SELECT count(*) INTO total_objetos
      FROM pg_proc p JOIN pg_roles r ON r.oid = p.proowner
     WHERE r.rolname IN ('nsi_eventos_owner', 'nsi_aplicacao', 'nsi_expiracao', 'nsi_operador_restrito');
    IF total_objetos <> 0 THEN
        RAISE EXCEPTION 'Encontrada(s) % funcao(oes) em nsi_dev pertencente(s) as roles de B3 - inesperado dado revisao 0001 ja confirmada. Abortando - investigue manualmente antes de prosseguir.', total_objetos;
    END IF;
END $$;

ALTER SCHEMA nsi_operacional OWNER TO nsi_dev_migrator;
REVOKE USAGE ON SCHEMA nsi_operacional FROM nsi_dev_migrator;
REVOKE USAGE ON SCHEMA nsi_operacional FROM nsi_aplicacao, nsi_expiracao, nsi_operador_restrito;

\c nsi_test
DO $$
DECLARE total_objetos integer;
BEGIN
    SELECT count(*) INTO total_objetos
      FROM pg_class c JOIN pg_roles r ON r.oid = c.relowner
     WHERE r.rolname IN ('nsi_eventos_owner', 'nsi_aplicacao', 'nsi_expiracao', 'nsi_operador_restrito');
    IF total_objetos <> 0 THEN
        RAISE EXCEPTION 'Encontrado(s) % objeto(s) (tabela/indice/sequencia) em nsi_test pertencente(s) as roles de B3 - inesperado dado revisao 0001 ja confirmada. Abortando - investigue manualmente antes de prosseguir.', total_objetos;
    END IF;

    SELECT count(*) INTO total_objetos
      FROM pg_proc p JOIN pg_roles r ON r.oid = p.proowner
     WHERE r.rolname IN ('nsi_eventos_owner', 'nsi_aplicacao', 'nsi_expiracao', 'nsi_operador_restrito');
    IF total_objetos <> 0 THEN
        RAISE EXCEPTION 'Encontrada(s) % funcao(oes) em nsi_test pertencente(s) as roles de B3 - inesperado dado revisao 0001 ja confirmada. Abortando - investigue manualmente antes de prosseguir.', total_objetos;
    END IF;
END $$;

ALTER SCHEMA nsi_operacional OWNER TO nsi_test_migrator;
REVOKE USAGE ON SCHEMA nsi_operacional FROM nsi_test_migrator;
REVOKE USAGE ON SCHEMA nsi_operacional FROM nsi_aplicacao, nsi_expiracao, nsi_operador_restrito;

\c postgres

-- CONNECT: remove SOMENTE o das tres roles funcionais. O CONNECT
-- explicito dos migrators (nsi_dev_migrator em nsi_dev, nsi_test_migrator
-- em nsi_test) e PRESERVADO - nao revogado por este script (ver
-- explicacao no cabecalho). PUBLIC NAO recupera CONNECT automaticamente -
-- permanece endurecido; restaurar CONNECT para PUBLIC, se um dia
-- necessario, exige um comando administrativo separado e autorizacao
-- humana especifica, fora deste script.
REVOKE CONNECT ON DATABASE nsi_dev  FROM nsi_aplicacao, nsi_expiracao, nsi_operador_restrito;
REVOKE CONNECT ON DATABASE nsi_test FROM nsi_aplicacao, nsi_expiracao, nsi_operador_restrito;

REVOKE nsi_eventos_owner FROM nsi_dev_migrator;
REVOKE nsi_eventos_owner FROM nsi_test_migrator;

DROP ROLE IF EXISTS nsi_aplicacao;
DROP ROLE IF EXISTS nsi_expiracao;
DROP ROLE IF EXISTS nsi_operador_restrito;
DROP ROLE IF EXISTS nsi_eventos_owner;

\echo 'desprovisionar_b3_roles.sql concluido - roles funcionais removidas; migrators e PUBLIC no estado documentado no cabecalho.'
