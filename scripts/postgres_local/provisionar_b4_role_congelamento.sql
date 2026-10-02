-- =============================================================
-- scripts/postgres_local/provisionar_b4_role_congelamento.sql
-- Sprint B (B4.3, Etapa 1) - ADR-009 (Secoes 11 e 21) / Especificacao
-- Tecnica da Sprint B (Secao 18, "Role nsi_congelamento").
--
-- APENAS PARA DESENVOLVIMENTO/TESTE LOCAL. NUNCA PRODUCAO.
--
-- Execute conectado ao banco de manutencao "postgres":
--
--     psql -U postgres -d postgres -f scripts/postgres_local/provisionar_b4_role_congelamento.sql
--
-- Pre-requisito: scripts/postgres_local/provisionar_b3_roles.sql (B3.1)
-- ja executado - as quatro roles funcionais, as memberships dos dois
-- migrators e a propriedade do schema "nsi_operacional" ja existem. Este
-- script NUNCA recria nem altera esses objetos.
--
-- O QUE ESTE SCRIPT FAZ (e nada alem disso):
--   1. cria a role nsi_congelamento (NOLOGIN, de proposito unico), com
--      TODOS os atributos de seguranca explicitos;
--   2. concede a membership de nsi_aplicacao em nsi_congelamento, com
--      INHERIT FALSE, SET TRUE, ADMIN FALSE - a excecao unica a regra de
--      membership da B3.1, formalizada na ADR-009 (Secao 21);
--   3. concede USAGE no schema "nsi_operacional" a nsi_congelamento, em
--      nsi_dev e em nsi_test.
--
-- O QUE ESTE SCRIPT NUNCA FAZ: nao concede CONNECT, EXECUTE nem privilegio
-- em tabela; nao revoga nem remove nada; nao altera atributo de nenhuma
-- role existente; nao toca nos migrators, em PUBLIC nem nas outras tres
-- roles da B3.1; nao cria tabela, funcao nem qualquer objeto de banco; nao
-- define senha. O EXECUTE da funcao de congelamento e concedido pela
-- migration 0005 - nunca por este script.
--
-- Requer privilegio de superusuario - nesta maquina, o usuario "postgres"
-- da instalacao local.
--
-- NAO CONTEM SENHA. nsi_congelamento e NOLOGIN - nunca recebe senha, nunca
-- e usada para conexao. So e alcancada por SET ROLE explicito, a partir de
-- uma conexao nsi_aplicacao.
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
-- FASE 2 (convergencia): unica fase que escreve. Quatro acoes, e so
--   quatro. Cada acao confirma o estado do seu objeto imediatamente antes
--   de alterar, por leitura direta do servidor feita pela propria acao:
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
--   ponto: o marcador da Fase 2. Esta protecao faz parte das garantias do
--   script - nao depende da disciplina de quem o escreve ou edita.
--
-- PRINCIPIO ARQUITETURAL - CADA FASE E AUTOSSUFICIENTE: nenhuma fase
--   transmite estado, variaveis ou resultados para outra fase. A unica
--   informacao transmitida entre fases e o fato de a fase anterior ter
--   sido concluida com sucesso (o script para no primeiro erro). Toda
--   validacao e feita de novo, por leitura direta do estado atual do
--   servidor, dentro da fase que precisa dela. Dentro de uma mesma fase,
--   um valor pode ser levado de um banco para outro (variaveis de cliente
--   do psql, prefixadas pela fase: f1_ so na Fase 1, f3_ so na Fase 3).
--   Diferenca deliberada em relacao a provisionar_b3_roles.sql, em que a
--   Fase 1 decide e a Fase 2 "nunca recalcula".
--
-- REVISOES ACEITAS: nsi_dev e nsi_test na MESMA revisao do Alembic, 0004
--   ou 0005. Em 0004, nsi_congelamento nao pode ter EXECUTE em nenhuma
--   funcao do schema; em 0005, tem EXECUTE somente em
--   fn_registrar_congelamento (concedido pela migration). E isso que
--   permite reexecutar este script depois da migration 0005.
--
-- ALCANCE DE "NENHUM OUTRO PRIVILEGIO": verificam-se as concessoes
--   nominais a role (em qualquer objeto, de qualquer banco) e o privilegio
--   efetivo dela sobre o schema "nsi_operacional" e seus objetos. O que
--   toda role recebe de PUBLIC por padrao do PostgreSQL (ex.: TEMPORARY
--   nos bancos, funcoes internas) nao e tocado nem verificado - a B3.1
--   tambem nao o alterou.
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
-- provisionar_b3_roles.sql (B3.1).
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

-- Privilegio de superusuario (CREATE ROLE, GRANT de membership e leitura
-- de pg_authid exigem).
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
-- nao pertencem a nenhuma role; nsi_aplicacao nao pertence a nenhuma, ou
-- pertence exatamente a nsi_congelamento (uma linha, INHERIT FALSE,
-- SET TRUE, ADMIN FALSE).
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
    IF total_linhas > 1 OR total_fora_da_excecao <> 0 THEN
        RAISE EXCEPTION 'nsi_aplicacao possui membership inesperada (linhas=%, fora da excecao=%; aceito: nenhuma, ou exatamente uma em nsi_congelamento com inherit=false, set=true, admin=false - ADR-009, Secao 21). Abortando na preflight, sem nenhuma alteracao.',
            total_linhas, total_fora_da_excecao;
    END IF;
