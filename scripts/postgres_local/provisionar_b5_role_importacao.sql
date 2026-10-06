-- =============================================================
-- scripts/postgres_local/provisionar_b5_role_importacao.sql
-- Sprint B (B5.3) - ADR-010 (Secao 16) / Especificacao Tecnica da
-- Sprint B (Secao 18, B5.2, itens 4 e 20).
--
-- APENAS PARA DESENVOLVIMENTO/TESTE LOCAL. NUNCA PRODUCAO.
--
-- Execute conectado ao banco de manutencao "postgres":
--
--     psql -U postgres -d postgres -f scripts/postgres_local/provisionar_b5_role_importacao.sql
--
-- Pre-requisitos: provisionar_b3_roles.sql (B3.1) e
-- provisionar_b4_role_congelamento.sql (B4.3) ja executados - as quatro
-- roles funcionais, as memberships dos dois migrators, a propriedade do
-- schema "nsi_operacional" e a role nsi_congelamento (com a excecao unica
-- de membership da ADR-009, Secao 21) ja existem. Este script NUNCA recria
-- nem altera esses objetos.
--
-- O QUE ESTE SCRIPT FAZ (e nada alem disso):
--   1. cria a role nsi_importacao (LOGIN, de proposito unico: executar a
--      importacao do legado da ADR-010), com TODOS os atributos de
--      seguranca explicitos, sem senha;
--   2. concede CONNECT em nsi_test a nsi_importacao - SOMENTE em nsi_test
--      (B5.2, item 4; ADR-010, Secao 16.2);
--   3. concede USAGE no schema "nsi_operacional" a nsi_importacao, SOMENTE
--      em nsi_test.
--
-- O QUE ESTE SCRIPT NUNCA FAZ: nao concede CONNECT nem USAGE em nsi_dev;
-- nao concede EXECUTE nem privilegio em tabela; nao concede nem aceita
-- membership (nsi_importacao nao pertence a nenhuma role e nao tem
-- membros); nao revoga nem remove nada; nao altera atributo de nenhuma
-- role existente; nao toca nos migrators, em PUBLIC, nas quatro roles da
-- B3.1 nem em nsi_congelamento; nao cria tabela, funcao nem qualquer
-- objeto de banco; nao define senha. O EXECUTE das quatro funcoes de
-- importacao e concedido pela migration 0006 - nunca por este script.
--
-- Requer privilegio de superusuario - nesta maquina, o usuario "postgres"
-- da instalacao local.
--
-- NAO CONTEM SENHA. nsi_importacao e criada com LOGIN e SEM senha; o
-- operador define a senha interativamente, fora deste script, e configura
-- a URL TEST_DATABASE_URL_NSI_IMPORTACAO no .env (ver LEMBRETES no fim).
-- Uma reexecucao depois disso nunca toca a senha.
--
-- ESTE SCRIPT NAO E EXECUTADO AUTOMATICAMENTE por nenhum teste, por
-- migrations/env.py ou por qualquer codigo de aplicacao. Toda execucao -
-- a primeira ou uma repeticao - e um procedimento MANUAL autorizado.
--
-- ---------------------------------------------------------------
-- DESENHO DE TRES FASES
-- ---------------------------------------------------------------
-- FASE 1 (preflight): barreira global. Prova, antes de qualquer escrita em
--   qualquer banco, que o estado inteiro e um dos estados previstos.
--   Qualquer estado inesperado ABORTA aqui.
--
-- FASE 2 (convergencia): unica fase que escreve. Tres acoes, e so tres.
--   Cada acao confirma o estado do seu objeto imediatamente antes de
--   alterar, por leitura direta do servidor feita pela propria acao:
--   ausente -> executa; presente na forma exata -> nada a fazer; presente
--   em forma diferente -> ABORTA, nunca corrige.
--
-- FASE 3 (pos-validacao): reconfirma, a partir do zero, TODO o estado
--   final esperado.
--
-- GARANTIA ARQUITETURAL - READ ONLY NAS FASES 1 E 3: as Fases 1 e 3
--   executam integralmente com a sessao em modo somente leitura. Contrato
--   do script: qualquer comando de escrita nessas fases deve interromper
--   imediatamente a execucao, antes de produzir efeito e sem que nenhum
--   comando posterior seja executado. O modo e ligado no inicio de cada
--   fase e NOVAMENTE depois de cada \c (\c abre uma sessao nova, que nasce
--   em modo normal); logo apos ligar, o script le o modo efetivo da sessao
--   e aborta se ele nao estiver ativo. A escrita so e liberada em UM unico
--   ponto: o marcador da Fase 2.
--
-- PRINCIPIO ARQUITETURAL - CADA FASE E AUTOSSUFICIENTE: nenhuma fase
--   transmite estado, variaveis ou resultados para outra fase. A unica
--   informacao transmitida entre fases e o fato de a fase anterior ter
--   sido concluida com sucesso (o script para no primeiro erro). Toda
--   validacao e feita de novo, por leitura direta do estado atual do
--   servidor, dentro da fase que precisa dela. Dentro de uma mesma fase,
--   um valor pode ser levado de um banco para outro (variaveis de cliente
--   do psql, prefixadas pela fase: f1_ so na Fase 1, f3_ so na Fase 3).
--
-- REVISOES ACEITAS: nsi_dev e nsi_test na MESMA revisao do Alembic, 0005
--   ou 0006 (B5.2, item 4). Em 0005, nsi_importacao nao pode ter EXECUTE em
--   nenhuma funcao do schema; em 0006, tem EXECUTE somente nas quatro
--   funcoes de importacao (concedido pela migration, nos dois bancos - em
--   nsi_dev, sem CONNECT nem USAGE, a concessao e inerte). E isso que
--   permite reexecutar este script depois da migration 0006.
--
-- ALCANCE DE "NENHUM OUTRO PRIVILEGIO": verificam-se as concessoes
--   nominais a role (em qualquer objeto, de qualquer banco) e o privilegio
--   efetivo dela sobre os bancos nsi_dev/nsi_test e sobre o schema
--   "nsi_operacional" e seus objetos. O que toda role recebe de PUBLIC por
--   padrao do PostgreSQL (ex.: CONNECT no banco de manutencao "postgres",
--   TEMPORARY, funcoes internas) nao e tocado nem verificado - a B3.1 e a
--   B4.3 tambem nao o alteraram.
--
-- LIMITE ESTRUTURAL DE \c: o PostgreSQL nao tem transacao entre bancos
--   diferentes. A Fase 1 global elimina a classe de falha "ja escrevi X,
--   descobri que Y esta incompativel"; o risco remanescente e uma falha
--   NOVA em tempo de execucao no meio da Fase 2. A resposta e reexecutar
--   este mesmo script (idempotente por desenho), que completa o que
--   faltou - nunca desprovisionar como "conserto".
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

-- Verificacao de identidade do servidor - identica ao padrao ja usado em
-- provisionar_b3_roles.sql (B3.1) e provisionar_b4_role_congelamento.sql.
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

-- Privilegio de superusuario (CREATE ROLE e GRANT CONNECT exigem).
DO $$
BEGIN
    IF current_setting('is_superuser') <> 'on' THEN
        RAISE EXCEPTION 'Sessao sem privilegio de superusuario (session_user=%). Abortando sem nenhuma alteracao.', session_user;
    END IF;
END $$;

-- Os dois bancos precisam ja existir; este script nunca os cria.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'nsi_dev') THEN
        RAISE EXCEPTION 'Banco nsi_dev nao existe - execute provisionar_dev_teste.sql (B2.2) antes deste script. Abortando sem nenhuma alteracao.';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'nsi_test') THEN
        RAISE EXCEPTION 'Banco nsi_test nao existe - execute provisionar_dev_teste.sql (B2.2) antes deste script. Abortando sem nenhuma alteracao.';
    END IF;
END $$;

-- =============================================================
-- FASE 1 - PREFLIGHT. READ ONLY obrigatorio: nenhum CREATE/ALTER/GRANT/
-- REVOKE/DROP ocorre a partir daqui ate o marcador "FASE 2" abaixo.
-- =============================================================
\echo 'FASE 1 - preflight (somente leitura).'
SET default_transaction_read_only = on;
DO $$
BEGIN
    IF current_setting('transaction_read_only') <> 'on' THEN
        RAISE EXCEPTION 'Modo somente leitura NAO esta ativo na Fase 1 (postgres). Abortando na preflight, sem nenhuma alteracao.';
    END IF;
END $$;

-- 1.1 - as quatro roles da B3.1 existem, com os atributos aprovados.
DO $$
DECLARE
    nome_role text;
    canlogin_atual boolean; super_atual boolean; createdb_atual boolean;
    createrole_atual boolean; replication_atual boolean; bypassrls_atual boolean;
    inherit_atual boolean;
