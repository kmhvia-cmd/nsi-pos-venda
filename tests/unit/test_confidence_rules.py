"""
tests/unit/test_confidence_rules.py

Testes das Regras de Confiança (limite de 5 categorias + desempate).
Critérios de aceite — Plano de Implementação, Fase 6.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from confidence.confidence_rules import (
    LIMITE_CATEGORIAS_POR_RESPOSTA,
    ordenar_e_aplicar_limite,
)
from models.output_models import CategoriaDetectada


def _categoria(
    codigo: str,
    confianca: float,
    intensidade_semantica: float = 50.0,
    tipo: str = "dor",
) -> CategoriaDetectada:
    return CategoriaDetectada(
        tipo=tipo,
        codigo_catalogo=codigo,
        familia=codigo.split("-")[0],
        subcategoria="subcategoria teste",
        nicho=None,
        area_responsavel="Atendimento",
        confianca=confianca,
        intensidade_semantica=intensidade_semantica,
    )


def test_limite_de_5_com_8_candidatos():
    """Entrada com 8 candidatos, confianças variadas -> saída tem exatamente 5, as de maior confianca."""
    candidatos = [
        _categoria("A-001", 90.0),
        _categoria("A-002", 85.0),
        _categoria("A-003", 95.0),
        _categoria("A-004", 60.0),
        _categoria("A-005", 70.0),
        _categoria("A-006", 99.0),
        _categoria("A-007", 55.0),
        _categoria("A-008", 80.0),
    ]

    resultado = ordenar_e_aplicar_limite(candidatos)

    assert len(resultado.mantidas) == 5
    assert len(resultado.excedentes) == 3
    codigos_mantidos = [c.codigo_catalogo for c in resultado.mantidas]
    assert codigos_mantidos == ["A-006", "A-003", "A-001", "A-002", "A-008"]
    print("OK: test_limite_de_5_com_8_candidatos")


def test_3_candidatos_nao_corta():
    """Entrada com 3 candidatos -> saída retorna os 3, sem alteração."""
    candidatos = [_categoria("A-001", 90.0), _categoria("A-002", 50.0), _categoria("A-003", 70.0)]

    resultado = ordenar_e_aplicar_limite(candidatos)

    assert len(resultado.mantidas) == 3
    assert len(resultado.excedentes) == 0
    print("OK: test_3_candidatos_nao_corta")


def test_desempate_nivel_1_confianca():
    """Confianças diferentes -> ordena só por confiança (caso base, sem empate)."""
    candidatos = [_categoria("A-001", 50.0), _categoria("A-002", 90.0)]

    resultado = ordenar_e_aplicar_limite(candidatos)

    assert [c.codigo_catalogo for c in resultado.mantidas] == ["A-002", "A-001"]
    print("OK: test_desempate_nivel_1_confianca")


def test_desempate_nivel_2_intensidade_semantica():
    """Empate exato em confianca -> desempata por intensidade_semantica (maior primeiro)."""
    candidatos = [
        _categoria("A-001", 80.0, intensidade_semantica=30.0),
        _categoria("A-002", 80.0, intensidade_semantica=90.0),
    ]

    resultado = ordenar_e_aplicar_limite(candidatos)

    assert [c.codigo_catalogo for c in resultado.mantidas] == ["A-002", "A-001"]
    print("OK: test_desempate_nivel_2_intensidade_semantica")


def test_desempate_nivel_3_quantidade_evidencias():
    """Empate em confianca E intensidade_semantica -> desempata por quantidade de evidências."""
    candidatos = [
        _categoria("A-001", 80.0, intensidade_semantica=50.0),
        _categoria("A-002", 80.0, intensidade_semantica=50.0),
    ]
    quantidade_evidencias = {"A-001": 2, "A-002": 7}

    resultado = ordenar_e_aplicar_limite(candidatos, quantidade_evidencias)

    assert [c.codigo_catalogo for c in resultado.mantidas] == ["A-002", "A-001"]
    print("OK: test_desempate_nivel_3_quantidade_evidencias")


def test_desempate_nivel_4_ordem_alfabetica_codigo():
    """Empate em TODOS os 3 níveis anteriores -> desempata por ordem alfabética do código."""
    candidatos = [
        _categoria("ZETA-009", 80.0, intensidade_semantica=50.0),
        _categoria("ATEND-001", 80.0, intensidade_semantica=50.0),
        _categoria("MARK-005", 80.0, intensidade_semantica=50.0),
    ]
    quantidade_evidencias = {"ZETA-009": 3, "ATEND-001": 3, "MARK-005": 3}

    resultado = ordenar_e_aplicar_limite(candidatos, quantidade_evidencias)

    codigos = [c.codigo_catalogo for c in resultado.mantidas]
    assert codigos == ["ATEND-001", "MARK-005", "ZETA-009"], f"Obtido: {codigos}"
    print("OK: test_desempate_nivel_4_ordem_alfabetica_codigo")


def test_determinismo_mesma_entrada_mesmo_resultado():
    """
    Para o mesmo lote de entrada, o resultado é sempre idêntico —
    roda a mesma ordenação 50 vezes e confirma resultado idêntico em todas.
    """
    candidatos = [
        _categoria("C-003", 80.0, intensidade_semantica=50.0),
        _categoria("A-001", 80.0, intensidade_semantica=50.0),
        _categoria("B-002", 80.0, intensidade_semantica=50.0),
        _categoria("D-004", 95.0),
        _categoria("E-005", 60.0),
    ]
    quantidade_evidencias = {"C-003": 1, "A-001": 1, "B-002": 1}

    resultados = [
        [c.codigo_catalogo for c in ordenar_e_aplicar_limite(candidatos, quantidade_evidencias).mantidas]
        for _ in range(50)
    ]

    assert all(r == resultados[0] for r in resultados), "Resultado não determinístico entre execuções"
    print(f"OK: test_determinismo_mesma_entrada_mesmo_resultado (resultado fixo: {resultados[0]})")


def test_sem_aleatoriedade_nem_dependencia_externa():
    """Verificação estática: módulo não importa random, nem cliente de IA/rede."""
    import confidence.confidence_rules as mod

    codigo_fonte = Path(mod.__file__).read_text(encoding="utf-8")
    proibidos = ["import random", "requests", "groq", "ai_classifier", "httpx"]
    for termo in proibidos:
        assert termo not in codigo_fonte, f"Encontrada referência proibida: {termo!r}"
    print("OK: test_sem_aleatoriedade_nem_dependencia_externa")


def test_excedentes_nao_descartados_conceitualmente():
    """As categorias além do limite são retornadas em `excedentes`, não perdidas."""
    candidatos = [_categoria(f"A-{i:03d}", 100.0 - i) for i in range(7)]

    resultado = ordenar_e_aplicar_limite(candidatos)

    assert len(resultado.mantidas) == LIMITE_CATEGORIAS_POR_RESPOSTA
    assert len(resultado.excedentes) == 2
    codigos_excedentes = {c.codigo_catalogo for c in resultado.excedentes}
    assert codigos_excedentes == {"A-005", "A-006"}
    print("OK: test_excedentes_nao_descartados_conceitualmente")


if __name__ == "__main__":
    test_limite_de_5_com_8_candidatos()
    test_3_candidatos_nao_corta()
    test_desempate_nivel_1_confianca()
    test_desempate_nivel_2_intensidade_semantica()
    test_desempate_nivel_3_quantidade_evidencias()
    test_desempate_nivel_4_ordem_alfabetica_codigo()
    test_determinismo_mesma_entrada_mesmo_resultado()
    test_sem_aleatoriedade_nem_dependencia_externa()
    test_excedentes_nao_descartados_conceitualmente()
    print("\nTodos os testes da Fase 6 (Regras de Confiança) passaram.")
