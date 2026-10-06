-- =============================================================
-- scripts/postgres_local/desprovisionar_b5_role_importacao.sql
-- Sprint B (B5.3) - ADR-010 (Secao 16) / Especificacao Tecnica da
-- Sprint B (Secao 18, B5.2, item 18, "Criterios de rollback").
--
-- *** SCRIPT DESTRUTIVO - APENAS DESENVOLVIMENTO/TESTE LOCAL ***
-- *** NUNCA EXECUTAR CONTRA PRODUCAO - NUNCA EXECUTADO AUTOMATICAMENTE ***
-- *** NENHUM TESTE AUTOMATIZADO CHAMA ESTE ARQUIVO - execucao manual,
--     autorizada e deliberada, sempre. ***
--
-- Execute conectado ao banco de manutencao "postgres":
--
--     psql -U postgres -d postgres -f scripts/postgres_local/desprovisionar_b5_role_importacao.sql
--
-- Pre-requisitos: provisionar_b3_roles.sql (B3.1) executado e integro;
-- migration 0006 AUSENTE nos dois bancos (nsi_dev e nsi_test na revisao
-- 0005). Requer privilegio de superusuario - nesta maquina, o usuario
-- "postgres" da instalacao local.
--
-- DELIMITACAO: este script remove EXCLUSIVAMENTE os efeitos
-- administrativos de provisionar_b5_role_importacao.sql. A migration 0006
-- e revertida EXCLUSIVAMENTE pelo downgrade do Alembic; este script nunca
-- cria, altera, revoga ou remove objetos criados pela migration (tabelas,
-- as quatro funcoes de importacao e suas concessoes) - por isso exige a
-- 0006 ja revertida antes de executar.
--
-- O QUE ESTE SCRIPT FAZ (e nada alem disso), na ordem inversa estrita do
-- provisionamento:
--   1. revoga USAGE no schema "nsi_operacional" de nsi_importacao, em
--      nsi_test;
--   2. revoga CONNECT em nsi_test de nsi_importacao;
--   3. remove a role nsi_importacao.
--
-- O QUE ESTE SCRIPT NUNCA FAZ: nao toca as quatro roles da B3.1, nem
-- nsi_congelamento (atributos, memberships, CONNECT, USAGE), os migrators,
-- PUBLIC, a propriedade do schema, alembic_version, tabelas, dados,
-- eventos, recibos ou funcoes; nao toca nsi_dev (onde nsi_importacao nunca
-- recebe concessao administrativa); nao usa remocao em massa de objetos da
-- role, reatribuicao de propriedade, remocao em cadeia nem remocao
-- condicional cega da role; nao executa reversao de migration; nao define
-- senha; nunca corrige um estado divergente.
--
-- NAO CONTEM SENHA. A senha de nsi_importacao, se definida pelo operador,
-- desaparece junto com a role; este script nunca a le nem a altera.
--
-- ---------------------------------------------------------------
-- DESENHO DE TRES FASES, COM GATE DE CONFIRMACAO
-- ---------------------------------------------------------------
-- FASE 1 (preflight): barreira global. Prova, antes de qualquer escrita em
--   qualquer banco, que o estado inteiro e um dos estados aceitos.
--   Qualquer estado inesperado ABORTA aqui.
--
-- GATE (confirmacao): confirmacao textual exata, pedida sempre - mesmo
--   quando nao ha nada a fazer. Frase incorreta ou ausente encerra o
--   script antes da Fase 2, sem nenhuma alteracao.
--
-- FASE 2 (desprovisionamento): unica fase que realiza operacoes de
--   escrita. Tres acoes, e so tres. Cada acao confirma o estado do seu
--   objeto imediatamente antes de alterar, por leitura direta do servidor
--   feita pela propria acao: presente na forma exata -> executa; ausente
--   -> nada a fazer; presente em forma diferente -> ABORTA, nunca corrige.
--   Logo depois da escrita, a propria acao confirma o efeito (em
--   PostgreSQL 16+, uma revogacao sem efeito gera apenas WARNING); se o
--   efeito nao ocorreu, aborta e a acao inteira e desfeita.
--
-- FASE 3 (pos-validacao): reconfirma, a partir do zero, TODO o estado
--   final esperado.
--
-- GARANTIA ARQUITETURAL - READ ONLY FORA DA FASE 2: as protecoes iniciais,
--   a Fase 1, o gate, a Fase 3 e o encerramento executam integralmente com
--   a sessao em modo somente leitura. Contrato do script: qualquer comando
--   de escrita nesses blocos deve interromper imediatamente a execucao,
--   antes de produzir efeito e sem que nenhum comando posterior seja
--   executado. O modo e ligado no inicio de cada bloco e NOVAMENTE depois
--   de cada \c (\c abre uma sessao nova, que nasce em modo normal); logo
--   apos ligar, o script le o modo efetivo da sessao e aborta se ele nao
--   estiver ativo. A Fase 2 e a unica fase que realiza operacoes de
--   escrita.
--
-- PRINCIPIO ARQUITETURAL - CADA FASE E AUTOSSUFICIENTE: nenhuma fase
--   transmite estado, variaveis ou resultados para outra fase. A unica
--   informacao transmitida entre fases e o fato de a fase anterior ter
--   sido concluida com sucesso (o script para no primeiro erro). Toda
--   validacao e feita de novo, por leitura direta do estado atual do
--   servidor, dentro da fase que precisa dela. Variaveis de cliente do
--   psql sao prefixadas pelo bloco que as cria e usadas so nele: f1_ na
--   Fase 1, conf_ no gate, f3_ na Fase 3. A Fase 2 nao usa nenhuma.
--
-- REVISAO ACEITA: nsi_dev e nsi_test na revisao 0005 do Alembic. Alem
--   disso, um gate proprio exige que nenhuma das quatro funcoes de
--   importacao exista em "nsi_operacional", de qualquer assinatura -
--   barreira independente da revisao.
--
-- ALCANCE DE "NENHUM RESIDUO": verificam-se as concessoes nominais a role
--   (em qualquer objeto, de qualquer banco, via pg_shdepend - propriedade,
--   ACL, privilegio padrao, politica RLS, tablespace) e, banco a banco, o
--   detalhe no schema "nsi_operacional". O que toda role recebe de PUBLIC
--   por padrao do PostgreSQL nao e tocado nem verificado.
--
-- ESTADOS ACEITOS NA FASE 1: role ausente (ja desprovisionado, ou nunca
--   provisionado); ou role presente na forma exata, com o CONNECT em
--   nsi_test presente ou ausente e o USAGE em nsi_test presente ou
--   ausente, independentemente - todo ponto de parada possivel do
--   provisionamento ou deste script.
--
-- LIMITE ESTRUTURAL DE \c: o PostgreSQL nao tem transacao entre bancos
--   diferentes. Cada acao da Fase 2 e atomica; o risco remanescente e uma
--   falha NOVA em tempo de execucao entre duas acoes. A resposta e
--   reexecutar este mesmo script (idempotente por desenho), que completa o
--   que faltou - nunca usar o provisionamento como "conserto".
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
-- provisionar_b5_role_importacao.sql.
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