BEGIN
    FOREACH nome_role IN ARRAY ARRAY['nsi_eventos_owner', 'nsi_aplicacao', 'nsi_expiracao', 'nsi_operador_restrito'] LOOP
        SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls, rolinherit
          INTO canlogin_atual, super_atual, createdb_atual, createrole_atual, replication_atual, bypassrls_atual, inherit_atual
          FROM pg_roles WHERE rolname = nome_role;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'Role % nao existe - execute provisionar_b3_roles.sql (B3.1) antes deste script. Abortando na preflight, sem nenhuma alteracao.', nome_role;
        END IF;
        IF canlogin_atual IS DISTINCT FROM (nome_role <> 'nsi_eventos_owner')
           OR super_atual IS DISTINCT FROM false OR createdb_atual IS DISTINCT FROM false
           OR createrole_atual IS DISTINCT FROM false OR replication_atual IS DISTINCT FROM false
           OR bypassrls_atual IS DISTINCT FROM false OR inherit_atual IS DISTINCT FROM true THEN
            RAISE EXCEPTION 'Role % com atributos diferentes dos aprovados na B3.1 (canlogin=%, super=%, createdb=%, createrole=%, replication=%, bypassrls=%, inherit=%). Abortando na preflight, sem nenhuma alteracao.',
                nome_role, canlogin_atual, super_atual, createdb_atual, createrole_atual, replication_atual, bypassrls_atual, inherit_atual;
        END IF;
    END LOOP;
END $$;

-- 1.2 - memberships dos dois migrators em nsi_eventos_owner: intactas.
DO $$
DECLARE
    nome_migrator text;
    total_linhas integer; total_incompativeis integer;
BEGIN
    FOREACH nome_migrator IN ARRAY ARRAY['nsi_dev_migrator', 'nsi_test_migrator'] LOOP
        SELECT count(*),
               count(*) FILTER (WHERE m.inherit_option IS DISTINCT FROM false
                                   OR m.set_option IS DISTINCT FROM true
                                   OR m.admin_option IS DISTINCT FROM false)
          INTO total_linhas, total_incompativeis
          FROM pg_auth_members m
          JOIN pg_roles r_role ON r_role.oid = m.roleid
          JOIN pg_roles r_member ON r_member.oid = m.member
         WHERE r_role.rolname = 'nsi_eventos_owner' AND r_member.rolname = nome_migrator;
        IF total_linhas <> 1 OR total_incompativeis <> 0 THEN
            RAISE EXCEPTION 'Membership de % em nsi_eventos_owner fora do aprovado na B3.1 (linhas=%, incompativeis=%; esperado exatamente 1 linha com inherit=false, set=true, admin=false). Abortando na preflight, sem nenhuma alteracao.',
                nome_migrator, total_linhas, total_incompativeis;
        END IF;
    END LOOP;
END $$;

-- 1.3 - regra de membership da B3.1, com a excecao unica da ADR-009
-- (Secao 21): nsi_eventos_owner, nsi_expiracao e nsi_operador_restrito
-- nao pertencem a nenhuma role; nsi_aplicacao pertence exatamente a
-- nsi_congelamento (uma linha, INHERIT FALSE, SET TRUE, ADMIN FALSE) - a
-- B4.3 ja esta provisionada, por pre-requisito.
DO $$
DECLARE
    nome_role text;
    total_linhas integer; total_fora_da_excecao integer;
BEGIN
    FOREACH nome_role IN ARRAY ARRAY['nsi_eventos_owner', 'nsi_expiracao', 'nsi_operador_restrito'] LOOP
        SELECT count(*) INTO total_linhas
          FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.member
         WHERE r.rolname = nome_role;
        IF total_linhas <> 0 THEN
            RAISE EXCEPTION 'Role % pertence a % outra(s) role(s) - esperado zero (regra da B3.1). Abortando na preflight, sem nenhuma alteracao.', nome_role, total_linhas;
        END IF;
    END LOOP;

    SELECT count(*),
           count(*) FILTER (WHERE g.rolname <> 'nsi_congelamento'
                               OR m.inherit_option IS DISTINCT FROM false
                               OR m.set_option IS DISTINCT FROM true
                               OR m.admin_option IS DISTINCT FROM false)
      INTO total_linhas, total_fora_da_excecao
      FROM pg_auth_members m
      JOIN pg_roles r ON r.oid = m.member
      JOIN pg_roles g ON g.oid = m.roleid
     WHERE r.rolname = 'nsi_aplicacao';
    IF total_linhas <> 1 OR total_fora_da_excecao <> 0 THEN
        RAISE EXCEPTION 'nsi_aplicacao fora do estado da B4.3 (linhas=%, fora da excecao=%; esperado exatamente uma membership, em nsi_congelamento, com inherit=false, set=true, admin=false - ADR-009, Secao 21). Execute provisionar_b4_role_congelamento.sql (B4.3) antes deste script. Abortando na preflight, sem nenhuma alteracao.',
            total_linhas, total_fora_da_excecao;
    END IF;
END $$;

-- 1.4 - nsi_congelamento (B4.3) existe na forma exata: NOLOGIN, atributos
-- de seguranca explicitos, sem pertencer a nenhuma role, e com exatamente
-- um membro (nsi_aplicacao, com as tres opcoes exatas).
DO $$
DECLARE
    canlogin_atual boolean; super_atual boolean; createdb_atual boolean;
    createrole_atual boolean; replication_atual boolean; bypassrls_atual boolean;
    inherit_atual boolean;
    total_linhas integer; total_fora_da_excecao integer;
BEGIN
    SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls, rolinherit
      INTO canlogin_atual, super_atual, createdb_atual, createrole_atual, replication_atual, bypassrls_atual, inherit_atual
      FROM pg_roles WHERE rolname = 'nsi_congelamento';
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Role nsi_congelamento nao existe - execute provisionar_b4_role_congelamento.sql (B4.3) antes deste script. Abortando na preflight, sem nenhuma alteracao.';
    END IF;
    IF canlogin_atual IS DISTINCT FROM false OR super_atual IS DISTINCT FROM false
       OR createdb_atual IS DISTINCT FROM false OR createrole_atual IS DISTINCT FROM false
       OR replication_atual IS DISTINCT FROM false OR bypassrls_atual IS DISTINCT FROM false
       OR inherit_atual IS DISTINCT FROM true THEN
        RAISE EXCEPTION 'Role nsi_congelamento com atributos diferentes dos aprovados na B4.3 (canlogin=%, super=%, createdb=%, createrole=%, replication=%, bypassrls=%, inherit=%). Abortando na preflight, sem nenhuma alteracao.',
            canlogin_atual, super_atual, createdb_atual, createrole_atual, replication_atual, bypassrls_atual, inherit_atual;
    END IF;

    SELECT count(*) INTO total_linhas
      FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.member
     WHERE r.rolname = 'nsi_congelamento';
    IF total_linhas <> 0 THEN
        RAISE EXCEPTION 'Role nsi_congelamento pertence a % outra(s) role(s) - esperado zero. Abortando na preflight, sem nenhuma alteracao.', total_linhas;
    END IF;

    SELECT count(*),
           count(*) FILTER (WHERE r.rolname <> 'nsi_aplicacao'
                               OR m.inherit_option IS DISTINCT FROM false
                               OR m.set_option IS DISTINCT FROM true
                               OR m.admin_option IS DISTINCT FROM false)
      INTO total_linhas, total_fora_da_excecao
      FROM pg_auth_members m
      JOIN pg_roles r ON r.oid = m.member
      JOIN pg_roles g ON g.oid = m.roleid
     WHERE g.rolname = 'nsi_congelamento';
    IF total_linhas <> 1 OR total_fora_da_excecao <> 0 THEN
        RAISE EXCEPTION 'Role nsi_congelamento com membros fora do aprovado na B4.3 (linhas=%, fora da excecao=%; esperado exatamente nsi_aplicacao com inherit=false, set=true, admin=false). Abortando na preflight, sem nenhuma alteracao.',
            total_linhas, total_fora_da_excecao;
    END IF;
END $$;

-- 1.5 - nsi_importacao: ausente (aceito), ou presente exatamente na forma
-- esperada - LOGIN, atributos de seguranca explicitos, sem pertencer a
-- nenhuma role e sem nenhum membro. A senha nao e verificada: e definida
-- pelo operador, fora deste script, depois da primeira execucao.
DO $$
DECLARE
    canlogin_atual boolean; super_atual boolean; createdb_atual boolean;
    createrole_atual boolean; replication_atual boolean; bypassrls_atual boolean;
    inherit_atual boolean;
    total_pertence integer; total_membros integer;
BEGIN
    SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls, rolinherit
      INTO canlogin_atual, super_atual, createdb_atual, createrole_atual, replication_atual, bypassrls_atual, inherit_atual
      FROM pg_roles WHERE rolname = 'nsi_importacao';
    IF NOT FOUND THEN
        RETURN;
    END IF;

    IF canlogin_atual IS DISTINCT FROM true OR super_atual IS DISTINCT FROM false
       OR createdb_atual IS DISTINCT FROM false OR createrole_atual IS DISTINCT FROM false
       OR replication_atual IS DISTINCT FROM false OR bypassrls_atual IS DISTINCT FROM false
       OR inherit_atual IS DISTINCT FROM true THEN
        RAISE EXCEPTION 'Role nsi_importacao ja existe com atributos incompativeis (canlogin=%, super=%, createdb=%, createrole=%, replication=%, bypassrls=%, inherit=%). Abortando na preflight, sem nenhuma alteracao.',
            canlogin_atual, super_atual, createdb_atual, createrole_atual, replication_atual, bypassrls_atual, inherit_atual;
    END IF;

    SELECT count(*) INTO total_pertence
      FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.member
     WHERE r.rolname = 'nsi_importacao';
    SELECT count(*) INTO total_membros
      FROM pg_auth_members m JOIN pg_roles g ON g.oid = m.roleid
     WHERE g.rolname = 'nsi_importacao';
    IF total_pertence <> 0 OR total_membros <> 0 THEN
        RAISE EXCEPTION 'Role nsi_importacao com membership inesperada (pertence_a=%, membros=%; esperado zero e zero - ADR-010, Secao 16.2). Abortando na preflight, sem nenhuma alteracao.',
            total_pertence, total_membros;
    END IF;
