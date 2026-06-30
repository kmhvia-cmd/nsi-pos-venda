"""
tests/unit/test_linguistic_processor.py

Testes unitários da Camada Linguística (parte determinística).
Critérios de aceite — Plano de Implementação, Fase 2.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from processors.linguistic_processor import (
    agregar_linguistica_lote,
    processar_linguistica_resposta,
)


def test_pontuacao_intensificada_e_caixa_alta():
    """'MUITO BOM!!!' -> pontuacao_intensificada: true, caixa_alta: true"""
    resultado = processar_linguistica_resposta("MUITO BOM!!!")

    assert resultado.marcadores_detectados.pontuacao_intensificada is True
    assert resultado.marcadores_detectados.caixa_alta is True
    print("OK: test_pontuacao_intensificada_e_caixa_alta")


def test_texto_neutro_sem_marcadores():
    """Texto sem pontuação intensa, sem caixa alta, sem emoji -> tudo False/vazio."""
    resultado = processar_linguistica_resposta("Gostei muito do atendimento.")

    assert resultado.marcadores_detectados.pontuacao_intensificada is False
    assert resultado.marcadores_detectados.caixa_alta is False
    assert resultado.marcadores_detectados.emojis == []
    print("OK: test_texto_neutro_sem_marcadores")


def test_emoji_detectado_e_polaridade():
    """Emoji positivo conhecido -> detectado com polaridade positiva."""
    resultado = processar_linguistica_resposta("Atendimento top 🔥")

    assert len(resultado.marcadores_detectados.emojis) == 1
    assert resultado.marcadores_detectados.emojis[0]["simbolo"] == "🔥"
    assert resultado.marcadores_detectados.emojis[0]["polaridade"] == "positiva"
    assert resultado.polaridade_linguistica > 0
    print("OK: test_emoji_detectado_e_polaridade")


def test_giria_regionalismo_detectado():
    """'da hora' -> detectado em girias_regionalismos, formalidade reduzida."""
    resultado = processar_linguistica_resposta("Atendimento da hora, gostei muito.")

    termos = [g["termo"] for g in resultado.marcadores_detectados.girias_regionalismos]
    assert "da hora" in termos
    assert resultado.formalidade < 100.0
    print("OK: test_giria_regionalismo_detectado")


def test_abreviacao_detectada():
    """'vlw' -> detectado em abreviacoes."""
    resultado = processar_linguistica_resposta("vlw pela ajuda")

    termos = [a["termo"] for a in resultado.marcadores_detectados.abreviacoes]
    assert "vlw" in termos
    print("OK: test_abreviacao_detectada")


def test_repeticao_enfase():
    """'muitooo bom' -> repeticao_enfase: true."""
    resultado = processar_linguistica_resposta("muitooo bom o atendimento")

    assert resultado.marcadores_detectados.repeticao_enfase is True
    print("OK: test_repeticao_enfase")


def test_formalidade_e_marca_regional_dentro_da_faixa():
    """formalidade e marca_regional sempre calculáveis e dentro de 0-100%."""
    textos = [
        "O atendimento foi excelente.",
        "vlw flw, foi da hora memo",
        "",
        "🔥🔥🔥 top demais!!!",
    ]
    for texto in textos:
        resultado = processar_linguistica_resposta(texto)
        assert 0.0 <= resultado.formalidade <= 100.0, f"formalidade fora da faixa para: {texto!r}"
        assert 0.0 <= resultado.marca_regional <= 100.0, f"marca_regional fora da faixa para: {texto!r}"
    print("OK: test_formalidade_e_marca_regional_dentro_da_faixa")


def test_nenhuma_chamada_externa():
    """
    Módulo roda de forma independente da IA — nenhuma chamada externa.
    Verificação estática: o módulo não importa nenhum cliente de IA/rede.
    """
    import processors.linguistic_processor as mod

    codigo_fonte = Path(mod.__file__).read_text(encoding="utf-8")
    proibidos = ["requests", "groq", "ai_classifier", "httpx", "urllib"]
    for termo in proibidos:
        assert termo not in codigo_fonte, f"Encontrada referência proibida: {termo!r}"
    print("OK: test_nenhuma_chamada_externa")


def test_agregacao_no_nivel_do_lote():
    """agregar_linguistica_lote calcula médias corretamente sobre múltiplas respostas."""
    r1 = processar_linguistica_resposta("Muito bom! 🔥")
    r2 = processar_linguistica_resposta("nao gostei")
    agregado = agregar_linguistica_lote([r1, r2])

    media_esperada_intensidade = round((r1.intensidade_emocional + r2.intensidade_emocional) / 2, 1)
    assert agregado.intensidade_emocional_media == media_esperada_intensidade
    print("OK: test_agregacao_no_nivel_do_lote")


def test_agregacao_lote_vazio():
    """Lote sem respostas não quebra a agregação."""
    agregado = agregar_linguistica_lote([])
    assert agregado.intensidade_emocional_media == 0.0
    print("OK: test_agregacao_lote_vazio")


if __name__ == "__main__":
    test_pontuacao_intensificada_e_caixa_alta()
    test_texto_neutro_sem_marcadores()
    test_emoji_detectado_e_polaridade()
    test_giria_regionalismo_detectado()
    test_abreviacao_detectada()
    test_repeticao_enfase()
    test_formalidade_e_marca_regional_dentro_da_faixa()
    test_nenhuma_chamada_externa()
    test_agregacao_no_nivel_do_lote()
    test_agregacao_lote_vazio()
    print("\nTodos os testes da Fase 2 (Camada Linguística determinística) passaram.")
