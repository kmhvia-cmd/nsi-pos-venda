-- =============================================================
-- scripts/postgres_local/provisionar_b6_ensaio.sql
-- Sprint B (B6) - ADR-008 (Secao 16) / ADR-010 (Secao 16.2) /
-- SPRINT-B6-ESPECIFICACAO-ENSAIO-DE-CORTE.md (Secoes 14 e 15, componente C2).
--
-- APENAS PARA O ENSAIO DE CORTE, NO POSTGRESQL LOCAL. NUNCA PRODUCAO.
--
-- Execute conectado ao banco de manutencao "postgres":
--
--     psql -U postgres -d postgres -f scripts/postgres_local/provisionar_b6_ensaio.sql
--
-- Pre-requisitos: provisionamentos da B3.1, da B4.3 e da B5.3 ja executados
-- (as oito roles existem na forma aprovada); nsi_dev e nsi_test na revisao
-- 0006. Este script NUNCA recria nem altera esses objetos.
--
-- O QUE ESTE SCRIPT FAZ (e nada alem disso) - cria o ambiente DESCARTAVEL
-- de uma rodada do ensaio:
--   1. a role nsi_ensaio_migrator (LOGIN, atributos de seguranca
--      explicitos, sem senha), com a mesma membership dos outros migrators
--      em nsi_eventos_owner (INHERIT FALSE, SET TRUE, ADMIN FALSE);
--   2. o banco nsi_ensaio (UTF8, a partir de template0), sem CONNECT para
--      PUBLIC, com CONNECT somente para nsi_ensaio_migrator e
--      nsi_importacao;
--   3. em nsi_ensaio: o schema "nsi_operacional", de nsi_eventos_owner, com
--      USAGE somente para nsi_ensaio_migrator e nsi_importacao; e a tabela
--      de controle do Alembic, vazia, de nsi_ensaio_migrator.
--
-- O QUE ESTE SCRIPT NUNCA FAZ: nao aplica migration (isso e o Alembic, com
-- NSI_DATABASE_ENV=ensaio); nao cria tabela de negocio nem funcao; nao
-- concede nada em nsi_dev nem em nsi_test; nao concede CONNECT em
-- nsi_ensaio a nsi_aplicacao, nsi_expiracao, nsi_operador_restrito ou
-- nsi_congelamento (o fluxo novo nao roda no ensaio); nao concede EXECUTE
-- nem privilegio em tabela; nao altera atributo, senha ou membership de
-- nenhuma role existente; nao define senha; nunca corrige um estado
-- divergente.
--
-- NAO CONTEM SENHA. nsi_ensaio_migrator e criada SEM senha; o operador a
-- define interativamente, fora deste script, e configura as variaveis
-- ENSAIO_DATABASE_URL e ENSAIO_DATABASE_URL_NSI_IMPORTACAO no .env local
-- (ver LEMBRETES no fim).
--
-- ESTE SCRIPT NAO E EXECUTADO AUTOMATICAMENTE por nenhum teste, por
-- migrations/env.py ou por qualquer codigo de aplicacao. Toda execucao e
-- um procedimento MANUAL autorizado.
--
-- ---------------------------------------------------------------
-- DESENHO DE TRES FASES
-- ---------------------------------------------------------------
-- FASE 1 (preflight): barreira global, somente leitura. Aceita exatamente
--   DOIS estados: ambiente AUSENTE (nem a role nsi_ensaio_migrator nem o
--   banco nsi_ensaio existem) ou ambiente PRESENTE na forma exata desta
--   especificacao. Qualquer outro estado - inclusive um ambiente pela
--   metade - ABORTA aqui.
--
-- FASE 2 (convergencia): unica fase que escreve. Le o estado de novo, por
--   conta propria: ausente -> cria tudo; presente -> nada a fazer. Como
--   CREATE DATABASE nao roda dentro de bloco de codigo nem de transacao,
--   as escritas sao comandos diretos, sob um unico \if.
--
-- FASE 3 (pos-validacao): reconfirma, a partir do zero e somente leitura,
--   TODO o estado final esperado.
--
-- AMBIENTE PELA METADE: uma falha no meio da Fase 2 pode deixar o ambiente
--   incompleto. Ele NUNCA e consertado nem completado: execute
--   desprovisionar_b6_ensaio.sql, que aceita qualquer estado parcial, e
--   provisione de novo (especificacao da B6, Secao 59).
--
-- GARANTIA - READ ONLY NAS FASES 1 E 3: o modo somente leitura e ligado no
--   inicio de cada fase e NOVAMENTE depois de cada \c (que abre uma sessao
--   nova, em modo normal); logo apos ligar, o script le o modo efetivo e
--   aborta se nao estiver ativo. A escrita so e liberada em UM ponto: o
--   marcador da Fase 2.
--
-- CADA FASE E AUTOSSUFICIENTE: nenhuma fase transmite estado para outra.
--   Variaveis de cliente do psql sao prefixadas pela fase (f1_, f2_, f3_) e
--   nunca cruzam fases.
--
-- EFEITO SOBRE OS DEMAIS SCRIPTS (limitacao aceita - especificacao da B6,
--   Secao 15): enquanto nsi_ensaio existir, os scripts de provisionamento
--   da B3.1, da B4.3 e da B5.3 nao sao reexecutaveis, porque so conhecem
--   nsi_dev e nsi_test. Eles nao sao alterados.
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