-- Privilegio de superusuario (revogacao de CONNECT, remocao de role e
-- leitura de pg_authid exigem).
DO $$
BEGIN
    IF current_setting('is_superuser') <> 'on' THEN
        RAISE EXCEPTION 'Sessao sem privilegio de superusuario (session_user=%). Abortando sem nenhuma alteracao.', session_user;
    END IF;
END $$;

-- Os dois bancos precisam existir; este script nunca os cria nem remove.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'nsi_dev') THEN
        RAISE EXCEPTION 'Banco nsi_dev nao existe. Abortando sem nenhuma alteracao.';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'nsi_test') THEN
        RAISE EXCEPTION 'Banco nsi_test nao existe. Abortando sem nenhuma alteracao.';
    END IF;
END $$;

-- =============================================================
-- FASE 1 - PREFLIGHT. READ ONLY obrigatorio: nenhuma operacao de escrita
-- ocorre neste bloco.
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
            RAISE EXCEPTION 'Role % nao existe - a B3.1 nao esta integra. Abortando na preflight, sem nenhuma alteracao.', nome_role;
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
-- SET TRUE, ADMIN FALSE). Este script nao depende do estado da B4.3 e
-- nunca o altera.
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

-- 1.4 - nsi_importacao: ausente (aceito), ou presente exatamente na forma
-- esperada - LOGIN, atributos de seguranca explicitos, sem pertencer a
-- nenhuma role e sem nenhum membro.
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
        RAISE EXCEPTION 'Role nsi_importacao existe com atributos incompativeis (canlogin=%, super=%, createdb=%, createrole=%, replication=%, bypassrls=%, inherit=%). Abortando na preflight, sem nenhuma alteracao.',
            canlogin_atual, super_atual, createdb_atual, createrole_atual, replication_atual, bypassrls_atual, inherit_atual;
    END IF;

    SELECT count(*) INTO total_pertence
      FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.member
     WHERE r.rolname = 'nsi_importacao';
    SELECT count(*) INTO total_membros
      FROM pg_auth_members m JOIN pg_roles g ON g.oid = m.roleid
     WHERE g.rolname = 'nsi_importacao';
    IF total_pertence <> 0 OR total_membros <> 0 THEN
        RAISE EXCEPTION 'Role nsi_importacao com membership inesperada (pertence_a=%, membros=%; esperado zero e zero). Abortando na preflight, sem nenhuma alteracao.',
            total_pertence, total_membros;
    END IF;
