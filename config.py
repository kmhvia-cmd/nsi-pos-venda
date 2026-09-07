import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"

class Config:
    HOST  = os.getenv("HOST", "0.0.0.0")
    PORT  = int(os.getenv("PORT", 5055))
    DEBUG = os.getenv("DEBUG", "true").lower() == "true"

    DATA_DIR      = DATA_DIR
    LOTES_DIR     = DATA_DIR / "lotes"
    RESPOSTAS_DIR = DATA_DIR / "respostas"
    PDFS_DIR      = DATA_DIR / "pdfs"
    LOGS_DIR      = DATA_DIR / "logs"

    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL   = os.getenv("GROQ_MODEL", "llama3-8b-8192")

    WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
    WHATSAPP_URL   = os.getenv("WHATSAPP_URL", "")
    META_APP_SECRET = os.getenv("META_APP_SECRET", "")

    # ============================================================
    # Sprint B (B2.1) - persistencia operacional (ADR-008).
    # Nenhum destes valores e usado por nenhum modulo ainda - B2.1 apenas
    # prepara a leitura segura da configuracao. Conexao real, Alembic e
    # criacao de banco pertencem as subetapas B2.2/B2.3.
    # ============================================================

    # Marcador EXPLICITO e FECHADO de qual URL de banco esta em uso nesta
    # execucao - nunca inferido pela mera presenca de uma variavel. Valores
    # permitidos: "development" (usa exclusivamente DATABASE_URL) ou "test"
    # (usa exclusivamente TEST_DATABASE_URL). Nenhuma direcao tem fallback
    # para a outra URL - resolver_url_banco() falha explicitamente se a URL
    # exigida pelo ambiente ativo estiver ausente.
    NSI_DATABASE_ENV = os.getenv("NSI_DATABASE_ENV", "development")

    DATABASE_URL      = os.getenv("DATABASE_URL", "")
    TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "")

    # Unico nome de banco aceito quando NSI_DATABASE_ENV=test (Especificacao
    # Tecnica da Sprint B, protecao contra banco de producao). Qualquer outra
    # TEST_DATABASE_URL e recusada por resolver_url_banco().
    NOME_BANCO_TESTE_PERMITIDO = "nsi_test"

    # sslmode e a UNICA fonte de politica de SSL configurada pela aplicacao -
    # nunca decidido por um parametro sslmode embutido na propria URL (ver
    # verificar_conflito_sslmode). B2 nao decide a politica de producao
    # (pendente na Especificacao Tecnica, Secao 12) - apenas garante leitura
    # segura e sem ambiguidade. "prefer" e um padrao razoavel para
    # desenvolvimento local (mesma maquina); nunca deve ser assumido como
    # adequado para producao.
    DATABASE_SSLMODE = os.getenv("DATABASE_SSLMODE", "prefer")


_AMBIENTES_BANCO_VALIDOS = {"development", "test"}

# Mesmo conjunto de valores reconhecido pela libpq/psycopg para sslmode.
_SSLMODES_VALIDOS = {"disable", "allow", "prefer", "require", "verify-ca", "verify-full"}

# Chaves de uma DSN/URL de conexao que podem aparecer com seguranca em log ou
# mensagem diagnostica. Usuario, senha e qualquer outro parametro NUNCA entram
# nesta lista (ver mascarar_dsn).
_CHAVES_SEGURAS_PARA_LOG = {"host", "port", "dbname"}


class AmbienteBancoInvalido(RuntimeError):
    """NSI_DATABASE_ENV contem um valor fora de {"development", "test"}."""


class ConfiguracaoBancoAusente(RuntimeError):
    """A URL de banco exigida pelo ambiente ativo (NSI_DATABASE_ENV) nao esta
    definida. Nunca ha fallback silencioso de uma URL para a outra."""


class BancoDeTesteNaoPermitido(RuntimeError):
    """TEST_DATABASE_URL aponta para um banco diferente de
    Config.NOME_BANCO_TESTE_PERMITIDO. Protecao contra banco de producao
    (Especificacao Tecnica da Sprint B) - lista de permissao fechada, nunca
    uma comparacao frouxa entre DATABASE_URL e TEST_DATABASE_URL."""


