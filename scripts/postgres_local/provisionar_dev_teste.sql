-- =============================================================
-- scripts/postgres_local/provisionar_dev_teste.sql
-- Sprint B (B2.2) - ADR-008
--
-- APENAS PARA DESENVOLVIMENTO/TESTE LOCAL. NUNCA PRODUCAO.
--
-- Execute conectado ao banco de manutencao "postgres" - o bloco de
-- verificacao abaixo aborta a execucao se isso nao for verdade:
--
--     psql -U postgres -d postgres -f scripts/postgres_local/provisionar_dev_teste.sql
--
-- Provisiona a infraestrutura administrativa minima usada pelas subetapas
-- B2/B3 nesta maquina: duas roles de migracao/conexao LOCAL (donas do
-- schema apenas nos bancos de desenvolvimento/teste desta sprint) e dois
-- bancos, cada um com o schema "nsi_operacional".
--
-- Estas roles NAO SAO as quatro roles funcionais aprovadas para a Sprint B3
-- (nsi_eventos_owner, nsi_aplicacao, nsi_expiracao, nsi_operador_restrito) -
-- permanecem inteiramente distintas e exclusivas de B3. Nenhum codigo de
-- aplicacao deve usar a credencial administrativa/migradora em producao.
--
-- Requer privilegio de superusuario (ou CREATEDB + CREATEROLE) - nesta
-- maquina, o usuario "postgres" da instalacao local do PostgreSQL 17.
--
-- NAO CONTEM SENHA. As roles sao criadas SEM senha (LOGIN, sem PASSWORD).
-- A senha e definida DEPOIS, interativamente, dentro de uma sessao psql,
-- via \password - NUNCA como argumento de linha de comando, NUNCA como
-- variavel -v do psql, NUNCA gravada em nenhum arquivo (ver "PROXIMOS
-- PASSOS" ao final deste arquivo).
--
-- ESTE SCRIPT NAO E EXECUTADO AUTOMATICAMENTE por nenhum teste, por
-- migrations/env.py ou por qualquer codigo de aplicacao. Execucao manual,
-- uma unica vez, mediante autorizacao especifica e separada desta
-- aprovacao de planejamento.
--
-- NAO E ATOMICO COMO UM TODO: CREATE DATABASE nunca roda dentro de bloco
-- de transacao no PostgreSQL (e sempre autocommit) - cada instrucao deste
-- script e aplicada e confirmada independentemente. Uma falha no meio
-- deixa um estado PARCIAL, nunca revertido automaticamente.
--
-- RETOMADA/DESFAZIMENTO APOS FALHA PARCIAL: com \set ON_ERROR_STOP on
-- (abaixo), a execucao para exatamente na primeira falha - a saida do
-- psql mostra ate onde chegou. A partir dai, NAO tente completar
-- manualmente os passos faltantes: rode
-- scripts/postgres_local/desprovisionar_dev_teste.sql (tolerante a estado
-- parcial, via IF EXISTS) e reinicie este script do zero.
--
-- Ordem aprovada:
--   1) roles de migracao (sem senha)
--   2) databases, com OWNER ja atribuido na criacao
--   3) conectar em cada database
--   4) schema "nsi_operacional" com AUTHORIZATION do migrator
--   5) restringir "public" (CREATE) e "nsi_operacional" (ALL) de PUBLIC
--   6) (fora deste arquivo) definir senha interativamente
--   7) (fora deste arquivo e fora do Git) configurar as URLs no .env local
-- =============================================================

-- Interrompe a execucao na primeira instrucao que falhar - sem isto, um
-- erro no meio do script (ex.: role ja existe, ou um \c que falha) nao
-- impede que os comandos seguintes continuem rodando contra um estado
-- inconsistente ou contra a conexao/banco errado.
\set ON_ERROR_STOP on

-- Verificacao de identidade do servidor - aborta ANTES de qualquer CREATE
-- se a conexao inicial nao for exatamente o esperado. "psql.exe existir no
-- disco" nunca prova nada sobre qual servidor uma conexao especifica
-- atinge - so esta consulta, executada apos conectar, prova.
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

-- 1) Roles de migracao/conexao local - SEM senha nesta etapa.
CREATE ROLE nsi_dev_migrator  LOGIN;
CREATE ROLE nsi_test_migrator LOGIN;

-- 2) Databases, com OWNER ja atribuido na criacao.
--
-- Avaliacao (ja aprovada): CREATE DATABASE ... OWNER e preferivel a criar
-- o database primeiro e usar ALTER DATABASE ... OWNER TO depois. Como as
-- roles ja existem neste ponto (passo 1), a atribuicao de ownership e
-- feita atomicamente NA PROPRIA instrucao de criacao do banco - mas isso
-- descreve apenas essa instrucao isolada, nao o script inteiro (ver aviso
-- de nao-atomicidade acima).
CREATE DATABASE nsi_dev  OWNER nsi_dev_migrator;
CREATE DATABASE nsi_test OWNER nsi_test_migrator;

-- 3) e 4) Conectar em cada banco e criar o schema "nsi_operacional", de
-- propriedade do migrator correspondente. O Alembic (migrations/env.py)
-- APENAS verifica a existencia deste schema - nunca o cria (evita a
-- dependencia circular entre version_table_schema e a criacao do proprio
-- schema onde a tabela de versao precisaria nascer).
\c nsi_dev
CREATE SCHEMA IF NOT EXISTS nsi_operacional AUTHORIZATION nsi_dev_migrator;

-- Restringe permissoes de PUBLIC (ver "Ordem aprovada" no cabecalho):
-- USAGE de "public" permanece concedido a PUBLIC, por decisao explicita -
-- nao usamos REVOKE ALL em "public". "nsi_operacional" e restringido por
-- completo de PUBLIC, mesmo que o comportamento padrao do PostgreSQL para
-- um schema recem-criado provavelmente ja nao conceda nada a PUBLIC -
-- nunca presumido, sempre explicito.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON SCHEMA nsi_operacional FROM PUBLIC;

\c nsi_test
CREATE SCHEMA IF NOT EXISTS nsi_operacional AUTHORIZATION nsi_test_migrator;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON SCHEMA nsi_operacional FROM PUBLIC;

-- =============================================================
-- PROXIMOS PASSOS (fora deste arquivo, NUNCA automatizados):
--
-- 6) Definir a senha de cada role INTERATIVAMENTE, dentro de uma sessao
--    psql (nunca como argumento de linha de comando, nunca em variavel -v,
--    nunca gravada em texto neste script ou em qualquer outro arquivo
--    versionado). O que sera digitado nao aparece na tela; nada e gravado
--    em terminal, script, Git ou relatorio:
--
--        psql -U postgres -d postgres
--        \password nsi_dev_migrator
--        (digite a senha quando solicitado)
--        \password nsi_test_migrator
--        (digite a senha quando solicitado)
--        \q
--
-- 7) Configurar DATABASE_URL/TEST_DATABASE_URL SOMENTE no .env local
--    (ja coberto por .gitignore) - nunca em nenhum arquivo versionado,
--    nunca em log, nunca em historico de shell:
--
--        DATABASE_URL=postgresql://nsi_dev_migrator:<senha>@localhost:5432/nsi_dev
--        NSI_DATABASE_ENV=test
--        TEST_DATABASE_URL=postgresql://nsi_test_migrator:<senha>@localhost:5432/nsi_test
-- =============================================================