END $$;

-- 1.4 - nsi_congelamento: ausente (aceito), ou presente exatamente na
-- forma esperada - atributos, sem pertencer a nenhuma role, e com no
-- maximo um membro (nsi_aplicacao, com as tres opcoes exatas).
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
        RETURN;
    END IF;

    IF canlogin_atual IS DISTINCT FROM false OR super_atual IS DISTINCT FROM false
       OR createdb_atual IS DISTINCT FROM false OR createrole_atual IS DISTINCT FROM false
       OR replication_atual IS DISTINCT FROM false OR bypassrls_atual IS DISTINCT FROM false
       OR inherit_atual IS DISTINCT FROM true THEN
        RAISE EXCEPTION 'Role nsi_congelamento ja existe com atributos incompativeis (canlogin=%, super=%, createdb=%, createrole=%, replication=%, bypassrls=%, inherit=%). Abortando na preflight, sem nenhuma alteracao.',
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
    IF total_linhas > 1 OR total_fora_da_excecao <> 0 THEN
        RAISE EXCEPTION 'Role nsi_congelamento possui membro(s) inesperado(s) (linhas=%, fora da excecao=%; aceito: nenhum, ou exatamente nsi_aplicacao com inherit=false, set=true, admin=false). Abortando na preflight, sem nenhuma alteracao.',
            total_linhas, total_fora_da_excecao;
    END IF;
END $$;

-- 1.5 - nsi_congelamento, se existir, nao tem senha (pg_authid - leitura
-- exclusiva de superusuario).
DO $$
DECLARE tem_senha boolean;
BEGIN
    SELECT rolpassword IS NOT NULL INTO tem_senha FROM pg_authid WHERE rolname = 'nsi_congelamento';
    IF FOUND AND tem_senha THEN
        RAISE EXCEPTION 'Role nsi_congelamento possui senha definida - esperado nenhuma (role NOLOGIN, nunca usada para conexao). Abortando na preflight, sem nenhuma alteracao.';
    END IF;
END $$;

-- 1.6 - dependencias compartilhadas de nsi_congelamento, em TODO o
-- cluster (pg_shdepend e um catalogo compartilhado): a role nao e dona de
-- nada e so pode ser citada em listas de permissao de schema ou de funcao,
-- e somente em nsi_dev/nsi_test. Qualquer outra dependencia (propriedade
-- de objeto, concessao em banco, tabela, tipo, ou em qualquer outro banco)
-- aborta. O detalhe de QUAL schema/funcao e verificado banco a banco, a
-- seguir.
DO $$
DECLARE total_inesperadas integer;
BEGIN
    SELECT count(*) INTO total_inesperadas
      FROM pg_shdepend s
      JOIN pg_roles r ON r.oid = s.refobjid
     WHERE s.refclassid = 'pg_authid'::regclass
       AND r.rolname = 'nsi_congelamento'
       AND NOT (s.deptype = 'a'
                AND s.classid IN ('pg_namespace'::regclass, 'pg_proc'::regclass)
                AND s.dbid IN (SELECT oid FROM pg_database WHERE datname IN ('nsi_dev', 'nsi_test')));
    IF total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Role nsi_congelamento possui % dependencia(s) inesperada(s) no cluster (propriedade de objeto, ou concessao fora de schema/funcao de nsi_dev/nsi_test). Abortando na preflight, sem nenhuma alteracao.', total_inesperadas;
    END IF;
END $$;

-- 1.7 - nsi_dev: schema, revisao e concessoes nominais a nsi_congelamento.
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
    IF revisao NOT IN ('0004', '0005') THEN
        RAISE EXCEPTION 'nsi_operacional.alembic_version em % esta em revisao % - aceito: 0004 ou 0005. Abortando na preflight, sem nenhuma alteracao.', current_database(), revisao;
    END IF;

    SELECT (SELECT count(*) FROM pg_class c JOIN pg_roles r ON r.oid = c.relowner WHERE r.rolname = 'nsi_congelamento')
         + (SELECT count(*) FROM pg_proc p JOIN pg_roles r ON r.oid = p.proowner WHERE r.rolname = 'nsi_congelamento')
         + (SELECT count(*) FROM pg_namespace n JOIN pg_roles r ON r.oid = n.nspowner WHERE r.rolname = 'nsi_congelamento')
      INTO total_inesperadas;
    IF total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Role nsi_congelamento e dona de % objeto(s) em % - esperado zero. Abortando na preflight, sem nenhuma alteracao.', total_inesperadas, current_database();
    END IF;

    SELECT count(*) INTO total_inesperadas
      FROM pg_namespace n
     CROSS JOIN LATERAL aclexplode(n.nspacl) a
      JOIN pg_roles g ON g.oid = a.grantee
     WHERE g.rolname = 'nsi_congelamento'
       AND NOT (n.nspname = 'nsi_operacional' AND a.privilege_type = 'USAGE' AND NOT a.is_grantable);
    IF total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Role nsi_congelamento possui % concessao(oes) inesperada(s) em schema de % - aceito: nenhuma, ou somente USAGE em nsi_operacional. Abortando na preflight, sem nenhuma alteracao.', total_inesperadas, current_database();
    END IF;

    SELECT (SELECT count(*) FROM pg_class c CROSS JOIN LATERAL aclexplode(c.relacl) a JOIN pg_roles g ON g.oid = a.grantee WHERE g.rolname = 'nsi_congelamento')
         + (SELECT count(*) FROM pg_attribute t CROSS JOIN LATERAL aclexplode(t.attacl) a JOIN pg_roles g ON g.oid = a.grantee WHERE g.rolname = 'nsi_congelamento')
         + (SELECT count(*) FROM pg_default_acl d CROSS JOIN LATERAL aclexplode(d.defaclacl) a JOIN pg_roles g ON g.oid = a.grantee WHERE g.rolname = 'nsi_congelamento')
      INTO total_inesperadas;
    IF total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Role nsi_congelamento possui % concessao(oes) em tabela, coluna ou privilegio padrao de % - esperado zero. Abortando na preflight, sem nenhuma alteracao.', total_inesperadas, current_database();
    END IF;

    SELECT count(*) INTO total_inesperadas
      FROM pg_proc p
      JOIN pg_namespace n ON n.oid = p.pronamespace
     CROSS JOIN LATERAL aclexplode(p.proacl) a
      JOIN pg_roles g ON g.oid = a.grantee
     WHERE g.rolname = 'nsi_congelamento'
       AND NOT (revisao = '0005' AND n.nspname = 'nsi_operacional'
                AND p.proname = 'fn_registrar_congelamento'
                AND a.privilege_type = 'EXECUTE' AND NOT a.is_grantable);
    IF total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Role nsi_congelamento possui % concessao(oes) inesperada(s) em funcao de % (revisao %) - aceito: nenhuma em 0004; somente EXECUTE em nsi_operacional.fn_registrar_congelamento em 0005. Abortando na preflight, sem nenhuma alteracao.', total_inesperadas, current_database(), revisao;
    END IF;