class SSLModeInvalido(RuntimeError):
    """DATABASE_SSLMODE contem um valor fora do conjunto reconhecido pela
    libpq, ou a URL de conexao contradiz o sslmode configurado."""


class DSNInvalida(RuntimeError):
    """
    Uma URL/DSN de conexao fornecida nao pode ser interpretada pelo parser do
    psycopg. Mensagem DELIBERADAMENTE FIXA, sem interpolar a entrada recebida
    nem a excecao original do parser - uma DSN malformada pode conter, e na
    pratica ja demonstrou conter, usuario, senha, query string ou fragmento
    sensivel dentro da propria mensagem de erro do parser (ex.: erro de
    sintaxe de URI que ecoa a URI inteira, incluindo credenciais). Nunca usar
    'raise ... from <excecao original>' nem interpolar str(excecao original)
    aqui - isso reintroduziria exatamente o vazamento que esta excecao existe
    para impedir.
    """

    def __init__(self) -> None:
        super().__init__("DSN de conexao invalida ou nao pode ser interpretada")


def _parsear_dsn_com_seguranca(url: str) -> dict:
    """
    Parser UNICO e compartilhado de URL/DSN de conexao (psycopg.conninfo.
    conninfo_to_dict - nunca regex artesanal). Usado por toda funcao deste
    modulo que precisa interpretar uma DSN.

    Qualquer excecao do parser original e substituida por DSNInvalida(),
    NUNCA repassada como estava - a mensagem de erro do proprio parser pode
    ecoar a DSN inteira (usuario, senha, query string): confirmado
    empiricamente com uma URI IPv6 malformada, cuja excecao original
    continha a senha em texto puro.

    IMPORTANTE: 'raise DSNInvalida() from None' NAO basta - suprime apenas a
    EXIBICAO do encadeamento em traceback (__suppress_context__), mas a
    excecao original permanece acessivel via __context__, alcancavel por
    qualquer código que a inspecione (ex.: um logger que percorre a cadeia
    de causas). Por isso o 'raise' ocorre FORA do bloco except - uma flag
    e usada em vez de relancar de dentro do except - garantindo
    __context__ is None de fato, verificado por teste.
    """
    from psycopg.conninfo import conninfo_to_dict
    dsn_invalida = False
    info: dict = {}
    try:
        info = conninfo_to_dict(url)
    except Exception:
        dsn_invalida = True
    if dsn_invalida:
        raise DSNInvalida()
    return info


def _extrair_nome_banco(url: str) -> str:
    """
    Extrai o nome do banco de uma URL/DSN de conexao usando o parser
    compartilhado (_parsear_dsn_com_seguranca) - nunca regex artesanal.

    Importado/chamado sem dependencia de topo de modulo: a ausencia ou
    falha do driver de banco nunca deve quebrar a importacao de config.py
    inteiro - somente os caminhos que efetivamente usam banco sao afetados.
    """
    return _parsear_dsn_com_seguranca(url).get("dbname", "") or ""


