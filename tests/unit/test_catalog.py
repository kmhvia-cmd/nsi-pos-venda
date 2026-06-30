"""
tests/unit/test_catalog.py

Testes do Catálogo NSI: carregamento e matcher determinístico.
Critérios de aceite — Plano de Implementação, Fase 3.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from catalog.loader import carregar_catalogo
from catalog.matcher import codigos_candidatos
from catalog.versioning import mesma_versao, versao_catalogo_corrente


def test_carrega_91_entradas():
    """Loader carrega exatamente 91 entradas."""
    catalogo = carregar_catalogo()
    assert catalogo.total_entradas == 91, f"Esperado 91, obtido {catalogo.total_entradas}"
    print("OK: test_carrega_91_entradas")


def test_todas_entradas_tem_campos_obrigatorios():
    """Todas as 91 entradas têm codigo, tipo, familia, areas preenchidos."""
    catalogo = carregar_catalogo()
    for entrada in catalogo.todas_entradas():
        assert entrada.codigo, f"codigo vazio em entrada"
        assert entrada.tipo in ("F", "D"), f"tipo inválido em {entrada.codigo}"
        assert entrada.familia, f"familia vazia em {entrada.codigo}"
        assert entrada.areas.primaria, f"area primaria vazia em {entrada.codigo}"
    print("OK: test_todas_entradas_tem_campos_obrigatorios")


def test_versao_catalogo_e_1_1():
    """versao_catalogo retornada é exatamente '1.1'."""
    catalogo = carregar_catalogo()
    assert versao_catalogo_corrente(catalogo) == "1.1"
    print("OK: test_versao_catalogo_e_1_1")


def test_matcher_encontra_atend_001_por_evidencia():
    """Evidência real do catálogo -> matcher encontra o código certo."""
    catalogo = carregar_catalogo()
    # Evidência 2 contém a gíria "demorou um tempão", cadastrada em ATEND-001.
    # (Evidência 1, "Esperei mais de vinte minutos...", é semanticamente
    # equivalente mas lexicalmente diferente dos termos cadastrados — caso
    # de Hermenêutica, resolvido pela IA na Camada Semântica, não pelo
    # matcher determinístico. Ver test_cobertura_completa_91_entradas, que
    # aceita match em QUALQUER uma das 2 evidências por entrada.)
    texto = "Demorou um tempão pra alguém me responder, viu."

    codigos = codigos_candidatos(texto, catalogo)

    assert "ATEND-001" in codigos, f"ATEND-001 não encontrado. Candidatos: {codigos}"
    print("OK: test_matcher_encontra_atend_001_por_evidencia")


def test_matcher_nao_quebra_com_texto_vazio():
    """Texto vazio não lança excecão, retorna conjunto vazio."""
    catalogo = carregar_catalogo()
    codigos = codigos_candidatos("", catalogo)
    assert codigos == set()
    print("OK: test_matcher_nao_quebra_com_texto_vazio")


def test_cobertura_lexical_do_matcher_determinístico():
    """
    Critério de aceite da Fase 3 (ajustado após execução real contra o
    catálogo): o matcher determinístico cobre por correspondência LEXICAL
    direta (substring de sinônimo/gíria/regionalismo/subcategoria).

    84 das 91 entradas (92%) têm ao menos uma das 2 evidências-exemplo
    cobertas por correspondência lexical pura.

    As 7 entradas restantes (ATEND-003, ATEND-004, PROD-002, ENTR-002,
    POSV-003, ESTR-001, MKT-004) têm evidências que são equivalentes
    SEMANTICAMENTE ao termo cadastrado, mas usam redação diferente
    (paráfrase, ordem de palavras distinta, inflexão verbal diferente).

    Isso NÃO é falha do matcher — é o limite arquitetural correto entre
    Camada Determinística e Motor Semântico (IA), confirmado e aprovado
    explicitamente: "o matcher determinístico não deve tentar resolver
    equivalência semântica... toda equivalência de significado, paráfrase,
    inferência, hermenêutica, semântica e pragmática pertence exclusivamente
    ao Motor Semântico (IA)." Essas 7 entradas serão cobertas pela Camada
    Semântica via IA (Fase 5), não pelo matcher.

    Este teste documenta e fixa esse comportamento esperado — se a
    cobertura lexical cair abaixo de 84/91 em uma recalibração futura do
    catálogo, este teste falha e sinaliza regressão real. Se subir (por
    adição de mais sinônimos/gírias ao catálogo), o teste deve ser
    atualizado para refletir o novo número.
    """
    import json

    catalogo = carregar_catalogo()
    caminho_json = Path(__file__).resolve().parents[2] / "catalog" / "catalogo_v1.1.json"
    dados_brutos = json.loads(caminho_json.read_text(encoding="utf-8"))

    excecoes_esperadas = {
        "ATEND-003", "ATEND-004", "PROD-002", "ENTR-002",
        "POSV-003", "ESTR-001", "MKT-004",
    }

    sem_cobertura_lexical = []
    for entrada_bruta in dados_brutos["entradas"]:
        codigo = entrada_bruta["codigo"]
        evidencias = entrada_bruta["evidencias_exemplo"]

        encontrado_em_alguma = any(
            codigo in codigos_candidatos(evidencia, catalogo) for evidencia in evidencias
        )
        if not encontrado_em_alguma:
            sem_cobertura_lexical.append(codigo)

    sem_cobertura_lexical_set = set(sem_cobertura_lexical)

    # As exceções encontradas devem ser EXATAMENTE as 7 já documentadas e
    # aprovadas — nem mais (regressão real), nem menos (sem reabrir o teste).
    assert sem_cobertura_lexical_set == excecoes_esperadas, (
        f"Conjunto de exceções mudou. Esperado: {excecoes_esperadas}, "
        f"obtido: {sem_cobertura_lexical_set}. "
        f"Se a diferença for por melhoria real do catálogo, atualize "
        f"`excecoes_esperadas` neste teste."
    )

    cobertura = 91 - len(sem_cobertura_lexical_set)
    print(
        f"OK: test_cobertura_lexical_do_matcher_determinístico "
        f"({cobertura}/91 = {cobertura/91*100:.1f}% via matcher puro; "
        f"7/91 esperadas para resolução via IA na Fase 5)"
    )


if __name__ == "__main__":
    test_carrega_91_entradas()
    test_todas_entradas_tem_campos_obrigatorios()
    test_versao_catalogo_e_1_1()
    test_matcher_encontra_atend_001_por_evidencia()
    test_matcher_nao_quebra_com_texto_vazio()
    test_cobertura_lexical_do_matcher_determinístico()
    print("\nTodos os testes da Fase 3 (Catálogo) passaram.")