END $$;
SELECT version_num AS f1_revisao_dev FROM nsi_operacional.alembic_version
\gset

-- 1.8 - nsi_test: as mesmas verificacoes, e a mesma revisao de nsi_dev.
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
    IF revisao NOT IN ('0004', '0005') THEN
        RAISE EXCEPTION 'nsi_operacional.alembic_version em % esta em revisao % - aceito: 0004 ou 0005. Abortando na preflight, sem nenhuma alteracao.', current_database(), revisao;
    END IF;

    SELECT (SELECT count(*) FROM pg_class c JOIN pg_roles r ON r.oid = c.relowner WHERE r.rolname = 'nsi_congelamento')
         + (SELECT count(*) FROM pg_proc p JOIN pg_roles r ON r.oid = p.proowner WHERE r.rolname = 'nsi_congelamento')
         + (SELECT count(*) FROM pg_namespace n JOIN pg_roles r ON r.oid = n.nspowner WHERE r.rolname = 'nsi_congelamento')
      INTO total_inesperadas;
    IF total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Role nsi_congelamento e dona de % objeto(s) em % - esperado zero. Abortando na preflight, sem nenhuma alteracao.', total_inesperadas, current_database();
    END IF;

    SELECT count(*) INTO total_inesperadas
      FROM pg_namespace n
     CROSS JOIN LATERAL aclexplode(n.nspacl) a
      JOIN pg_roles g ON g.oid = a.grantee
     WHERE g.rolname = 'nsi_congelamento'
       AND NOT (n.nspname = 'nsi_operacional' AND a.privilege_type = 'USAGE' AND NOT a.is_grantable);
    IF total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Role nsi_congelamento possui % concessao(oes) inesperada(s) em schema de % - aceito: nenhuma, ou somente USAGE em nsi_operacional. Abortando na preflight, sem nenhuma alteracao.', total_inesperadas, current_database();
    END IF;

    SELECT (SELECT count(*) FROM pg_class c CROSS JOIN LATERAL aclexplode(c.relacl) a JOIN pg_roles g ON g.oid = a.grantee WHERE g.rolname = 'nsi_congelamento')
         + (SELECT count(*) FROM pg_attribute t CROSS JOIN LATERAL aclexplode(t.attacl) a JOIN pg_roles g ON g.oid = a.grantee WHERE g.rolname = 'nsi_congelamento')
         + (SELECT count(*) FROM pg_default_acl d CROSS JOIN LATERAL aclexplode(d.defaclacl) a JOIN pg_roles g ON g.oid = a.grantee WHERE g.rolname = 'nsi_congelamento')
      INTO total_inesperadas;
    IF total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Role nsi_congelamento possui % concessao(oes) em tabela, coluna ou privilegio padrao de % - esperado zero. Abortando na preflight, sem nenhuma alteracao.', total_inesperadas, current_database();
    END IF;

    SELECT count(*) INTO total_inesperadas
      FROM pg_proc p
      JOIN pg_namespace n ON n.oid = p.pronamespace
     CROSS JOIN LATERAL aclexplode(p.proacl) a
      JOIN pg_roles g ON g.oid = a.grantee
     WHERE g.rolname = 'nsi_congelamento'
       AND NOT (revisao = '0005' AND n.nspname = 'nsi_operacional'
                AND p.proname = 'fn_registrar_congelamento'
                AND a.privilege_type = 'EXECUTE' AND NOT a.is_grantable);
    IF total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Role nsi_congelamento possui % concessao(oes) inesperada(s) em funcao de % (revisao %) - aceito: nenhuma em 0004; somente EXECUTE em nsi_operacional.fn_registrar_congelamento em 0005. Abortando na preflight, sem nenhuma alteracao.', total_inesperadas, current_database(), revisao;
    END IF;
