-- =============================================================
-- scripts/postgres_local/desprovisionar_b6_ensaio.sql
-- Sprint B (B6) - SPRINT-B6-ESPECIFICACAO-ENSAIO-DE-CORTE.md (Secoes 15,
-- 30, 32 e 34, componente C2): DESCARTE do ambiente de ensaio.
--
-- *** SCRIPT DESTRUTIVO - APENAS O AMBIENTE DE ENSAIO, NO POSTGRESQL LOCAL ***
-- *** NUNCA EXECUTAR CONTRA PRODUCAO - NUNCA EXECUTADO AUTOMATICAMENTE ***
-- *** NENHUM TESTE AUTOMATIZADO CHAMA ESTE ARQUIVO - execucao manual,
--     autorizada e deliberada, sempre. ***
--
-- Execute conectado ao banco de manutencao "postgres":
--
--     psql -U postgres -d postgres -f scripts/postgres_local/desprovisionar_b6_ensaio.sql
--
-- Ao contrario das reversoes da B3.1, da B4.3 e da B5.3, este script E
-- executado em TODA rodada do ensaio, qualquer que seja o resultado: o
-- ambiente de ensaio e descartavel por definicao (especificacao da B6,
-- Secao 34). E a unica forma de desfazer uma rodada - nunca downgrade,
-- nunca remocao seletiva de linhas, nunca desabilitar trigger.
--
-- ANTES DE EXECUTAR: as evidencias da rodada ja precisam estar gravadas e
-- copiadas para fora da area de ensaio (Secao 32, passo 1). O banco contem o
-- snapshot legado, com dado pessoal; depois deste script ele nao existe mais.
--
-- O QUE ESTE SCRIPT FAZ (e nada alem disso):
--   1. revoga o CONNECT de nsi_importacao em nsi_ensaio;
--   2. remove o banco nsi_ensaio inteiro - com ele, o schema, as tabelas, o
--      snapshot, o registro tecnico e toda concessao interna;
--   3. revoga a membership de nsi_ensaio_migrator em nsi_eventos_owner;
--   4. remove a role nsi_ensaio_migrator;
--   5. forca um checkpoint e a troca do segmento de WAL, para reduzir o
--      residuo do snapshot no log de transacoes.
--
-- O QUE ESTE SCRIPT NUNCA FAZ: nao toca nsi_dev nem nsi_test (bancos,
-- schemas, tabelas, dados, concessoes); nao toca as oito roles permanentes,
-- exceto o CONNECT de nsi_importacao no banco de ensaio; nao usa remocao em
-- cadeia, reatribuicao de propriedade nem remocao forcada de sessoes; nao
-- executa reversao de migration; nunca corrige um estado divergente.
--
-- ESTADO PARCIAL: um provisionamento interrompido pode deixar o ambiente
-- pela metade. Este script aceita qualquer combinacao - cada objeto ausente
-- ou presente - e remove o que existir.
--
-- NAO CONTEM SENHA.
--
-- ---------------------------------------------------------------
-- DESENHO DE TRES FASES, COM GATE DE CONFIRMACAO
-- ---------------------------------------------------------------
-- FASE 1 (preflight): somente leitura. Confirma a identidade do servidor,
--   que nao ha sessao conectada ao banco de ensaio e que a role a remover
--   nao e dona nem beneficiaria de nada fora dele.
-- GATE: confirmacao textual exata, pedida sempre. Frase incorreta ou
--   ausente encerra o script antes da Fase 2, sem nenhuma alteracao.
-- FASE 2 (descarte): unica fase que escreve. Le o estado de novo. Como DROP
--   DATABASE nao roda dentro de bloco de codigo nem de transacao, as
--   escritas sao comandos diretos, sob \if.
-- FASE 3 (pos-validacao): somente leitura. Reconfirma, a partir do zero,
--   que nada do ambiente de ensaio restou e que o estado permanente esta
--   intacto.
--
-- READ ONLY nas Fases 1 e 3 e no gate, religado depois de cada \c e
-- conferido logo apos ligar. Variaveis de cliente prefixadas pelo bloco
-- (conf_, f2_) e nunca cruzam blocos.
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