-- Verificacao de identidade do servidor - identica ao padrao da B3.1, da
-- B4.3 e da B5.3.
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

-- Privilegio de superusuario (CREATE ROLE e CREATE DATABASE exigem).
DO $$
BEGIN
    IF current_setting('is_superuser') <> 'on' THEN
        RAISE EXCEPTION 'Sessao sem privilegio de superusuario (session_user=%). Abortando sem nenhuma alteracao.', session_user;
    END IF;
END $$;

-- Os dois bancos permanentes precisam existir; este script nunca os cria.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'nsi_dev')
       OR NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'nsi_test') THEN
        RAISE EXCEPTION 'Bancos nsi_dev e nsi_test precisam existir. Abortando sem nenhuma alteracao.';
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

-- 1.2 - estado do ambiente de ensaio: AUSENTE por inteiro ou PRESENTE por
-- inteiro. Role sem banco, ou banco sem role, e ambiente pela metade.
DO $$
DECLARE role_existe boolean; banco_existe boolean;
BEGIN
    role_existe := EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nsi_ensaio_migrator');
    banco_existe := EXISTS (SELECT 1 FROM pg_database WHERE datname = 'nsi_ensaio');
    IF role_existe <> banco_existe THEN
        RAISE EXCEPTION 'Ambiente de ensaio pela metade (role=%, banco=%). Execute desprovisionar_b6_ensaio.sql e provisione de novo. Abortando na preflight, sem nenhuma alteracao.', role_existe, banco_existe;
    END IF;
END $$;

-- 1.3 - membros de nsi_eventos_owner: os dois migrators permanentes e, se o
-- ambiente existir, o de ensaio - cada um com uma unica linha, INHERIT
-- FALSE, SET TRUE, ADMIN FALSE. Nenhum outro membro.
DO $$
DECLARE total_inesperados integer; total_esperados integer; esperados text[];
BEGIN
    esperados := ARRAY['nsi_dev_migrator', 'nsi_test_migrator'];
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nsi_ensaio_migrator') THEN
        esperados := esperados || 'nsi_ensaio_migrator'::text;
    END IF;
    SELECT count(*) FILTER (WHERE r.rolname <> ALL (esperados) OR m.inherit_option OR NOT m.set_option OR m.admin_option),
           count(*) FILTER (WHERE r.rolname = ANY (esperados))
      INTO total_inesperados, total_esperados
      FROM pg_auth_members m
      JOIN pg_roles g ON g.oid = m.roleid
      JOIN pg_roles r ON r.oid = m.member
     WHERE g.rolname = 'nsi_eventos_owner';
    IF total_inesperados <> 0 OR total_esperados <> cardinality(esperados) THEN
        RAISE EXCEPTION 'Membros de nsi_eventos_owner fora do previsto (inesperados=%, esperados encontrados=% de %). Abortando na preflight, sem nenhuma alteracao.', total_inesperados, total_esperados, cardinality(esperados);
    END IF;