END $$;
SELECT (version_num <> :'f1_revisao_dev') AS f1_revisoes_divergem FROM nsi_operacional.alembic_version
\gset
\if :f1_revisoes_divergem
DO $$
BEGIN
    RAISE EXCEPTION 'nsi_dev e nsi_test estao em revisoes diferentes do Alembic - esperado a mesma revisao (0004 ou 0005) nos dois. Abortando na preflight, sem nenhuma alteracao.';
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
SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nsi_congelamento') AS role_presente,
       EXISTS (SELECT 1
                 FROM pg_auth_members m
                 JOIN pg_roles r ON r.oid = m.member
                 JOIN pg_roles g ON g.oid = m.roleid
                WHERE r.rolname = 'nsi_aplicacao' AND g.rolname = 'nsi_congelamento') AS membership_presente;
\echo 'FASE 1 concluida - estado previsto; nenhuma escrita ocorreu.'

-- =============================================================
-- FASE 2 - CONVERGENCIA. UNICO ponto do script em que a escrita e
-- liberada. Quatro acoes, e so quatro. Cada acao confirma o estado do seu
-- objeto imediatamente antes de alterar, por leitura direta do servidor.
-- =============================================================
\echo 'FASE 2 - convergencia (escrita liberada).'
SET default_transaction_read_only = off;

-- Acao 1 - role nsi_congelamento. Ausente: cria. Presente na forma exata:
-- nada a fazer. Presente em forma diferente: aborta, nunca corrige.
DO $$
DECLARE
    canlogin_atual boolean; super_atual boolean; createdb_atual boolean;
    createrole_atual boolean; replication_atual boolean; bypassrls_atual boolean;
    inherit_atual boolean; tem_senha boolean; total_linhas integer;
BEGIN
    SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls, rolinherit
      INTO canlogin_atual, super_atual, createdb_atual, createrole_atual, replication_atual, bypassrls_atual, inherit_atual
      FROM pg_roles WHERE rolname = 'nsi_congelamento';
    IF NOT FOUND THEN
        EXECUTE 'CREATE ROLE nsi_congelamento NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS';
        RAISE NOTICE 'Acao 1 (role nsi_congelamento): executado - role criada.';
        RETURN;
    END IF;

    SELECT rolpassword IS NOT NULL INTO tem_senha FROM pg_authid WHERE rolname = 'nsi_congelamento';
    SELECT count(*) INTO total_linhas
      FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.member
     WHERE r.rolname = 'nsi_congelamento';
    IF canlogin_atual IS DISTINCT FROM false OR super_atual IS DISTINCT FROM false
       OR createdb_atual IS DISTINCT FROM false OR createrole_atual IS DISTINCT FROM false
       OR replication_atual IS DISTINCT FROM false OR bypassrls_atual IS DISTINCT FROM false
       OR inherit_atual IS DISTINCT FROM true OR tem_senha OR total_linhas <> 0 THEN
        RAISE EXCEPTION 'Acao 1: role nsi_congelamento existe em forma diferente da esperada (canlogin=%, super=%, createdb=%, createrole=%, replication=%, bypassrls=%, inherit=%, tem_senha=%, pertence_a=%). Abortando sem corrigir.',
            canlogin_atual, super_atual, createdb_atual, createrole_atual, replication_atual, bypassrls_atual, inherit_atual, tem_senha, total_linhas;
    END IF;
    RAISE NOTICE 'Acao 1 (role nsi_congelamento): ja presente, nada a fazer.';
END $$;

-- Acao 2 - membership de nsi_aplicacao em nsi_congelamento (ADR-009,
-- Secao 21). Ausente: concede. Presente na forma exata: nada a fazer.
-- Presente em forma diferente, ou acompanhada de outra: aborta.
DO $$
DECLARE
    total_linhas integer; total_fora_da_excecao integer; total_membros integer;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nsi_congelamento') THEN
        RAISE EXCEPTION 'Acao 2: role nsi_congelamento nao existe. Abortando.';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nsi_aplicacao') THEN
        RAISE EXCEPTION 'Acao 2: role nsi_aplicacao nao existe. Abortando.';
    END IF;

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
    SELECT count(*) INTO total_membros
      FROM pg_auth_members m JOIN pg_roles g ON g.oid = m.roleid
     WHERE g.rolname = 'nsi_congelamento';

    IF total_linhas > 1 OR total_fora_da_excecao <> 0 OR total_membros <> total_linhas THEN
        RAISE EXCEPTION 'Acao 2: memberships em forma diferente da esperada (linhas de nsi_aplicacao=%, fora da excecao=%, membros de nsi_congelamento=%). Abortando sem corrigir.',
            total_linhas, total_fora_da_excecao, total_membros;
    END IF;

    IF total_linhas = 0 THEN
        EXECUTE 'GRANT nsi_congelamento TO nsi_aplicacao WITH INHERIT FALSE, SET TRUE, ADMIN FALSE';
        RAISE NOTICE 'Acao 2 (membership nsi_aplicacao em nsi_congelamento): executado - membership concedida.';
    ELSE
        RAISE NOTICE 'Acao 2 (membership nsi_aplicacao em nsi_congelamento): ja presente, nada a fazer.';
    END IF;
END $$;