-- 1.1 - os bancos permanentes e a role nsi_importacao existem: o descarte
-- do ensaio nunca pode ser confundido com eles.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'nsi_dev')
       OR NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'nsi_test')
       OR NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nsi_importacao') THEN
        RAISE EXCEPTION 'Estado permanente inesperado (nsi_dev, nsi_test ou nsi_importacao ausente). Abortando na preflight, sem nenhuma alteracao.';
    END IF;
END $$;

-- 1.2 - nenhuma sessao conectada ao banco de ensaio. Este script nunca
-- derruba sessao: encerre o executor, a auditoria e qualquer psql antes.
DO $$
DECLARE total integer;
BEGIN
    SELECT count(*) INTO total FROM pg_stat_activity WHERE datname = 'nsi_ensaio';
    IF total <> 0 THEN
        RAISE EXCEPTION 'Existem % sessao(oes) conectada(s) a nsi_ensaio. Encerre-as e execute de novo. Abortando na preflight, sem nenhuma alteracao.', total;
    END IF;
END $$;

-- 1.3 - o migrator de ensaio, se existir, nao e superusuario, nao tem
-- membros, so pertence a nsi_eventos_owner e nao tem nenhuma dependencia
-- fora do banco de ensaio (nada em nsi_dev, em nsi_test ou em outro banco).
DO $$
DECLARE total integer; total_fora integer;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nsi_ensaio_migrator') THEN
        RETURN;
    END IF;
    SELECT count(*) INTO total FROM pg_roles
     WHERE rolname = 'nsi_ensaio_migrator' AND NOT rolsuper AND NOT rolcreatedb AND NOT rolcreaterole
       AND NOT rolreplication AND NOT rolbypassrls;
    IF total <> 1 THEN
        RAISE EXCEPTION 'Role nsi_ensaio_migrator com atributos inesperados - nao e a role criada por provisionar_b6_ensaio.sql. Abortando na preflight, sem nenhuma alteracao.';
    END IF;
    SELECT count(*) INTO total FROM pg_auth_members m JOIN pg_roles g ON g.oid = m.roleid
     WHERE g.rolname = 'nsi_ensaio_migrator';
    SELECT count(*) INTO total_fora
      FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.member JOIN pg_roles g ON g.oid = m.roleid
     WHERE r.rolname = 'nsi_ensaio_migrator' AND g.rolname <> 'nsi_eventos_owner';
    IF total <> 0 OR total_fora <> 0 THEN
        RAISE EXCEPTION 'Role nsi_ensaio_migrator com membership inesperada (membros=%, outras roles=%). Abortando na preflight, sem nenhuma alteracao.', total, total_fora;
    END IF;
    SELECT count(*) INTO total_fora
      FROM pg_shdepend s JOIN pg_roles r ON r.oid = s.refobjid
     WHERE s.refclassid = 'pg_authid'::regclass AND r.rolname = 'nsi_ensaio_migrator'
       AND NOT (s.dbid = COALESCE((SELECT oid FROM pg_database WHERE datname = 'nsi_ensaio'), 0)
                OR (s.classid = 'pg_database'::regclass
                    AND s.objid = COALESCE((SELECT oid FROM pg_database WHERE datname = 'nsi_ensaio'), 0)));
    IF total_fora <> 0 THEN
        RAISE EXCEPTION 'Role nsi_ensaio_migrator possui % dependencia(s) fora do banco de ensaio. Abortando na preflight, sem nenhuma alteracao.', total_fora;
    END IF;
END $$;

\echo 'FASE 1 concluida - nenhuma escrita ocorreu.'

