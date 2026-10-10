# -*- coding: utf-8 -*-
"""
NSI — scripts/importar_legado.py
Responsabilidade: executor da importacao do legado operacional em JSON
(ADR-010; Especificacao Tecnica da Sprint B, Secao 18, B5.2, item 5).

Uso (somente ambiente de teste, banco nsi_test, role nsi_importacao):

    python scripts/importar_legado.py --origem <diretorio> [--fuso <IANA>]
                                      [--importacao-id <uuid>]

    --origem          diretorio raiz do legado; obrigatorio, sem valor padrao.
                      Nunca o diretorio de dados da aplicacao.
    --fuso            identificador IANA atestado por declaracao humana
                      (ADR-010, Secao 13.2). Omitido: nenhum lote e promovido
                      (motivo 'fuso_nao_declarado') - nunca ha valor padrao.
    --importacao-id   retoma uma execucao ABERTA (interrompida antes da
                      conclusao); omitido, um UUID novo. Uma execucao ja
                      concluida nao aceita novos lotes e nunca e retomada.

Fluxo (item 5): gate de identidade -> origem -> enumeracao do escopo ->
abertura -> um lote por transacao -> manifesto -> conclusao -> paridade ->
relatorio. A classificacao, a preservacao, a promocao e a paridade campo a
campo sao do banco (migration 0006); este executor so le arquivos, chama as
quatro funcoes e monta manifesto e relatorio com core/importacao_legado.py.

GATE DE IDENTIDADE (item 5, passo 1), antes de qualquer chamada: banco
nsi_test, servidor local, porta 5432, session_user = nsi_importacao - lidos
da conexao real, nunca da URL. O executor aceita somente o ambiente 'test'
(item 4); a URL vem de config.resolver_url_banco_papel, que ja exige
usuario e banco exatos.

Se fn_importar_lote_legado levantar 'conflito_de_idempotencia' (22023), o
arquivo mudou durante a execucao: o executor aborta, a execucao permanece
aberta e nunca e concluida, e a importacao recomeca numa execucao nova.

Transacoes: cada chamada roda em 'with conexao.transaction()'. Em producao
a conexao e aberta em autocommit, e cada bloco e uma transacao propria
(uma por lote). Se a conexao recebida ja estiver numa transacao, os blocos
viram savepoints dela - e o que permite aos testes exercitar a promocao de
ponta a ponta e terminar em ROLLBACK (B5.2, item 17).

Privacidade: a saida e o relatorio do modulo puro, sem valor pessoal. As
mensagens de erro sao fixas - nunca trazem DSN, caminho absoluto, conteudo
de arquivo ou detalhe do driver.

Codigos de saida: 0 paridade aprovada; 1 execucao concluida com paridade
reprovada; 2 execucao recusada ou abortada.
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

RAIZ_DO_PROJETO = Path(__file__).resolve().parent.parent
if str(RAIZ_DO_PROJETO) not in sys.path:
    sys.path.insert(0, str(RAIZ_DO_PROJETO))

import psycopg  # noqa: E402

from config import Config, resolver_url_banco_papel  # noqa: E402
from core.importacao_legado import (  # noqa: E402
    TIPO_LOTE,
    ArquivoDeOrigemAlterado,
    OrigemInvalida,
    conferir_origem,
    entrada_de_lote,
    entrada_de_tentativa_recusada,
    enumerar_escopo,
    ler_arquivo_do_escopo,
    montar_manifesto,
    montar_relatorio,
    sha256_bytes,
    validar_origem,
)

PAPEL = "nsi_importacao"
AMBIENTE_PERMITIDO = "test"
BANCO_PERMITIDO = "nsi_test"
PORTA_PERMITIDA = 5432
ENDERECOS_LOCAIS = ("127.0.0.1", "::1")

SAIDA_PARIDADE_APROVADA = 0
SAIDA_PARIDADE_REPROVADA = 1
SAIDA_RECUSADA_OU_ABORTADA = 2


class IdentidadeNaoComprovada(RuntimeError):
    """O gate de identidade falhou. Nenhuma chamada foi feita."""


class ExecucaoAbortada(RuntimeError):
    """A execucao foi interrompida e NAO foi concluida. Carrega um motivo de
    vocabulario fixo e, quando existir, a execucao que permanece aberta."""

    def __init__(self, motivo: str, importacao_id: str | None = None) -> None:
        super().__init__(motivo)
        self.motivo = motivo
        self.importacao_id = importacao_id


def validar_ambiente(ambiente: str) -> None:
    """Item 4: o executor da B5 aceita somente o ambiente 'test'."""
    if ambiente != AMBIENTE_PERMITIDO:
        raise IdentidadeNaoComprovada("ambiente nao permitido - o executor aceita somente NSI_DATABASE_ENV=test")


def validar_identidade(banco, endereco_do_servidor, porta, usuario_da_sessao) -> None:
    """Gate de identidade (item 5, passo 1) sobre valores lidos da conexao
    real. Qualquer divergencia aborta antes de qualquer chamada. As
    mensagens sao fixas: nunca repetem o valor encontrado."""
    if banco != BANCO_PERMITIDO:
        raise IdentidadeNaoComprovada("banco nao permitido - esperado nsi_test")
    if endereco_do_servidor is not None and str(endereco_do_servidor).split("/")[0] not in ENDERECOS_LOCAIS:
        raise IdentidadeNaoComprovada("servidor remoto - o executor e exclusivo do PostgreSQL local")
    if porta != PORTA_PERMITIDA:
        raise IdentidadeNaoComprovada("porta nao permitida - esperada 5432")
    if usuario_da_sessao != PAPEL:
        raise IdentidadeNaoComprovada("usuario da sessao nao permitido - esperado nsi_importacao")


def comprovar_identidade(conexao) -> None:
    """Le a identidade da conexao real e aplica o gate."""
    with conexao.transaction():
        linha = conexao.execute(
            "SELECT current_database(), inet_server_addr()::text, inet_server_port(), session_user"
        ).fetchone()
    validar_identidade(*linha)


def _chamar(conexao, sql: str, parametros: tuple) -> dict:
    """Uma chamada de funcao numa transacao propria (ou num savepoint da
    transacao em que a conexao ja estiver)."""
    with conexao.transaction():
        return conexao.execute(sql, parametros).fetchone()[0]


def executar_importacao(conexao, origem, fuso=None, importacao_id=None) -> dict:
    """Executa o fluxo completo do item 5 sobre uma conexao ja aberta como
    nsi_importacao e devolve o relatorio, sem valor pessoal."""
    # Passo 1 - gate de identidade, antes de qualquer chamada.
    comprovar_identidade(conexao)

    # Passo 2 - origem explicita, nunca o diretorio de dados da aplicacao.
    origem = validar_origem(origem, Config.DATA_DIR)

    # Passo 3 - enumeracao do escopo, com tamanho e SHA-256 de cada arquivo.
    arquivos = enumerar_escopo(origem)

    # Passo 4 - abertura (ou retomada) da execucao.
    retomada = bool(importacao_id)
    importacao_id = str(uuid.UUID(str(importacao_id))) if retomada else str(uuid.uuid4())
    try:
        _chamar(conexao, "SELECT nsi_operacional.fn_iniciar_importacao_legado(%s, %s)", (importacao_id, fuso))
    except psycopg.errors.InvalidParameterValue:
        # Execucao ja aberta com outro fuso: nunca reaproveitada.
        raise ExecucaoAbortada("conflito_de_idempotencia_na_abertura", importacao_id) from None
    except psycopg.errors.DataException:
        raise ExecucaoAbortada("fuso_ou_execucao_invalidos") from None

    # So uma execucao ABERTA pode ser retomada: a concluida nao aceita novos
    # lotes (item 12), e reapresenta-los so produziria recusas do banco. O
    # executor nao le tabelas; a paridade informa se ja houve conclusao.
    if retomada and _chamar(
            conexao, "SELECT nsi_operacional.fn_verificar_paridade_legado(%s)", (importacao_id,))["concluida"]:
        raise ExecucaoAbortada("execucao_ja_concluida", importacao_id)

    # Passo 5 - um lote por transacao. As tentativas recusadas da A3 nunca
    # sao importadas: entram so no manifesto.
    entradas, retornos = [], []
    for arquivo in arquivos:
        if arquivo.tipo != TIPO_LOTE:
            entradas.append(entrada_de_tentativa_recusada(arquivo))
            continue
        try:
            conteudo = ler_arquivo_do_escopo(origem, arquivo)
            retorno = _chamar(
                conexao, "SELECT nsi_operacional.fn_importar_lote_legado(%s, %s, %s, %s)",
                (importacao_id, arquivo.caminho_relativo, conteudo, arquivo.sha256))
        except (ArquivoDeOrigemAlterado, psycopg.errors.InvalidParameterValue):
            # O arquivo mudou durante a execucao: ela permanece aberta e
            # nunca e concluida; a importacao recomeca numa execucao nova.
            raise ExecucaoAbortada("arquivo_alterado_durante_a_execucao", importacao_id) from None
        except psycopg.errors.DataException:
            raise ExecucaoAbortada("entrada_estrutural_invalida", importacao_id) from None
        retornos.append(retorno)
        entradas.append(entrada_de_lote(arquivo, retorno))

    # Passo 6 - manifesto canonico.
    manifesto = montar_manifesto(importacao_id, fuso, entradas)

    # Passo 7 - conclusao: o banco grava os bytes e recalcula o SHA-256.
    try:
        _chamar(
            conexao, "SELECT nsi_operacional.fn_concluir_importacao_legado(%s, %s, %s, %s)",
            (importacao_id, manifesto, sha256_bytes(manifesto), len(retornos)))
    except psycopg.errors.InvalidParameterValue:
        # Execucao ja concluida com outro manifesto (retomada indevida).
        raise ExecucaoAbortada("conflito_de_idempotencia_na_conclusao", importacao_id) from None
    except psycopg.errors.DataException:
        raise ExecucaoAbortada("conclusao_recusada", importacao_id) from None

    # Passo 8 - paridade: a do banco, mais a conferencia dos arquivos de
    # origem contra o registrado e a completude do manifesto.
    paridade_do_banco = _chamar(
        conexao, "SELECT nsi_operacional.fn_verificar_paridade_legado(%s)", (importacao_id,))
    conferencia = conferir_origem(origem, arquivos, entradas)

    # Passo 9 - relatorio sem valor pessoal.
    return montar_relatorio(importacao_id, fuso, entradas, retornos, manifesto, paridade_do_banco, conferencia)


def _conectar():
    """Conexao como nsi_importacao em nsi_test, em autocommit: cada chamada
    e uma transacao propria. Falha de conexao vira mensagem fixa - a
    excecao do driver pode ecoar a DSN."""
    validar_ambiente(Config.NSI_DATABASE_ENV)
    url = resolver_url_banco_papel(PAPEL, AMBIENTE_PERMITIDO)
    conexao = None
    try:
        conexao = psycopg.connect(url, autocommit=True)
    except Exception:
        pass
    if conexao is None:
        raise IdentidadeNaoComprovada("nao foi possivel conectar como nsi_importacao em nsi_test")
    return conexao


def _argumentos(argv) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="importar_legado",
        description="Importacao do legado operacional em JSON (ADR-010) - somente nsi_test.")
    parser.add_argument("--origem", required=True, help="diretorio raiz do legado (sem valor padrao)")
    parser.add_argument("--fuso", default=None,
                        help="identificador IANA declarado por humano; omitido, nenhum lote e promovido")
    parser.add_argument("--importacao-id", default=None, dest="importacao_id",
                        help="UUID de uma execucao aberta, para retoma-la")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    argumentos = _argumentos(argv)
    falha = None
    try:
        if argumentos.importacao_id is not None:
            try:
                uuid.UUID(argumentos.importacao_id)
            except ValueError:
                raise ExecucaoAbortada("importacao_id_invalido") from None
        # Origem conferida antes de abrir qualquer conexao.
        validar_origem(argumentos.origem, Config.DATA_DIR)
        conexao = _conectar()
        try:
            relatorio = executar_importacao(conexao, argumentos.origem, argumentos.fuso, argumentos.importacao_id)
        finally:
            conexao.close()
    except ExecucaoAbortada as exc:
        falha = {"executada": False, "motivo": exc.motivo, "importacao_id_aberta": exc.importacao_id}
    except (IdentidadeNaoComprovada, OrigemInvalida) as exc:
        falha = {"executada": False, "motivo": str(exc), "importacao_id_aberta": None}
    except Exception as exc:
        # Mensagem fixa: a excecao original pode trazer DSN ou conteudo. So
        # o nome da classe e o SQLSTATE (quando houver) sao repassados.
        falha = {"executada": False, "motivo": "falha_inesperada", "importacao_id_aberta": None,
                 "tipo": type(exc).__name__, "sqlstate": getattr(exc, "sqlstate", None)}

    if falha is not None:
        print(json.dumps(falha, ensure_ascii=False, sort_keys=True, indent=2))
        return SAIDA_RECUSADA_OU_ABORTADA

    print(json.dumps({"executada": True, **relatorio}, ensure_ascii=False, sort_keys=True, indent=2))
    return SAIDA_PARIDADE_APROVADA if relatorio["paridade"]["aprovada"] else SAIDA_PARIDADE_REPROVADA


if __name__ == "__main__":
    sys.exit(main())
