"""
tests/unit/test_logs.py

Testes da Fase 12 — Logs e Auditoria.
Critérios de aceite — Plano de Implementação, Fase 12.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from models.output_models import (
    DistribuicaoTempoResposta,
    ModeloClassificacao,
    ResultadoLinguisticoAgregado,
    ResultadoMatematico,
    SaidaMotorCompleta,
)
from logs.engine_logger import log_fallback, log_fim_pipeline, log_inicio_pipeline, medir_etapa
from logs.classification_logger import log_classificacao_realizada
from logs.audit_logger import log_saida_final


def _capturar_logs(logger_name: str, nivel: int = logging.DEBUG):
    """Context manager para capturar logs emitidos durante o teste."""
    import io
    from contextlib import contextmanager

    @contextmanager
    def _ctx():
        logger = logging.getLogger(logger_name)
        logger.setLevel(nivel)
        buffer = io.StringIO()
        handler = logging.StreamHandler(buffer)
        handler.setLevel(nivel)
        logger.addHandler(handler)
        try:
            yield buffer
        finally:
            logger.removeHandler(handler)

    return _ctx()


def test_log_inicio_e_fim_pipeline_tem_lote_id():
    """Logs de início/fim do pipeline contêm lote_id."""
    with _capturar_logs("nsi.engine") as buf:
        log_inicio_pipeline("NSI-TESTE-001", "empresa_teste")
        log_fim_pipeline("NSI-TESTE-001", "concluido", 1.234)

    saida = buf.getvalue()
    assert "NSI-TESTE-001" in saida
    assert "empresa_teste" in saida
    assert "concluido" in saida
    print("OK: test_log_inicio_e_fim_pipeline_tem_lote_id")


def test_log_fallback_gerado_quando_e_so_quando_fallback_acionado():
    """Log de fallback gerado com motivo, com lote_id."""
    with _capturar_logs("nsi.engine") as buf:
        log_fallback("NSI-TESTE-001", "timeout na chamada à Groq")

    saida = buf.getvalue()
    assert "NSI-TESTE-001" in saida
    assert "FALLBACK" in saida
    assert "timeout" in saida
    print("OK: test_log_fallback_gerado_quando_e_so_quando_fallback_acionado")


def test_log_etapa_via_context_manager():
    """medir_etapa registra o tempo de execução de uma etapa."""
    import time

    with _capturar_logs("nsi.engine") as buf:
        with medir_etapa("NSI-TESTE-001", "camada_matematica"):
            time.sleep(0.01)

    saida = buf.getvalue()
    assert "NSI-TESTE-001" in saida
    assert "camada_matematica" in saida
    print("OK: test_log_etapa_via_context_manager")


def test_log_classificacao_registra_modelo_classificacao():
    """
    classification_logger registra modelo_classificacao em toda chamada
    de IA (Contrato Seção 1.1).
    """
    modelo = ModeloClassificacao(provider="groq", modelo="llama", versao_prompt="v1")

    with _capturar_logs("nsi.classification") as buf:
        log_classificacao_realizada(
            lote_id="NSI-TESTE-001",
            tarefa="classificacao_semantica",
            modelo_classificacao=modelo,
            categorias_detectadas=["ATEND-006", "ENTR-001"],
            cliente_id="5511955525922",
        )

    saida = buf.getvalue()
    assert "NSI-TESTE-001" in saida
    assert "groq" in saida
    assert "llama" in saida
    assert "v1" in saida
    assert "ATEND-006" in saida
    print("OK: test_log_classificacao_registra_modelo_classificacao")


def test_log_auditoria_final_registra_campos_de_rastreabilidade():
    """audit_logger registra versao_motor, versao_catalogo, modelo e ice_nsi."""
    from models.output_models import ModeloClassificacao, ResultadoLinguisticoAgregado

    saida = SaidaMotorCompleta(
        empresa="empresa_teste", segmento="generico", lote_id="NSI-TESTE-001",
        data_processamento=datetime.now(), versao_motor="3.1", versao_catalogo="1.1",
        status_semantico="concluido", evidencias_semanticas_validas=41,
        modelo_classificacao=ModeloClassificacao(
            provider="groq", modelo="llama", versao_prompt="v1"
        ),
        matematica=ResultadoMatematico(
            taxa_resposta=62.0, taxa_silencio=38.0, taxa_visualizado_sem_resposta=0.0,
            taxa_nao_entrega=0.0, tempo_medio_resposta_minutos=0.0,
            tempo_mediano_resposta_minutos=0.0,
            distribuicao_tempo_resposta=DistribuicaoTempoResposta(0.0, 0.0, 0.0, 0.0),
            tamanho_medio_resposta_caracteres=0, participacao_valida=0.0,
            qualidade_participacao_media=0.0,
        ),
        linguistica_agregada=ResultadoLinguisticoAgregado(
            intensidade_emocional_media=0.0, polaridade_linguistica_media=0.0,
            engajamento_linguistico_medio=0.0, formalidade_media=0.0, marca_regional_media=0.0,
        ),
    )

    with _capturar_logs("nsi.audit") as buf:
        log_saida_final(saida)

    conteudo = buf.getvalue()
    assert "NSI-TESTE-001" in conteudo
    assert "3.1" in conteudo
    assert "1.1" in conteudo
    assert "groq" in conteudo
    assert "41" in conteudo
    print("OK: test_log_auditoria_final_registra_campos_de_rastreabilidade")


def test_logs_nao_registram_texto_de_resposta_do_cliente():
    """
    Verificação estática: nenhum logger registra o texto completo de
    respostas de clientes — apenas identificadores e agregados.
    """
    for modulo_path in [
        "logs/engine_logger.py",
        "logs/classification_logger.py",
        "logs/audit_logger.py",
    ]:
        codigo = (Path(__file__).resolve().parents[2] / modulo_path).read_text(encoding="utf-8")
        assert "resposta.resposta" not in codigo, (
            f"{modulo_path} registra texto de resposta diretamente (dado pessoal)"
        )
    print("OK: test_logs_nao_registram_texto_de_resposta_do_cliente")


if __name__ == "__main__":
    test_log_inicio_e_fim_pipeline_tem_lote_id()
    test_log_fallback_gerado_quando_e_so_quando_fallback_acionado()
    test_log_etapa_via_context_manager()
    test_log_classificacao_registra_modelo_classificacao()
    test_log_auditoria_final_registra_campos_de_rastreabilidade()
    test_logs_nao_registram_texto_de_resposta_do_cliente()
    print("\nTodos os testes da Fase 12 (Logs e Auditoria) passaram.")