END $$;

-- 1.4 - concessoes de banco a nsi_importacao: CONNECT em nsi_test e, se o
-- ambiente existir, em nsi_ensaio. Nunca em nsi_dev nem em outro banco.
DO $$
DECLARE total_inesperadas integer;
BEGIN
    SELECT count(*) INTO total_inesperadas
      FROM pg_database d
     CROSS JOIN LATERAL aclexplode(d.datacl) a
      JOIN pg_roles g ON g.oid = a.grantee
     WHERE g.rolname = 'nsi_importacao'
       AND NOT (d.datname IN ('nsi_test', 'nsi_ensaio') AND a.privilege_type = 'CONNECT' AND NOT a.is_grantable);
    IF total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Role nsi_importacao possui % concessao(oes) de banco inesperada(s). Abortando na preflight, sem nenhuma alteracao.', total_inesperadas;
    END IF;
END $$;

-- 1.5 - se o ambiente existir: role, membership e banco na forma exata.
DO $$
DECLARE total integer; total_inesperadas integer;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'nsi_ensaio') THEN
        RETURN;
    END IF;
    SELECT count(*) INTO total FROM pg_roles
     WHERE rolname = 'nsi_ensaio_migrator' AND rolcanlogin AND NOT rolsuper AND NOT rolcreatedb
       AND NOT rolcreaterole AND NOT rolreplication AND NOT rolbypassrls;
    IF total <> 1 THEN
        RAISE EXCEPTION 'Role nsi_ensaio_migrator com atributos diferentes dos especificados. Abortando na preflight, sem nenhuma alteracao.';
    END IF;
    SELECT count(*) INTO total FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.member
     WHERE r.rolname = 'nsi_ensaio_migrator';
    SELECT count(*) INTO total_inesperadas FROM pg_auth_members m JOIN pg_roles g ON g.oid = m.roleid
     WHERE g.rolname = 'nsi_ensaio_migrator';
    IF total <> 1 OR total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Role nsi_ensaio_migrator com membership inesperada (pertence_a=%, membros=%; esperado 1 e 0). Abortando na preflight, sem nenhuma alteracao.', total, total_inesperadas;
    END IF;

    SELECT count(*) INTO total
      FROM pg_database e, pg_database t
     WHERE e.datname = 'nsi_ensaio' AND t.datname = 'nsi_test'
       AND pg_encoding_to_char(e.encoding) = 'UTF8' AND e.encoding = t.encoding
       AND e.datcollate = t.datcollate AND e.datctype = t.datctype AND e.datlocprovider = t.datlocprovider;
    IF total <> 1 THEN
        RAISE EXCEPTION 'Banco nsi_ensaio com codificacao ou localidade diferente das de nsi_test. Abortando na preflight, sem nenhuma alteracao.';
    END IF;

    SELECT count(*) FILTER (WHERE a.grantee = 0 AND a.privilege_type = 'CONNECT'),
           count(*) FILTER (WHERE a.grantee <> 0 AND a.grantee <> d.datdba
                              AND NOT (a.privilege_type = 'CONNECT' AND NOT a.is_grantable
                                       AND pg_get_userbyid(a.grantee) IN ('nsi_ensaio_migrator', 'nsi_importacao')))
      INTO total, total_inesperadas
      FROM pg_database d CROSS JOIN LATERAL aclexplode(d.datacl) a
     WHERE d.datname = 'nsi_ensaio';
    IF total <> 0 OR total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Concessoes do banco nsi_ensaio fora do especificado (CONNECT de PUBLIC=%, inesperadas=%). Abortando na preflight, sem nenhuma alteracao.', total, total_inesperadas;
    END IF;
    SELECT count(*) INTO total
      FROM pg_database d CROSS JOIN LATERAL aclexplode(d.datacl) a
     WHERE d.datname = 'nsi_ensaio' AND a.privilege_type = 'CONNECT' AND NOT a.is_grantable
       AND pg_get_userbyid(a.grantee) IN ('nsi_ensaio_migrator', 'nsi_importacao');
    IF total <> 2 THEN
        RAISE EXCEPTION 'Banco nsi_ensaio sem o CONNECT de nsi_ensaio_migrator e de nsi_importacao. Abortando na preflight, sem nenhuma alteracao.';
    END IF;