-- Acao 3 - USAGE no schema nsi_operacional, em nsi_dev. Concessao
-- declarativa, sempre reaplicada (repetir nao muda nada).
\c nsi_dev
DO $$
DECLARE
    dono_atual name; total_inesperadas integer; ja_presente boolean;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nsi_congelamento') THEN
        RAISE EXCEPTION 'USAGE em %: role nsi_congelamento nao existe. Abortando.', current_database();
    END IF;
    SELECT r.rolname INTO dono_atual
      FROM pg_namespace n JOIN pg_roles r ON r.oid = n.nspowner
     WHERE n.nspname = 'nsi_operacional';
    IF dono_atual IS DISTINCT FROM 'nsi_eventos_owner' THEN
        RAISE EXCEPTION 'USAGE em %: schema nsi_operacional ausente ou com dono inesperado (%). Abortando sem corrigir.', current_database(), dono_atual;
    END IF;

    SELECT count(*) FILTER (WHERE NOT (a.privilege_type = 'USAGE' AND NOT a.is_grantable)),
           count(*) FILTER (WHERE a.privilege_type = 'USAGE' AND NOT a.is_grantable) > 0
      INTO total_inesperadas, ja_presente
      FROM pg_namespace n
     CROSS JOIN LATERAL aclexplode(n.nspacl) a
      JOIN pg_roles g ON g.oid = a.grantee
     WHERE n.nspname = 'nsi_operacional' AND g.rolname = 'nsi_congelamento';
    IF total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'USAGE em %: nsi_congelamento possui % concessao(oes) inesperada(s) no schema nsi_operacional. Abortando sem corrigir.', current_database(), total_inesperadas;
    END IF;

    EXECUTE 'GRANT USAGE ON SCHEMA nsi_operacional TO nsi_congelamento';
    IF ja_presente THEN
        RAISE NOTICE 'Acao 3 (USAGE no schema, %): ja presente, nada a fazer (concessao reaplicada sem efeito).', current_database();
    ELSE
        RAISE NOTICE 'Acao 3 (USAGE no schema, %): executado - USAGE concedido.', current_database();
    END IF;
END $$;

-- Acao 4 - USAGE no schema nsi_operacional, em nsi_test.
\c nsi_test
DO $$
DECLARE
    dono_atual name; total_inesperadas integer; ja_presente boolean;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nsi_congelamento') THEN
        RAISE EXCEPTION 'USAGE em %: role nsi_congelamento nao existe. Abortando.', current_database();
    END IF;
    SELECT r.rolname INTO dono_atual
      FROM pg_namespace n JOIN pg_roles r ON r.oid = n.nspowner
     WHERE n.nspname = 'nsi_operacional';
    IF dono_atual IS DISTINCT FROM 'nsi_eventos_owner' THEN
        RAISE EXCEPTION 'USAGE em %: schema nsi_operacional ausente ou com dono inesperado (%). Abortando sem corrigir.', current_database(), dono_atual;
    END IF;

    SELECT count(*) FILTER (WHERE NOT (a.privilege_type = 'USAGE' AND NOT a.is_grantable)),
           count(*) FILTER (WHERE a.privilege_type = 'USAGE' AND NOT a.is_grantable) > 0
      INTO total_inesperadas, ja_presente
      FROM pg_namespace n
     CROSS JOIN LATERAL aclexplode(n.nspacl) a
      JOIN pg_roles g ON g.oid = a.grantee
     WHERE n.nspname = 'nsi_operacional' AND g.rolname = 'nsi_congelamento';
    IF total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'USAGE em %: nsi_congelamento possui % concessao(oes) inesperada(s) no schema nsi_operacional. Abortando sem corrigir.', current_database(), total_inesperadas;
    END IF;

    EXECUTE 'GRANT USAGE ON SCHEMA nsi_operacional TO nsi_congelamento';
    IF ja_presente THEN
        RAISE NOTICE 'Acao 4 (USAGE no schema, %): ja presente, nada a fazer (concessao reaplicada sem efeito).', current_database();
    ELSE
        RAISE NOTICE 'Acao 4 (USAGE no schema, %): executado - USAGE concedido.', current_database();
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

-- 3.1 - nsi_congelamento existe, na forma exata; seu unico membro e
-- nsi_aplicacao, em uma unica linha, com as tres opcoes exatas.
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
        RAISE EXCEPTION 'Pos-validacao falhou: role nsi_congelamento nao existe.';
    END IF;
    IF canlogin_atual IS DISTINCT FROM false OR super_atual IS DISTINCT FROM false
       OR createdb_atual IS DISTINCT FROM false OR createrole_atual IS DISTINCT FROM false
       OR replication_atual IS DISTINCT FROM false OR bypassrls_atual IS DISTINCT FROM false
       OR inherit_atual IS DISTINCT FROM true THEN
        RAISE EXCEPTION 'Pos-validacao falhou: role nsi_congelamento com atributos incorretos (canlogin=%, super=%, createdb=%, createrole=%, replication=%, bypassrls=%, inherit=%).',
            canlogin_atual, super_atual, createdb_atual, createrole_atual, replication_atual, bypassrls_atual, inherit_atual;
    END IF;

    SELECT count(*) INTO total_linhas
      FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.member
     WHERE r.rolname = 'nsi_congelamento';
    IF total_linhas <> 0 THEN
        RAISE EXCEPTION 'Pos-validacao falhou: role nsi_congelamento pertence a % outra(s) role(s) - esperado zero.', total_linhas;
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
        RAISE EXCEPTION 'Pos-validacao falhou: membros de nsi_congelamento incorretos (linhas=%, fora da excecao=%; esperado exatamente nsi_aplicacao com inherit=false, set=true, admin=false).', total_linhas, total_fora_da_excecao;
    END IF;
