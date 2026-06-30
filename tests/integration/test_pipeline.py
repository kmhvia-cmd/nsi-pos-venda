"""
tests/integration/test_pipeline.py

Testes de integração do Pipeline completo do Motor NSI.
Critérios de aceite — Plano de Implementação, Fase 11.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from catalog.loader import carregar_catalogo
from engine.pipeline import executar_pipeline
from models.input_models import Lote, RespostaCliente
from services.ai_classifier import ClienteIAFalso


def _resposta(
    cliente_id: str, texto: str, status: str = "respondido", minutos: float = 30.0
) -> RespostaCliente:
    envio = datetime(2026, 6, 1, 9, 0, 0)
    return RespostaCliente(
        cliente_id=cliente_id, telefone=f"5511{cliente_id}",
        nome=f"Cliente {cliente_id}", produto="Produto Teste", resposta=texto,
        data_envio_mensagem=envio,
        data_resposta=envio + timedelta(minutes=minutos) if status == "respondido" else None,
        status_entrega=status,
    )


def _lote_teste(respostas: list[RespostaCliente]) -> Lote:
    respondidas = [r for r in respostas if r.status_entrega == "respondido"]
    return Lote(
        empresa="empresa_teste", segmento="generico", lote_id="NSI-TESTE-001",
        data_envio=datetime(2026, 6, 1, 9, 0, 0),
        quantidade_enviada=len(respostas),
        quantidade_respondida=len(respondidas),
        respostas=respostas,
    )


def _cliente_ia_completo() -> ClienteIAFalso:
    """ClienteIAFalso configurado com respostas para todas as tarefas."""
    cliente = ClienteIAFalso()
    cliente.configurar_resposta("classificacao_semantica", {
        "categorias": [
            {"codigo_catalogo": "ATEND-006", "confianca": 92.0,
             "intensidade_semantica": 68.0, "trecho_evidencia": "gostei do atendimento"},
            {"codigo_catalogo": "ENTR-001", "confianca": 85.0,
             "intensidade_semantica": 45.0, "trecho_evidencia": "entrega demorou"},
        ]
    })
    cliente.configurar_resposta("experiencia_humana", {
        "entusiasmo": 60.0, "confianca_cliente": 70.0, "frustracao": 30.0,
        "envolvimento": 65.0, "empolgacao": 45.0, "seguranca": 68.0,
        "indiferenca": 15.0, "lealdade": 62.0, "gratidao": 45.0, "desgaste": 20.0,
    })
    cliente.configurar_resposta("resumo_executivo", {
        "resumo_executivo": "Atendimento excelente, entrega a melhorar.",
        "resumo_comercial": "Boa retenção esperada.", "resumo_operacional": "Prazo crítico.",
        "resumo_atendimento": "Força no atendimento.", "resumo_produto": "Produto aprovado.",
        "resumo_experiencia": "Satisfação geral alta.", "resumo_evolutivo": "", "resumo_nicho": "",
    })
    cliente.configurar_resposta("acao_recomendada", {"acoes": []})
    return cliente


def test_pipeline_completo_roda_sem_erro():
    """Pipeline completo de ponta a ponta entrega saída válida com todas as camadas."""
    catalogo = carregar_catalogo()
    cliente = _cliente_ia_completo()

    respostas = [
        _resposta("001", "Gostei muito do atendimento, mas a entrega demorou."),
        _resposta("002", "Ótimo atendimento! Entrega deixou a desejar."),
        _resposta("003", "Atendimento foi bom, mas esperava mais."),
    ]
    lote = _lote_teste(respostas)

    saida = executar_pipeline(lote, catalogo, cliente)

    assert saida.status_semantico == "concluido"
    assert saida.empresa == "empresa_teste"
    assert saida.lote_id == "NSI-TESTE-001"
    assert saida.matematica is not None
    assert saida.linguistica_agregada is not None
    assert saida.semantica is not None
    assert saida.experiencia_humana_agregada is not None
    assert saida.executiva is not None
    assert saida.versao_motor == "3.1"
    assert saida.versao_catalogo == "1.1"
    print(f"OK: test_pipeline_completo_roda_sem_erro (ICE={saida.executiva.ice_nsi})")


def test_pipeline_com_fallback_entrega_saida_parcial():
    """
    Pipeline com IA indisponível entrega saída parcial com
    status_semantico='pendente', matematica e linguistica presentes,
    blocos de IA ausentes.
    """
    catalogo = carregar_catalogo()
    cliente = ClienteIAFalso()
    cliente.configurar_falha("classificacao_semantica")

    respostas = [_resposta("001", "Texto qualquer para testar o fallback.")]
    lote = _lote_teste(respostas)

    saida = executar_pipeline(lote, catalogo, cliente)

    assert saida.status_semantico == "pendente"
    assert saida.matematica is not None
    assert saida.linguistica_agregada is not None
    assert saida.semantica is None
    assert saida.executiva is None
    print("OK: test_pipeline_com_fallback_entrega_saida_parcial")


def test_pipeline_caso_real_nsi_teste_001():
    """
    Reproduz o caso real já validado em produção (NSI-TESTE-001,
    telefone 5511955525922, mensagem real recebida via WhatsApp).
    Confirma que o pipeline não falha com o texto real.
    """
    catalogo = carregar_catalogo()
    cliente = _cliente_ia_completo()

    respostas = [
        _resposta("5511955525922", "O lá mais rim testev", minutos=14.0),
    ]
    lote = Lote(
        empresa="empresa_teste", segmento="generico", lote_id="NSI-TESTE-001",
        data_envio=datetime(2026, 6, 1, 9, 0, 0),
        quantidade_enviada=1, quantidade_respondida=1, respostas=respostas,
    )

    saida = executar_pipeline(lote, catalogo, cliente)

    assert saida.matematica.taxa_resposta == 100.0
    assert saida.status_semantico == "concluido"
    print("OK: test_pipeline_caso_real_nsi_teste_001")


def test_pipeline_lote_vazio_nao_quebra():
    """Lote com zero respostas não levanta exceção, entrega saída válida."""
    catalogo = carregar_catalogo()
    cliente = ClienteIAFalso()
    cliente.configurar_resposta("resumo_executivo", {
        "resumo_executivo": "", "resumo_comercial": "", "resumo_operacional": "",
        "resumo_atendimento": "", "resumo_produto": "", "resumo_experiencia": "",
        "resumo_evolutivo": "", "resumo_nicho": "",
    })
    cliente.configurar_resposta("classificacao_semantica", {"categorias": []})
    cliente.configurar_resposta("experiencia_humana", {
        "entusiasmo": 0.0, "confianca_cliente": 0.0, "frustracao": 0.0,
        "envolvimento": 0.0, "empolgacao": 0.0, "seguranca": 0.0,
        "indiferenca": 0.0, "lealdade": 0.0, "gratidao": 0.0, "desgaste": 0.0,
    })
    cliente.configurar_resposta("acao_recomendada", {"acoes": []})

    lote = Lote(
        empresa="empresa_teste", segmento="generico", lote_id="NSI-VAZIO-001",
        data_envio=datetime(2026, 6, 1, 9, 0, 0),
        quantidade_enviada=0, quantidade_respondida=0, respostas=[],
    )

    saida = executar_pipeline(lote, catalogo, cliente)

    assert saida.matematica.taxa_resposta == 0.0
    print("OK: test_pipeline_lote_vazio_nao_quebra")


if __name__ == "__main__":
    test_pipeline_completo_roda_sem_erro()
    test_pipeline_com_fallback_entrega_saida_parcial()
    test_pipeline_caso_real_nsi_teste_001()
    test_pipeline_lote_vazio_nao_quebra()
    print("\nTodos os testes da Fase 11 (Pipeline) passaram.")