END $$;

-- 1.6 - nsi_dev e nsi_test na revisao 0006.
\c nsi_dev
SET default_transaction_read_only = on;
DO $$
BEGIN
    IF current_setting('transaction_read_only') <> 'on' THEN
        RAISE EXCEPTION 'Modo somente leitura NAO esta ativo na Fase 1 (%). Abortando na preflight, sem nenhuma alteracao.', current_database();
    END IF;
    IF (SELECT version_num FROM nsi_operacional.alembic_version) IS DISTINCT FROM '0006' THEN
        RAISE EXCEPTION 'Banco % fora da revisao 0006. Abortando na preflight, sem nenhuma alteracao.', current_database();
    END IF;
END $$;

\c nsi_test
SET default_transaction_read_only = on;
DO $$
BEGIN
    IF current_setting('transaction_read_only') <> 'on' THEN
        RAISE EXCEPTION 'Modo somente leitura NAO esta ativo na Fase 1 (%). Abortando na preflight, sem nenhuma alteracao.', current_database();
    END IF;
    IF (SELECT version_num FROM nsi_operacional.alembic_version) IS DISTINCT FROM '0006' THEN
        RAISE EXCEPTION 'Banco % fora da revisao 0006. Abortando na preflight, sem nenhuma alteracao.', current_database();
    END IF;
END $$;

-- 1.7 - se o ambiente existir: schema e tabela de controle, dentro dele.
\c postgres
SET default_transaction_read_only = on;
DO $$
BEGIN
    IF current_setting('transaction_read_only') <> 'on' THEN
        RAISE EXCEPTION 'Modo somente leitura NAO esta ativo na Fase 1 (postgres). Abortando na preflight, sem nenhuma alteracao.';
    END IF;
