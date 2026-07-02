"""
tests/unit/test_scheduler_disparar_lote.py

Bloco 2 (Opcao A - fonte unica no webhook, aprovado em revisao arquitetural).

Valida que disparar_lote grava data_envio_mensagem no lote.json para cada
cliente com envio confirmado (HTTP 200), reutilizando adapters.storage.
salvar_lote_atomico (mesma funcao oficial de escrita segura criada no
Bloco 1), sem alterar o comportamento ja existente de status_pipeline/
status (atualizar_status_pipeline/atualizar_status_lote permanecem
intocadas nesta Sprint). services.whatsapp.enviar_template_d8 e mockado -
nenhuma chamada real a WhatsApp Cloud API.

Usa diretorios temporarios (tmp_path) via monkeypatch em Config - nunca
toca em data/ real.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config import Config
from core import scheduler
import services.whatsapp as whatsapp


def _criar_lote_de_teste(tmp_path, monkeypatch) -> str:
    monkeypatch.setattr(Config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(Config, "LOTES_DIR", tmp_path / "lotes")

    lote_id = "NSI-TESTE-000002"
    lote_dir = Path(Config.LOTES_DIR) / lote_id
    lote_dir.mkdir(parents=True)

    lote = {
        "lote_id": lote_id,
        "empresa": "empresa teste",
        "status": "aguardando_d8",
        "status_pipeline": {"disparo_whatsapp": False},
        "clientes": [
            {"nome": "Cliente Um", "telefone": "5511999990000", "produto": "Produto X"},
            {"nome": "Cliente Dois", "telefone": "5511999990001", "produto": "Produto Y"},
        ],
    }
    with open(lote_dir / "lote.json", "w", encoding="utf-8") as f:
        json.dump(lote, f, ensure_ascii=False, indent=2)

    return lote_id


def _carregar_lote_bruto(lote_id: str) -> dict:
    caminho = Path(Config.LOTES_DIR) / lote_id / "lote.json"
    return json.loads(caminho.read_text(encoding="utf-8"))


def test_disparar_lote_grava_data_envio_mensagem_no_sucesso(tmp_path, monkeypatch):
    lote_id = _criar_lote_de_teste(tmp_path, monkeypatch)
    monkeypatch.setattr(
        whatsapp, "enviar_template_d8",
        lambda telefone, nome, empresa, produto: {"status": 200, "resposta": {"ok": True}},
    )

    resultado = scheduler.disparar_lote(lote_id)

    assert resultado["enviados"] == 2
    assert resultado["erros"] == 0

    lote_atualizado = _carregar_lote_bruto(lote_id)
    for cliente in lote_atualizado["clientes"]:
        assert cliente["data_envio_mensagem"]
    print("OK: test_disparar_lote_grava_data_envio_mensagem_no_sucesso")


def test_disparar_lote_nao_grava_data_envio_mensagem_no_erro(tmp_path, monkeypatch):
    lote_id = _criar_lote_de_teste(tmp_path, monkeypatch)
    monkeypatch.setattr(
        whatsapp, "enviar_template_d8",
        lambda telefone, nome, empresa, produto: {"status": 500, "resposta": {"erro": "falha simulada"}},
    )

    resultado = scheduler.disparar_lote(lote_id)

    assert resultado["enviados"] == 0
    assert resultado["erros"] == 2

    lote_atualizado = _carregar_lote_bruto(lote_id)
    for cliente in lote_atualizado["clientes"]:
        assert "data_envio_mensagem" not in cliente
    print("OK: test_disparar_lote_nao_grava_data_envio_mensagem_no_erro")


def test_disparar_lote_mantem_atualizacao_de_status_pipeline_existente(tmp_path, monkeypatch):
    lote_id = _criar_lote_de_teste(tmp_path, monkeypatch)
    monkeypatch.setattr(
        whatsapp, "enviar_template_d8",
        lambda telefone, nome, empresa, produto: {"status": 200, "resposta": {}},
    )

    scheduler.disparar_lote(lote_id)

    lote_atualizado = _carregar_lote_bruto(lote_id)
    assert lote_atualizado["status_pipeline"]["disparo_whatsapp"] is True
    assert lote_atualizado["status"] == "disparado"
    print("OK: test_disparar_lote_mantem_atualizacao_de_status_pipeline_existente")


def test_disparar_lote_cliente_sem_telefone_nao_recebe_data_envio(tmp_path, monkeypatch):
    lote_id = _criar_lote_de_teste(tmp_path, monkeypatch)
    lote_dir = Path(Config.LOTES_DIR) / lote_id
    lote = _carregar_lote_bruto(lote_id)
    lote["clientes"].append({"nome": "Sem Telefone", "telefone": "", "produto": "Z"})
    with open(lote_dir / "lote.json", "w", encoding="utf-8") as f:
        json.dump(lote, f, ensure_ascii=False, indent=2)

    monkeypatch.setattr(
        whatsapp, "enviar_template_d8",
        lambda telefone, nome, empresa, produto: {"status": 200, "resposta": {}},
    )

    resultado = scheduler.disparar_lote(lote_id)

    assert resultado["erros"] == 1
    lote_atualizado = _carregar_lote_bruto(lote_id)
    cliente_sem_telefone = next(c for c in lote_atualizado["clientes"] if c["nome"] == "Sem Telefone")
    assert "data_envio_mensagem" not in cliente_sem_telefone
    print("OK: test_disparar_lote_cliente_sem_telefone_nao_recebe_data_envio")


if __name__ == "__main__":
    print("Rode com: pytest tests/unit/test_scheduler_disparar_lote.py")