END $$;

-- 1.6 - dependencias compartilhadas de nsi_importacao, em TODO o cluster
-- (pg_shdepend e um catalogo compartilhado): a role nao e dona de nada e
-- so pode ser citada (a) na lista de permissao do banco nsi_test - CONNECT
-- -, (b) em lista de permissao de schema de nsi_test, ou (c) em lista de
-- permissao de funcao de nsi_dev/nsi_test (EXECUTE concedido pela 0006).
-- Qualquer outra dependencia aborta. O detalhe e verificado a seguir.
DO $$
DECLARE total_inesperadas integer;
BEGIN
    SELECT count(*) INTO total_inesperadas
      FROM pg_shdepend s
      JOIN pg_roles r ON r.oid = s.refobjid
     WHERE s.refclassid = 'pg_authid'::regclass
       AND r.rolname = 'nsi_importacao'
       AND NOT (s.deptype = 'a' AND (
                (s.classid = 'pg_database'::regclass AND s.dbid = 0
                 AND s.objid = (SELECT oid FROM pg_database WHERE datname = 'nsi_test'))
             OR (s.classid = 'pg_namespace'::regclass
                 AND s.dbid = (SELECT oid FROM pg_database WHERE datname = 'nsi_test'))
             OR (s.classid = 'pg_proc'::regclass
                 AND s.dbid IN (SELECT oid FROM pg_database WHERE datname IN ('nsi_dev', 'nsi_test')))));
    IF total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Role nsi_importacao possui % dependencia(s) inesperada(s) no cluster (propriedade de objeto, ou concessao fora de CONNECT em nsi_test, schema de nsi_test ou funcao de nsi_dev/nsi_test). Abortando na preflight, sem nenhuma alteracao.', total_inesperadas;
    END IF;
END $$;

-- 1.7 - concessoes de banco a nsi_importacao: nenhuma, ou somente CONNECT
-- (sem GRANT OPTION) em nsi_test. Nunca em nsi_dev, nunca em outro banco.
DO $$
DECLARE total_inesperadas integer;
BEGIN
    SELECT count(*) INTO total_inesperadas
      FROM pg_database d
     CROSS JOIN LATERAL aclexplode(d.datacl) a
      JOIN pg_roles g ON g.oid = a.grantee
     WHERE g.rolname = 'nsi_importacao'
       AND NOT (d.datname = 'nsi_test' AND a.privilege_type = 'CONNECT' AND NOT a.is_grantable);
    IF total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Role nsi_importacao possui % concessao(oes) de banco inesperada(s) - aceito: nenhuma, ou somente CONNECT em nsi_test. Abortando na preflight, sem nenhuma alteracao.', total_inesperadas;
    END IF;
END $$;

-- 1.8 - nsi_dev: schema, revisao e concessoes nominais a nsi_importacao.
-- Em nsi_dev, nsi_importacao nao recebe nenhuma concessao de schema; em
-- 0006, so o EXECUTE das quatro funcoes, concedido pela migration.
\c nsi_dev
SET default_transaction_read_only = on;
DO $$
BEGIN
    IF current_setting('transaction_read_only') <> 'on' THEN
        RAISE EXCEPTION 'Modo somente leitura NAO esta ativo na Fase 1 (%). Abortando na preflight, sem nenhuma alteracao.', current_database();
    END IF;
END $$;
DO $$
DECLARE
    dono_atual name;
    total_linhas integer; revisao text; total_inesperadas integer;
BEGIN
    SELECT r.rolname INTO dono_atual
      FROM pg_namespace n JOIN pg_roles r ON r.oid = n.nspowner
     WHERE n.nspname = 'nsi_operacional';
    IF dono_atual IS NULL THEN
        RAISE EXCEPTION 'Schema nsi_operacional nao existe em %. Abortando na preflight, sem nenhuma alteracao.', current_database();
    END IF;
    IF dono_atual <> 'nsi_eventos_owner' THEN
        RAISE EXCEPTION 'Schema nsi_operacional em % tem dono inesperado (%) - esperado nsi_eventos_owner (B3.1). Abortando na preflight, sem nenhuma alteracao.', current_database(), dono_atual;
    END IF;

    IF to_regclass('nsi_operacional.alembic_version') IS NULL THEN
        RAISE EXCEPTION 'nsi_operacional.alembic_version nao existe em %. Abortando na preflight, sem nenhuma alteracao.', current_database();
    END IF;
    SELECT count(*) INTO total_linhas FROM nsi_operacional.alembic_version;
    IF total_linhas <> 1 THEN
        RAISE EXCEPTION 'nsi_operacional.alembic_version em % tem % linha(s), esperado exatamente 1. Abortando na preflight, sem nenhuma alteracao.', current_database(), total_linhas;
    END IF;
    SELECT version_num INTO revisao FROM nsi_operacional.alembic_version;
    IF revisao NOT IN ('0005', '0006') THEN
        RAISE EXCEPTION 'nsi_operacional.alembic_version em % esta em revisao % - aceito: 0005 ou 0006. Abortando na preflight, sem nenhuma alteracao.', current_database(), revisao;
    END IF;

    SELECT (SELECT count(*) FROM pg_class c JOIN pg_roles r ON r.oid = c.relowner WHERE r.rolname = 'nsi_importacao')
         + (SELECT count(*) FROM pg_proc p JOIN pg_roles r ON r.oid = p.proowner WHERE r.rolname = 'nsi_importacao')
         + (SELECT count(*) FROM pg_namespace n JOIN pg_roles r ON r.oid = n.nspowner WHERE r.rolname = 'nsi_importacao')
      INTO total_inesperadas;
    IF total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Role nsi_importacao e dona de % objeto(s) em % - esperado zero. Abortando na preflight, sem nenhuma alteracao.', total_inesperadas, current_database();
    END IF;

    SELECT count(*) INTO total_inesperadas
      FROM pg_namespace n
     CROSS JOIN LATERAL aclexplode(n.nspacl) a
      JOIN pg_roles g ON g.oid = a.grantee
     WHERE g.rolname = 'nsi_importacao';
    IF total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Role nsi_importacao possui % concessao(oes) em schema de % - esperado zero (nsi_importacao so recebe USAGE em nsi_test). Abortando na preflight, sem nenhuma alteracao.', total_inesperadas, current_database();
    END IF;

    SELECT (SELECT count(*) FROM pg_class c CROSS JOIN LATERAL aclexplode(c.relacl) a JOIN pg_roles g ON g.oid = a.grantee WHERE g.rolname = 'nsi_importacao')
         + (SELECT count(*) FROM pg_attribute t CROSS JOIN LATERAL aclexplode(t.attacl) a JOIN pg_roles g ON g.oid = a.grantee WHERE g.rolname = 'nsi_importacao')
         + (SELECT count(*) FROM pg_default_acl d CROSS JOIN LATERAL aclexplode(d.defaclacl) a JOIN pg_roles g ON g.oid = a.grantee WHERE g.rolname = 'nsi_importacao')
      INTO total_inesperadas;
    IF total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Role nsi_importacao possui % concessao(oes) em tabela, coluna ou privilegio padrao de % - esperado zero. Abortando na preflight, sem nenhuma alteracao.', total_inesperadas, current_database();
    END IF;

    SELECT count(*) INTO total_inesperadas
      FROM pg_proc p
      JOIN pg_namespace n ON n.oid = p.pronamespace
     CROSS JOIN LATERAL aclexplode(p.proacl) a
      JOIN pg_roles g ON g.oid = a.grantee
     WHERE g.rolname = 'nsi_importacao'
       AND NOT (revisao = '0006' AND n.nspname = 'nsi_operacional'
                AND p.proname IN ('fn_iniciar_importacao_legado', 'fn_importar_lote_legado',
                                  'fn_concluir_importacao_legado', 'fn_verificar_paridade_legado')
                AND a.privilege_type = 'EXECUTE' AND NOT a.is_grantable);
    IF total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Role nsi_importacao possui % concessao(oes) inesperada(s) em funcao de % (revisao %) - aceito: nenhuma em 0005; somente EXECUTE nas quatro funcoes de importacao em 0006. Abortando na preflight, sem nenhuma alteracao.', total_inesperadas, current_database(), revisao;
    END IF;
END $$;
SELECT version_num AS f1_revisao_dev FROM nsi_operacional.alembic_version
\gset