def resolver_url_banco(ambiente: str | None = None) -> str:
    """
    Funcao UNICA de resolucao da URL de conexao (Especificacao Tecnica da
    Sprint B, Secao 4). Mecanismo explicito e fechado:

    - ambiente=None usa Config.NSI_DATABASE_ENV; um valor explicito pode ser
      passado (uso principalmente em teste desta propria funcao).
    - "development": usa EXCLUSIVAMENTE Config.DATABASE_URL. TEST_DATABASE_URL
      nunca e sequer consultada.
    - "test": usa EXCLUSIVAMENTE Config.TEST_DATABASE_URL. DATABASE_URL nunca
      e sequer consultada. O nome do banco resultante precisa ser exatamente
      Config.NOME_BANCO_TESTE_PERMITIDO.
    - Nenhum fallback de uma URL para a outra, em nenhuma direcao.
    - Falha imediata (ConfiguracaoBancoAusente) se a URL exigida pelo
      ambiente ativo estiver vazia - nunca um valor padrao silencioso.
    - Falha imediata (AmbienteBancoInvalido) se NSI_DATABASE_ENV nao for
      exatamente "development" ou "test".
    """
    ambiente_resolvido = ambiente if ambiente is not None else Config.NSI_DATABASE_ENV
    if ambiente_resolvido not in _AMBIENTES_BANCO_VALIDOS:
        raise AmbienteBancoInvalido(
            f"NSI_DATABASE_ENV={ambiente_resolvido!r} invalido - "
            f"valores permitidos: {sorted(_AMBIENTES_BANCO_VALIDOS)}"
        )

    if ambiente_resolvido == "development":
        url = Config.DATABASE_URL
        if not url:
            raise ConfiguracaoBancoAusente(
                "NSI_DATABASE_ENV=development exige DATABASE_URL definida - "
                "nenhum fallback para TEST_DATABASE_URL e permitido"
            )
        return url

    # ambiente_resolvido == "test"
    url = Config.TEST_DATABASE_URL
    if not url:
        raise ConfiguracaoBancoAusente(
            "NSI_DATABASE_ENV=test exige TEST_DATABASE_URL definida - "
            "nenhum fallback para DATABASE_URL e permitido"
        )
    nome_banco = _extrair_nome_banco(url)
    if nome_banco != Config.NOME_BANCO_TESTE_PERMITIDO:
        raise BancoDeTesteNaoPermitido(
            f"TEST_DATABASE_URL aponta para o banco {nome_banco!r}, mas o modo "
            f"de teste so aceita {Config.NOME_BANCO_TESTE_PERMITIDO!r}"
        )
    return url


def mascarar_dsn(url_ou_dsn: str) -> str:
    """
    Retorna uma representacao segura de uma URL/DSN de conexao, contendo
    somente host, porta e nome do banco - NUNCA usuario, senha, query string
    completa ou qualquer outro parametro. Usa o parser oficial do psycopg
    (psycopg.conninfo.conninfo_to_dict), nunca regex, para tratar
    corretamente senha com caracteres especiais e URL com percent-encoding.

    Nunca lanca excecao: uma DSN invalida produz um texto de erro seguro,
    nunca a tentativa de exibir o valor bruto recebido.
    """
    try:
        from psycopg.conninfo import conninfo_to_dict
        info = conninfo_to_dict(url_ou_dsn)
    except Exception:
        return "<dsn invalida - nao pode ser exibida>"
    seguro = {k: v for k, v in info.items() if k in _CHAVES_SEGURAS_PARA_LOG}
    return "host={host} port={port} dbname={dbname}".format(
        host=seguro.get("host", "?"),
        port=seguro.get("port", "?"),
        dbname=seguro.get("dbname", "?"),
    )


def validar_sslmode(valor: str) -> str:
    """
    Valida que 'valor' pertence ao conjunto de sslmode reconhecido pela
    libpq. Nao decide a politica de producao (Especificacao Tecnica da
    Sprint B, Secao 12 - ainda pendente) - garante somente que o valor
    configurado e sintaticamente valido.
    """
    if valor not in _SSLMODES_VALIDOS:
        raise SSLModeInvalido(
            f"DATABASE_SSLMODE={valor!r} invalido - "
            f"valores permitidos: {sorted(_SSLMODES_VALIDOS)}"
        )
    return valor


def verificar_conflito_sslmode(url: str, sslmode_configurado: str) -> None:
    """
    Impede ambiguidade entre Config.DATABASE_SSLMODE (fonte unica de
    verdade) e um eventual parametro sslmode ja embutido na propria
    URL/DSN de conexao. Se a URL trouxer um sslmode diferente do
    configurado, falha explicitamente em vez de deixar um dos dois
    vencer silenciosamente. Ausencia de sslmode na URL nunca e conflito.

    Qualquer excecao do parser e substituida por DSNInvalida(), com
    __context__ genuinamente limpo (ver _parsear_dsn_com_seguranca) - nunca
    repassada como estava, e nunca apenas suprimida via 'from None'.
    """
    info = _parsear_dsn_com_seguranca(url)
    sslmode_na_url = info.get("sslmode")
    if sslmode_na_url is not None and sslmode_na_url != sslmode_configurado:
        raise SSLModeInvalido(
            f"Conflito de sslmode: a URL de conexao especifica "
            f"sslmode={sslmode_na_url!r}, mas DATABASE_SSLMODE="
            f"{sslmode_configurado!r}. Defina o sslmode em uma unica fonte."
        )