END $$;

-- 1.5 - dependencias compartilhadas de nsi_importacao, em TODO o cluster:
-- a role nao e dona de nada e so pode ser citada na lista de permissao do
-- banco nsi_test (CONNECT) ou em lista de permissao de schema de nsi_test.
-- Mais estrito que o provisionamento: nenhuma concessao em funcao e
-- aceita, porque a 0006 precisa estar ausente.
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
                 AND s.dbid = (SELECT oid FROM pg_database WHERE datname = 'nsi_test'))));
    IF total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Role nsi_importacao possui % dependencia(s) inesperada(s) no cluster (aceito somente CONNECT em nsi_test e ACL em schema de nsi_test). Abortando na preflight, sem nenhuma alteracao.', total_inesperadas;
    END IF;
END $$;

-- 1.6 - concessoes de banco a nsi_importacao: nenhuma, ou somente CONNECT
-- (sem opcao de repasse) em nsi_test.
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

-- 1.7 - nsi_dev: schema, revisao 0005, funcoes de importacao ausentes e
-- nenhuma concessao a nsi_importacao.
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
    IF revisao NOT IN ('0005') THEN
        RAISE EXCEPTION 'nsi_operacional.alembic_version em % esta em revisao % - aceito: somente 0005 (a 0006 deve ser revertida antes, exclusivamente pela ferramenta de migration). Abortando na preflight, sem nenhuma alteracao.', current_database(), revisao;
    END IF;

    SELECT count(*) INTO total_inesperadas
      FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
     WHERE n.nspname = 'nsi_operacional'
       AND p.proname IN ('fn_iniciar_importacao_legado', 'fn_importar_lote_legado',
                         'fn_concluir_importacao_legado', 'fn_verificar_paridade_legado');
    IF total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Encontrada(s) % funcao(oes) de importacao em nsi_operacional de % - devem estar ausentes. Abortando na preflight, sem nenhuma alteracao.', total_inesperadas, current_database();
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
        RAISE EXCEPTION 'Role nsi_importacao possui % concessao(oes) em schema de % - esperado zero. Abortando na preflight, sem nenhuma alteracao.', total_inesperadas, current_database();
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
     CROSS JOIN LATERAL aclexplode(p.proacl) a
      JOIN pg_roles g ON g.oid = a.grantee
     WHERE g.rolname = 'nsi_importacao';
    IF total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Role nsi_importacao possui % concessao(oes) em funcao de % - esperado zero com a 0006 ausente. Abortando na preflight, sem nenhuma alteracao.', total_inesperadas, current_database();
    END IF;
END $$;
SELECT version_num AS f1_revisao_dev FROM nsi_operacional.alembic_version
\gset

