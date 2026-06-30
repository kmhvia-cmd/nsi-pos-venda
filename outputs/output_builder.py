from __future__ import annotations
from dataclasses import asdict
from datetime import datetime
from typing import Any
from models.output_models import ModeloClassificacao, RespostaIndividualCompleta, ResultadoEvolucaoTemporal, ResultadoExecutivo, ResultadoExperienciaHumanaAgregado, ResultadoLinguisticoAgregado, ResultadoMatematico, ResultadoSemantico, SaidaMotorCompleta

VERSAO_MOTOR = "3.1"

class ErroSchemaInvalido(Exception):
    pass

def _validar_saida_completa(saida: SaidaMotorCompleta) -> None:
    erros = []
    if not saida.empresa: erros.append("empresa: obrigatorio")
    if not saida.lote_id: erros.append("lote_id: obrigatorio")
    if saida.matematica is None: erros.append("matematica: obrigatorio")
    if saida.linguistica_agregada is None: erros.append("linguistica_agregada: obrigatorio")
    if saida.status_semantico == "concluido":
        if saida.semantica is None: erros.append("semantica: obrigatorio quando concluido")
        if saida.executiva is None: erros.append("executiva: obrigatorio quando concluido")
    if saida.status_semantico == "pendente":
        if saida.semantica is not None: erros.append("semantica: deve ser None quando pendente")
        if saida.executiva is not None: erros.append("executiva: deve ser None quando pendente")
    if erros:
        raise ErroSchemaInvalido("\n".join(erros))

def montar_saida_completa(empresa, segmento, lote_id, versao_catalogo, modelo_classificacao, matematica, linguistica_agregada, semantica, experiencia_humana_agregada, evolucao_temporal, executiva, respostas_individuais, evidencias_semanticas_validas) -> SaidaMotorCompleta:
    saida = SaidaMotorCompleta(empresa=empresa, segmento=segmento, lote_id=lote_id, data_processamento=datetime.now(), versao_motor=VERSAO_MOTOR, versao_catalogo=versao_catalogo, status_semantico="concluido", evidencias_semanticas_validas=evidencias_semanticas_validas, modelo_classificacao=modelo_classificacao, matematica=matematica, linguistica_agregada=linguistica_agregada, semantica=semantica, experiencia_humana_agregada=experiencia_humana_agregada, evolucao_temporal=evolucao_temporal, executiva=executiva, respostas_individuais=respostas_individuais)
    _validar_saida_completa(saida)
    return saida

def montar_saida_parcial(empresa, segmento, lote_id, versao_catalogo, modelo_classificacao, matematica, linguistica_agregada) -> SaidaMotorCompleta:
    saida = SaidaMotorCompleta(empresa=empresa, segmento=segmento, lote_id=lote_id, data_processamento=datetime.now(), versao_motor=VERSAO_MOTOR, versao_catalogo=versao_catalogo, status_semantico="pendente", evidencias_semanticas_validas=0, modelo_classificacao=modelo_classificacao, matematica=matematica, linguistica_agregada=linguistica_agregada)
    _validar_saida_completa(saida)
    return saida

def saida_para_dict(saida: SaidaMotorCompleta) -> dict[str, Any]:
    d = asdict(saida)
    d["data_processamento"] = saida.data_processamento.isoformat()
    return d