END $$;
\echo '  3.1 role nsi_congelamento e seu unico membro: ok.'

-- 3.2 - nsi_congelamento nao tem senha.
DO $$
DECLARE tem_senha boolean;
BEGIN
    SELECT rolpassword IS NOT NULL INTO tem_senha FROM pg_authid WHERE rolname = 'nsi_congelamento';
    IF NOT FOUND OR tem_senha THEN
        RAISE EXCEPTION 'Pos-validacao falhou: role nsi_congelamento ausente em pg_authid ou com senha definida.';
    END IF;
END $$;
\echo '  3.2 role sem senha: ok.'

-- 3.3 - as quatro roles da B3.1 continuam com os atributos aprovados; tres
-- delas sem nenhuma membership; nsi_aplicacao com exatamente a membership
-- formalizada; memberships dos migrators intactas.
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

    FOREACH nome_role IN ARRAY ARRAY['nsi_eventos_owner', 'nsi_expiracao', 'nsi_operador_restrito'] LOOP
        SELECT count(*) INTO total_linhas
          FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.member
         WHERE r.rolname = nome_role;
        IF total_linhas <> 0 THEN
            RAISE EXCEPTION 'Pos-validacao falhou: role % pertence a % outra(s) role(s) - esperado zero (regra da B3.1).', nome_role, total_linhas;
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
\echo '  3.3 roles e memberships da B3.1, com a excecao unica da ADR-009: ok.'

-- 3.4 - dependencias compartilhadas de nsi_congelamento, em todo o
-- cluster: nada alem de listas de permissao de schema/funcao em
-- nsi_dev/nsi_test.
DO $$
DECLARE total_inesperadas integer;
BEGIN
    SELECT count(*) INTO total_inesperadas
      FROM pg_shdepend s
      JOIN pg_roles r ON r.oid = s.refobjid
     WHERE s.refclassid = 'pg_authid'::regclass
       AND r.rolname = 'nsi_congelamento'
       AND NOT (s.deptype = 'a'
                AND s.classid IN ('pg_namespace'::regclass, 'pg_proc'::regclass)
                AND s.dbid IN (SELECT oid FROM pg_database WHERE datname IN ('nsi_dev', 'nsi_test')));
    IF total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Pos-validacao falhou: role nsi_congelamento possui % dependencia(s) inesperada(s) no cluster.', total_inesperadas;
    END IF;
END $$;
\echo '  3.4 nenhuma dependencia inesperada no cluster: ok.'

-- 3.5 - PUBLIC continua sem CONNECT em nsi_dev e nsi_test (B3.1).
DO $$
DECLARE nome_banco text; lista_nula boolean; total_public integer;
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
END $$;
\echo '  3.5 PUBLIC sem CONNECT nos dois bancos: ok.'