-- 1.9 - nsi_test: as mesmas verificacoes (aqui o USAGE em nsi_operacional
-- e aceito), e a mesma revisao de nsi_dev.
\c nsi_test
SET default_transaction_read_only = on;
DO $$
BEGIN
    IF current_setting('transaction_read_only') <> 'on' THEN
        RAISE EXCEPTION 'Modo somente leitura NAO esta ativo na Fase 1 (%). Abortando na preflight, sem nenhuma alteracao.', current_database();
    END IF;
END $$;
DO $$
DECLARE
    dono_atual name;
    total_linhas integer; revisao text; total_inesperadas integer;
BEGIN
    SELECT r.rolname INTO dono_atual
      FROM pg_namespace n JOIN pg_roles r ON r.oid = n.nspowner
     WHERE n.nspname = 'nsi_operacional';
    IF dono_atual IS NULL THEN
        RAISE EXCEPTION 'Schema nsi_operacional nao existe em %. Abortando na preflight, sem nenhuma alteracao.', current_database();
    END IF;
    IF dono_atual <> 'nsi_eventos_owner' THEN
        RAISE EXCEPTION 'Schema nsi_operacional em % tem dono inesperado (%) - esperado nsi_eventos_owner (B3.1). Abortando na preflight, sem nenhuma alteracao.', current_database(), dono_atual;
    END IF;

    IF to_regclass('nsi_operacional.alembic_version') IS NULL THEN
        RAISE EXCEPTION 'nsi_operacional.alembic_version nao existe em %. Abortando na preflight, sem nenhuma alteracao.', current_database();
    END IF;
    SELECT count(*) INTO total_linhas FROM nsi_operacional.alembic_version;
    IF total_linhas <> 1 THEN
        RAISE EXCEPTION 'nsi_operacional.alembic_version em % tem % linha(s), esperado exatamente 1. Abortando na preflight, sem nenhuma alteracao.', current_database(), total_linhas;
    END IF;
    SELECT version_num INTO revisao FROM nsi_operacional.alembic_version;
    IF revisao NOT IN ('0005', '0006') THEN
        RAISE EXCEPTION 'nsi_operacional.alembic_version em % esta em revisao % - aceito: 0005 ou 0006. Abortando na preflight, sem nenhuma alteracao.', current_database(), revisao;
    END IF;

    SELECT (SELECT count(*) FROM pg_class c JOIN pg_roles r ON r.oid = c.relowner WHERE r.rolname = 'nsi_importacao')
         + (SELECT count(*) FROM pg_proc p JOIN pg_roles r ON r.oid = p.proowner WHERE r.rolname = 'nsi_importacao')
         + (SELECT count(*) FROM pg_namespace n JOIN pg_roles r ON r.oid = n.nspowner WHERE r.rolname = 'nsi_importacao')
      INTO total_inesperadas;
    IF total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Role nsi_importacao e dona de % objeto(s) em % - esperado zero. Abortando na preflight, sem nenhuma alteracao.', total_inesperadas, current_database();
    END IF;

    SELECT count(*) INTO total_inesperadas
      FROM pg_namespace n
     CROSS JOIN LATERAL aclexplode(n.nspacl) a
      JOIN pg_roles g ON g.oid = a.grantee
     WHERE g.rolname = 'nsi_importacao'
       AND NOT (n.nspname = 'nsi_operacional' AND a.privilege_type = 'USAGE' AND NOT a.is_grantable);
    IF total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Role nsi_importacao possui % concessao(oes) inesperada(s) em schema de % - aceito: nenhuma, ou somente USAGE em nsi_operacional. Abortando na preflight, sem nenhuma alteracao.', total_inesperadas, current_database();
    END IF;

    SELECT (SELECT count(*) FROM pg_class c CROSS JOIN LATERAL aclexplode(c.relacl) a JOIN pg_roles g ON g.oid = a.grantee WHERE g.rolname = 'nsi_importacao')
         + (SELECT count(*) FROM pg_attribute t CROSS JOIN LATERAL aclexplode(t.attacl) a JOIN pg_roles g ON g.oid = a.grantee WHERE g.rolname = 'nsi_importacao')
         + (SELECT count(*) FROM pg_default_acl d CROSS JOIN LATERAL aclexplode(d.defaclacl) a JOIN pg_roles g ON g.oid = a.grantee WHERE g.rolname = 'nsi_importacao')
      INTO total_inesperadas;
    IF total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Role nsi_importacao possui % concessao(oes) em tabela, coluna ou privilegio padrao de % - esperado zero. Abortando na preflight, sem nenhuma alteracao.', total_inesperadas, current_database();
    END IF;

    SELECT count(*) INTO total_inesperadas
      FROM pg_proc p
      JOIN pg_namespace n ON n.oid = p.pronamespace
     CROSS JOIN LATERAL aclexplode(p.proacl) a
      JOIN pg_roles g ON g.oid = a.grantee
     WHERE g.rolname = 'nsi_importacao'
       AND NOT (revisao = '0006' AND n.nspname = 'nsi_operacional'
                AND p.proname IN ('fn_iniciar_importacao_legado', 'fn_importar_lote_legado',
                                  'fn_concluir_importacao_legado', 'fn_verificar_paridade_legado')
                AND a.privilege_type = 'EXECUTE' AND NOT a.is_grantable);
    IF total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Role nsi_importacao possui % concessao(oes) inesperada(s) em funcao de % (revisao %) - aceito: nenhuma em 0005; somente EXECUTE nas quatro funcoes de importacao em 0006. Abortando na preflight, sem nenhuma alteracao.', total_inesperadas, current_database(), revisao;
    END IF;
END $$;
SELECT (version_num <> :'f1_revisao_dev') AS f1_revisoes_divergem FROM nsi_operacional.alembic_version
\gset
\if :f1_revisoes_divergem
DO $$
BEGIN
    RAISE EXCEPTION 'nsi_dev e nsi_test estao em revisoes diferentes do Alembic - esperado a mesma revisao (0005 ou 0006) nos dois. Abortando na preflight, sem nenhuma alteracao.';
END $$;
\endif

-- Fim da FASE 1: de volta ao banco de manutencao, ainda em modo somente
-- leitura. O resumo abaixo e apenas informativo para quem le a saida - a
-- Fase 2 NAO o utiliza (cada acao le o estado por conta propria).
\c postgres
SET default_transaction_read_only = on;
DO $$
BEGIN
    IF current_setting('transaction_read_only') <> 'on' THEN
        RAISE EXCEPTION 'Modo somente leitura NAO esta ativo no fim da Fase 1 (postgres). Abortando na preflight, sem nenhuma alteracao.';
    END IF;
END $$;
SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nsi_importacao') AS role_presente,
       EXISTS (SELECT 1
                 FROM pg_shdepend s
                 JOIN pg_roles r ON r.oid = s.refobjid
                WHERE s.refclassid = 'pg_authid'::regclass AND r.rolname = 'nsi_importacao'
                  AND s.classid = 'pg_database'::regclass) AS connect_presente_nsi_test,
       EXISTS (SELECT 1
                 FROM pg_shdepend s
                 JOIN pg_roles r ON r.oid = s.refobjid
                WHERE s.refclassid = 'pg_authid'::regclass AND r.rolname = 'nsi_importacao'
                  AND s.classid = 'pg_namespace'::regclass) AS usage_presente_nsi_test;
\echo 'FASE 1 concluida - estado previsto; nenhuma escrita ocorreu.'

-- =============================================================
-- FASE 2 - CONVERGENCIA. UNICO ponto do script em que a escrita e
-- liberada. Tres acoes, e so tres. Cada acao confirma o estado do seu
-- objeto imediatamente antes de alterar, por leitura direta do servidor.
-- =============================================================
\echo 'FASE 2 - convergencia (escrita liberada).'
SET default_transaction_read_only = off;

-- Acao 1 - role nsi_importacao. Ausente: cria (LOGIN, sem senha).
-- Presente na forma exata: nada a fazer. Presente em forma diferente:
-- aborta, nunca corrige.
DO $$
DECLARE
    canlogin_atual boolean; super_atual boolean; createdb_atual boolean;
    createrole_atual boolean; replication_atual boolean; bypassrls_atual boolean;
    inherit_atual boolean; total_pertence integer; total_membros integer;
BEGIN
    SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls, rolinherit
      INTO canlogin_atual, super_atual, createdb_atual, createrole_atual, replication_atual, bypassrls_atual, inherit_atual
      FROM pg_roles WHERE rolname = 'nsi_importacao';
    IF NOT FOUND THEN
        EXECUTE 'CREATE ROLE nsi_importacao LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS';
        RAISE NOTICE 'Acao 1 (role nsi_importacao): executado - role criada, sem senha.';
        RETURN;
    END IF;

    SELECT count(*) INTO total_pertence
      FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.member
     WHERE r.rolname = 'nsi_importacao';
    SELECT count(*) INTO total_membros
      FROM pg_auth_members m JOIN pg_roles g ON g.oid = m.roleid
     WHERE g.rolname = 'nsi_importacao';
    IF canlogin_atual IS DISTINCT FROM true OR super_atual IS DISTINCT FROM false
       OR createdb_atual IS DISTINCT FROM false OR createrole_atual IS DISTINCT FROM false
       OR replication_atual IS DISTINCT FROM false OR bypassrls_atual IS DISTINCT FROM false
       OR inherit_atual IS DISTINCT FROM true OR total_pertence <> 0 OR total_membros <> 0 THEN
        RAISE EXCEPTION 'Acao 1: role nsi_importacao existe em forma diferente da esperada (canlogin=%, super=%, createdb=%, createrole=%, replication=%, bypassrls=%, inherit=%, pertence_a=%, membros=%). Abortando sem corrigir.',
            canlogin_atual, super_atual, createdb_atual, createrole_atual, replication_atual, bypassrls_atual, inherit_atual, total_pertence, total_membros;
    END IF;
    RAISE NOTICE 'Acao 1 (role nsi_importacao): ja presente, nada a fazer.';
