"""
tests/integration/test_nsi_integration_status_entrega.py

Bloco 3 (Opcao A - fonte unica no webhook, aprovado em revisao arquitetural).

Valida a REGRA DO CONJUNTO COMPLETO em
integration/nsi_integration.py::_montar_resposta_cliente: um cliente so
e promovido a status_entrega="respondido" perante o Motor quando os tres
fatos observados (status_entrega, data_resposta, data_envio_mensagem)
estiverem TODOS presentes na fonte legada (lote.json). Nenhum fallback,
nenhuma data aproximada, nenhuma inferencia a partir de dado parcial.

O ultimo teste (test_montar_lote_com_fato_incompleto_nao_quebra_motor)
reproduz o cenario de risco identificado antes da implementacao: um
cliente respondeu (via webhook) mas o lote nunca foi de fato disparado
(sem data_envio_mensagem) - confirma que processors/math_processor.py
(nao alterado) nao quebra com TypeError nesse caso.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config import Config
from integration.nsi_integration import _montar_lote, _montar_resposta_cliente
from processors.math_processor import processar_matematica


def test_conjunto_completo_promove_para_respondido():
    cliente = {
        "nome": "Cliente Um",
        "telefone": "5511999990000",
        "produto": "Produto X",
        "resposta": "Adorei o atendimento!",
        "status_entrega": "respondido",
        "data_resposta": "2026-06-04T13:49:34.317612",
        "data_envio_mensagem": "2026-06-01T09:00:00",
    }

    resposta = _montar_resposta_cliente(cliente)

    assert resposta.status_entrega == "respondido"
    assert resposta.data_resposta == datetime.fromisoformat("2026-06-04T13:49:34.317612")
    assert resposta.data_envio_mensagem == datetime.fromisoformat("2026-06-01T09:00:00")
    print("OK: test_conjunto_completo_promove_para_respondido")


def test_falta_data_envio_mensagem_nao_promove():
    """Cenario de risco: cliente respondeu via webhook, mas disparar_lote nunca rodou."""
    cliente = {
        "nome": "Cliente Dois",
        "telefone": "5511999990001",
        "produto": "Produto X",
        "resposta": "Otimo produto!",
        "status_entrega": "respondido",
        "data_resposta": "2026-06-04T13:49:34.317612",
        # data_envio_mensagem ausente de proposito
    }

    resposta = _montar_resposta_cliente(cliente)

    assert resposta.status_entrega is None
    assert resposta.data_resposta is None
    assert resposta.data_envio_mensagem is None
    print("OK: test_falta_data_envio_mensagem_nao_promove")


def test_falta_data_resposta_nao_promove():
    cliente = {
        "nome": "Cliente Tres",
        "telefone": "5511999990002",
        "produto": "Produto X",
        "resposta": "",
        "status_entrega": "respondido",
        "data_envio_mensagem": "2026-06-01T09:00:00",
        # data_resposta ausente de proposito
    }

    resposta = _montar_resposta_cliente(cliente)

    assert resposta.status_entrega is None
    assert resposta.data_resposta is None
    assert resposta.data_envio_mensagem is None
    print("OK: test_falta_data_resposta_nao_promove")


def test_status_entrega_ausente_nao_promove_mesmo_com_ambas_datas():
    cliente = {
        "nome": "Cliente Quatro",
        "telefone": "5511999990003",
        "produto": "Produto X",
        "resposta": "texto qualquer",
        "data_resposta": "2026-06-04T13:49:34.317612",
        "data_envio_mensagem": "2026-06-01T09:00:00",
        # status_entrega ausente de proposito
    }

    resposta = _montar_resposta_cliente(cliente)

    assert resposta.status_entrega is None
    print("OK: test_status_entrega_ausente_nao_promove_mesmo_com_ambas_datas")


def test_cliente_apenas_com_dados_de_csv_mantem_compatibilidade_anterior():
    """Lote antigo, so com dados de upload (sem Bloco 1/2 aplicados a ele)."""
    cliente = {
        "nome": "Cliente Cinco",
        "telefone": "5511999990004",
        "produto": "Produto X",
        "resposta": "resposta pre-preenchida no CSV",
    }

    resposta = _montar_resposta_cliente(cliente)

    assert resposta.resposta == "resposta pre-preenchida no CSV"
    assert resposta.status_entrega is None
    assert resposta.data_resposta is None
    assert resposta.data_envio_mensagem is None
    print("OK: test_cliente_apenas_com_dados_de_csv_mantem_compatibilidade_anterior")


def test_montar_lote_com_fato_incompleto_nao_quebra_motor(tmp_path, monkeypatch):
    """
    Reproduz o cenario de risco identificado antes da implementacao do
    Bloco 3: um cliente com status_entrega="respondido" e data_resposta
    (via webhook), mas SEM data_envio_mensagem (disparar_lote nunca
    rodou para este lote). Confirma que processar_matematica roda sem
    TypeError e exclui corretamente esse cliente de "respondidas".
    """
    monkeypatch.setattr(Config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(Config, "LOTES_DIR", tmp_path / "lotes")

    lote_id = "NSI-TESTE-RISCO"
    lote_dir = Path(Config.LOTES_DIR) / lote_id
    lote_dir.mkdir(parents=True)

    lote_bruto = {
        "lote_id": lote_id,
        "empresa": "empresa teste",
        "criado_em": "2026-06-01T09:00:00",
        "total_clientes": 2,
        "clientes": [
            {
                "nome": "Cliente Completo",
                "telefone": "5511999990000",
                "produto": "Produto X",
                "resposta": "Gostei muito!",
                "status_entrega": "respondido",
                "data_resposta": "2026-06-01T10:00:00",
                "data_envio_mensagem": "2026-06-01T09:00:00",
            },
            {
                "nome": "Cliente Sem Disparo Registrado",
                "telefone": "5511999990001",
                "produto": "Produto Y",
                "resposta": "Respondeu sem o lote ter sido disparado",
                "status_entrega": "respondido",
                "data_resposta": "2026-06-01T11:00:00",
                # data_envio_mensagem ausente de proposito - cenario de risco
            },
        ],
    }
    with open(lote_dir / "lote.json", "w", encoding="utf-8") as f:
        json.dump(lote_bruto, f, ensure_ascii=False, indent=2)

    lote = _montar_lote(lote_id)

    # Nao pode lancar TypeError (datetime - None) dentro de processar_matematica
    resultado = processar_matematica(lote)

    respondidas_no_lote = [r for r in lote.respostas if r.status_entrega == "respondido"]
    assert len(respondidas_no_lote) == 1
    assert respondidas_no_lote[0].telefone == "5511999990000"
    assert resultado.taxa_resposta == 50.0
    print("OK: test_montar_lote_com_fato_incompleto_nao_quebra_motor")


if __name__ == "__main__":
    print("Rode com: pytest tests/integration/test_nsi_integration_status_entrega.py")
