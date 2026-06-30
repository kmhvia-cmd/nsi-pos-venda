"""
models/input_models.py

Estruturas de entrada do Motor NSI.
Espelha exatamente o Contrato Oficial do Motor NSI v3.1, Seção 1 (Contrato de Entrada).

Nenhuma lógica de cálculo ou validação de regra de negócio vive aqui — apenas tipos.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Optional


StatusEntrega = Literal[
    "respondido",
    "visualizado_sem_resposta",
    "entregue_sem_visualizacao",
    "nao_entregue",
]


@dataclass
class RespostaCliente:
    """
    Uma resposta individual de cliente dentro de um lote.
    Contrato v3.1, Seção 1.
    """
    cliente_id: str
    telefone: str
    nome: str
    produto: str
    resposta: str
    data_envio_mensagem: datetime
    data_resposta: Optional[datetime]
    status_entrega: StatusEntrega


@dataclass
class Lote:
    """
    Um lote completo de campanha, com todas as respostas associadas.
    Contrato v3.1, Seção 1.

    `segmento` é "generico" quando a empresa não tiver segmento de nicho definido
    (Contrato Seção 4.4) — nesse caso o motor usa apenas subcategorias universais.
    """
    empresa: str
    segmento: str
    lote_id: str
    data_envio: datetime
    quantidade_enviada: int
    quantidade_respondida: int
    respostas: list[RespostaCliente]