END $$;
SELECT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'nsi_ensaio') AS f1_ambiente_presente
\gset
\if :f1_ambiente_presente
    \c nsi_ensaio
    SET default_transaction_read_only = on;
    DO $$
    DECLARE total integer; total_inesperadas integer;
    BEGIN
        IF current_setting('transaction_read_only') <> 'on' THEN
            RAISE EXCEPTION 'Modo somente leitura NAO esta ativo na Fase 1 (%). Abortando na preflight, sem nenhuma alteracao.', current_database();
        END IF;
        SELECT count(*) INTO total FROM pg_namespace n
         WHERE n.nspname = 'nsi_operacional' AND pg_get_userbyid(n.nspowner) = 'nsi_eventos_owner';
        IF total <> 1 THEN
            RAISE EXCEPTION 'Schema nsi_operacional ausente ou com dono inesperado em nsi_ensaio. Abortando na preflight, sem nenhuma alteracao.';
        END IF;
        SELECT count(*) FILTER (WHERE a.privilege_type = 'USAGE' AND NOT a.is_grantable
                                  AND pg_get_userbyid(a.grantee) IN ('nsi_ensaio_migrator', 'nsi_importacao')),
               count(*) FILTER (WHERE a.grantee <> n.nspowner
                                  AND NOT (a.privilege_type = 'USAGE' AND NOT a.is_grantable
                                           AND a.grantee <> 0
                                           AND pg_get_userbyid(a.grantee) IN ('nsi_ensaio_migrator', 'nsi_importacao')))
          INTO total, total_inesperadas
          FROM pg_namespace n CROSS JOIN LATERAL aclexplode(n.nspacl) a
         WHERE n.nspname = 'nsi_operacional';
        IF total <> 2 OR total_inesperadas <> 0 THEN
            RAISE EXCEPTION 'Concessoes do schema nsi_operacional em nsi_ensaio fora do especificado (USAGE esperados=% de 2, inesperadas=%). Abortando na preflight, sem nenhuma alteracao.', total, total_inesperadas;
        END IF;
        SELECT count(*) INTO total FROM pg_tables
         WHERE schemaname = 'nsi_operacional' AND tablename = 'alembic_version' AND tableowner = 'nsi_ensaio_migrator';
        IF total <> 1 THEN
            RAISE EXCEPTION 'Tabela de controle do Alembic ausente ou com dono inesperado em nsi_ensaio. Abortando na preflight, sem nenhuma alteracao.';
        END IF;
    END $$;
    \c postgres
    SET default_transaction_read_only = on;
\endif

\echo 'FASE 1 concluida - estado previsto; nenhuma escrita ocorreu.'

-- =============================================================
-- FASE 2 - CONVERGENCIA. UNICO ponto do script em que a escrita e
-- liberada. Le o estado de novo: ambiente ausente -> cria tudo, na ordem;
-- presente -> nada a fazer.
-- =============================================================
\echo 'FASE 2 - convergencia (escrita liberada).'
SET default_transaction_read_only = off;

SELECT (NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nsi_ensaio_migrator')
        AND NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'nsi_ensaio')) AS f2_ambiente_ausente
\gset
\if :f2_ambiente_ausente
    -- Acao 1 - migrator de ensaio, sem senha.
    CREATE ROLE nsi_ensaio_migrator LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
    -- Acao 2 - mesma membership dos migrators da B3.1.
    GRANT nsi_eventos_owner TO nsi_ensaio_migrator WITH INHERIT FALSE, SET TRUE, ADMIN FALSE;
    -- Acao 3 - banco descartavel, com a codificacao e a localidade de template0 (as de nsi_test).
    CREATE DATABASE nsi_ensaio TEMPLATE template0 ENCODING 'UTF8';
    -- Acao 4 - isolamento de CONNECT.
    REVOKE CONNECT ON DATABASE nsi_ensaio FROM PUBLIC;
    GRANT CONNECT ON DATABASE nsi_ensaio TO nsi_ensaio_migrator;
    GRANT CONNECT ON DATABASE nsi_ensaio TO nsi_importacao;
    -- Acao 5 - schema e tabela de controle do Alembic, dentro do banco novo.
    \c nsi_ensaio
    CREATE SCHEMA nsi_operacional AUTHORIZATION nsi_eventos_owner;
    GRANT USAGE ON SCHEMA nsi_operacional TO nsi_ensaio_migrator;
    GRANT USAGE ON SCHEMA nsi_operacional TO nsi_importacao;
    CREATE TABLE nsi_operacional.alembic_version (
        version_num VARCHAR(32) NOT NULL,
        CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
    );
    ALTER TABLE nsi_operacional.alembic_version OWNER TO nsi_ensaio_migrator;
    \c postgres
    \echo 'FASE 2: ambiente de ensaio criado.'
\else
    \echo 'FASE 2: ambiente de ensaio ja presente, nada a fazer.'
\endif

\echo 'FASE 2 concluida.'

