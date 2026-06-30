"""
processors/linguistic_processor.py

Camada Linguística do Motor NSI — PARTE DETERMINÍSTICA.
Contrato Oficial do Motor NSI v3.1, Seção 3.

Esta implementação cobre apenas os sinais de superfície que NÃO dependem
de IA (Especificação Técnica v1, Seção 7.2): emojis, pontuação intensificada,
caixa alta, abreviações, regionalismo/gíria de uso geral, repetição de ênfase.

Pragmática, Hermenêutica e Ironia identificável (Contrato Seção 3.1) exigem
interpretação contextual e ficam para a Fase 7 (Plano de Implementação),
implementadas em conjunto com a Camada de Experiência Humana, via IA.

`formalidade` e `marca_regional` são calculáveis nesta fase porque dependem
de léxico (dicionário), não de interpretação de contexto.

Mede a FORMA da fala — nunca o tema (isso é responsabilidade da Camada
Semântica, Contrato Seção 4).
"""

from __future__ import annotations

import re
import unicodedata
from statistics import mean

from models.output_models import (
    IroniaDetectada,
    MarcadoresDetectados,
    ResultadoLinguistico,
    ResultadoLinguisticoAgregado,
)


# ---------------------------------------------------------------------------
# Dicionários de calibração — ponto de partida, cresce com uso real
# (mesmo princípio do Catálogo NSI, Contrato Seção 4.1: calibração contínua,
# sem exigir nova versão do contrato).
# ---------------------------------------------------------------------------

# Emojis frequentes e sua polaridade/intensidade de superfície.
# Não confundir com a polaridade SEMÂNTICA (Contrato Seção 4) — aqui é só
# o sinal de forma que alimenta intensidade_emocional e polaridade_linguistica.
_EMOJIS_POLARIDADE: dict[str, tuple[str, int]] = {
    "😍": ("positiva", 95), "🔥": ("positiva", 90), "👏": ("positiva", 85),
    "❤️": ("positiva", 90), "🙏": ("positiva", 70), "😊": ("positiva", 75),
    "👍": ("positiva", 70), "🎉": ("positiva", 85), "✅": ("positiva", 60),
    "💛": ("positiva", 70), "🤩": ("positiva", 90), "😄": ("positiva", 75),
    "😡": ("negativa", 90), "😞": ("negativa", 70), "👎": ("negativa", 75),
    "😤": ("negativa", 70), "😩": ("negativa", 75), "😠": ("negativa", 85),
    "😕": ("negativa", 55), "😢": ("negativa", 70), "🙄": ("negativa", 55),
    "😴": ("negativa", 45), "❌": ("negativa", 65), "💔": ("negativa", 80),
}

# Abreviações de uso nacional informal — sinal de informalidade (formalidade baixa)
_ABREVIACOES = {
    "vlw", "blz", "tb", "tbm", "vc", "vcs", "pq", "q", "td", "mto", "msm",
    "obg", "qq", "n", "naum", "pra", "pro", "cmg", "ctg",
}

# Regionalismos/gírias de uso geral, capturados como marca de informalidade
# e regionalidade na FORMA — não atrelados a uma família semântica específica
# nesta camada (a ligação a família/subcategoria é responsabilidade do
# catalog/matcher.py na Fase 3 e da Camada Semântica).
_REGIONALISMOS_GIRIAS: dict[str, str] = {
    "vaqueta": "Nordeste", "balaio": "interior SP/MG", "leu-leu": "RJ",
    "topete": "Nordeste", "bobeira": "uso nacional informal",
    "boiando": "uso nacional informal", "ligeirinho": "Norte/Nordeste",
    "da hora": "uso nacional informal", "massa": "Nordeste",
    "animal": "uso nacional informal", "brabo": "uso nacional informal",
    "top": "uso nacional informal", "tri": "Sul", "show de bola": "uso nacional informal",
    "sopa": "uso nacional informal", "gente fina": "uso nacional informal",
    "cria": "uso nacional informal", "rim": "uso nacional informal",
}