-- 1.8 - nsi_test: as mesmas verificacoes (aqui o USAGE em nsi_operacional
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
    IF revisao NOT IN ('0005') THEN
        RAISE EXCEPTION 'nsi_operacional.alembic_version em % esta em revisao % - aceito: somente 0005 (a 0006 deve ser revertida antes, exclusivamente pela ferramenta de migration). Abortando na preflight, sem nenhuma alteracao.', current_database(), revisao;
    END IF;

    SELECT count(*) INTO total_inesperadas
      FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
     WHERE n.nspname = 'nsi_operacional'
       AND p.proname IN ('fn_iniciar_importacao_legado', 'fn_importar_lote_legado',
                         'fn_concluir_importacao_legado', 'fn_verificar_paridade_legado');
    IF total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Encontrada(s) % funcao(oes) de importacao em nsi_operacional de % - devem estar ausentes. Abortando na preflight, sem nenhuma alteracao.', total_inesperadas, current_database();
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
     CROSS JOIN LATERAL aclexplode(p.proacl) a
      JOIN pg_roles g ON g.oid = a.grantee
     WHERE g.rolname = 'nsi_importacao';
    IF total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Role nsi_importacao possui % concessao(oes) em funcao de % - esperado zero com a 0006 ausente. Abortando na preflight, sem nenhuma alteracao.', total_inesperadas, current_database();
    END IF;
END $$;
SELECT (version_num <> :'f1_revisao_dev') AS f1_revisoes_divergem FROM nsi_operacional.alembic_version
\gset
\if :f1_revisoes_divergem
DO $$
BEGIN
    RAISE EXCEPTION 'nsi_dev e nsi_test estao em revisoes diferentes - esperado 0005 nos dois. Abortando na preflight, sem nenhuma alteracao.';
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
\echo 'FASE 1 concluida - estado aceito; nenhuma escrita ocorreu.'

-- =============================================================
-- GATE DE CONFIRMACAO. Somente leitura. Confirmacao textual exata, pedida
-- sempre - mesmo quando nao ha nada a fazer. Frase incorreta ou ausente
-- encerra o script aqui, antes da Fase 2, sem nenhuma alteracao.
-- =============================================================
SET default_transaction_read_only = on;
DO $$
BEGIN
    IF current_setting('transaction_read_only') <> 'on' THEN
        RAISE EXCEPTION 'Modo somente leitura NAO esta ativo no gate de confirmacao (postgres). Abortando sem nenhuma alteracao.';
    END IF;
END $$;

\prompt 'Digite exatamente CONFIRMO-DESPROVISIONAR-NSI-B5-ROLE-IMPORTACAO para prosseguir com a destruicao: ' conf_frase

SELECT CASE WHEN :'conf_frase' = 'CONFIRMO-DESPROVISIONAR-NSI-B5-ROLE-IMPORTACAO'
            THEN 'true' ELSE 'false' END AS conf_pode_prosseguir
\gset

\if :conf_pode_prosseguir
    \echo 'Confirmacao recebida - prosseguindo para a Fase 2.'
\else
    \echo 'Confirmacao incorreta ou ausente - encerrando sem nenhuma alteracao.'
    \quit
\endif

-- =============================================================
-- FASE 2 - DESPROVISIONAMENTO. Unica fase que realiza operacoes de
-- escrita. Tres acoes, e so tres, na ordem inversa estrita do
-- provisionamento. Cada acao confirma o estado do seu objeto
-- imediatamente antes de alterar, por leitura direta do servidor, e
-- confirma o efeito logo depois.
-- =============================================================
\echo 'FASE 2 - desprovisionamento (operacoes de escrita).'
SET default_transaction_read_only = off;

-- Acao 1 - USAGE no schema nsi_operacional, em nsi_test. Presente na
-- forma exata: revoga. Ausente: nada a fazer. Forma diferente: aborta.
\c nsi_test
DO $$
DECLARE
    dono_atual name; total_funcoes integer; total_inesperadas integer;
    total_usage integer; total_restante integer;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nsi_importacao') THEN
        RAISE NOTICE 'Acao 1 (USAGE no schema, %): role nsi_importacao ausente, nada a fazer.', current_database();
        RETURN;
    END IF;
    SELECT r.rolname INTO dono_atual
      FROM pg_namespace n JOIN pg_roles r ON r.oid = n.nspowner
     WHERE n.nspname = 'nsi_operacional';
    IF dono_atual IS DISTINCT FROM 'nsi_eventos_owner' THEN
        RAISE EXCEPTION 'Acao 1 (%): schema nsi_operacional ausente ou com dono inesperado (%). Abortando sem corrigir.', current_database(), dono_atual;
    END IF;
    SELECT count(*) INTO total_funcoes
      FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
     WHERE n.nspname = 'nsi_operacional'
       AND p.proname IN ('fn_iniciar_importacao_legado', 'fn_importar_lote_legado',
                         'fn_concluir_importacao_legado', 'fn_verificar_paridade_legado');
    IF total_funcoes <> 0 THEN
        RAISE EXCEPTION 'Acao 1 (%): funcao(oes) de importacao presente(s) em nsi_operacional - devem estar ausentes. Abortando sem corrigir.', current_database();
    END IF;

    SELECT count(*) FILTER (WHERE NOT (n.nspname = 'nsi_operacional' AND a.privilege_type = 'USAGE' AND NOT a.is_grantable)),
           count(*) FILTER (WHERE n.nspname = 'nsi_operacional' AND a.privilege_type = 'USAGE' AND NOT a.is_grantable)
      INTO total_inesperadas, total_usage
      FROM pg_namespace n
     CROSS JOIN LATERAL aclexplode(n.nspacl) a
      JOIN pg_roles g ON g.oid = a.grantee
     WHERE g.rolname = 'nsi_importacao';
    IF total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Acao 1 (%): nsi_importacao possui % concessao(oes) inesperada(s) em schema. Abortando sem corrigir.', current_database(), total_inesperadas;
    END IF;
    IF total_usage = 0 THEN
        RAISE NOTICE 'Acao 1 (USAGE no schema, %): ja ausente, nada a fazer.', current_database();
        RETURN;
    END IF;

    EXECUTE 'REVOKE USAGE ON SCHEMA nsi_operacional FROM nsi_importacao';

    SELECT count(*) INTO total_restante
      FROM pg_namespace n
     CROSS JOIN LATERAL aclexplode(n.nspacl) a
      JOIN pg_roles g ON g.oid = a.grantee
     WHERE g.rolname = 'nsi_importacao';
    IF total_restante <> 0 THEN
        RAISE EXCEPTION 'Acao 1 (%): revogacao sem efeito - nsi_importacao ainda possui % concessao(oes) em schema. Abortando; acao desfeita.', current_database(), total_restante;
    END IF;
    RAISE NOTICE 'Acao 1 (USAGE no schema, %): executado - USAGE revogado.', current_database();
END $$;

-- Acao 2 - CONNECT em nsi_test. Presente na forma exata: revoga. Ausente:
-- nada a fazer. Qualquer outra concessao de banco: aborta.
\c postgres
DO $$
DECLARE
    total_inesperadas integer; total_connect integer; total_restante integer;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nsi_importacao') THEN
        RAISE NOTICE 'Acao 2 (CONNECT em nsi_test): role nsi_importacao ausente, nada a fazer.';
        RETURN;
    END IF;

    SELECT count(*) FILTER (WHERE NOT (d.datname = 'nsi_test' AND a.privilege_type = 'CONNECT' AND NOT a.is_grantable)),
           count(*) FILTER (WHERE d.datname = 'nsi_test' AND a.privilege_type = 'CONNECT' AND NOT a.is_grantable)
      INTO total_inesperadas, total_connect
      FROM pg_database d
     CROSS JOIN LATERAL aclexplode(d.datacl) a
      JOIN pg_roles g ON g.oid = a.grantee
     WHERE g.rolname = 'nsi_importacao';
    IF total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Acao 2: nsi_importacao possui % concessao(oes) de banco inesperada(s). Abortando sem corrigir.', total_inesperadas;
    END IF;
    IF total_connect = 0 THEN
        RAISE NOTICE 'Acao 2 (CONNECT em nsi_test): ja ausente, nada a fazer.';
        RETURN;
    END IF;

    EXECUTE 'REVOKE CONNECT ON DATABASE nsi_test FROM nsi_importacao';

    SELECT count(*) INTO total_restante
      FROM pg_database d
     CROSS JOIN LATERAL aclexplode(d.datacl) a
      JOIN pg_roles g ON g.oid = a.grantee
     WHERE g.rolname = 'nsi_importacao';
    IF total_restante <> 0 THEN
        RAISE EXCEPTION 'Acao 2: revogacao sem efeito - nsi_importacao ainda possui % concessao(oes) de banco. Abortando; acao desfeita.', total_restante;
    END IF;
    RAISE NOTICE 'Acao 2 (CONNECT em nsi_test): executado - CONNECT revogado.';
END $$;

-- Acao 3 - role nsi_importacao. Presente na forma exata, sem membership,
-- sem nenhuma dependencia no cluster e sem nenhuma sessao aberta: remove.
-- Ausente: nada a fazer. Qualquer outra situacao: aborta, NUNCA remove.
DO $$
DECLARE
    canlogin_atual boolean; super_atual boolean; createdb_atual boolean;
    createrole_atual boolean; replication_atual boolean; bypassrls_atual boolean;
    inherit_atual boolean;
    total_pertence integer; total_membros integer; total_dependencias integer; total_sessoes integer;
BEGIN
    SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls, rolinherit
      INTO canlogin_atual, super_atual, createdb_atual, createrole_atual, replication_atual, bypassrls_atual, inherit_atual
      FROM pg_roles WHERE rolname = 'nsi_importacao';
    IF NOT FOUND THEN
        RAISE NOTICE 'Acao 3 (role nsi_importacao): ja ausente, nada a fazer.';
        RETURN;
    END IF;

    SELECT count(*) INTO total_pertence
      FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.member
     WHERE r.rolname = 'nsi_importacao';
    SELECT count(*) INTO total_membros
      FROM pg_auth_members m JOIN pg_roles g ON g.oid = m.roleid
     WHERE g.rolname = 'nsi_importacao';
    SELECT count(*) INTO total_dependencias
      FROM pg_shdepend s
      JOIN pg_roles r ON r.oid = s.refobjid
     WHERE s.refclassid = 'pg_authid'::regclass
       AND r.rolname = 'nsi_importacao';
    SELECT count(*) INTO total_sessoes
      FROM pg_stat_activity WHERE usename = 'nsi_importacao';

    IF canlogin_atual IS DISTINCT FROM true OR super_atual IS DISTINCT FROM false
       OR createdb_atual IS DISTINCT FROM false OR createrole_atual IS DISTINCT FROM false
       OR replication_atual IS DISTINCT FROM false OR bypassrls_atual IS DISTINCT FROM false
       OR inherit_atual IS DISTINCT FROM true
       OR total_pertence <> 0 OR total_membros <> 0 OR total_dependencias <> 0 OR total_sessoes <> 0 THEN
        RAISE EXCEPTION 'Acao 3: role nsi_importacao nao pode ser removida (canlogin=%, super=%, createdb=%, createrole=%, replication=%, bypassrls=%, inherit=%, pertence_a=%, membros=%, dependencias_no_cluster=%, sessoes_abertas=%). Abortando sem remover.',
            canlogin_atual, super_atual, createdb_atual, createrole_atual, replication_atual, bypassrls_atual, inherit_atual,
            total_pertence, total_membros, total_dependencias, total_sessoes;
    END IF;

    EXECUTE 'DROP ROLE nsi_importacao';

    PERFORM 1 FROM pg_roles WHERE rolname = 'nsi_importacao';
    IF FOUND THEN
        RAISE EXCEPTION 'Acao 3: remocao sem efeito - role nsi_importacao ainda existe. Abortando; acao desfeita.';
    END IF;
    RAISE NOTICE 'Acao 3 (role nsi_importacao): executado - role removida.';
END $$;

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

-- 3.1 - nsi_importacao nao existe (pg_roles e pg_authid).
DO $$
BEGIN
    PERFORM 1 FROM pg_roles WHERE rolname = 'nsi_importacao';
    IF FOUND THEN
        RAISE EXCEPTION 'Pos-validacao falhou: role nsi_importacao ainda existe em pg_roles.';
    END IF;
    PERFORM 1 FROM pg_authid WHERE rolname = 'nsi_importacao';
    IF FOUND THEN
        RAISE EXCEPTION 'Pos-validacao falhou: role nsi_importacao ainda existe em pg_authid.';
    END IF;
END $$;
\echo '  3.1 role nsi_importacao ausente: ok.'

-- 3.2 - nenhuma dependencia compartilhada orfa no cluster: toda linha de
-- pg_shdepend que referencia uma role referencia uma role existente.
DO $$
DECLARE total_orfas integer;
BEGIN
    SELECT count(*) INTO total_orfas
      FROM pg_shdepend s
     WHERE s.refclassid = 'pg_authid'::regclass
       AND NOT EXISTS (SELECT 1 FROM pg_authid a WHERE a.oid = s.refobjid);
    IF total_orfas <> 0 THEN
        RAISE EXCEPTION 'Pos-validacao falhou: % dependencia(s) compartilhada(s) referenciando role inexistente no cluster.', total_orfas;
    END IF;
END $$;
\echo '  3.2 nenhuma dependencia orfa no cluster: ok.'

-- 3.3 - as quatro roles da B3.1 continuam com os atributos aprovados; a
-- regra de membership da B3.1 continua valendo com a excecao unica da
-- ADR-009 (este script nunca toca a B4.3); memberships dos migrators
-- intactas.
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
    IF total_linhas > 1 OR total_incompativeis <> 0 THEN
        RAISE EXCEPTION 'Pos-validacao falhou: memberships de nsi_aplicacao incorretas (linhas=%, fora da excecao=%; aceito: nenhuma, ou exatamente uma em nsi_congelamento - ADR-009, Secao 21).', total_linhas, total_incompativeis;
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
\echo '  3.3 roles da B3.1, regra de membership e migrators: ok.'

-- 3.4 - bancos: PUBLIC continua sem CONNECT em nsi_dev e nsi_test (B3.1),
-- e nenhuma entrada de permissao de banco ficou orfa.
DO $$
DECLARE nome_banco text; lista_nula boolean; total_public integer; total_orfas integer;
BEGIN
    FOREACH nome_banco IN ARRAY ARRAY['nsi_dev', 'nsi_test'] LOOP
        SELECT d.datacl IS NULL INTO lista_nula FROM pg_database d WHERE d.datname = nome_banco;
        SELECT count(*) INTO total_public
          FROM pg_database d CROSS JOIN LATERAL aclexplode(d.datacl) a
         WHERE d.datname = nome_banco AND a.grantee = 0 AND a.privilege_type = 'CONNECT';
        IF lista_nula IS DISTINCT FROM false OR total_public <> 0 THEN
            RAISE EXCEPTION 'Pos-validacao falhou: PUBLIC possui CONNECT em % (B3.1 exige que nao possua).', nome_banco;
        END IF;
        SELECT count(*) INTO total_orfas
          FROM pg_database d CROSS JOIN LATERAL aclexplode(d.datacl) a
         WHERE d.datname = nome_banco AND a.grantee <> 0
           AND NOT EXISTS (SELECT 1 FROM pg_roles g WHERE g.oid = a.grantee);
        IF total_orfas <> 0 THEN
            RAISE EXCEPTION 'Pos-validacao falhou: % entrada(s) de permissao orfa(s) no banco %.', total_orfas, nome_banco;
        END IF;
    END LOOP;
END $$;
\echo '  3.4 PUBLIC sem CONNECT nos dois bancos; nenhuma permissao de banco orfa: ok.'

-- 3.5 - nsi_dev: schema, revisao, ausencia das funcoes e nenhuma ACL orfa.
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
    IF revisao NOT IN ('0005') THEN
        RAISE EXCEPTION 'Pos-validacao falhou: % esta em revisao % - aceito: somente 0005.', current_database(), revisao;
    END IF;

    SELECT count(*) INTO total_inesperadas
      FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
     WHERE n.nspname = 'nsi_operacional'
       AND p.proname IN ('fn_iniciar_importacao_legado', 'fn_importar_lote_legado',
                         'fn_concluir_importacao_legado', 'fn_verificar_paridade_legado');
    IF total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Pos-validacao falhou: funcao(oes) de importacao presente(s) em nsi_operacional de %.', current_database();
    END IF;

    SELECT (SELECT count(*) FROM pg_namespace n CROSS JOIN LATERAL aclexplode(n.nspacl) a
             WHERE n.nspname = 'nsi_operacional' AND a.grantee <> 0
               AND NOT EXISTS (SELECT 1 FROM pg_roles g WHERE g.oid = a.grantee))
         + (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
             CROSS JOIN LATERAL aclexplode(c.relacl) a
             WHERE n.nspname = 'nsi_operacional' AND a.grantee <> 0
               AND NOT EXISTS (SELECT 1 FROM pg_roles g WHERE g.oid = a.grantee))
         + (SELECT count(*) FROM pg_attribute t JOIN pg_class c ON c.oid = t.attrelid
             JOIN pg_namespace n ON n.oid = c.relnamespace
             CROSS JOIN LATERAL aclexplode(t.attacl) a
             WHERE n.nspname = 'nsi_operacional' AND a.grantee <> 0
               AND NOT EXISTS (SELECT 1 FROM pg_roles g WHERE g.oid = a.grantee))
         + (SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
             CROSS JOIN LATERAL aclexplode(p.proacl) a
             WHERE n.nspname = 'nsi_operacional' AND a.grantee <> 0
               AND NOT EXISTS (SELECT 1 FROM pg_roles g WHERE g.oid = a.grantee))
      INTO total_inesperadas;
    IF total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Pos-validacao falhou: % entrada(s) de ACL orfa(s) (grantee sem role) no schema nsi_operacional de %.', total_inesperadas, current_database();
    END IF;
END $$;
SELECT version_num AS f3_revisao_dev FROM nsi_operacional.alembic_version
\gset
\echo '  3.5 nsi_dev - schema, revisao, ausencia das funcoes e nenhuma ACL orfa: ok.'

-- 3.6 - nsi_test: as mesmas verificacoes, e a mesma revisao de nsi_dev.
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
    IF revisao NOT IN ('0005') THEN
        RAISE EXCEPTION 'Pos-validacao falhou: % esta em revisao % - aceito: somente 0005.', current_database(), revisao;
    END IF;

    SELECT count(*) INTO total_inesperadas
      FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
     WHERE n.nspname = 'nsi_operacional'
       AND p.proname IN ('fn_iniciar_importacao_legado', 'fn_importar_lote_legado',
                         'fn_concluir_importacao_legado', 'fn_verificar_paridade_legado');
    IF total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Pos-validacao falhou: funcao(oes) de importacao presente(s) em nsi_operacional de %.', current_database();
    END IF;

    SELECT (SELECT count(*) FROM pg_namespace n CROSS JOIN LATERAL aclexplode(n.nspacl) a
             WHERE n.nspname = 'nsi_operacional' AND a.grantee <> 0
               AND NOT EXISTS (SELECT 1 FROM pg_roles g WHERE g.oid = a.grantee))
         + (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
             CROSS JOIN LATERAL aclexplode(c.relacl) a
             WHERE n.nspname = 'nsi_operacional' AND a.grantee <> 0
               AND NOT EXISTS (SELECT 1 FROM pg_roles g WHERE g.oid = a.grantee))
         + (SELECT count(*) FROM pg_attribute t JOIN pg_class c ON c.oid = t.attrelid
             JOIN pg_namespace n ON n.oid = c.relnamespace
             CROSS JOIN LATERAL aclexplode(t.attacl) a
             WHERE n.nspname = 'nsi_operacional' AND a.grantee <> 0
               AND NOT EXISTS (SELECT 1 FROM pg_roles g WHERE g.oid = a.grantee))
         + (SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
             CROSS JOIN LATERAL aclexplode(p.proacl) a
             WHERE n.nspname = 'nsi_operacional' AND a.grantee <> 0
               AND NOT EXISTS (SELECT 1 FROM pg_roles g WHERE g.oid = a.grantee))
      INTO total_inesperadas;
    IF total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Pos-validacao falhou: % entrada(s) de ACL orfa(s) (grantee sem role) no schema nsi_operacional de %.', total_inesperadas, current_database();
    END IF;
END $$;
SELECT (version_num <> :'f3_revisao_dev') AS f3_revisoes_divergem FROM nsi_operacional.alembic_version
\gset
\if :f3_revisoes_divergem
DO $$
BEGIN
    RAISE EXCEPTION 'Pos-validacao falhou: nsi_dev e nsi_test estao em revisoes diferentes.';
END $$;
\endif
\echo '  3.6 nsi_test - schema, revisao, ausencia das funcoes e nenhuma ACL orfa: ok.'

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
\echo 'desprovisionar_b5_role_importacao.sql concluido - Fase 3 (pos-validacao completa) passou integralmente.'

-- =============================================================
-- LEMBRETES (fora deste script).
--
-- 1. A migration 0006 exige nsi_importacao existente: aplica-la depois
--    deste script exige reprovisionar a role antes
--    (provisionar_b5_role_importacao.sql) e redefinir a senha.
--
-- 2. Depois deste script, remova do .env local a variavel
--    TEST_DATABASE_URL_NSI_IMPORTACAO - ela deixa de corresponder a uma
--    role existente.
--
-- 3. Este script nunca e o "conserto" de um provisionamento falho, e o
--    provisionamento nunca e o "conserto" de um desprovisionamento falho:
--    falha no meio de qualquer um deles se resolve reexecutando o MESMO
--    script.
--
-- 4. A role e do cluster, compartilhada por nsi_dev e nsi_test. Quando
--    nsi_dev estiver na 0006 (que nunca sofre reversao), este script fica
--    permanentemente bloqueado no cluster principal - comportamento
--    intencional. Ele so e utilizavel antes da 0006, ou em cluster
--    descartavel.
--
-- 5. Feche toda sessao aberta como nsi_importacao ANTES de executar este
--    script. As sessoes so sao conferidas na Acao 3 (remocao da role):
--    com uma sessao aberta, as Acoes 1 e 2 revogam USAGE e CONNECT e a
--    Acao 3 aborta. O resultado e um estado aceito pela Fase 1 (role
--    presente, sem concessoes); basta fechar a sessao e reexecutar este
--    mesmo script. Conferir as sessoes ja na Fase 1 e uma melhoria
--    registrada como pendencia de decisao - ver o procedimento manual
--    da B5.3, Secao 11.
-- =============================================================
