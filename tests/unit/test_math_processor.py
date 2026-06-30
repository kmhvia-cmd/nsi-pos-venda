"""
tests/unit/test_math_processor.py

Testes unitários da Camada Matemática.
Critérios de aceite — Plano de Implementação, Fase 1.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from models.input_models import Lote, RespostaCliente
from processors.math_processor import processar_matematica


def _resposta(
    cliente_id: str,
    status: str,
    minutos_para_responder: float | None = None,
    texto: str = "",
) -> RespostaCliente:
    envio = datetime(2026, 6, 1, 9, 0, 0)
    resposta_em = (
        envio + timedelta(minutes=minutos_para_responder)
        if minutos_para_responder is not None
        else None
    )
    return RespostaCliente(
        cliente_id=cliente_id,
        telefone="5511955525922",
        nome="Cliente Teste",
        produto="Produto Teste",
        resposta=texto,
        data_envio_mensagem=envio,
        data_resposta=resposta_em,
        status_entrega=status,
    )


def _lote(quantidade_enviada: int, respostas: list[RespostaCliente]) -> Lote:
    return Lote(
        empresa="empresa_teste",
        segmento="generico",
        lote_id="LOTE-TESTE",
        data_envio=datetime(2026, 6, 1, 9, 0, 0),
        quantidade_enviada=quantidade_enviada,
        quantidade_respondida=sum(1 for r in respostas if r.status_entrega == "respondido"),
        respostas=respostas,
    )


def test_taxa_resposta_60_porcento():
    """10 enviadas, 6 respondidas -> taxa_resposta == 60.0"""
    respostas = [_resposta(f"c{i}", "respondido", 30, "ok") for i in range(6)]
    respostas += [_resposta(f"c{i}", "nao_entregue") for i in range(6, 10)]
    lote = _lote(10, respostas)

    resultado = processar_matematica(lote)

    assert resultado.taxa_resposta == 60.0, f"Esperado 60.0, obtido {resultado.taxa_resposta}"
    print("OK: test_taxa_resposta_60_porcento")


def test_tempo_medio_e_distribuicao():
    """Timestamps conhecidos -> tempo médio e distribuição batem com cálculo manual."""
    respostas = [
        _resposta("c1", "respondido", 30, "respondeu rapido"),     # ate_1h
        _resposta("c2", "respondido", 60 * 10, "respondeu em horas"),  # ate_24h
        _resposta("c3", "respondido", 60 * 24 * 2, "demorou dias"),    # ate_3_dias
        _resposta("c4", "respondido", 60 * 24 * 10, "demorou muito"),  # acima_3_dias
    ]
    lote = _lote(4, respostas)

    resultado = processar_matematica(lote)

    tempos_esperados = [30, 600, 2880, 14400]
    media_esperada = round(sum(tempos_esperados) / len(tempos_esperados), 1)
    assert resultado.tempo_medio_resposta_minutos == media_esperada, (
        f"Esperado {media_esperada}, obtido {resultado.tempo_medio_resposta_minutos}"
    )

    dist = resultado.distribuicao_tempo_resposta
    assert dist.ate_1h == 25.0
    assert dist.ate_24h == 25.0
    assert dist.ate_3_dias == 25.0
    assert dist.acima_3_dias == 25.0
    print("OK: test_tempo_medio_e_distribuicao")


def test_lote_vazio_nao_quebra():
    """Lote com zero enviados não lança excecão — retorna estrutura válida com zeros."""
    lote = _lote(0, [])

    resultado = processar_matematica(lote)

    assert resultado.taxa_resposta == 0.0
    assert resultado.taxa_silencio == 0.0
    assert resultado.tempo_medio_resposta_minutos == 0.0
    assert resultado.qualidade_participacao_media == 0.0
    print("OK: test_lote_vazio_nao_quebra")


def test_qualidade_participacao_dentro_da_faixa():
    """qualidade_participacao_media calculável e dentro de 0-100% para qualquer entrada."""
    respostas = [
        _resposta("c1", "respondido", 30, "Gostei muito do atendimento, mas a entrega demorou."),
        _resposta("c2", "respondido", 45, "ok"),
        _resposta("c3", "respondido", 50, ""),
    ]
    lote = _lote(3, respostas)

    resultado = processar_matematica(lote)

    assert 0.0 <= resultado.qualidade_participacao_media <= 100.0, (
        f"qualidade_participacao_media fora da faixa: {resultado.qualidade_participacao_media}"
    )
    print(
        f"OK: test_qualidade_participacao_dentro_da_faixa "
        f"(valor obtido: {resultado.qualidade_participacao_media})"
    )


def test_qualidade_participacao_resposta_rica_supera_resposta_pobre():
    """Resposta rica e detalhada deve pontuar mais que resposta monossilábica."""
    respostas = [
        _resposta(
            "c1", "respondido", 30,
            "O atendimento foi excelente, super atenciosos, mas a entrega demorou bastante "
            "e isso prejudicou minha experiência geral com a compra."
        ),
        _resposta("c2", "respondido", 30, "ok ok ok"),
    ]
    lote = _lote(2, respostas)

    from processors.math_processor import _calcular_qualidade_participacao

    qualidade_rica = _calcular_qualidade_participacao(respostas[0].resposta)
    qualidade_pobre = _calcular_qualidade_participacao(respostas[1].resposta)

    assert qualidade_rica > qualidade_pobre, (
        f"Esperado resposta rica > pobre, obtido rica={qualidade_rica} pobre={qualidade_pobre}"
    )
    print(
        f"OK: test_qualidade_participacao_resposta_rica_supera_resposta_pobre "
        f"(rica={qualidade_rica}, pobre={qualidade_pobre})"
    )


def test_caso_real_validado_em_producao():
    """
    Reproduz o caso real já validado em produção (lote NSI-TESTE-001,
    telefone 5511955525922) — não bate número exato (não temos os
    timestamps reais completos), mas confirma que o processor não falha
    com o texto real e produz saída coerente.
    """
    respostas = [
        _resposta(
            "5511955525922", "respondido", 14,
            "O lá mais rim testev",
        ),
    ]
    lote = _lote(1, respostas)

    resultado = processar_matematica(lote)

    assert resultado.taxa_resposta == 100.0
    assert resultado.participacao_valida == 100.0
    print("OK: test_caso_real_validado_em_producao")


if __name__ == "__main__":
    test_taxa_resposta_60_porcento()
    test_tempo_medio_e_distribuicao()
    test_lote_vazio_nao_quebra()
    test_qualidade_participacao_dentro_da_faixa()
    test_qualidade_participacao_resposta_rica_supera_resposta_pobre()
    test_caso_real_validado_em_producao()
    print("\nTodos os testes da Fase 1 (Camada Matemática) passaram.")