-- 3.6 - nsi_dev: schema, revisao, concessoes nominais e privilegio efetivo.
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
    IF revisao NOT IN ('0004', '0005') THEN
        RAISE EXCEPTION 'Pos-validacao falhou: % esta em revisao % - aceito: 0004 ou 0005.', current_database(), revisao;
    END IF;

    -- Concessoes nominais.
    SELECT (SELECT count(*) FROM pg_class c JOIN pg_roles r ON r.oid = c.relowner WHERE r.rolname = 'nsi_congelamento')
         + (SELECT count(*) FROM pg_proc p JOIN pg_roles r ON r.oid = p.proowner WHERE r.rolname = 'nsi_congelamento')
         + (SELECT count(*) FROM pg_namespace n JOIN pg_roles r ON r.oid = n.nspowner WHERE r.rolname = 'nsi_congelamento')
      INTO total_inesperadas;
    IF total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Pos-validacao falhou: role nsi_congelamento e dona de % objeto(s) em %.', total_inesperadas, current_database();
    END IF;

    SELECT count(*) FILTER (WHERE NOT (n.nspname = 'nsi_operacional' AND a.privilege_type = 'USAGE' AND NOT a.is_grantable)),
           count(*) FILTER (WHERE n.nspname = 'nsi_operacional' AND a.privilege_type = 'USAGE' AND NOT a.is_grantable)
      INTO total_inesperadas, total_usage
      FROM pg_namespace n
     CROSS JOIN LATERAL aclexplode(n.nspacl) a
      JOIN pg_roles g ON g.oid = a.grantee
     WHERE g.rolname = 'nsi_congelamento';
    IF total_inesperadas <> 0 OR total_usage <> 1 THEN
        RAISE EXCEPTION 'Pos-validacao falhou: concessoes de schema a nsi_congelamento em % incorretas (USAGE em nsi_operacional=%, inesperadas=%; esperado exatamente 1 e 0).', current_database(), total_usage, total_inesperadas;
    END IF;

    SELECT (SELECT count(*) FROM pg_class c CROSS JOIN LATERAL aclexplode(c.relacl) a JOIN pg_roles g ON g.oid = a.grantee WHERE g.rolname = 'nsi_congelamento')
         + (SELECT count(*) FROM pg_attribute t CROSS JOIN LATERAL aclexplode(t.attacl) a JOIN pg_roles g ON g.oid = a.grantee WHERE g.rolname = 'nsi_congelamento')
         + (SELECT count(*) FROM pg_default_acl d CROSS JOIN LATERAL aclexplode(d.defaclacl) a JOIN pg_roles g ON g.oid = a.grantee WHERE g.rolname = 'nsi_congelamento')
      INTO total_inesperadas;
    IF total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Pos-validacao falhou: role nsi_congelamento possui % concessao(oes) em tabela, coluna ou privilegio padrao de %.', total_inesperadas, current_database();
    END IF;

    SELECT count(*) INTO total_inesperadas
      FROM pg_proc p
      JOIN pg_namespace n ON n.oid = p.pronamespace
     CROSS JOIN LATERAL aclexplode(p.proacl) a
      JOIN pg_roles g ON g.oid = a.grantee
     WHERE g.rolname = 'nsi_congelamento'
       AND NOT (revisao = '0005' AND n.nspname = 'nsi_operacional'
                AND p.proname = 'fn_registrar_congelamento'
                AND a.privilege_type = 'EXECUTE' AND NOT a.is_grantable);
    IF total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Pos-validacao falhou: role nsi_congelamento possui % concessao(oes) inesperada(s) em funcao de % (revisao %).', total_inesperadas, current_database(), revisao;
    END IF;

    -- Privilegio efetivo sobre o schema nsi_operacional e seus objetos.
    IF NOT has_schema_privilege('nsi_congelamento', 'nsi_operacional', 'USAGE') THEN
        RAISE EXCEPTION 'Pos-validacao falhou: nsi_congelamento sem USAGE efetivo no schema nsi_operacional em %.', current_database();
    END IF;
    IF has_schema_privilege('nsi_congelamento', 'nsi_operacional', 'CREATE') THEN
        RAISE EXCEPTION 'Pos-validacao falhou: nsi_congelamento com CREATE no schema nsi_operacional em %.', current_database();
    END IF;

    SELECT count(*) INTO total_inesperadas
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'nsi_operacional' AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
       AND (has_table_privilege('nsi_congelamento', c.oid, 'SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER')
            OR has_any_column_privilege('nsi_congelamento', c.oid, 'SELECT, INSERT, UPDATE, REFERENCES'));
    IF total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Pos-validacao falhou: nsi_congelamento possui privilegio efetivo em % tabela(s) do schema nsi_operacional em % - esperado zero.', total_inesperadas, current_database();
    END IF;

    SELECT count(*) INTO total_inesperadas
      FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
     WHERE n.nspname = 'nsi_operacional'
       AND has_function_privilege('nsi_congelamento', p.oid, 'EXECUTE')
       AND NOT (revisao = '0005' AND p.proname = 'fn_registrar_congelamento');
    IF total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Pos-validacao falhou: nsi_congelamento possui EXECUTE efetivo em % funcao(oes) inesperada(s) do schema nsi_operacional em % (revisao %).', total_inesperadas, current_database(), revisao;
    END IF;

    IF revisao = '0005' THEN
        SELECT count(*) INTO total_linhas
          FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
         WHERE n.nspname = 'nsi_operacional' AND p.proname = 'fn_registrar_congelamento'
           AND has_function_privilege('nsi_congelamento', p.oid, 'EXECUTE');
        IF total_linhas <> 1 THEN
            RAISE EXCEPTION 'Pos-validacao falhou: em revisao 0005, nsi_congelamento deveria ter EXECUTE em exatamente uma funcao nsi_operacional.fn_registrar_congelamento em % (encontrado: %).', current_database(), total_linhas;
        END IF;
    END IF;
END $$;
SELECT version_num AS f3_revisao_dev FROM nsi_operacional.alembic_version
\gset
\echo '  3.6 nsi_dev - schema, revisao, concessoes e privilegio efetivo: ok.'