-- =============================================================
-- GATE DE CONFIRMACAO. Somente leitura. Confirmacao textual exata, pedida
-- sempre - mesmo quando nao ha nada a remover.
-- =============================================================
SET default_transaction_read_only = on;
DO $$
BEGIN
    IF current_setting('transaction_read_only') <> 'on' THEN
        RAISE EXCEPTION 'Modo somente leitura NAO esta ativo no gate de confirmacao (postgres). Abortando sem nenhuma alteracao.';
    END IF;
END $$;

\prompt 'Digite exatamente CONFIRMO-DESCARTAR-NSI-B6-AMBIENTE-DE-ENSAIO para remover o banco nsi_ensaio: ' conf_frase

SELECT CASE WHEN :'conf_frase' = 'CONFIRMO-DESCARTAR-NSI-B6-AMBIENTE-DE-ENSAIO'
            THEN 'true' ELSE 'false' END AS conf_pode_prosseguir
\gset

\if :conf_pode_prosseguir
    \echo 'Confirmacao recebida - prosseguindo para a Fase 2.'
\else
    \echo 'Confirmacao incorreta ou ausente - encerrando sem nenhuma alteracao.'
    \quit
\endif

-- =============================================================
-- FASE 2 - DESCARTE. Unica fase que realiza operacoes de escrita. Le o
-- estado de novo; remove o que existir, na ordem inversa da criacao.
-- =============================================================
\echo 'FASE 2 - descarte (escrita liberada).'
SET default_transaction_read_only = off;

-- Reconferencia imediata: nenhuma sessao no banco de ensaio.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_stat_activity WHERE datname = 'nsi_ensaio') THEN
        RAISE EXCEPTION 'Sessao conectada a nsi_ensaio no momento do descarte. Abortando; nada foi removido.';
    END IF;
END $$;

SELECT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'nsi_ensaio') AS f2_banco_existe
\gset
\if :f2_banco_existe
    -- Acao 1 - CONNECT de nsi_importacao fora do banco de ensaio.
    REVOKE CONNECT ON DATABASE nsi_ensaio FROM nsi_importacao;
    -- Acao 2 - o banco inteiro.
    DROP DATABASE nsi_ensaio;
    \echo 'FASE 2: banco nsi_ensaio removido.'
\else
    \echo 'FASE 2: banco nsi_ensaio ausente, nada a remover.'
\endif

SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nsi_ensaio_migrator') AS f2_role_existe
\gset
\if :f2_role_existe
    -- Acao 3 - membership do migrator de ensaio.
    REVOKE nsi_eventos_owner FROM nsi_ensaio_migrator;
    -- Acao 4 - a role.
    DROP ROLE nsi_ensaio_migrator;
    \echo 'FASE 2: role nsi_ensaio_migrator removida.'
\else
    \echo 'FASE 2: role nsi_ensaio_migrator ausente, nada a remover.'
\endif

-- Acao 5 - reduz o residuo do snapshot no log de transacoes.
CHECKPOINT;
SELECT pg_switch_wal() IS NOT NULL AS f2_wal_trocado;

\echo 'FASE 2 concluida.'

-- =============================================================
-- FASE 3 - POS-VALIDACAO COMPLETA. READ ONLY obrigatorio. Reconfirma, a
-- partir do zero, que nada do ambiente de ensaio restou.
-- =============================================================
\echo 'FASE 3 - pos-validacao completa (somente leitura).'
SET default_transaction_read_only = on;
DO $$
BEGIN
    IF current_setting('transaction_read_only') <> 'on' THEN
        RAISE EXCEPTION 'Modo somente leitura NAO esta ativo na Fase 3 (postgres).';
    END IF;
END $$;

-- 3.1 - banco e role de ensaio inexistentes.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_database WHERE datname = 'nsi_ensaio') THEN
        RAISE EXCEPTION 'Pos-validacao falhou: o banco nsi_ensaio ainda existe.';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nsi_ensaio_migrator') THEN
        RAISE EXCEPTION 'Pos-validacao falhou: a role nsi_ensaio_migrator ainda existe.';
    END IF;
END $$;