END $$;

-- Acao 2 - CONNECT em nsi_test. Concessao declarativa, sempre reaplicada
-- (repetir nao muda nada). Qualquer outra concessao de banco a
-- nsi_importacao aborta, nunca e corrigida.
DO $$
DECLARE
    total_inesperadas integer; ja_presente boolean; total_depois integer;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nsi_importacao') THEN
        RAISE EXCEPTION 'Acao 2: role nsi_importacao nao existe. Abortando.';
    END IF;

    SELECT count(*) FILTER (WHERE NOT (d.datname = 'nsi_test' AND a.privilege_type = 'CONNECT' AND NOT a.is_grantable)),
           count(*) FILTER (WHERE d.datname = 'nsi_test' AND a.privilege_type = 'CONNECT' AND NOT a.is_grantable) > 0
      INTO total_inesperadas, ja_presente
      FROM pg_database d
     CROSS JOIN LATERAL aclexplode(d.datacl) a
      JOIN pg_roles g ON g.oid = a.grantee
     WHERE g.rolname = 'nsi_importacao';
    IF total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Acao 2: nsi_importacao possui % concessao(oes) de banco inesperada(s). Abortando sem corrigir.', total_inesperadas;
    END IF;

    EXECUTE 'GRANT CONNECT ON DATABASE nsi_test TO nsi_importacao';

    SELECT count(*) INTO total_depois
      FROM pg_database d
     CROSS JOIN LATERAL aclexplode(d.datacl) a
      JOIN pg_roles g ON g.oid = a.grantee
     WHERE g.rolname = 'nsi_importacao' AND d.datname = 'nsi_test'
       AND a.privilege_type = 'CONNECT' AND NOT a.is_grantable;
    IF total_depois <> 1 THEN
        RAISE EXCEPTION 'Acao 2: concessao sem efeito - nsi_importacao sem CONNECT em nsi_test depois do GRANT. Abortando; acao desfeita.';
    END IF;
    IF ja_presente THEN
        RAISE NOTICE 'Acao 2 (CONNECT em nsi_test): ja presente, nada a fazer (concessao reaplicada sem efeito).';
    ELSE
        RAISE NOTICE 'Acao 2 (CONNECT em nsi_test): executado - CONNECT concedido.';
    END IF;
END $$;

-- Acao 3 - USAGE no schema nsi_operacional, em nsi_test. Concessao
-- declarativa, sempre reaplicada.
\c nsi_test
DO $$
DECLARE
    dono_atual name; total_inesperadas integer; ja_presente boolean;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nsi_importacao') THEN
        RAISE EXCEPTION 'USAGE em %: role nsi_importacao nao existe. Abortando.', current_database();
    END IF;
    SELECT r.rolname INTO dono_atual
      FROM pg_namespace n JOIN pg_roles r ON r.oid = n.nspowner
     WHERE n.nspname = 'nsi_operacional';
    IF dono_atual IS DISTINCT FROM 'nsi_eventos_owner' THEN
        RAISE EXCEPTION 'USAGE em %: schema nsi_operacional ausente ou com dono inesperado (%). Abortando sem corrigir.', current_database(), dono_atual;
    END IF;

    SELECT count(*) FILTER (WHERE NOT (n.nspname = 'nsi_operacional' AND a.privilege_type = 'USAGE' AND NOT a.is_grantable)),
           count(*) FILTER (WHERE n.nspname = 'nsi_operacional' AND a.privilege_type = 'USAGE' AND NOT a.is_grantable) > 0
      INTO total_inesperadas, ja_presente
      FROM pg_namespace n
     CROSS JOIN LATERAL aclexplode(n.nspacl) a
      JOIN pg_roles g ON g.oid = a.grantee
     WHERE g.rolname = 'nsi_importacao';
    IF total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'USAGE em %: nsi_importacao possui % concessao(oes) inesperada(s) em schema. Abortando sem corrigir.', current_database(), total_inesperadas;
    END IF;

    EXECUTE 'GRANT USAGE ON SCHEMA nsi_operacional TO nsi_importacao';
    IF ja_presente THEN
        RAISE NOTICE 'Acao 3 (USAGE no schema, %): ja presente, nada a fazer (concessao reaplicada sem efeito).', current_database();
    ELSE
        RAISE NOTICE 'Acao 3 (USAGE no schema, %): executado - USAGE concedido.', current_database();
    END IF;
END $$;

\c postgres
\echo 'FASE 2 concluida.'

-- =============================================================
-- FASE 3 - POS-VALIDACAO COMPLETA. READ ONLY obrigatorio. Reconfirma, a
-- partir do zero (nunca reaproveitando nada das Fases 1 e 2), TODO o
-- estado final esperado.
-- =============================================================
\echo 'FASE 3 - pos-validacao completa (somente leitura).'
SET default_transaction_read_only = on;
DO $$
BEGIN
    IF current_setting('transaction_read_only') <> 'on' THEN
        RAISE EXCEPTION 'Pos-validacao falhou: modo somente leitura NAO esta ativo na Fase 3 (postgres).';
    END IF;
END $$;

-- 3.1 - nsi_importacao existe, na forma exata, sem pertencer a nenhuma
-- role e sem nenhum membro.
DO $$
DECLARE
    canlogin_atual boolean; super_atual boolean; createdb_atual boolean;
    createrole_atual boolean; replication_atual boolean; bypassrls_atual boolean;
    inherit_atual boolean; total_pertence integer; total_membros integer;
BEGIN
    SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls, rolinherit
      INTO canlogin_atual, super_atual, createdb_atual, createrole_atual, replication_atual, bypassrls_atual, inherit_atual
      FROM pg_roles WHERE rolname = 'nsi_importacao';
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Pos-validacao falhou: role nsi_importacao nao existe.';
    END IF;
    IF canlogin_atual IS DISTINCT FROM true OR super_atual IS DISTINCT FROM false
       OR createdb_atual IS DISTINCT FROM false OR createrole_atual IS DISTINCT FROM false
       OR replication_atual IS DISTINCT FROM false OR bypassrls_atual IS DISTINCT FROM false
       OR inherit_atual IS DISTINCT FROM true THEN
        RAISE EXCEPTION 'Pos-validacao falhou: role nsi_importacao com atributos incorretos (canlogin=%, super=%, createdb=%, createrole=%, replication=%, bypassrls=%, inherit=%).',
            canlogin_atual, super_atual, createdb_atual, createrole_atual, replication_atual, bypassrls_atual, inherit_atual;
    END IF;

    SELECT count(*) INTO total_pertence
      FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.member
     WHERE r.rolname = 'nsi_importacao';
    SELECT count(*) INTO total_membros
      FROM pg_auth_members m JOIN pg_roles g ON g.oid = m.roleid
     WHERE g.rolname = 'nsi_importacao';
    IF total_pertence <> 0 OR total_membros <> 0 THEN
        RAISE EXCEPTION 'Pos-validacao falhou: role nsi_importacao com membership (pertence_a=%, membros=%; esperado zero e zero).', total_pertence, total_membros;
    END IF;
END $$;
\echo '  3.1 role nsi_importacao, sem membership: ok.'

-- 3.2 - as quatro roles da B3.1 continuam com os atributos aprovados; tres
-- delas sem nenhuma membership; nsi_aplicacao com exatamente a membership
-- da ADR-009 (Secao 21); nsi_congelamento intacta; memberships dos
-- migrators intactas.
DO $$
DECLARE
    nome_role text;
    canlogin_atual boolean; super_atual boolean; createdb_atual boolean;
    createrole_atual boolean; replication_atual boolean; bypassrls_atual boolean;
    inherit_atual boolean;
    total_linhas integer; total_incompativeis integer;
