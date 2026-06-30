"""
tests/regression/test_regression_final.py

Suíte de Regressão Final do Motor NSI.
Critérios de aceite — Plano de Implementação, Fase 13.

Conjunto de lotes com saída esperada congelada — toda mudança no motor
(novo prompt, nova versão de catálogo, refatoração) deve rodar contra
esta suíte para detectar regressão não intencional.

Inclui obrigatoriamente:
    - o caso real NSI-TESTE-001 (lote validado em produção)
    - cenários cobrindo cada camada isoladamente
    - cenário de fallback
    - caso com Evolução Temporal
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from catalog.loader import carregar_catalogo
from engine.pipeline import executar_pipeline
from models.input_models import Lote, RespostaCliente
from processors.evolution_processor import LoteAnteriorComparavel
from models.output_models import (
    DistribuicaoTempoResposta,
    ResultadoMatematico,
    ResultadoSemantico,
)
from services.ai_classifier import ClienteIAFalso


def _resposta(cliente_id, texto, status="respondido", minutos=30.0):
    envio = datetime(2026, 6, 1, 9, 0)
    return RespostaCliente(
        cliente_id=cliente_id, telefone=f"5511{cliente_id}",
        nome=f"Cliente {cliente_id}", produto="Produto Teste", resposta=texto,
        data_envio_mensagem=envio,
        data_resposta=envio + timedelta(minutes=minutos) if status == "respondido" else None,
        status_entrega=status,
    )


def _lote(lote_id, respostas, empresa="empresa_teste"):
    respondidas = [r for r in respostas if r.status_entrega == "respondido"]
    return Lote(
        empresa=empresa, segmento="generico", lote_id=lote_id,
        data_envio=datetime(2026, 6, 1, 9, 0),
        quantidade_enviada=len(respostas),
        quantidade_respondida=len(respondidas),
        respostas=respostas,
    )


def _cliente_completo():
    c = ClienteIAFalso()
    c.configurar_resposta("classificacao_semantica", {
        "categorias": [
            {"codigo_catalogo": "ATEND-006", "confianca": 92.0,
             "intensidade_semantica": 68.0, "trecho_evidencia": "atendimento ótimo"},
            {"codigo_catalogo": "ENTR-001", "confianca": 85.0,
             "intensidade_semantica": 45.0, "trecho_evidencia": "entrega demorou"},
        ]
    })
    c.configurar_resposta("experiencia_humana", {
        "entusiasmo": 60.0, "confianca_cliente": 70.0, "frustracao": 30.0,
        "envolvimento": 65.0, "empolgacao": 45.0, "seguranca": 68.0,
        "indiferenca": 15.0, "lealdade": 62.0, "gratidao": 45.0, "desgaste": 20.0,
    })
    c.configurar_resposta("resumo_executivo", {
        "resumo_executivo": "Atendimento é a maior força.",
        "resumo_comercial": "Retenção estável.", "resumo_operacional": "Entrega crítica.",
        "resumo_atendimento": "Atendimento excelente.", "resumo_produto": "Produto ok.",
        "resumo_experiencia": "Satisfação positiva.", "resumo_evolutivo": "", "resumo_nicho": "",
    })
    c.configurar_resposta("acao_recomendada", {"acoes": []})
    return c


# ---------------------------------------------------------------------------
# CASO 1: caso real NSI-TESTE-001 (lote validado em produção)
# ---------------------------------------------------------------------------

def test_regressao_caso_real_nsi_teste_001():
    """
    Reproduz o caso real validado em produção: lote NSI-TESTE-001,
    telefone 5511955525922, resposta "O lá mais rim testev" recebida via
    WhatsApp. Saída esperada congelada: taxa_resposta=100%, pipeline não
    falha, status_semantico='concluido'.
    """
    catalogo = carregar_catalogo()
    cliente = _cliente_completo()

    lote = _lote("NSI-TESTE-001", [_resposta("5511955525922", "O lá mais rim testev", minutos=14.0)])
    saida = executar_pipeline(lote, catalogo, cliente)

    assert saida.lote_id == "NSI-TESTE-001"
    assert saida.matematica.taxa_resposta == 100.0
    assert saida.matematica.taxa_silencio == 0.0
    assert saida.status_semantico == "concluido"
    assert saida.semantica is not None
    assert saida.executiva is not None
    print(f"OK: test_regressao_caso_real_nsi_teste_001 (ICE={saida.executiva.ice_nsi})")


# ---------------------------------------------------------------------------
# CASO 2: camada matemática — valores exatos congelados
# ---------------------------------------------------------------------------

def test_regressao_matematica_taxa_60_porcento():
    """Regressão da Camada Matemática: 10 enviadas, 6 respondidas -> taxa_resposta=60.0"""
    catalogo = carregar_catalogo()
    cliente = _cliente_completo()

    respostas = [_resposta(f"{i}", "texto válido") for i in range(6)]
    respostas += [_resposta(f"{i+6}", "", status="nao_entregue") for i in range(4)]
    lote = _lote("LOTE-MATH", respostas)
    saida = executar_pipeline(lote, catalogo, cliente)

    assert saida.matematica.taxa_resposta == 60.0
    assert saida.matematica.taxa_nao_entrega == 40.0
    print("OK: test_regressao_matematica_taxa_60_porcento")


# ---------------------------------------------------------------------------
# CASO 3: convivência força/dor — regra fundamental do Contrato
# ---------------------------------------------------------------------------

def test_regressao_convivencia_forca_e_dor():
    """
    Regressão do Contrato Seção 4.3: força e dor coexistem na mesma
    resposta. Saída esperada congelada: ambas as famílias presentes.
    """
    catalogo = carregar_catalogo()
    cliente = _cliente_completo()

    lote = _lote("LOTE-CONVIVENCIA", [
        _resposta("001", "O atendimento foi ótimo, mas a entrega demorou.")
    ])
    saida = executar_pipeline(lote, catalogo, cliente)

    familias_forcas = {f.familia for f in saida.semantica.forcas_identificadas}
    familias_dores = {d.familia for d in saida.semantica.dores_identificadas}

    assert "ATENDIMENTO" in familias_forcas, "ATENDIMENTO deveria ser força"
    assert "ENTREGA" in familias_dores, "ENTREGA deveria ser dor"
    print("OK: test_regressao_convivencia_forca_e_dor")


# ---------------------------------------------------------------------------
# CASO 4: fallback — saída parcial com campos obrigatórios e ausentes corretos
# ---------------------------------------------------------------------------

def test_regressao_fallback_saida_parcial():
    """
    Regressão do Contrato Seção 1.2: fallback gera saída parcial exata.
    Saída esperada congelada: matematica e linguistica_agregada presentes,
    semantica e executiva ausentes, status_semantico='pendente'.
    """
    catalogo = carregar_catalogo()
    cliente = ClienteIAFalso()
    cliente.configurar_falha("classificacao_semantica")

    lote = _lote("LOTE-FALLBACK", [_resposta("001", "Resposta qualquer.")])
    saida = executar_pipeline(lote, catalogo, cliente)

    assert saida.status_semantico == "pendente"
    assert saida.matematica is not None
    assert saida.linguistica_agregada is not None
    assert saida.semantica is None
    assert saida.executiva is None
    assert saida.evidencias_semanticas_validas == 0
    print("OK: test_regressao_fallback_saida_parcial")


# ---------------------------------------------------------------------------
# CASO 5: ICE bloqueado por cobertura insuficiente
# ---------------------------------------------------------------------------

def test_regressao_ice_cobertura_insuficiente():
    """
    Regressão do Contrato Seção 9.17: ICE bloqueado quando cobertura <20%
    E evidências <10. Status_ice='cobertura_insuficiente', ice_nsi=None.
    """
    catalogo = carregar_catalogo()
    cliente = ClienteIAFalso()
    cliente.configurar_resposta("classificacao_semantica", {"categorias": []})
    cliente.configurar_resposta("experiencia_humana", {
        "entusiasmo": 0.0, "confianca_cliente": 0.0, "frustracao": 0.0,
        "envolvimento": 0.0, "empolgacao": 0.0, "seguranca": 0.0,
        "indiferenca": 0.0, "lealdade": 0.0, "gratidao": 0.0, "desgaste": 0.0,
    })
    cliente.configurar_resposta("resumo_executivo", {
        "resumo_executivo": "", "resumo_comercial": "", "resumo_operacional": "",
        "resumo_atendimento": "", "resumo_produto": "", "resumo_experiencia": "",
        "resumo_evolutivo": "", "resumo_nicho": "",
    })
    cliente.configurar_resposta("acao_recomendada", {"acoes": []})

    # 1 resposta, nenhuma categoria -> cobertura 0%, evidências 0
    lote = _lote("LOTE-SEM-COBERTURA", [_resposta("001", "ok")])
    saida = executar_pipeline(lote, catalogo, cliente)

    assert saida.executiva.status_ice == "cobertura_insuficiente"
    assert saida.executiva.ice_nsi is None
    assert saida.executiva.motivo is not None
    print("OK: test_regressao_ice_cobertura_insuficiente")


# ---------------------------------------------------------------------------
# CASO 6: evolução temporal com mesma versão de catálogo
# ---------------------------------------------------------------------------

def test_regressao_evolucao_temporal():
    """
    Regressão da Camada de Evolução Temporal: lote atual comparado com
    anterior da mesma empresa e mesma versao_catalogo ->
    comparabilidade='total', variacoes_matematica presentes.
    """
    catalogo = carregar_catalogo()
    cliente = _cliente_completo()

    lote_anterior = LoteAnteriorComparavel(
        lote_id="LOTE-ANTERIOR-001",
        empresa="empresa_teste",
        versao_catalogo="1.1",
        matematica=ResultadoMatematico(
            taxa_resposta=50.0, taxa_silencio=50.0, taxa_visualizado_sem_resposta=0.0,
            taxa_nao_entrega=0.0, tempo_medio_resposta_minutos=120.0,
            tempo_mediano_resposta_minutos=110.0,
            distribuicao_tempo_resposta=DistribuicaoTempoResposta(0.0, 100.0, 0.0, 0.0),
            tamanho_medio_resposta_caracteres=80, participacao_valida=85.0,
            qualidade_participacao_media=65.0,
        ),
        semantica=ResultadoSemantico(dores_identificadas=[], forcas_identificadas=[]),
    )

    lote = _lote("LOTE-ATUAL-002", [
        _resposta("001", "Atendimento ótimo, entrega melhorou."),
        _resposta("002", "Muito bom!"),
    ])
    saida = executar_pipeline(lote, catalogo, cliente, lote_anterior=lote_anterior)

    assert saida.evolucao_temporal is not None
    assert saida.evolucao_temporal.comparabilidade == "total"
    assert saida.evolucao_temporal.lote_comparado_id == "LOTE-ANTERIOR-001"
    assert len(saida.evolucao_temporal.variacoes_matematica) > 0
    print(
        f"OK: test_regressao_evolucao_temporal "
        f"(variacao taxa_resposta: {next(v.variacao for v in saida.evolucao_temporal.variacoes_matematica if v.indicador == 'taxa_resposta')})"
    )


if __name__ == "__main__":
    test_regressao_caso_real_nsi_teste_001()
    test_regressao_matematica_taxa_60_porcento()
    test_regressao_convivencia_forca_e_dor()
    test_regressao_fallback_saida_parcial()
    test_regressao_ice_cobertura_insuficiente()
    test_regressao_evolucao_temporal()
    print("\nTodos os testes de regressão final passaram. Motor NSI validado.")
