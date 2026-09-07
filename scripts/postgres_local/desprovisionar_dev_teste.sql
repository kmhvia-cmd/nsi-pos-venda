-- =============================================================
-- scripts/postgres_local/desprovisionar_dev_teste.sql
-- Sprint B (B2.2) - ADR-008
--
-- *** SCRIPT DESTRUTIVO - APENAS DESENVOLVIMENTO/TESTE LOCAL ***
-- *** NUNCA EXECUTAR CONTRA PRODUCAO - NUNCA EXECUTADO AUTOMATICAMENTE ***
--
-- Remove EXATAMENTE os quatro objetos administrativos criados por
-- provisionar_dev_teste.sql: os bancos "nsi_dev" e "nsi_test", e as roles
-- "nsi_dev_migrator" e "nsi_test_migrator". Nenhum nome e recebido por
-- variavel, parametro ou wildcard - todos os alvos sao literais fixos
-- neste arquivo, exatamente para impedir que este script seja reaproveitado
-- contra qualquer outro banco/role por engano ou copia descuidada.
--
-- NUNCA e chamado por nenhum teste, por migrations/env.py ou por qualquer
-- codigo de aplicacao. Execucao manual, uma unica vez, mediante
-- autorizacao especifica e separada.
--
-- Execute conectado ao banco de manutencao "postgres" - NUNCA aos proprios
-- bancos sendo removidos (o PostgreSQL nunca permite DROP DATABASE do
-- banco atualmente em uso pela sessao). O bloco de verificacao abaixo
-- aborta a execucao se isso nao for verdade:
--
--     psql -U postgres -d postgres -f scripts/postgres_local/desprovisionar_dev_teste.sql
--
-- Ordem obrigatoria: verificar identidade -> confirmar por escrito ->
-- encerrar conexoes ativas -> DROP DATABASE -> DROP ROLE (somente depois
-- dos bancos, que dependem das roles como owner).
-- =============================================================

-- Interrompe a execucao na primeira instrucao que falhar.
\set ON_ERROR_STOP on

-- Verificacao de identidade do servidor - aborta ANTES de qualquer acao
-- destrutiva se a conexao inicial nao for exatamente o esperado.
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

-- Confirmacao textual obrigatoria - nenhuma acao destrutiva ocorre sem
-- que o operador digite EXATAMENTE a frase abaixo. Pressionar Enter (ou
-- digitar qualquer outra coisa) aborta sem nenhuma alteracao.
\prompt 'Digite exatamente CONFIRMO-DESPROVISIONAR-NSI-DEV-TESTE para prosseguir com a destruicao: ' confirmacao_desprovisionamento

SELECT CASE WHEN :'confirmacao_desprovisionamento' = 'CONFIRMO-DESPROVISIONAR-NSI-DEV-TESTE'
            THEN 'true' ELSE 'false' END AS pode_prosseguir
\gset

\if :pode_prosseguir
    \echo 'Confirmacao recebida - prosseguindo com o desprovisionamento.'
\else
    \echo 'Confirmacao incorreta ou ausente - abortando sem nenhuma alteracao.'
    \quit
\endif

-- 1) Encerra conexoes ativas EXCLUSIVAMENTE nos dois bancos-alvo fixos -
-- necessario porque o PostgreSQL recusa DROP DATABASE com conexoes abertas.
SELECT pg_terminate_backend(pid)
  FROM pg_stat_activity
 WHERE datname IN ('nsi_dev', 'nsi_test')
   AND pid <> pg_backend_pid();

-- 2) Remove os bancos - alvos fixos, nunca recebidos livremente.
DROP DATABASE IF EXISTS nsi_dev;
DROP DATABASE IF EXISTS nsi_test;

-- 3) Remove as roles SOMENTE depois de os bancos (que as tem como owner)
-- terem sido removidos.
DROP ROLE IF EXISTS nsi_dev_migrator;
DROP ROLE IF EXISTS nsi_test_migrator;
