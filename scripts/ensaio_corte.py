# -*- coding: utf-8 -*-
"""
NSI — scripts/ensaio_corte.py
Responsabilidade: linha de comando das ferramentas do ensaio de corte da
B6 (SPRINT-B6-ESPECIFICACAO-ENSAIO-DE-CORTE.md, Secoes 16, 17, 22 a 24, 28
e 56). A logica pura esta em core/ensaio_corte.py e
core/ensaio_sintetico.py; aqui ficam a area de ensaio, a gravacao das
evidencias e a conexao da auditoria.

Uso - sempre com a variavel NSI_ENSAIO_DIR definida (decisao D5: nao existe
valor padrao; ausente, todo comando falha):

    python scripts/ensaio_corte.py preparar        --ensaio-id <id>
    python scripts/ensaio_corte.py gerar-sintetico --ensaio-id <id> [--fuso <IANA>]
    python scripts/ensaio_corte.py inventario      --ensaio-id <id> --rotulo <I0|I1|...> --diretorio <dir>
    python scripts/ensaio_corte.py comparar        --ensaio-id <id> --a <rotulo> --b <rotulo>
    python scripts/ensaio_corte.py copiar          --ensaio-id <id> --instalacao <dir> --referencia <rotulo>
    python scripts/ensaio_corte.py levantamento    --ensaio-id <id>
    python scripts/ensaio_corte.py auditar         --ensaio-id <id> [--fuso <IANA>]
    python scripts/ensaio_corte.py indice          --ensaio-id <id>

A importacao em si e do executor (scripts/importar_legado.py, com
NSI_DATABASE_ENV=ensaio). O backup integral usa a ferramenta nativa do
sistema operacional (Secao 22); o seu teste de restauracao e um
'inventario' do diretorio restaurado seguido de 'comparar'.

Cada comando grava uma evidencia em <area>/<ensaio_id>/evidencias - nunca
sobrescrita - e imprime o mesmo conteudo. Nenhuma saida contem valor
pessoal nem nome de arquivo fora do escopo.

AUDITORIA: conecta como o migrator de ensaio (ENSAIO_DATABASE_URL), com
gate de identidade (banco nsi_ensaio, servidor local, porta 5432,
session_user = nsi_ensaio_migrator), em transacao READ ONLY sob SET LOCAL
ROLE nsi_eventos_owner. Le o snapshot somente para contar e para amostrar,
EM MEMORIA, os valores usados na varredura de privacidade das evidencias.
Nenhum comando deste script conecta a nsi_dev.

Codigos de saida: 0 sucesso; 1 verificacao reprovada; 2 recusado.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

RAIZ_DO_PROJETO = Path(__file__).resolve().parent.parent
if str(RAIZ_DO_PROJETO) not in sys.path:
    sys.path.insert(0, str(RAIZ_DO_PROJETO))

import psycopg  # noqa: E402

from config import Config, resolver_url_banco  # noqa: E402
from core import ensaio_corte as ec  # noqa: E402
from core import ensaio_sintetico as es  # noqa: E402

CAMINHO_DA_AUDITORIA = RAIZ_DO_PROJETO / "scripts" / "postgres_local" / "auditoria_b6_ensaio.sql"
DIRETORIO_DAS_FIXTURES = RAIZ_DO_PROJETO / "tests" / "fixtures" / "legado"

BANCO_DE_ENSAIO = "nsi_ensaio"
MIGRATOR_DE_ENSAIO = "nsi_ensaio_migrator"
PAPEIS_COM_ACESSO_AO_ENSAIO = (MIGRATOR_DE_ENSAIO, "nsi_importacao")
PORTA_PERMITIDA = 5432
ENDERECOS_LOCAIS = ("127.0.0.1", "::1")
MARCADOR_DE_CONSULTA = "-- @consulta "
AMOSTRA_DE_VALORES_PESSOAIS = 500
# Decisao D10 (Secao 49): pelo menos 20 lotes por geracao, alem das fixtures.
LOTES_EXTRAS_DA_RODADA_S = 20

SAIDA_SUCESSO = 0
SAIDA_REPROVADA = 1
SAIDA_RECUSADA = 2


class EnsaioRecusado(RuntimeError):
    """O comando nao pode prosseguir. Mensagem fixa, sem caminho nem DSN."""


def area_de_ensaio() -> Path:
    """Area de ensaio da variavel NSI_ENSAIO_DIR - sem valor padrao."""
    return ec.validar_area_de_ensaio(Config.NSI_ENSAIO_DIR, Config.DATA_DIR, RAIZ_DO_PROJETO)


def _evidencias(ensaio_id: str) -> Path:
    diretorio = ec.diretorio_da_rodada(area_de_ensaio(), ensaio_id, ec.SUBDIRETORIO_EVIDENCIAS)
    if not diretorio.is_dir():
        raise EnsaioRecusado("rodada inexistente - execute 'preparar' antes")
    return diretorio


def _ler_evidencia(ensaio_id: str, nome: str) -> dict:
    caminho = _evidencias(ensaio_id) / nome
    if not caminho.is_file():
        raise EnsaioRecusado("evidencia de referencia inexistente")
    return json.loads(caminho.read_bytes())


# ============================================================
# Auditoria (C7)
# ============================================================

def ler_consultas(caminho=CAMINHO_DA_AUDITORIA) -> dict:
    """Le auditoria_b6_ensaio.sql e devolve {nome: consulta}. Recusa o
    arquivo inteiro se alguma consulta nao for um unico SELECT."""
    consultas, nome, linhas = {}, None, []

    def fechar() -> None:
        if nome is not None:
            sql = "\n".join(l for l in linhas if not l.strip().startswith("--")).strip().rstrip(";").strip()
            if not sql.upper().startswith("SELECT") or ";" in sql or nome in consultas:
                raise EnsaioRecusado("arquivo de auditoria invalido - cada consulta precisa ser um unico SELECT")
            consultas[nome] = sql

    for linha in Path(caminho).read_text(encoding="utf-8").splitlines():
        if linha.startswith(MARCADOR_DE_CONSULTA):
            fechar()
            nome, linhas = linha[len(MARCADOR_DE_CONSULTA):].strip(), []
        elif nome is not None:
            linhas.append(linha)
    fechar()
    if not consultas:
        raise EnsaioRecusado("arquivo de auditoria sem consultas")
    return consultas


def ler_revisao(conexao):
    """Revisao do Alembic, lida COMO O MIGRATOR - antes de assumir
    nsi_eventos_owner, que nao tem privilegio na tabela de controle."""
    linha = conexao.execute("SELECT version_num FROM nsi_operacional.alembic_version").fetchone()
    return linha[0] if linha else None


def executar_consultas(conexao, revisao, consultas=None) -> dict:
    """Executa as consultas de auditoria na transacao corrente da conexao,
    ja sob nsi_eventos_owner. 'revisao' vem de ler_revisao()."""
    resultado = {}
    for nome, sql in (consultas or ler_consultas()).items():
        resultado[nome] = conexao.execute(sql).fetchone()[0]
    resultado["a_revisao"]["revisao"] = revisao
    return resultado


def amostrar_valores_pessoais(conexao, limite: int = AMOSTRA_DE_VALORES_PESSOAIS) -> list:
    """Amostra, EM MEMORIA, valores pessoais do snapshot para a varredura de
    privacidade das evidencias. O retorno nunca e gravado nem impresso."""
    linhas = conexao.execute(
        """
        SELECT DISTINCT v.valor
          FROM nsi_operacional.registros_legado AS r
         CROSS JOIN LATERAL (VALUES (r.conteudo_bruto ->> 'nome'), (r.conteudo_bruto ->> 'telefone'),
                                    (r.conteudo_bruto ->> 'nome_bruto'), (r.conteudo_bruto ->> 'whatsapp_bruto'))
               AS v(valor)
         WHERE v.valor IS NOT NULL AND length(btrim(v.valor)) >= 4
         LIMIT %s
        """, (limite,)).fetchall()
    return [linha[0] for linha in linhas]


def validar_identidade_da_auditoria(banco, endereco_do_servidor, porta, usuario_da_sessao) -> None:
    """Gate da auditoria: so o migrator de ensaio, so em nsi_ensaio, so no
    servidor local. Mensagens fixas."""
    if banco != BANCO_DE_ENSAIO:
        raise EnsaioRecusado("banco nao permitido - esperado nsi_ensaio")
    if endereco_do_servidor is not None and str(endereco_do_servidor).split("/")[0] not in ENDERECOS_LOCAIS:
        raise EnsaioRecusado("servidor remoto - a auditoria e exclusiva do PostgreSQL local")
    if porta != PORTA_PERMITIDA:
        raise EnsaioRecusado("porta nao permitida - esperada 5432")
    if usuario_da_sessao != MIGRATOR_DE_ENSAIO:
        raise EnsaioRecusado("usuario da sessao nao permitido - esperado nsi_ensaio_migrator")


def _impressao_do_catalogo_de_teste():
    """Impressao digital do catalogo de nsi_test, para comparar com a do
    ensaio. Leitura de catalogo, somente leitura. Sem TEST_DATABASE_URL, a
    comparacao nao e feita - e a auditoria registra isso como divergencia."""
    try:
        url = resolver_url_banco("test")
        with psycopg.connect(url) as conexao:
            conexao.read_only = True
            impressao = conexao.execute(ler_consultas()["a_catalogo"]).fetchone()[0]["impressao_digital"]
            conexao.rollback()
        return impressao
    except Exception:
        return None


def auditar_ensaio(ensaio_id: str, fuso) -> dict:
    """Partes A a D da auditoria (Secao 28), sobre o banco de ensaio."""
    evidencias = _evidencias(ensaio_id)
    conexao = None
    try:
        conexao = psycopg.connect(resolver_url_banco("ensaio"))
    except Exception:
        pass
    if conexao is None:
        raise EnsaioRecusado("nao foi possivel conectar como o migrator de ensaio em nsi_ensaio")
    try:
        conexao.read_only = True
        validar_identidade_da_auditoria(*conexao.execute(
            "SELECT current_database(), inet_server_addr()::text, inet_server_port(), session_user").fetchone())
        revisao = ler_revisao(conexao)
        conexao.execute("SET LOCAL ROLE nsi_eventos_owner")
        resultado = executar_consultas(conexao, revisao)
        valores = amostrar_valores_pessoais(conexao)
    finally:
        conexao.rollback()
        conexao.close()

    avaliacao = ec.avaliar_auditoria(
        resultado, BANCO_DE_ENSAIO, PAPEIS_COM_ACESSO_AO_ENSAIO, "nsi_importacao", fuso,
        _impressao_do_catalogo_de_teste())

    quantificacao = {nome: valor for nome, valor in resultado.items() if nome.startswith("c_")}
    obtido = resultado["b_arquivos"]
    relatorio = {
        "ensaio_id": ensaio_id,
        "aprovada": avaliacao["aprovada"],
        "divergencias": avaliacao["divergencias"],
        "integridade": {nome: valor for nome, valor in resultado.items() if nome.startswith("a_")},
        "invariantes": {nome: valor for nome, valor in resultado.items()
                        if nome.startswith("b_") and nome != "b_arquivos"},
        "lotes_recusados": [a for a in obtido if a["destino"] == "recusado"],
    }
    caminho_do_esperado = evidencias / "esperado.json"
    if caminho_do_esperado.is_file():
        # Verificacao V5 (Rodada S): destinos obtidos contra os declarados.
        relatorio["v5_destinos_esperados"] = es.comparar_com_esperado(
            json.loads(caminho_do_esperado.read_bytes())["lotes"], obtido)
        relatorio["aprovada"] = relatorio["aprovada"] and relatorio["v5_destinos_esperados"]["confere"]

    ec.gravar_evidencia(evidencias, "E10_auditoria.json", relatorio)
    ec.gravar_evidencia(evidencias, "E11_quantificacao.json", quantificacao)

    # Parte D - privacidade: depois de gravar, para incluir as proprias saidas.
    varredura = ec.varrer_evidencias(evidencias, valores)
    ec.gravar_evidencia(evidencias, "E10_privacidade.json", varredura)
    relatorio["privacidade"] = varredura
    relatorio["aprovada"] = relatorio["aprovada"] and varredura["sem_valor_pessoal"]
    return relatorio


# ============================================================
# Comandos
# ============================================================

def _preparar(argumentos) -> tuple:
    base = ec.preparar_rodada(area_de_ensaio(), argumentos.ensaio_id)
    return {"ensaio_id": argumentos.ensaio_id, "subdiretorios": sorted(p.name for p in base.iterdir())}, True


def _gerar_sintetico(argumentos) -> tuple:
    evidencias = _evidencias(argumentos.ensaio_id)
    destino = ec.diretorio_da_rodada(area_de_ensaio(), argumentos.ensaio_id) / es.SUBDIRETORIO_DA_INSTALACAO_SINTETICA
    destino.mkdir()
    esperado = es.gerar_instalacao_sintetica(
        destino, DIRETORIO_DAS_FIXTURES, argumentos.fuso, argumentos.semente, argumentos.lotes_extras)
    conteudo = {"fuso_declarado": argumentos.fuso, "semente": argumentos.semente,
                "resumo": es.resumir_esperado(esperado), "lotes": esperado}
    ec.gravar_evidencia(evidencias, "esperado.json", conteudo)
    return {"instalacao_sintetica": es.SUBDIRETORIO_DA_INSTALACAO_SINTETICA, **conteudo["resumo"]}, True


def _inventario(argumentos) -> tuple:
    evidencias = _evidencias(argumentos.ensaio_id)
    ec.validar_ensaio_id(argumentos.rotulo)
    resumo = ec.resumo_do_inventario(ec.inventariar(argumentos.diretorio))
    ec.gravar_evidencia(evidencias, f"inventario_{argumentos.rotulo}.json", resumo)
    return {"rotulo": argumentos.rotulo, "escopo": resumo["escopo"], "fora_do_escopo": resumo["fora_do_escopo"]}, True


def _comparar(argumentos) -> tuple:
    evidencias = _evidencias(argumentos.ensaio_id)
    a = ec.inventario_do_resumo(_ler_evidencia(argumentos.ensaio_id, f"inventario_{ec.validar_ensaio_id(argumentos.a)}.json"))
    b = ec.inventario_do_resumo(_ler_evidencia(argumentos.ensaio_id, f"inventario_{ec.validar_ensaio_id(argumentos.b)}.json"))
    comparacao = {"a": argumentos.a, "b": argumentos.b, **ec.comparar_inventarios(a, b)}
    ec.gravar_evidencia(evidencias, f"comparacao_{argumentos.a}_{argumentos.b}.json", comparacao)
    return comparacao, comparacao["identicos"]


def _copiar(argumentos) -> tuple:
    evidencias = _evidencias(argumentos.ensaio_id)
    referencia = ec.inventario_do_resumo(
        _ler_evidencia(argumentos.ensaio_id, f"inventario_{ec.validar_ensaio_id(argumentos.referencia)}.json"))
    destino = ec.diretorio_da_rodada(area_de_ensaio(), argumentos.ensaio_id, ec.SUBDIRETORIO_ORIGEM)
    try:
        resultado = ec.copiar_escopo(argumentos.instalacao, destino, referencia)
    except ec.CopiaDivergente:
        resultado = {"confere": False}
    resultado["referencia"] = argumentos.referencia
    ec.gravar_evidencia(evidencias, "E6_copia_congelada.json", resultado)
    return resultado, resultado["confere"]


def _levantamento(argumentos) -> tuple:
    evidencias = _evidencias(argumentos.ensaio_id)
    origem = ec.diretorio_da_rodada(area_de_ensaio(), argumentos.ensaio_id, ec.SUBDIRETORIO_ORIGEM)
    levantamento = ec.levantar_estrutura(origem)
    ec.gravar_evidencia(evidencias, "E7_levantamento_estrutural.json", levantamento)
    resumo = {chave: valor for chave, valor in levantamento.items() if chave != "detalhe"}
    return resumo, True


def _auditar(argumentos) -> tuple:
    relatorio = auditar_ensaio(argumentos.ensaio_id, argumentos.fuso)
    return relatorio, relatorio["aprovada"]


def _indice(argumentos) -> tuple:
    return ec.fechar_indice(_evidencias(argumentos.ensaio_id)), True


def _argumentos(argv) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="ensaio_corte", description="Ferramentas do ensaio de corte da B6.")
    comandos = parser.add_subparsers(dest="comando", required=True)

    def comando(nome, funcao, ajuda):
        sub = comandos.add_parser(nome, help=ajuda)
        sub.add_argument("--ensaio-id", required=True, dest="ensaio_id")
        sub.set_defaults(funcao=funcao)
        return sub

    comando("preparar", _preparar, "cria a estrutura fixa de uma rodada")
    sub = comando("gerar-sintetico", _gerar_sintetico, "gera a instalacao sintetica da Rodada S e os destinos esperados")
    sub.add_argument("--fuso", default=None)
    sub.add_argument("--semente", type=int, default=20260203)
    sub.add_argument("--lotes-extras", type=int, default=LOTES_EXTRAS_DA_RODADA_S, dest="lotes_extras")
    sub = comando("inventario", _inventario, "inventaria um diretorio")
    sub.add_argument("--diretorio", required=True)
    sub.add_argument("--rotulo", required=True)
    sub = comando("comparar", _comparar, "compara dois inventarios gravados")
    sub.add_argument("--a", required=True)
    sub.add_argument("--b", required=True)
    sub = comando("copiar", _copiar, "copia congelada do escopo para a origem da rodada")
    sub.add_argument("--instalacao", required=True)
    sub.add_argument("--referencia", required=True)
    comando("levantamento", _levantamento, "levantamento estrutural da origem da rodada")
    sub = comando("auditar", _auditar, "auditoria e quantificacao do banco de ensaio")
    sub.add_argument("--fuso", default=None)
    comando("indice", _indice, "fecha o indice das evidencias da rodada")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    argumentos = _argumentos(argv)
    inicio = time.monotonic()
    try:
        saida, aprovado = argumentos.funcao(argumentos)
    except (EnsaioRecusado, ec.AreaDeEnsaioInvalida) as exc:
        print(json.dumps({"comando": argumentos.comando, "executado": False, "motivo": str(exc)},
                         ensure_ascii=False, sort_keys=True, indent=2))
        return SAIDA_RECUSADA
    except Exception as exc:
        # Mensagem fixa: a excecao original pode trazer caminho, DSN ou conteudo.
        print(json.dumps({"comando": argumentos.comando, "executado": False, "motivo": "falha_inesperada",
                          "tipo": type(exc).__name__}, ensure_ascii=False, sort_keys=True, indent=2))
        return SAIDA_RECUSADA
    print(json.dumps({"comando": argumentos.comando, "executado": True,
                      "duracao_segundos": round(time.monotonic() - inicio, 3), **saida},
                     ensure_ascii=False, sort_keys=True, indent=2))
    return SAIDA_SUCESSO if aprovado else SAIDA_REPROVADA


if __name__ == "__main__":
    sys.exit(main())
