"""
tests/unit/test_storage_salvar_resposta_cliente.py

Bloco 1 (Opcao A - fonte unica no webhook, aprovado em revisao arquitetural).

Valida que salvar_resposta_cliente:
  1. Atualiza o registro do cliente dentro do proprio lote.json (fonte
     oficial), gravando resposta, data_resposta e status_entrega="respondido".
  2. Continua gravando o log bruto de auditoria em
     data/empresas/<slug>/respostas/ (mantido por decisao explicita do
     projeto - nao e fonte de verdade, nao e lido por nenhum modulo).
  3. Nao altera o lote quando o telefone nao pertence a nenhum cliente.

Usa diretorios temporarios (tmp_path) via monkeypatch em Config - nunca
toca em data/ real.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config import Config
from adapters import storage


def _criar_lote_de_teste(tmp_path, monkeypatch) -> str:
    monkeypatch.setattr(Config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(Config, "LOTES_DIR", tmp_path / "lotes")

    lote_id = "NSI-TESTE-000001"
    lote_dir = Path(Config.LOTES_DIR) / lote_id
    lote_dir.mkdir(parents=True)

    lote = {
        "lote_id": lote_id,
        "empresa": "empresa teste",
        "clientes": [
            {
                "nome": "Cliente Um",
                "telefone": "5511999990000",
                "produto": "Produto X",
                "resposta": "",
            }
        ],
    }
    with open(lote_dir / "lote.json", "w", encoding="utf-8") as f:
        json.dump(lote, f, ensure_ascii=False, indent=2)

    return lote_id


def test_salvar_resposta_cliente_atualiza_lote_json_como_fonte_oficial(tmp_path, monkeypatch):
    lote_id = _criar_lote_de_teste(tmp_path, monkeypatch)

    resultado = storage.salvar_resposta_cliente(lote_id, "5511999990000", "Adorei o atendimento!")

    assert resultado["salvo"] is True

    lote_atualizado = storage.carregar_lote(lote_id)
    cliente = lote_atualizado["clientes"][0]
    assert cliente["resposta"] == "Adorei o atendimento!"
    assert cliente["status_entrega"] == "respondido"
    assert cliente["data_resposta"]
    print("OK: test_salvar_resposta_cliente_atualiza_lote_json_como_fonte_oficial")


def test_salvar_resposta_cliente_mantem_log_bruto_de_auditoria(tmp_path, monkeypatch):
    lote_id = _criar_lote_de_teste(tmp_path, monkeypatch)

    storage.salvar_resposta_cliente(lote_id, "5511999990000", "Excelente!")

    caminho_log = Path(Config.DATA_DIR) / "empresas" / "empresa_teste" / "respostas" / f"{lote_id}_5511999990000.json"
    assert caminho_log.exists()

    with open(caminho_log, encoding="utf-8") as f:
        log = json.load(f)
    assert log["resposta"] == "Excelente!"
    print("OK: test_salvar_resposta_cliente_mantem_log_bruto_de_auditoria")


def test_salvar_resposta_cliente_telefone_nao_encontrado_nao_altera_lote(tmp_path, monkeypatch):
    lote_id = _criar_lote_de_teste(tmp_path, monkeypatch)

    resultado = storage.salvar_resposta_cliente(lote_id, "0000000000000", "texto")

    assert "erro" in resultado

    lote_intacto = storage.carregar_lote(lote_id)
    cliente = lote_intacto["clientes"][0]
    assert cliente["resposta"] == ""
    assert "status_entrega" not in cliente
    print("OK: test_salvar_resposta_cliente_telefone_nao_encontrado_nao_altera_lote")


if __name__ == "__main__":
    print("Rode com: pytest tests/unit/test_storage_salvar_resposta_cliente.py")