_TETO_TAMANHO_ENGAJAMENTO = 150  # caracteres — mesmo princípio de saturação do math_processor


def _normalizar(texto: str) -> str:
    """Remove acentos e baixa a caixa, para matching de léxico."""
    sem_acento = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in sem_acento if not unicodedata.combining(c))


def _detectar_emojis(texto: str) -> list[dict]:
    encontrados = []
    for emoji, (polaridade, intensidade) in _EMOJIS_POLARIDADE.items():
        if emoji in texto:
            encontrados.append(
                {"simbolo": emoji, "polaridade": polaridade, "intensidade": intensidade}
            )
    return encontrados


def _detectar_girias_regionalismos(texto: str) -> list[dict]:
    texto_norm = _normalizar(texto)
    encontrados = []
    for termo, regiao in _REGIONALISMOS_GIRIAS.items():
        termo_norm = _normalizar(termo)
        if re.search(rf"\b{re.escape(termo_norm)}\b", texto_norm):
            encontrados.append({"termo": termo, "regiao": regiao})
    return encontrados


def _detectar_abreviacoes(texto: str) -> list[dict]:
    palavras = re.findall(r"\b\w+\b", texto.lower())
    encontradas = [p for p in palavras if p in _ABREVIACOES]
    return [{"termo": p} for p in encontradas]


def _pontuacao_intensificada(texto: str) -> bool:
    """Detecta '!!!', '???', '!?' ou sequências de 3+ pontuações repetidas."""
    return bool(re.search(r"[!?]{2,}", texto))


def _caixa_alta(texto: str) -> bool:
    """
    Detecta se há ao menos uma palavra inteira em caixa alta com 3+ letras
    (evita falso positivo em siglas curtas como "OK", "PIX" isoladas de 2 letras).
    """
    palavras = re.findall(r"\b[A-ZÀ-Ú]{3,}\b", texto)
    # Excecão: não conta se a palavra inteira do texto já é tudo maiúscula por padrão de sigla comum
    return len(palavras) > 0


def _repeticao_enfase(texto: str) -> bool:
    """Detecta repetição de letras (ex: 'muitooo') ou de palavra adjacente."""
    if re.search(r"(\w)\1{2,}", texto):
        return True
    palavras = texto.lower().split()
    for i in range(len(palavras) - 1):
        if palavras[i] == palavras[i + 1]:
            return True
    return False


def _calcular_formalidade(texto: str, abreviacoes: list[dict], girias: list[dict]) -> float:
    """
    0 = totalmente informal/gírias, 100 = totalmente formal.
    Penaliza por abreviação e gíria detectadas; texto limpo sem nenhuma
    comeca em 100 e só desce.
    """
    penalidade = len(abreviacoes) * 15 + len(girias) * 10
    return round(max(100.0 - penalidade, 0.0), 1)


def _calcular_marca_regional(girias: list[dict]) -> float:
    """
    0-100, intensidade de regionalismo detectado no léxico.
    Cada termo regional/gíria encontrado soma, com saturação em 100.
    """
    if not girias:
        return 0.0
    return round(min(len(girias) * 35.0, 100.0), 1)


def _calcular_intensidade_emocional(
    pontuacao_intensa: bool, caixa_alta: bool, emojis: list[dict], repeticao: bool
) -> float:
    """0-100, combinando pontuação + caixa alta + emoji + repetição."""
    pontos = 0.0
    if pontuacao_intensa:
        pontos += 25
    if caixa_alta:
        pontos += 25
    if emojis:
        pontos += min(mean(e["intensidade"] for e in emojis) * 0.4, 40)
    if repeticao:
        pontos += 10
    return round(min(pontos, 100.0), 1)