-- 3.2 - membros de nsi_eventos_owner: de volta aos dois migrators da B3.1.
DO $$
DECLARE total integer; total_exatos integer;
BEGIN
    SELECT count(*),
           count(*) FILTER (WHERE r.rolname IN ('nsi_dev_migrator', 'nsi_test_migrator')
                              AND NOT m.inherit_option AND m.set_option AND NOT m.admin_option)
      INTO total, total_exatos
      FROM pg_auth_members m JOIN pg_roles g ON g.oid = m.roleid JOIN pg_roles r ON r.oid = m.member
     WHERE g.rolname = 'nsi_eventos_owner';
    IF total <> 2 OR total_exatos <> 2 THEN
        RAISE EXCEPTION 'Pos-validacao falhou: membros de nsi_eventos_owner fora do aprovado na B3.1 (linhas=%, exatos=%).', total, total_exatos;
    END IF;
END $$;

-- 3.3 - nsi_importacao de volta ao estado da B5.3: CONNECT somente em
-- nsi_test, e nenhuma dependencia fora de nsi_dev/nsi_test.
DO $$
DECLARE total integer; total_inesperadas integer;
BEGIN
    SELECT count(*) FILTER (WHERE d.datname = 'nsi_test' AND a.privilege_type = 'CONNECT' AND NOT a.is_grantable),
           count(*) FILTER (WHERE NOT (d.datname = 'nsi_test' AND a.privilege_type = 'CONNECT' AND NOT a.is_grantable))
      INTO total, total_inesperadas
      FROM pg_database d
     CROSS JOIN LATERAL aclexplode(d.datacl) a
      JOIN pg_roles g ON g.oid = a.grantee
     WHERE g.rolname = 'nsi_importacao';
    IF total <> 1 OR total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Pos-validacao falhou: concessoes de banco de nsi_importacao fora do estado da B5.3 (CONNECT em nsi_test=%, inesperadas=%).', total, total_inesperadas;
    END IF;
    SELECT count(*) INTO total_inesperadas
      FROM pg_shdepend s JOIN pg_roles r ON r.oid = s.refobjid
     WHERE s.refclassid = 'pg_authid'::regclass AND r.rolname = 'nsi_importacao'
       AND s.dbid <> 0
       AND s.dbid NOT IN (SELECT oid FROM pg_database WHERE datname IN ('nsi_dev', 'nsi_test'));
    IF total_inesperadas <> 0 THEN
        RAISE EXCEPTION 'Pos-validacao falhou: nsi_importacao com % dependencia(s) fora de nsi_dev/nsi_test.', total_inesperadas;
    END IF;
END $$;

-- 3.4 - nsi_dev e nsi_test intocados, na revisao 0006.
\c nsi_dev
SET default_transaction_read_only = on;
DO $$
BEGIN
    IF current_setting('transaction_read_only') <> 'on' THEN
        RAISE EXCEPTION 'Modo somente leitura NAO esta ativo na Fase 3 (%).', current_database();
    END IF;
    IF (SELECT version_num FROM nsi_operacional.alembic_version) IS DISTINCT FROM '0006' THEN
        RAISE EXCEPTION 'Pos-validacao falhou: % fora da revisao 0006.', current_database();
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
        RAISE EXCEPTION 'Pos-validacao falhou: % fora da revisao 0006.', current_database();
    END IF;
END $$;

\c postgres
SET default_transaction_read_only = on;

-- =============================================================
-- ENCERRAMENTO
-- =============================================================
\echo 'Fase 3 (pos-validacao completa) passou integralmente - ambiente de ensaio descartado.'
\echo ''
\echo 'LEMBRETES (manuais, fora deste script - especificacao da B6, Secao 32):'
\echo '  1. Apagar da area de ensaio a origem, a restauracao e, conforme a decisao D7, o backup.'
\echo '  2. Remover do .env local as variaveis ENSAIO_DATABASE_URL e ENSAIO_DATABASE_URL_NSI_IMPORTACAO.'
\echo '  3. Executar a suite completa em nsi_test e conferir nsi_dev e nsi_test na revisao 0006.'
