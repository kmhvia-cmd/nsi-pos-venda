"""
tests/semantic/test_experience_processor.py

Testes da Camada de Experiência Humana.
Critérios de aceite — Plano de Implementação, Fase 7.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from models.output_models import (
    IroniaDetectada,
    MarcadoresDetectados,
    ResultadoLinguistico,
)
from processors.experience_processor import (
    agregar_experiencia_humana_lote,
    processar_experiencia_humana_resposta,
)
from services.ai_classifier import ClienteIAFalso


def _linguistica_neutra() -> ResultadoLinguistico:
    """Sinais de forma de uma frase curta, positiva, sem intensidade — 'Foi bom.'"""
    return ResultadoLinguistico(
        intensidade_emocional=5.0,
        polaridade_linguistica=20.0,  # positivo, mas fraco
        engajamento_linguistico=10.0,
        formalidade=80.0,
        marca_regional=0.0,
        ironia_detectada=IroniaDetectada(presente=False, confianca=0.0),
        marcadores_detectados=MarcadoresDetectados(),
    )


def _resposta_ia_10_campos(**overrides) -> dict:
    base = {
        "entusiasmo": 50.0, "confianca_cliente": 50.0, "frustracao": 50.0,
        "envolvimento": 50.0, "empolgacao": 50.0, "seguranca": 50.0,
        "indiferenca": 50.0, "lealdade": 50.0, "gratidao": 50.0, "desgaste": 50.0,
    }
    base.update(overrides)
    return base


def test_todos_os_10_indicadores_calculaveis_e_na_faixa():
    """Os 10 indicadores são calculáveis e estão dentro de 0-100%."""
    cliente = ClienteIAFalso()
    cliente.configurar_resposta("experiencia_humana", _resposta_ia_10_campos())

    resultado, sucesso = processar_experiencia_humana_resposta(
        "Gostei muito.", _linguistica_neutra(), [], cliente
    )

    assert sucesso is True
    for campo in (
        "entusiasmo", "confianca_cliente", "frustracao", "envolvimento",
        "empolgacao", "seguranca", "indiferenca", "lealdade", "gratidao", "desgaste",
    ):
        valor = getattr(resultado, campo)
        assert 0.0 <= valor <= 100.0, f"{campo} fora da faixa: {valor}"
    print("OK: test_todos_os_10_indicadores_calculaveis_e_na_faixa")


def test_caso_foi_bom_do_contrato_indiferenca_alta_entusiasmo_baixo():
    """
    Caso de teste exigido pelo Plano (Fase 7): 'Foi bom.' produz polaridade
    positiva mas entusiasmo baixo — a distinção do Contrato 5.0 precisa
    se manifestar no resultado real, não só na documentação.
    """
    cliente = ClienteIAFalso()
    cliente.configurar_resposta(
        "experiencia_humana",
        _resposta_ia_10_campos(entusiasmo=15.0, indiferenca=70.0, seguranca=60.0),
    )

    resultado, sucesso = processar_experiencia_humana_resposta(
        "Foi bom.", _linguistica_neutra(), [], cliente
    )

    assert sucesso is True
    assert resultado.entusiasmo < 30.0, "Entusiasmo deveria ser baixo para 'Foi bom.'"
    assert resultado.indiferenca > resultado.entusiasmo, (
        "Indiferença deveria superar entusiasmo neste caso de fronteira"
    )
    print("OK: test_caso_foi_bom_do_contrato_indiferenca_alta_entusiasmo_baixo")


def test_valor_fora_da_faixa_e_corrigido_para_limite():
    """Validação: valor > 100 ou < 0 retornado pela IA é truncado para o limite, não propagado."""
    cliente = ClienteIAFalso()
    cliente.configurar_resposta(
        "experiencia_humana", _resposta_ia_10_campos(entusiasmo=150.0, frustracao=-20.0)
    )

    resultado, sucesso = processar_experiencia_humana_resposta(
        "texto qualquer", _linguistica_neutra(), [], cliente
    )

    assert resultado.entusiasmo == 100.0
    assert resultado.frustracao == 0.0
    print("OK: test_valor_fora_da_faixa_e_corrigido_para_limite")


def test_campo_ausente_e_tratado_como_zero():
    """Se a IA omitir um campo, o valor é 0.0, não exceção."""
    cliente = ClienteIAFalso()
    resposta_incompleta = _resposta_ia_10_campos()
    del resposta_incompleta["gratidao"]
    cliente.configurar_resposta("experiencia_humana", resposta_incompleta)

    resultado, sucesso = processar_experiencia_humana_resposta(
        "texto qualquer", _linguistica_neutra(), [], cliente
    )

    assert sucesso is True
    assert resultado.gratidao == 0.0
    print("OK: test_campo_ausente_e_tratado_como_zero")


def test_falha_da_ia_retorna_none_sem_excecao():
    """Falha da IA -> resultado=None, sucesso=False, nunca lança exceção."""
    cliente = ClienteIAFalso()
    cliente.configurar_falha("experiencia_humana")

    resultado, sucesso = processar_experiencia_humana_resposta(
        "texto qualquer", _linguistica_neutra(), [], cliente
    )

    assert resultado is None
    assert sucesso is False
    print("OK: test_falha_da_ia_retorna_none_sem_excecao")


def test_agregacao_no_nivel_do_lote():
    """agregar_experiencia_humana_lote calcula médias corretamente."""
    cliente = ClienteIAFalso()
    cliente.configurar_resposta("experiencia_humana", _resposta_ia_10_campos(entusiasmo=20.0))
    r1, _ = processar_experiencia_humana_resposta("t1", _linguistica_neutra(), [], cliente)

    cliente2 = ClienteIAFalso()
    cliente2.configurar_resposta("experiencia_humana", _resposta_ia_10_campos(entusiasmo=80.0))
    r2, _ = processar_experiencia_humana_resposta("t2", _linguistica_neutra(), [], cliente2)

    agregado = agregar_experiencia_humana_lote([r1, r2])

    assert agregado.entusiasmo_medio == 50.0
    print("OK: test_agregacao_no_nivel_do_lote")


def test_agregacao_lote_vazio():
    """Lote sem resultados não quebra a agregação."""
    agregado = agregar_experiencia_humana_lote([])
    assert agregado.entusiasmo_medio == 0.0
    print("OK: test_agregacao_lote_vazio")


def test_nenhum_campo_de_texto_livre_na_saida():
    """
    Verificação estrutural: ResultadoExperienciaHumana só tem campos float
    — nenhum campo de texto/narrativa é parte desta camada (Contrato).
    """
    from dataclasses import fields

    from models.output_models import ResultadoExperienciaHumana

    for campo in fields(ResultadoExperienciaHumana):
        assert campo.type is float, (
            f"Campo {campo.name} não é float (é {campo.type}) — "
            f"possível saída narrativa indevida"
        )
    print("OK: test_nenhum_campo_de_texto_livre_na_saida")


def test_prompt_proibe_explicitamente_saida_narrativa():
    """Verificação estática: o prompt do sistema instrui explicitamente sem texto narrativo."""
    import processors.experience_processor as mod

    codigo_fonte = Path(mod.__file__).read_text(encoding="utf-8")
    assert "SEM NENHUM TEXTO NARRATIVO" in codigo_fonte or "sem texto narrativo" in codigo_fonte.lower()
    print("OK: test_prompt_proibe_explicitamente_saida_narrativa")


def test_usa_apenas_interface_clienteia():
    """Verificação estática: processor não importa Groq diretamente."""
    import processors.experience_processor as mod

    codigo_fonte = Path(mod.__file__).read_text(encoding="utf-8")
    assert "import groq" not in codigo_fonte
    assert "from groq" not in codigo_fonte
    print("OK: test_usa_apenas_interface_clienteia")


if __name__ == "__main__":
    test_todos_os_10_indicadores_calculaveis_e_na_faixa()
    test_caso_foi_bom_do_contrato_indiferenca_alta_entusiasmo_baixo()
    test_valor_fora_da_faixa_e_corrigido_para_limite()
    test_campo_ausente_e_tratado_como_zero()
    test_falha_da_ia_retorna_none_sem_excecao()
    test_agregacao_no_nivel_do_lote()
    test_agregacao_lote_vazio()
    test_nenhum_campo_de_texto_livre_na_saida()
    test_prompt_proibe_explicitamente_saida_narrativa()
    test_usa_apenas_interface_clienteia()
    print("\nTodos os testes da Fase 7 (Camada de Experiência Humana) passaram.")