-- =============================================================
-- FASE 3 - POS-VALIDACAO COMPLETA. READ ONLY obrigatorio. Reconfirma, a
-- partir do zero, TODO o estado final: o ambiente precisa existir, por
-- inteiro, na forma exata.
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

-- 3.2 - migrator de ensaio: atributos, membership unica e nenhum membro.
DO $$
DECLARE total integer; total_membros integer; total_exatas integer;
BEGIN
    SELECT count(*) INTO total FROM pg_roles
     WHERE rolname = 'nsi_ensaio_migrator' AND rolcanlogin AND NOT rolsuper AND NOT rolcreatedb
       AND NOT rolcreaterole AND NOT rolreplication AND NOT rolbypassrls;
    IF total <> 1 THEN
        RAISE EXCEPTION 'Pos-validacao falhou: role nsi_ensaio_migrator ausente ou com atributos diferentes dos especificados.';
    END IF;
    SELECT count(*),
           count(*) FILTER (WHERE g.rolname = 'nsi_eventos_owner' AND NOT m.inherit_option AND m.set_option AND NOT m.admin_option)
      INTO total, total_exatas
      FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.member JOIN pg_roles g ON g.oid = m.roleid
     WHERE r.rolname = 'nsi_ensaio_migrator';
    SELECT count(*) INTO total_membros FROM pg_auth_members m JOIN pg_roles g ON g.oid = m.roleid
     WHERE g.rolname = 'nsi_ensaio_migrator';
    IF total <> 1 OR total_exatas <> 1 OR total_membros <> 0 THEN
        RAISE EXCEPTION 'Pos-validacao falhou: membership de nsi_ensaio_migrator fora do especificado (linhas=%, exatas=%, membros=%).', total, total_exatas, total_membros;
    END IF;
END $$;

-- 3.3 - membros de nsi_eventos_owner: exatamente os tres migrators.
DO $$
DECLARE total integer; total_exatos integer;
BEGIN
    SELECT count(*),
           count(*) FILTER (WHERE r.rolname IN ('nsi_dev_migrator', 'nsi_test_migrator', 'nsi_ensaio_migrator')
                              AND NOT m.inherit_option AND m.set_option AND NOT m.admin_option)
      INTO total, total_exatos
      FROM pg_auth_members m JOIN pg_roles g ON g.oid = m.roleid JOIN pg_roles r ON r.oid = m.member
     WHERE g.rolname = 'nsi_eventos_owner';
    IF total <> 3 OR total_exatos <> 3 THEN
        RAISE EXCEPTION 'Pos-validacao falhou: membros de nsi_eventos_owner fora do previsto (linhas=%, exatos=%; esperado 3 e 3).', total, total_exatos;
    END IF;
END $$;

