# -*- coding: utf-8 -*-
"""
NSI — core/dispatcher.py
Responsabilidade: orquestrar a requisição HTTP de processamento de um
lote, delegando integralmente à Integration Layer.

Este módulo NÃO conhece storage.py, lote.json, catalog.loader nem
engine.pipeline diretamente — conhece apenas integration.nsi_integration,
conforme a arquitetura aprovada. Qualquer mudança em como o lote é
montado ou em como o Motor é composto vive em integration/, nunca aqui.
"""
from __future__ import annotations

from integration.nsi_integration import executar_pipeline_nsi


def processar_lote(lote_id: str) -> dict:
    """
    Processa um lote através do Motor NSI via Integration Layer.

    Mantém a mesma assinatura pública já consumida por app.py
    (rota POST /lote/<lote_id>/analisar) — só o corpo da função mudou,
    de iteração cliente-a-cliente com o motor legado para uma única
    chamada ao Motor real através da Integration Layer.
    """
    saida = executar_pipeline_nsi(lote_id)

    return {
        "lote_id": lote_id,
        "status": saida.status_semantico,
        "empresa": saida.empresa,
        "total_respostas": len(saida.respostas_individuais),
    }