BEGIN
    FOREACH nome_role IN ARRAY ARRAY['nsi_eventos_owner', 'nsi_aplicacao', 'nsi_expiracao', 'nsi_operador_restrito'] LOOP
        SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls, rolinherit
          INTO canlogin_atual, super_atual, createdb_atual, createrole_atual, replication_atual, bypassrls_atual, inherit_atual
          FROM pg_roles WHERE rolname = nome_role;
        IF NOT FOUND
           OR canlogin_atual IS DISTINCT FROM (nome_role <> 'nsi_eventos_owner')
           OR super_atual IS DISTINCT FROM false OR createdb_atual IS DISTINCT FROM false
           OR createrole_atual IS DISTINCT FROM false OR replication_atual IS DISTINCT FROM false
           OR bypassrls_atual IS DISTINCT FROM false OR inherit_atual IS DISTINCT FROM true THEN
            RAISE EXCEPTION 'Pos-validacao falhou: role % ausente ou com atributos diferentes dos aprovados na B3.1.', nome_role;
        END IF;
    END LOOP;

    FOREACH nome_role IN ARRAY ARRAY['nsi_eventos_owner', 'nsi_expiracao', 'nsi_operador_restrito', 'nsi_congelamento'] LOOP
        SELECT count(*) INTO total_linhas
          FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.member
         WHERE r.rolname = nome_role;
        IF total_linhas <> 0 THEN
            RAISE EXCEPTION 'Pos-validacao falhou: role % pertence a % outra(s) role(s) - esperado zero.', nome_role, total_linhas;
        END IF;
    END LOOP;

    SELECT count(*),
           count(*) FILTER (WHERE g.rolname <> 'nsi_congelamento'
                               OR m.inherit_option IS DISTINCT FROM false
                               OR m.set_option IS DISTINCT FROM true
                               OR m.admin_option IS DISTINCT FROM false)
      INTO total_linhas, total_incompativeis
      FROM pg_auth_members m
      JOIN pg_roles r ON r.oid = m.member
      JOIN pg_roles g ON g.oid = m.roleid
     WHERE r.rolname = 'nsi_aplicacao';
    IF total_linhas <> 1 OR total_incompativeis <> 0 THEN
        RAISE EXCEPTION 'Pos-validacao falhou: memberships de nsi_aplicacao incorretas (linhas=%, fora da excecao=%; esperado exatamente uma, em nsi_congelamento, com inherit=false, set=true, admin=false - ADR-009, Secao 21).', total_linhas, total_incompativeis;
    END IF;

    -- nsi_congelamento: mesma forma exata conferida na Fase 1 (passo 1.4).
    SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls, rolinherit
      INTO canlogin_atual, super_atual, createdb_atual, createrole_atual, replication_atual, bypassrls_atual, inherit_atual
      FROM pg_roles WHERE rolname = 'nsi_congelamento';
    IF NOT FOUND
       OR canlogin_atual IS DISTINCT FROM false OR super_atual IS DISTINCT FROM false
       OR createdb_atual IS DISTINCT FROM false OR createrole_atual IS DISTINCT FROM false
       OR replication_atual IS DISTINCT FROM false OR bypassrls_atual IS DISTINCT FROM false
       OR inherit_atual IS DISTINCT FROM true THEN
        RAISE EXCEPTION 'Pos-validacao falhou: role nsi_congelamento ausente ou com atributos diferentes dos aprovados na B4.3.';
    END IF;

    SELECT count(*),
           count(*) FILTER (WHERE r.rolname <> 'nsi_aplicacao'
                               OR m.inherit_option IS DISTINCT FROM false
                               OR m.set_option IS DISTINCT FROM true
                               OR m.admin_option IS DISTINCT FROM false)
      INTO total_linhas, total_incompativeis
      FROM pg_auth_members m
      JOIN pg_roles r ON r.oid = m.member
      JOIN pg_roles g ON g.oid = m.roleid
     WHERE g.rolname = 'nsi_congelamento';
    IF total_linhas <> 1 OR total_incompativeis <> 0 THEN
        RAISE EXCEPTION 'Pos-validacao falhou: membros de nsi_congelamento fora do aprovado na B4.3 (linhas=%, fora da excecao=%; esperado exatamente nsi_aplicacao com inherit=false, set=true, admin=false).', total_linhas, total_incompativeis;
    END IF;

    FOREACH nome_role IN ARRAY ARRAY['nsi_dev_migrator', 'nsi_test_migrator'] LOOP
        SELECT count(*),
               count(*) FILTER (WHERE m.inherit_option IS DISTINCT FROM false
                                   OR m.set_option IS DISTINCT FROM true
                                   OR m.admin_option IS DISTINCT FROM false)
          INTO total_linhas, total_incompativeis
          FROM pg_auth_members m
          JOIN pg_roles r_role ON r_role.oid = m.roleid
          JOIN pg_roles r_member ON r_member.oid = m.member
         WHERE r_role.rolname = 'nsi_eventos_owner' AND r_member.rolname = nome_role;
        IF total_linhas <> 1 OR total_incompativeis <> 0 THEN
            RAISE EXCEPTION 'Pos-validacao falhou: membership de % em nsi_eventos_owner fora do aprovado na B3.1 (linhas=%, incompativeis=%).', nome_role, total_linhas, total_incompativeis;
        END IF;
    END LOOP;
END $$;
\echo '  3.2 roles da B3.1, nsi_congelamento e memberships: ok.'

-- 3.3 - dependencias compartilhadas de nsi_importacao, em todo o cluster:
-- nada alem de CONNECT em nsi_test, schema de nsi_test e funcao de
-- nsi_dev/nsi_test.
DO $$
DECLARE total_inesperadas integer;
BEGIN
    SELECT count(*) INTO total_inesperadas
      FROM pg_shdepend s
      JOIN pg_roles r ON r.oid = s.refobjid
     WHERE s.refclassid = 'pg_authid'::regclass
       AND r.rolname = 'nsi_importacao'
       AND NOT (s.deptype = 'a' AND (
                (s.classid = 'pg_database'::regclass AND s.dbid = 0
                 AND s.objid = (SELECT oid FROM pg_database WHERE datname = 'nsi_test'))
             OR (s.classid = 'pg_namespace'::regclass
                 AND s.dbid = (SELECT oid FROM pg_database WHERE datname = 'nsi_test'))
             OR (s.classid = 'pg_proc'::regclass
                 AND s.dbid IN (SELECT oid FROM pg_database WHERE datname IN ('nsi_dev', 'nsi_test')))));
    IF total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Pos-validacao falhou: role nsi_importacao possui % dependencia(s) inesperada(s) no cluster.', total_inesperadas;
    END IF;
END $$;
\echo '  3.3 nenhuma dependencia inesperada no cluster: ok.'

-- 3.4 - bancos: PUBLIC continua sem CONNECT em nsi_dev e nsi_test (B3.1);
-- nsi_importacao tem exatamente CONNECT em nsi_test, nenhuma outra
-- concessao de banco, e nenhum CONNECT efetivo em nsi_dev.
DO $$
DECLARE
    nome_banco text; lista_nula boolean; total_public integer;
    total_connect_test integer; total_inesperadas integer;
BEGIN
    FOREACH nome_banco IN ARRAY ARRAY['nsi_dev', 'nsi_test'] LOOP
        SELECT d.datacl IS NULL INTO lista_nula FROM pg_database d WHERE d.datname = nome_banco;
        SELECT count(*) INTO total_public
          FROM pg_database d CROSS JOIN LATERAL aclexplode(d.datacl) a
         WHERE d.datname = nome_banco AND a.grantee = 0 AND a.privilege_type = 'CONNECT';
        IF lista_nula IS DISTINCT FROM false OR total_public <> 0 THEN
            RAISE EXCEPTION 'Pos-validacao falhou: PUBLIC possui CONNECT em % (B3.1 exige que nao possua).', nome_banco;
        END IF;
    END LOOP;

    SELECT count(*) FILTER (WHERE d.datname = 'nsi_test' AND a.privilege_type = 'CONNECT' AND NOT a.is_grantable),
           count(*) FILTER (WHERE NOT (d.datname = 'nsi_test' AND a.privilege_type = 'CONNECT' AND NOT a.is_grantable))
      INTO total_connect_test, total_inesperadas
      FROM pg_database d
     CROSS JOIN LATERAL aclexplode(d.datacl) a
      JOIN pg_roles g ON g.oid = a.grantee
     WHERE g.rolname = 'nsi_importacao';
    IF total_connect_test <> 1 OR total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Pos-validacao falhou: concessoes de banco a nsi_importacao incorretas (CONNECT em nsi_test=%, inesperadas=%; esperado exatamente 1 e 0).', total_connect_test, total_inesperadas;
    END IF;

    IF NOT has_database_privilege('nsi_importacao', 'nsi_test', 'CONNECT') THEN
        RAISE EXCEPTION 'Pos-validacao falhou: nsi_importacao sem CONNECT efetivo em nsi_test.';
    END IF;
    IF has_database_privilege('nsi_importacao', 'nsi_dev', 'CONNECT') THEN
        RAISE EXCEPTION 'Pos-validacao falhou: nsi_importacao com CONNECT efetivo em nsi_dev - a importacao nunca ocorre em nsi_dev (ADR-010, Secao 21).';
    END IF;
    IF has_database_privilege('nsi_importacao', 'nsi_dev', 'CREATE') OR has_database_privilege('nsi_importacao', 'nsi_test', 'CREATE') THEN
        RAISE EXCEPTION 'Pos-validacao falhou: nsi_importacao com CREATE efetivo em banco.';
    END IF;
END $$;
\echo '  3.4 bancos: PUBLIC sem CONNECT; nsi_importacao com CONNECT somente em nsi_test: ok.'