-- 3.4 - banco nsi_ensaio: codificacao e localidade de nsi_test; PUBLIC sem
-- CONNECT; CONNECT exatamente para o migrator de ensaio e nsi_importacao.
DO $$
DECLARE total integer; total_public integer; total_inesperadas integer;
BEGIN
    SELECT count(*) INTO total
      FROM pg_database e, pg_database t
     WHERE e.datname = 'nsi_ensaio' AND t.datname = 'nsi_test'
       AND pg_encoding_to_char(e.encoding) = 'UTF8' AND e.encoding = t.encoding
       AND e.datcollate = t.datcollate AND e.datctype = t.datctype AND e.datlocprovider = t.datlocprovider;
    IF total <> 1 THEN
        RAISE EXCEPTION 'Pos-validacao falhou: banco nsi_ensaio ausente ou com codificacao/localidade diferente das de nsi_test.';
    END IF;
    SELECT count(*) FILTER (WHERE a.grantee = 0 AND a.privilege_type = 'CONNECT'),
           count(*) FILTER (WHERE a.grantee <> 0 AND a.privilege_type = 'CONNECT' AND NOT a.is_grantable
                              AND pg_get_userbyid(a.grantee) IN ('nsi_ensaio_migrator', 'nsi_importacao')),
           count(*) FILTER (WHERE a.grantee <> 0 AND a.grantee <> d.datdba
                              AND NOT (a.privilege_type = 'CONNECT' AND NOT a.is_grantable
                                       AND pg_get_userbyid(a.grantee) IN ('nsi_ensaio_migrator', 'nsi_importacao')))
      INTO total_public, total, total_inesperadas
      FROM pg_database d CROSS JOIN LATERAL aclexplode(d.datacl) a
     WHERE d.datname = 'nsi_ensaio';
    IF total_public <> 0 OR total <> 2 OR total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Pos-validacao falhou: concessoes do banco nsi_ensaio fora do especificado (PUBLIC=%, esperadas=% de 2, inesperadas=%).', total_public, total, total_inesperadas;
    END IF;
    IF has_database_privilege('nsi_aplicacao', 'nsi_ensaio', 'CONNECT')
       OR has_database_privilege('nsi_expiracao', 'nsi_ensaio', 'CONNECT')
       OR has_database_privilege('nsi_operador_restrito', 'nsi_ensaio', 'CONNECT')
       OR has_database_privilege('nsi_dev_migrator', 'nsi_ensaio', 'CONNECT')
       OR has_database_privilege('nsi_test_migrator', 'nsi_ensaio', 'CONNECT') THEN
        RAISE EXCEPTION 'Pos-validacao falhou: role fora do previsto com CONNECT efetivo em nsi_ensaio.';
    END IF;
END $$;

-- 3.5 - nsi_importacao: CONNECT somente em nsi_test e nsi_ensaio.
DO $$
DECLARE total_inesperadas integer;
BEGIN
    SELECT count(*) INTO total_inesperadas
      FROM pg_database d
     CROSS JOIN LATERAL aclexplode(d.datacl) a
      JOIN pg_roles g ON g.oid = a.grantee
     WHERE g.rolname = 'nsi_importacao'
       AND NOT (d.datname IN ('nsi_test', 'nsi_ensaio') AND a.privilege_type = 'CONNECT' AND NOT a.is_grantable);
    IF total_inesperadas <> 0 OR has_database_privilege('nsi_importacao', 'nsi_dev', 'CONNECT') THEN
        RAISE EXCEPTION 'Pos-validacao falhou: nsi_importacao com concessao de banco fora do previsto.';
    END IF;
END $$;

-- 3.6 - dentro de nsi_ensaio: schema, USAGE e tabela de controle.
\c nsi_ensaio
SET default_transaction_read_only = on;
DO $$
DECLARE total integer; total_inesperadas integer;
BEGIN
    IF current_setting('transaction_read_only') <> 'on' THEN
        RAISE EXCEPTION 'Modo somente leitura NAO esta ativo na Fase 3 (%).', current_database();
    END IF;
    SELECT count(*) INTO total FROM pg_namespace n
     WHERE n.nspname = 'nsi_operacional' AND pg_get_userbyid(n.nspowner) = 'nsi_eventos_owner';
    IF total <> 1 THEN
        RAISE EXCEPTION 'Pos-validacao falhou: schema nsi_operacional ausente ou com dono inesperado em nsi_ensaio.';
    END IF;
    SELECT count(*) FILTER (WHERE a.privilege_type = 'USAGE' AND NOT a.is_grantable AND a.grantee <> 0
                              AND pg_get_userbyid(a.grantee) IN ('nsi_ensaio_migrator', 'nsi_importacao')),
           count(*) FILTER (WHERE a.grantee <> n.nspowner
                              AND NOT (a.privilege_type = 'USAGE' AND NOT a.is_grantable AND a.grantee <> 0
                                       AND pg_get_userbyid(a.grantee) IN ('nsi_ensaio_migrator', 'nsi_importacao')))
      INTO total, total_inesperadas
      FROM pg_namespace n CROSS JOIN LATERAL aclexplode(n.nspacl) a
     WHERE n.nspname = 'nsi_operacional';
    IF total <> 2 OR total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Pos-validacao falhou: concessoes do schema em nsi_ensaio fora do especificado (USAGE esperados=% de 2, inesperadas=%).', total, total_inesperadas;
    END IF;
    SELECT count(*) INTO total FROM pg_tables
     WHERE schemaname = 'nsi_operacional' AND tablename = 'alembic_version' AND tableowner = 'nsi_ensaio_migrator';
    IF total <> 1 THEN
        RAISE EXCEPTION 'Pos-validacao falhou: tabela de controle do Alembic ausente ou com dono inesperado em nsi_ensaio.';
    END IF;
    IF has_schema_privilege('nsi_importacao', 'nsi_operacional', 'CREATE')
       OR has_schema_privilege('nsi_ensaio_migrator', 'nsi_operacional', 'CREATE') THEN
        RAISE EXCEPTION 'Pos-validacao falhou: CREATE no schema concedido a role fora do previsto.';
    END IF;