-- 3.7 - nsi_test: as mesmas verificacoes, e a mesma revisao de nsi_dev.
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
    IF revisao NOT IN ('0004', '0005') THEN
        RAISE EXCEPTION 'Pos-validacao falhou: % esta em revisao % - aceito: 0004 ou 0005.', current_database(), revisao;
    END IF;

    -- Concessoes nominais.
    SELECT (SELECT count(*) FROM pg_class c JOIN pg_roles r ON r.oid = c.relowner WHERE r.rolname = 'nsi_congelamento')
         + (SELECT count(*) FROM pg_proc p JOIN pg_roles r ON r.oid = p.proowner WHERE r.rolname = 'nsi_congelamento')
         + (SELECT count(*) FROM pg_namespace n JOIN pg_roles r ON r.oid = n.nspowner WHERE r.rolname = 'nsi_congelamento')
      INTO total_inesperadas;
    IF total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Pos-validacao falhou: role nsi_congelamento e dona de % objeto(s) em %.', total_inesperadas, current_database();
    END IF;

    SELECT count(*) FILTER (WHERE NOT (n.nspname = 'nsi_operacional' AND a.privilege_type = 'USAGE' AND NOT a.is_grantable)),
           count(*) FILTER (WHERE n.nspname = 'nsi_operacional' AND a.privilege_type = 'USAGE' AND NOT a.is_grantable)
      INTO total_inesperadas, total_usage
      FROM pg_namespace n
     CROSS JOIN LATERAL aclexplode(n.nspacl) a
      JOIN pg_roles g ON g.oid = a.grantee
     WHERE g.rolname = 'nsi_congelamento';
    IF total_inesperadas <> 0 OR total_usage <> 1 THEN
        RAISE EXCEPTION 'Pos-validacao falhou: concessoes de schema a nsi_congelamento em % incorretas (USAGE em nsi_operacional=%, inesperadas=%; esperado exatamente 1 e 0).', current_database(), total_usage, total_inesperadas;
    END IF;

    SELECT (SELECT count(*) FROM pg_class c CROSS JOIN LATERAL aclexplode(c.relacl) a JOIN pg_roles g ON g.oid = a.grantee WHERE g.rolname = 'nsi_congelamento')
         + (SELECT count(*) FROM pg_attribute t CROSS JOIN LATERAL aclexplode(t.attacl) a JOIN pg_roles g ON g.oid = a.grantee WHERE g.rolname = 'nsi_congelamento')
         + (SELECT count(*) FROM pg_default_acl d CROSS JOIN LATERAL aclexplode(d.defaclacl) a JOIN pg_roles g ON g.oid = a.grantee WHERE g.rolname = 'nsi_congelamento')
      INTO total_inesperadas;
    IF total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Pos-validacao falhou: role nsi_congelamento possui % concessao(oes) em tabela, coluna ou privilegio padrao de %.', total_inesperadas, current_database();
    END IF;

    SELECT count(*) INTO total_inesperadas
      FROM pg_proc p
      JOIN pg_namespace n ON n.oid = p.pronamespace
     CROSS JOIN LATERAL aclexplode(p.proacl) a
      JOIN pg_roles g ON g.oid = a.grantee
     WHERE g.rolname = 'nsi_congelamento'
       AND NOT (revisao = '0005' AND n.nspname = 'nsi_operacional'
                AND p.proname = 'fn_registrar_congelamento'
                AND a.privilege_type = 'EXECUTE' AND NOT a.is_grantable);
    IF total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Pos-validacao falhou: role nsi_congelamento possui % concessao(oes) inesperada(s) em funcao de % (revisao %).', total_inesperadas, current_database(), revisao;
    END IF;

    -- Privilegio efetivo sobre o schema nsi_operacional e seus objetos.
    IF NOT has_schema_privilege('nsi_congelamento', 'nsi_operacional', 'USAGE') THEN
        RAISE EXCEPTION 'Pos-validacao falhou: nsi_congelamento sem USAGE efetivo no schema nsi_operacional em %.', current_database();
    END IF;
    IF has_schema_privilege('nsi_congelamento', 'nsi_operacional', 'CREATE') THEN
        RAISE EXCEPTION 'Pos-validacao falhou: nsi_congelamento com CREATE no schema nsi_operacional em %.', current_database();
    END IF;

    SELECT count(*) INTO total_inesperadas
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'nsi_operacional' AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
       AND (has_table_privilege('nsi_congelamento', c.oid, 'SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER')
            OR has_any_column_privilege('nsi_congelamento', c.oid, 'SELECT, INSERT, UPDATE, REFERENCES'));
    IF total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Pos-validacao falhou: nsi_congelamento possui privilegio efetivo em % tabela(s) do schema nsi_operacional em % - esperado zero.', total_inesperadas, current_database();
    END IF;

    SELECT count(*) INTO total_inesperadas
      FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
     WHERE n.nspname = 'nsi_operacional'
       AND has_function_privilege('nsi_congelamento', p.oid, 'EXECUTE')
       AND NOT (revisao = '0005' AND p.proname = 'fn_registrar_congelamento');
    IF total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Pos-validacao falhou: nsi_congelamento possui EXECUTE efetivo em % funcao(oes) inesperada(s) do schema nsi_operacional em % (revisao %).', total_inesperadas, current_database(), revisao;
    END IF;

    IF revisao = '0005' THEN
        SELECT count(*) INTO total_linhas
          FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
         WHERE n.nspname = 'nsi_operacional' AND p.proname = 'fn_registrar_congelamento'
           AND has_function_privilege('nsi_congelamento', p.oid, 'EXECUTE');
        IF total_linhas <> 1 THEN
            RAISE EXCEPTION 'Pos-validacao falhou: em revisao 0005, nsi_congelamento deveria ter EXECUTE em exatamente uma funcao nsi_operacional.fn_registrar_congelamento em % (encontrado: %).', current_database(), total_linhas;
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
\echo '  3.7 nsi_test - schema, revisao, concessoes e privilegio efetivo: ok.'

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
\echo 'provisionar_b4_role_congelamento.sql concluido - Fase 3 (pos-validacao completa) passou integralmente.'

-- =============================================================
-- LEMBRETES (fora deste script).
--
-- 1. nsi_congelamento NAO tem senha nem login - nao existe "proximo passo"
--    de senha. A role so e alcancada por SET ROLE explicito, a partir de
--    uma conexao nsi_aplicacao.
--
-- 2. Depois deste script, scripts/postgres_local/provisionar_b3_roles.sql
--    NAO pode ser reexecutado sem antes desprovisionar a B4
--    (desprovisionar_b4_role_congelamento.sql): a preflight da B3.1 exige
--    zero memberships para nsi_aplicacao e aborta, sem escrever nada. O
--    script da B3.1 nao foi alterado, por decisao (ADR-009, Secao 21).
--
-- 3. O EXECUTE de nsi_operacional.fn_registrar_congelamento e concedido
--    pela migration 0005 - nunca por este script. Reexecutar este script
--    depois da migration comprova, pela Fase 3, a matriz final de
--    privilegios da role.
-- =============================================================