-- 3.5 - nsi_dev: schema, revisao, concessoes nominais e privilegio efetivo.
-- Nenhum USAGE; EXECUTE somente nas quatro funcoes, e somente em 0006.
\c nsi_dev
SET default_transaction_read_only = on;
DO $$
BEGIN
    IF current_setting('transaction_read_only') <> 'on' THEN
        RAISE EXCEPTION 'Pos-validacao falhou: modo somente leitura NAO esta ativo na Fase 3 (%).', current_database();
    END IF;
END $$;
DO $$
DECLARE
    dono_atual name; dono_alembic name; migrator_esperado text;
    total_linhas integer; revisao text; total_inesperadas integer;
BEGIN
    migrator_esperado := CASE current_database() WHEN 'nsi_dev' THEN 'nsi_dev_migrator' WHEN 'nsi_test' THEN 'nsi_test_migrator' END;

    SELECT r.rolname INTO dono_atual
      FROM pg_namespace n JOIN pg_roles r ON r.oid = n.nspowner
     WHERE n.nspname = 'nsi_operacional';
    IF dono_atual IS DISTINCT FROM 'nsi_eventos_owner' THEN
        RAISE EXCEPTION 'Pos-validacao falhou: schema nsi_operacional em % ausente ou com dono inesperado (%).', current_database(), dono_atual;
    END IF;

    SELECT tableowner INTO dono_alembic FROM pg_catalog.pg_tables
     WHERE schemaname = 'nsi_operacional' AND tablename = 'alembic_version';
    IF dono_alembic IS DISTINCT FROM migrator_esperado THEN
        RAISE EXCEPTION 'Pos-validacao falhou: nsi_operacional.alembic_version em % pertence a % - esperado %.', current_database(), dono_alembic, migrator_esperado;
    END IF;
    SELECT count(*) INTO total_linhas FROM nsi_operacional.alembic_version;
    IF total_linhas <> 1 THEN
        RAISE EXCEPTION 'Pos-validacao falhou: nsi_operacional.alembic_version em % tem % linha(s), esperado exatamente 1.', current_database(), total_linhas;
    END IF;
    SELECT version_num INTO revisao FROM nsi_operacional.alembic_version;
    IF revisao NOT IN ('0005', '0006') THEN
        RAISE EXCEPTION 'Pos-validacao falhou: % esta em revisao % - aceito: 0005 ou 0006.', current_database(), revisao;
    END IF;

    -- Concessoes nominais.
    SELECT (SELECT count(*) FROM pg_class c JOIN pg_roles r ON r.oid = c.relowner WHERE r.rolname = 'nsi_importacao')
         + (SELECT count(*) FROM pg_proc p JOIN pg_roles r ON r.oid = p.proowner WHERE r.rolname = 'nsi_importacao')
         + (SELECT count(*) FROM pg_namespace n JOIN pg_roles r ON r.oid = n.nspowner WHERE r.rolname = 'nsi_importacao')
      INTO total_inesperadas;
    IF total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Pos-validacao falhou: role nsi_importacao e dona de % objeto(s) em %.', total_inesperadas, current_database();
    END IF;

    SELECT count(*) INTO total_inesperadas
      FROM pg_namespace n
     CROSS JOIN LATERAL aclexplode(n.nspacl) a
      JOIN pg_roles g ON g.oid = a.grantee
     WHERE g.rolname = 'nsi_importacao';
    IF total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Pos-validacao falhou: nsi_importacao possui % concessao(oes) de schema em % - esperado zero.', total_inesperadas, current_database();
    END IF;

    SELECT (SELECT count(*) FROM pg_class c CROSS JOIN LATERAL aclexplode(c.relacl) a JOIN pg_roles g ON g.oid = a.grantee WHERE g.rolname = 'nsi_importacao')
         + (SELECT count(*) FROM pg_attribute t CROSS JOIN LATERAL aclexplode(t.attacl) a JOIN pg_roles g ON g.oid = a.grantee WHERE g.rolname = 'nsi_importacao')
         + (SELECT count(*) FROM pg_default_acl d CROSS JOIN LATERAL aclexplode(d.defaclacl) a JOIN pg_roles g ON g.oid = a.grantee WHERE g.rolname = 'nsi_importacao')
      INTO total_inesperadas;
    IF total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Pos-validacao falhou: role nsi_importacao possui % concessao(oes) em tabela, coluna ou privilegio padrao de %.', total_inesperadas, current_database();
    END IF;

    SELECT count(*) INTO total_inesperadas
      FROM pg_proc p
      JOIN pg_namespace n ON n.oid = p.pronamespace
     CROSS JOIN LATERAL aclexplode(p.proacl) a
      JOIN pg_roles g ON g.oid = a.grantee
     WHERE g.rolname = 'nsi_importacao'
       AND NOT (revisao = '0006' AND n.nspname = 'nsi_operacional'
                AND p.proname IN ('fn_iniciar_importacao_legado', 'fn_importar_lote_legado',
                                  'fn_concluir_importacao_legado', 'fn_verificar_paridade_legado')
                AND a.privilege_type = 'EXECUTE' AND NOT a.is_grantable);
    IF total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Pos-validacao falhou: role nsi_importacao possui % concessao(oes) inesperada(s) em funcao de % (revisao %).', total_inesperadas, current_database(), revisao;
    END IF;

    -- Privilegio efetivo sobre o schema nsi_operacional e seus objetos.
    IF has_schema_privilege('nsi_importacao', 'nsi_operacional', 'USAGE') THEN
        RAISE EXCEPTION 'Pos-validacao falhou: nsi_importacao com USAGE efetivo no schema nsi_operacional em % - esperado nenhum.', current_database();
    END IF;
    IF has_schema_privilege('nsi_importacao', 'nsi_operacional', 'CREATE') THEN
        RAISE EXCEPTION 'Pos-validacao falhou: nsi_importacao com CREATE no schema nsi_operacional em %.', current_database();
    END IF;

    SELECT count(*) INTO total_inesperadas
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'nsi_operacional' AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
       AND (has_table_privilege('nsi_importacao', c.oid, 'SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER')
            OR has_any_column_privilege('nsi_importacao', c.oid, 'SELECT, INSERT, UPDATE, REFERENCES'));
    IF total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Pos-validacao falhou: nsi_importacao possui privilegio efetivo em % tabela(s) do schema nsi_operacional em % - esperado zero.', total_inesperadas, current_database();
    END IF;

    SELECT count(*) INTO total_inesperadas
      FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
     WHERE n.nspname = 'nsi_operacional'
       AND has_function_privilege('nsi_importacao', p.oid, 'EXECUTE')
       AND NOT (revisao = '0006' AND p.proname IN ('fn_iniciar_importacao_legado', 'fn_importar_lote_legado',
                                                  'fn_concluir_importacao_legado', 'fn_verificar_paridade_legado'));
    IF total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Pos-validacao falhou: nsi_importacao possui EXECUTE efetivo em % funcao(oes) inesperada(s) do schema nsi_operacional em % (revisao %).', total_inesperadas, current_database(), revisao;
    END IF;

    IF revisao = '0006' THEN
        SELECT count(*) INTO total_linhas
          FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
         WHERE n.nspname = 'nsi_operacional'
           AND p.proname IN ('fn_iniciar_importacao_legado', 'fn_importar_lote_legado',
                             'fn_concluir_importacao_legado', 'fn_verificar_paridade_legado')
           AND has_function_privilege('nsi_importacao', p.oid, 'EXECUTE');
        IF total_linhas <> 4 THEN
            RAISE EXCEPTION 'Pos-validacao falhou: em revisao 0006, nsi_importacao deveria ter EXECUTE em exatamente as quatro funcoes de importacao em % (encontrado: %).', current_database(), total_linhas;
        END IF;
    END IF;
END $$;
SELECT version_num AS f3_revisao_dev FROM nsi_operacional.alembic_version
\gset
\echo '  3.5 nsi_dev - schema, revisao, concessoes e privilegio efetivo: ok.'

-- 3.6 - nsi_test: USAGE exatamente uma vez; EXECUTE somente nas quatro
-- funcoes, e somente em 0006; a mesma revisao de nsi_dev.
\c nsi_test
SET default_transaction_read_only = on;
DO $$
BEGIN
    IF current_setting('transaction_read_only') <> 'on' THEN
        RAISE EXCEPTION 'Pos-validacao falhou: modo somente leitura NAO esta ativo na Fase 3 (%).', current_database();
    END IF;
END $$;
DO $$
DECLARE
    dono_atual name; dono_alembic name; migrator_esperado text;
    total_linhas integer; revisao text; total_inesperadas integer; total_usage integer;