END $$;

-- 3.7 - nsi_dev e nsi_test intocados: revisao 0006 e nenhuma concessao ao
-- migrator de ensaio.
\c nsi_dev
SET default_transaction_read_only = on;
DO $$
BEGIN
    IF current_setting('transaction_read_only') <> 'on' THEN
        RAISE EXCEPTION 'Modo somente leitura NAO esta ativo na Fase 3 (%).', current_database();
    END IF;
    IF (SELECT version_num FROM nsi_operacional.alembic_version) IS DISTINCT FROM '0006'
       OR has_database_privilege('nsi_ensaio_migrator', current_database(), 'CONNECT')
       OR has_schema_privilege('nsi_ensaio_migrator', 'nsi_operacional', 'USAGE') THEN
        RAISE EXCEPTION 'Pos-validacao falhou: % fora da revisao 0006 ou com acesso do migrator de ensaio.', current_database();
    END IF;
END $$;

\c nsi_test
SET default_transaction_read_only = on;
DO $$
BEGIN
    IF current_setting('transaction_read_only') <> 'on' THEN
        RAISE EXCEPTION 'Modo somente leitura NAO esta ativo na Fase 3 (%).', current_database();
    END IF;
    IF (SELECT version_num FROM nsi_operacional.alembic_version) IS DISTINCT FROM '0006'
       OR has_database_privilege('nsi_ensaio_migrator', current_database(), 'CONNECT')
       OR has_schema_privilege('nsi_ensaio_migrator', 'nsi_operacional', 'USAGE') THEN
        RAISE EXCEPTION 'Pos-validacao falhou: % fora da revisao 0006 ou com acesso do migrator de ensaio.', current_database();
    END IF;
END $$;

\c postgres
SET default_transaction_read_only = on;

-- =============================================================
-- ENCERRAMENTO
-- =============================================================
\echo 'Fase 3 (pos-validacao completa) passou integralmente.'
\echo ''
\echo 'LEMBRETES (manuais, fora deste script):'
\echo '  1. Definir a senha do migrator de ensaio:  \\password nsi_ensaio_migrator'
\echo '  2. Configurar no .env local, fora do versionamento:'
\echo '       ENSAIO_DATABASE_URL                (nsi_ensaio_migrator em nsi_ensaio)'
\echo '       ENSAIO_DATABASE_URL_NSI_IMPORTACAO (nsi_importacao em nsi_ensaio)'
\echo '  3. Aplicar as migrations, SOMENTE por upgrade:'
\echo '       NSI_DATABASE_ENV=ensaio alembic upgrade 0006'
\echo '  4. NUNCA executar downgrade em nsi_ensaio: o descarte e por'
\echo '     desprovisionar_b6_ensaio.sql, ao fim de TODA rodada.'