def _calcular_polaridade_linguistica(emojis: list[dict]) -> float:
    """
    -100 a +100. Sinal de superfície apenas (emojis de forma) — a polaridade
    semântica fina fica na Camada Semântica/Experiência Humana (via IA).
    Sem emoji detectado, retorna 0 (neutro) — esta camada não infere
    polaridade do texto puro sem marcador de forma.
    """
    if not emojis:
        return 0.0
    positivos = [e["intensidade"] for e in emojis if e["polaridade"] == "positiva"]
    negativos = [e["intensidade"] for e in emojis if e["polaridade"] == "negativa"]
    saldo = (sum(positivos) - sum(negativos)) / max(len(emojis), 1)
    return round(max(min(saldo, 100.0), -100.0), 1)


def _calcular_engajamento_linguistico(texto: str) -> float:
    """
    0-100, combinando tamanho da resposta (com saturação) — a parte de
    "tempo de resposta" do engajamento é responsabilidade de quem orquestra
    o pipeline (engine/pipeline.py), que tem acesso aos timestamps; este
    processor só vê o texto.
    """
    tamanho = len(texto.strip())
    return round(min((tamanho / _TETO_TAMANHO_ENGAJAMENTO) * 100, 100.0), 1)


def processar_linguistica_resposta(texto: str) -> ResultadoLinguistico:
    """
    Calcula a saída da Camada Linguística (parte determinística) para
    uma resposta individual.

    `ironia_detectada` é sempre {presente: False, confianca: 0.0} nesta
    fase — a detecção real de ironia exige IA (Contrato Seção 3.1,
    Plano de Implementação Fase 7). Marcado aqui como placeholder
    explícito, não como afirmação de que não há ironia.
    """
    emojis = _detectar_emojis(texto)
    girias = _detectar_girias_regionalismos(texto)
    abreviacoes = _detectar_abreviacoes(texto)
    pontuacao_intensa = _pontuacao_intensificada(texto)
    caixa_alta = _caixa_alta(texto)
    repeticao = _repeticao_enfase(texto)

    marcadores = MarcadoresDetectados(
        emojis=emojis,
        girias_regionalismos=girias,
        abreviacoes=abreviacoes,
        pontuacao_intensificada=pontuacao_intensa,
        caixa_alta=caixa_alta,
        repeticao_enfase=repeticao,
    )

    return ResultadoLinguistico(
        intensidade_emocional=_calcular_intensidade_emocional(
            pontuacao_intensa, caixa_alta, emojis, repeticao
        ),
        polaridade_linguistica=_calcular_polaridade_linguistica(emojis),
        engajamento_linguistico=_calcular_engajamento_linguistico(texto),
        formalidade=_calcular_formalidade(texto, abreviacoes, girias),
        marca_regional=_calcular_marca_regional(girias),
        ironia_detectada=IroniaDetectada(presente=False, confianca=0.0),
        marcadores_detectados=marcadores,
    )


def agregar_linguistica_lote(
    resultados: list[ResultadoLinguistico],
) -> ResultadoLinguisticoAgregado:
    """Agrega a Camada Linguística de todas as respostas no nível do lote."""
    if not resultados:
        return ResultadoLinguisticoAgregado(
            intensidade_emocional_media=0.0,
            polaridade_linguistica_media=0.0,
            engajamento_linguistico_medio=0.0,
            formalidade_media=0.0,
            marca_regional_media=0.0,
        )

    return ResultadoLinguisticoAgregado(
        intensidade_emocional_media=round(
            mean(r.intensidade_emocional for r in resultados), 1
        ),
        polaridade_linguistica_media=round(
            mean(r.polaridade_linguistica for r in resultados), 1
        ),
        engajamento_linguistico_medio=round(
            mean(r.engajamento_linguistico for r in resultados), 1
        ),
        formalidade_media=round(mean(r.formalidade for r in resultados), 1),
        marca_regional_media=round(mean(r.marca_regional for r in resultados), 1),
    )
