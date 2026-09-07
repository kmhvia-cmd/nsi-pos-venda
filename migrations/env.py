# -*- coding: utf-8 -*-
r"""
NSI - migrations/env.py (Sprint B, B2.2 - ADR-008)

Ambiente de execucao do Alembic. Resolve a URL de conexao por
config.resolver_url_banco() - NUNCA le nem grava a URL em alembic.ini.

Marcador de ambiente (NSI_DATABASE_ENV, sem fallback entre os dois modos -
ver config.resolver_url_banco):
  - "development" (padrao) -> usa exclusivamente Config.DATABASE_URL.
  - "test"                 -> usa exclusivamente Config.TEST_DATABASE_URL,
                                e exige que o banco referenciado seja
                                exatamente "nsi_test".

Comandos PowerShell (ambiente real deste projeto e Windows/PowerShell):

    # ativar a venv
    .\.venv\Scripts\Activate.ps1

    # rodar migrations contra o banco de DESENVOLVIMENTO
    # (NSI_DATABASE_ENV default ja e "development" - nao e preciso definir)
    $env:DATABASE_URL = "postgresql://nsi_dev_migrator:***@localhost:5432/nsi_dev"
    alembic upgrade head
    Remove-Item Env:\DATABASE_URL -ErrorAction SilentlyContinue

    # rodar migrations contra o banco de TESTE (marcador explicito)
    $env:NSI_DATABASE_ENV = "test"
    $env:TEST_DATABASE_URL = "postgresql://nsi_test_migrator:***@localhost:5432/nsi_test"
    alembic upgrade head
    Remove-Item Env:\NSI_DATABASE_ENV, Env:\TEST_DATABASE_URL -ErrorAction SilentlyContinue

Bash (equivalente, quando aplicavel):

    NSI_DATABASE_ENV=test TEST_DATABASE_URL="postgresql://nsi_test_migrator:***@localhost:5432/nsi_test" \
        alembic upgrade head

Este arquivo NUNCA cria o schema "nsi_operacional" - apenas verifica sua
existencia (leitura) e falha com mensagem instrutiva se ausente. A criacao
do schema e responsabilidade exclusiva do provisionamento administrativo
(scripts/postgres_local/provisionar_dev_teste.sql), executado uma unica vez,
fora do fluxo comum de `alembic upgrade` - nunca um efeito colateral
silencioso desta execucao.
"""
from logging.config import fileConfig

from sqlalchemy import create_engine, text
from alembic import context

from config import Config, resolver_url_banco, mascarar_dsn

# Nome do schema onde a tabela de controle do Alembic (alembic_version) e as
# futuras tabelas de negocio (Sprint B3) vivem. Ja aprovado na Especificacao
# Tecnica da Sprint B (Secao 5) - nunca criado por este arquivo.
NOME_SCHEMA = "nsi_operacional"

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# B2 nao define metadata de nenhuma tabela de negocio - a migration bootstrap
# desta sprint e intencionalmente vazia (ver migrations/versions/0001_bootstrap_vazio.py).
target_metadata = None


def _verificar_schema_existe(conn) -> None:
    """
    Verificacao de LEITURA apenas - este modulo NUNCA executa CREATE SCHEMA.
    Falha com mensagem clara e instrutiva se o schema nao existir, em vez de
    deixar o Alembic falhar mais adiante com um erro generico, e em vez de
    criar o schema silenciosamente como efeito colateral de toda execucao.
    """
    existe = conn.execute(
        text("SELECT 1 FROM information_schema.schemata WHERE schema_name = :nome"),
        {"nome": NOME_SCHEMA},
    ).scalar()
    if not existe:
        raise RuntimeError(
            f"O schema '{NOME_SCHEMA}' nao existe no banco de destino. "
            "Execute o provisionamento administrativo "
            "(scripts/postgres_local/provisionar_dev_teste.sql) antes de "
            "rodar o Alembic - este ambiente nunca cria o schema "
            "automaticamente."
        )


def run_migrations_offline() -> None:
    url = resolver_url_banco()
    context.configure(
        url=_url_para_sqlalchemy(url),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table_schema=NOME_SCHEMA,
        include_schemas=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _url_para_sqlalchemy(url: str) -> str:
    """
    SQLAlchemy seleciona o dialeto 'psycopg2' por padrao para qualquer URL
    'postgresql://' sem driver explicito - psycopg2 NAO esta instalado
    neste projeto (a Sprint B usa psycopg v3, Especificacao Tecnica, Secao
    3). Reescreve o prefixo para 'postgresql+psycopg://', selecionando o
    dialeto psycopg (v3) explicitamente. Config.DATABASE_URL/
    TEST_DATABASE_URL permanecem inalteradas - o restante do projeto usa
    psycopg.connect() diretamente e nunca precisa desse prefixo; a
    adaptacao e local a este arquivo, exclusivo do Alembic/SQLAlchemy.
    """
    for prefixo_generico in ("postgresql://", "postgres://"):
        if url.startswith(prefixo_generico):
            return "postgresql+psycopg://" + url[len(prefixo_generico):]
    return url


def run_migrations_online() -> None:
    url = resolver_url_banco()
    connectable = create_engine(_url_para_sqlalchemy(url))

    falha_conexao = False
    connection = None
    try:
        connection = connectable.connect()
    except Exception:
        falha_conexao = True

    # 'raise' fora do bloco except: uma excecao de conexao do SQLAlchemy/
    # psycopg pode ecoar a URL bruta na propria mensagem - a mesma razao
    # documentada em config.py (_parsear_dsn_com_seguranca). Levantar aqui,
    # apos sair do except, evita que a excecao original fique acessivel via
    # __context__.
    if falha_conexao:
        raise RuntimeError(
            f"Falha ao conectar ao banco ({mascarar_dsn(url)}) - verifique "
            "se o servico PostgreSQL esta acessivel e se as credenciais "
            "estao corretas."
        )

    with connection:
        _verificar_schema_existe(connection)
        # SQLAlchemy 2.0 usa "autobegin": a propria consulta de verificacao
        # acima ja inicia uma transacao implicita nesta conexao. Sem
        # encerra-la aqui, context.begin_transaction() (abaixo) herda essa
        # transacao ja aberta em vez de abrir e possuir a sua propria -
        # e deixa de comitar corretamente ao final, fazendo com que
        # 'alembic upgrade' pareca ter sucesso (imprime "Running upgrade")
        # mas nada seja persistido (nem a tabela alembic_version, nem o
        # carimbo de revisao). Confirmado empiricamente nesta sessao.
        # rollback (nao commit) porque a verificacao e somente leitura.
        connection.rollback()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table_schema=NOME_SCHEMA,
            include_schemas=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