BEGIN
    migrator_esperado := CASE current_database() WHEN 'nsi_dev' THEN 'nsi_dev_migrator' WHEN 'nsi_test' THEN 'nsi_test_migrator' END;

    SELECT r.rolname INTO dono_atual
      FROM pg_namespace n JOIN pg_roles r ON r.oid = n.nspowner
     WHERE n.nspname = 'nsi_operacional';
    IF dono_atual IS DISTINCT FROM 'nsi_eventos_owner' THEN
        RAISE EXCEPTION 'Pos-validacao falhou: schema nsi_operacional em % ausente ou com dono inesperado (%).', current_database(), dono_atual;
    END IF;

    SELECT tableowner INTO dono_alembic FROM pg_catalog.pg_tables
     WHERE schemaname = 'nsi_operacional' AND tablename = 'alembic_version';
    IF dono_alembic IS DISTINCT FROM migrator_esperado THEN
        RAISE EXCEPTION 'Pos-validacao falhou: nsi_operacional.alembic_version em % pertence a % - esperado %.', current_database(), dono_alembic, migrator_esperado;
    END IF;
    SELECT count(*) INTO total_linhas FROM nsi_operacional.alembic_version;
    IF total_linhas <> 1 THEN
        RAISE EXCEPTION 'Pos-validacao falhou: nsi_operacional.alembic_version em % tem % linha(s), esperado exatamente 1.', current_database(), total_linhas;
    END IF;
    SELECT version_num INTO revisao FROM nsi_operacional.alembic_version;
    IF revisao NOT IN ('0005', '0006') THEN
        RAISE EXCEPTION 'Pos-validacao falhou: % esta em revisao % - aceito: 0005 ou 0006.', current_database(), revisao;
    END IF;

    -- Concessoes nominais.
    SELECT (SELECT count(*) FROM pg_class c JOIN pg_roles r ON r.oid = c.relowner WHERE r.rolname = 'nsi_importacao')
         + (SELECT count(*) FROM pg_proc p JOIN pg_roles r ON r.oid = p.proowner WHERE r.rolname = 'nsi_importacao')
         + (SELECT count(*) FROM pg_namespace n JOIN pg_roles r ON r.oid = n.nspowner WHERE r.rolname = 'nsi_importacao')
      INTO total_inesperadas;
    IF total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Pos-validacao falhou: role nsi_importacao e dona de % objeto(s) em %.', total_inesperadas, current_database();
    END IF;

    SELECT count(*) FILTER (WHERE NOT (n.nspname = 'nsi_operacional' AND a.privilege_type = 'USAGE' AND NOT a.is_grantable)),
           count(*) FILTER (WHERE n.nspname = 'nsi_operacional' AND a.privilege_type = 'USAGE' AND NOT a.is_grantable)
      INTO total_inesperadas, total_usage
      FROM pg_namespace n
     CROSS JOIN LATERAL aclexplode(n.nspacl) a
      JOIN pg_roles g ON g.oid = a.grantee
     WHERE g.rolname = 'nsi_importacao';
    IF total_inesperadas <> 0 OR total_usage <> 1 THEN
        RAISE EXCEPTION 'Pos-validacao falhou: concessoes de schema a nsi_importacao em % incorretas (USAGE em nsi_operacional=%, inesperadas=%; esperado exatamente 1 e 0).', current_database(), total_usage, total_inesperadas;
    END IF;

    SELECT (SELECT count(*) FROM pg_class c CROSS JOIN LATERAL aclexplode(c.relacl) a JOIN pg_roles g ON g.oid = a.grantee WHERE g.rolname = 'nsi_importacao')
         + (SELECT count(*) FROM pg_attribute t CROSS JOIN LATERAL aclexplode(t.attacl) a JOIN pg_roles g ON g.oid = a.grantee WHERE g.rolname = 'nsi_importacao')
         + (SELECT count(*) FROM pg_default_acl d CROSS JOIN LATERAL aclexplode(d.defaclacl) a JOIN pg_roles g ON g.oid = a.grantee WHERE g.rolname = 'nsi_importacao')
      INTO total_inesperadas;
    IF total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Pos-validacao falhou: role nsi_importacao possui % concessao(oes) em tabela, coluna ou privilegio padrao de %.', total_inesperadas, current_database();
    END IF;

    SELECT count(*) INTO total_inesperadas
      FROM pg_proc p
      JOIN pg_namespace n ON n.oid = p.pronamespace
     CROSS JOIN LATERAL aclexplode(p.proacl) a
      JOIN pg_roles g ON g.oid = a.grantee
     WHERE g.rolname = 'nsi_importacao'
       AND NOT (revisao = '0006' AND n.nspname = 'nsi_operacional'
                AND p.proname IN ('fn_iniciar_importacao_legado', 'fn_importar_lote_legado',
                                  'fn_concluir_importacao_legado', 'fn_verificar_paridade_legado')
                AND a.privilege_type = 'EXECUTE' AND NOT a.is_grantable);
    IF total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Pos-validacao falhou: role nsi_importacao possui % concessao(oes) inesperada(s) em funcao de % (revisao %).', total_inesperadas, current_database(), revisao;
    END IF;

    -- Privilegio efetivo sobre o schema nsi_operacional e seus objetos.
    IF NOT has_schema_privilege('nsi_importacao', 'nsi_operacional', 'USAGE') THEN
        RAISE EXCEPTION 'Pos-validacao falhou: nsi_importacao sem USAGE efetivo no schema nsi_operacional em %.', current_database();
    END IF;
    IF has_schema_privilege('nsi_importacao', 'nsi_operacional', 'CREATE') THEN
        RAISE EXCEPTION 'Pos-validacao falhou: nsi_importacao com CREATE no schema nsi_operacional em %.', current_database();
    END IF;

    SELECT count(*) INTO total_inesperadas
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'nsi_operacional' AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
       AND (has_table_privilege('nsi_importacao', c.oid, 'SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER')
            OR has_any_column_privilege('nsi_importacao', c.oid, 'SELECT, INSERT, UPDATE, REFERENCES'));
    IF total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Pos-validacao falhou: nsi_importacao possui privilegio efetivo em % tabela(s) do schema nsi_operacional em % - esperado zero.', total_inesperadas, current_database();
    END IF;

    SELECT count(*) INTO total_inesperadas
      FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
     WHERE n.nspname = 'nsi_operacional'
       AND has_function_privilege('nsi_importacao', p.oid, 'EXECUTE')
       AND NOT (revisao = '0006' AND p.proname IN ('fn_iniciar_importacao_legado', 'fn_importar_lote_legado',
                                                  'fn_concluir_importacao_legado', 'fn_verificar_paridade_legado'));
    IF total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Pos-validacao falhou: nsi_importacao possui EXECUTE efetivo em % funcao(oes) inesperada(s) do schema nsi_operacional em % (revisao %).', total_inesperadas, current_database(), revisao;
    END IF;

    IF revisao = '0006' THEN
        SELECT count(*) INTO total_linhas
          FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
         WHERE n.nspname = 'nsi_operacional'
           AND p.proname IN ('fn_iniciar_importacao_legado', 'fn_importar_lote_legado',
                             'fn_concluir_importacao_legado', 'fn_verificar_paridade_legado')
           AND has_function_privilege('nsi_importacao', p.oid, 'EXECUTE');
        IF total_linhas <> 4 THEN
            RAISE EXCEPTION 'Pos-validacao falhou: em revisao 0006, nsi_importacao deveria ter EXECUTE em exatamente as quatro funcoes de importacao em % (encontrado: %).', current_database(), total_linhas;
        END IF;
    END IF;
END $$;
SELECT (version_num <> :'f3_revisao_dev') AS f3_revisoes_divergem FROM nsi_operacional.alembic_version
\gset
\if :f3_revisoes_divergem
DO $$
BEGIN
    RAISE EXCEPTION 'Pos-validacao falhou: nsi_dev e nsi_test estao em revisoes diferentes do Alembic.';
END $$;
\endif
\echo '  3.6 nsi_test - schema, revisao, concessoes e privilegio efetivo: ok.'

-- =============================================================
-- ENCERRAMENTO. De volta ao banco de manutencao, em modo somente leitura.
-- =============================================================
\c postgres
SET default_transaction_read_only = on;
DO $$
BEGIN
    IF current_setting('transaction_read_only') <> 'on' THEN
        RAISE EXCEPTION 'Pos-validacao falhou: modo somente leitura NAO esta ativo no encerramento (postgres).';
    END IF;
END $$;
\echo 'provisionar_b5_role_importacao.sql concluido - Fase 3 (pos-validacao completa) passou integralmente.'

-- =============================================================
-- LEMBRETES (fora deste script).
--
-- 1. Depois da PRIMEIRA execucao, o operador define a senha de
--    nsi_importacao interativamente (no psql, como superusuario:
--    \password nsi_importacao) e configura, no .env local (fora do
--    versionamento), a variavel TEST_DATABASE_URL_NSI_IMPORTACAO apontando
--    para nsi_test com o usuario nsi_importacao. Este script nunca le nem
--    define senha; reexecuta-lo depois disso nao toca a senha.
--
-- 2. Depois da migration 0006, scripts/postgres_local/
--    provisionar_b4_role_congelamento.sql deixa de ser reexecutavel (aceita
--    somente 0004 ou 0005) - limitacao registrada e aceita na B5.2 (item
--    4); os artefatos da B4 nao sao alterados.
--
-- 3. O EXECUTE das quatro funcoes de importacao e concedido pela migration
--    0006 - nunca por este script. Reexecutar este script depois da
--    migration comprova, pela Fase 3, a matriz final de privilegios da role.
--
-- 4. Ao fim da importacao definitiva (B7) e da sua validacao, a role e
--    desabilitada (NOLOGIN) por ato administrativo proprio (ADR-010, Secao
--    16.5) - nunca por este script.
-- =============================================================
