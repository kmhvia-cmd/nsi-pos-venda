"""
tests/unit/test_scheduler_disparar_lote.py

Bloco 2 (Opcao A - fonte unica no webhook, aprovado em revisao arquitetural)
+ Sprint A2 (bloqueio de lote sem registros validos, ADR-007 SS8).

Valida que disparar_lote grava data_envio_mensagem no lote.json para cada
cliente com envio confirmado (HTTP 200), reutilizando adapters.storage.
salvar_lote_atomico (mesma funcao oficial de escrita segura criada no
Bloco 1), sem alterar o comportamento ja existente de status_pipeline/
status (atualizar_status_pipeline/atualizar_status_lote permanecem
intocadas nesta Sprint). services.whatsapp.enviar_template_d8 e mockado -
nenhuma chamada real a WhatsApp Cloud API.

Sprint A2 acrescenta os testes do bloqueio em dois niveis: exclusao em
verificar_lotes_prontos() e recusa deterministica e sem escrita em
disparar_lote(), incluindo compatibilidade com lotes anteriores a esta
sprint (sem total_valido, com ou sem total_clientes).

Usa diretorios temporarios (tmp_path) via monkeypatch em Config - nunca
toca em data/ real.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
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


def _criar_lote_arquivo(tmp_path, monkeypatch, lote_id: str, dados: dict) -> str:
    """
    Cria um lote.json com o conteudo EXATO fornecido - permite simular
    tanto lotes novos (Sprint A2, com status/total_valido) quanto lotes
    legados (sem esses campos), sem impor nenhuma estrutura implicita.
    """
    monkeypatch.setattr(Config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(Config, "LOTES_DIR", tmp_path / "lotes")
    lote_dir = Path(Config.LOTES_DIR) / lote_id
    lote_dir.mkdir(parents=True, exist_ok=True)
    with open(lote_dir / "lote.json", "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)
    return lote_id


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


# ============================================================
# Sprint A2 - bloqueio em dois niveis de lote sem registros validos
# ============================================================

def test_verificar_lotes_prontos_exclui_lote_sem_registros_validos_por_status(tmp_path, monkeypatch):
    criado_em_passado = (datetime.now() - timedelta(days=9)).isoformat()

    id_bloqueado = _criar_lote_arquivo(tmp_path, monkeypatch, "NSI-TESTE-BLOQ1", {
        "lote_id": "NSI-TESTE-BLOQ1", "empresa": "empresa teste",
        "status": "sem_registros_validos", "total_valido": 0,
        "criado_em": criado_em_passado,
        "status_pipeline": {"lote_criado": True, "disparo_whatsapp": False},
        "clientes": [],
    })
    # Controle positivo: lote valido e pronto (D+8 ja passou) - prova
    # que a ausencia do bloqueado na lista nao e um falso positivo por
    # verificar_lotes_prontos estar simplesmente quebrada.
    id_controle = _criar_lote_arquivo(tmp_path, monkeypatch, "NSI-TESTE-CTRL1", {
        "lote_id": "NSI-TESTE-CTRL1", "empresa": "empresa teste",
        "status": "aguardando_d8", "total_valido": 1,
        "criado_em": criado_em_passado,
        "status_pipeline": {"lote_criado": True, "disparo_whatsapp": False},
        "clientes": [{"nome": "Ana", "telefone": "5511999990000", "produto": "X"}],
    })

    ids_prontos = [p["lote_id"] for p in scheduler.verificar_lotes_prontos()]

    assert id_bloqueado not in ids_prontos
    assert id_controle in ids_prontos
    print("OK: test_verificar_lotes_prontos_exclui_lote_sem_registros_validos_por_status")


def test_verificar_lotes_prontos_exclui_lote_com_total_valido_zero(tmp_path, monkeypatch):
    criado_em_passado = (datetime.now() - timedelta(days=9)).isoformat()

    id_bloqueado = _criar_lote_arquivo(tmp_path, monkeypatch, "NSI-TESTE-BLOQ2", {
        "lote_id": "NSI-TESTE-BLOQ2", "empresa": "empresa teste",
        "status": "aguardando_d8",  # status normal - bloqueio vem da contagem
        "total_valido": 0,
        "criado_em": criado_em_passado,
        "status_pipeline": {"lote_criado": True, "disparo_whatsapp": False},
        "clientes": [],
    })
    id_controle = _criar_lote_arquivo(tmp_path, monkeypatch, "NSI-TESTE-CTRL2", {
        "lote_id": "NSI-TESTE-CTRL2", "empresa": "empresa teste",
        "status": "aguardando_d8", "total_valido": 1,
        "criado_em": criado_em_passado,
        "status_pipeline": {"lote_criado": True, "disparo_whatsapp": False},
        "clientes": [{"nome": "Ana", "telefone": "5511999990000", "produto": "X"}],
    })

    ids_prontos = [p["lote_id"] for p in scheduler.verificar_lotes_prontos()]

    assert id_bloqueado not in ids_prontos
    assert id_controle in ids_prontos
    print("OK: test_verificar_lotes_prontos_exclui_lote_com_total_valido_zero")


def test_disparar_lote_recusa_por_status_sem_registros_validos(tmp_path, monkeypatch):
    lote_id = _criar_lote_arquivo(tmp_path, monkeypatch, "NSI-TESTE-RECUSA1", {
        "lote_id": "NSI-TESTE-RECUSA1", "empresa": "empresa teste",
        "status": "sem_registros_validos", "total_valido": 0,
        "status_pipeline": {"disparo_whatsapp": False},
        "clientes": [],
    })

    resultado = scheduler.disparar_lote(lote_id)

    assert resultado["recusado"] is True
    print("OK: test_disparar_lote_recusa_por_status_sem_registros_validos")


def test_disparar_lote_status_prevalece_mesmo_com_total_valido_inconsistente(tmp_path, monkeypatch):
    # total_valido incorretamente maior que zero - o status, como
    # regra principal, prevalece e bloqueia mesmo assim.
    lote_id = _criar_lote_arquivo(tmp_path, monkeypatch, "NSI-TESTE-INCONSIST1", {
        "lote_id": "NSI-TESTE-INCONSIST1", "empresa": "empresa teste",
        "status": "sem_registros_validos", "total_valido": 5,
        "status_pipeline": {"disparo_whatsapp": False},
        "clientes": [{"nome": "Ana", "telefone": "5511999990000", "produto": "X"}],
    })

    resultado = scheduler.disparar_lote(lote_id)

    assert resultado["recusado"] is True
    print("OK: test_disparar_lote_status_prevalece_mesmo_com_total_valido_inconsistente")


def test_disparar_lote_total_valido_zero_bloqueia_com_status_diferente(tmp_path, monkeypatch):
    lote_id = _criar_lote_arquivo(tmp_path, monkeypatch, "NSI-TESTE-ZERO2", {
        "lote_id": "NSI-TESTE-ZERO2", "empresa": "empresa teste",
        "status": "aguardando_d8", "total_valido": 0,
        "status_pipeline": {"disparo_whatsapp": False},
        "clientes": [],
    })

    resultado = scheduler.disparar_lote(lote_id)

    assert resultado["recusado"] is True
    print("OK: test_disparar_lote_total_valido_zero_bloqueia_com_status_diferente")


def test_disparar_lote_recusa_nao_chama_whatsapp(tmp_path, monkeypatch):
    lote_id = _criar_lote_arquivo(tmp_path, monkeypatch, "NSI-TESTE-RECUSA2", {
        "lote_id": "NSI-TESTE-RECUSA2", "empresa": "empresa teste",
        "status": "sem_registros_validos", "total_valido": 0,
        "status_pipeline": {"disparo_whatsapp": False},
        "clientes": [],
    })

    def _falha_se_chamado(*args, **kwargs):
        raise AssertionError("enviar_template_d8 nao deveria ser chamado na recusa")

    monkeypatch.setattr(whatsapp, "enviar_template_d8", _falha_se_chamado)

    resultado = scheduler.disparar_lote(lote_id)

    assert resultado["recusado"] is True
    print("OK: test_disparar_lote_recusa_nao_chama_whatsapp")


def test_disparar_lote_recusa_nao_regrava_arquivo_nem_pipeline(tmp_path, monkeypatch):
    lote_id = _criar_lote_arquivo(tmp_path, monkeypatch, "NSI-TESTE-RECUSA3", {
        "lote_id": "NSI-TESTE-RECUSA3", "empresa": "empresa teste",
        "status": "sem_registros_validos", "total_valido": 0,
        "status_pipeline": {"disparo_whatsapp": False},
        "clientes": [],
    })
    caminho = Path(Config.LOTES_DIR) / lote_id / "lote.json"
    conteudo_antes = caminho.read_bytes()

    resultado = scheduler.disparar_lote(lote_id)

    assert resultado["recusado"] is True
    # Nenhuma escrita ocorreu - o arquivo permanece byte-a-byte identico.
    assert caminho.read_bytes() == conteudo_antes

    lote_apos = _carregar_lote_bruto(lote_id)
    assert lote_apos["status_pipeline"]["disparo_whatsapp"] is False
    assert lote_apos["status"] == "sem_registros_validos"
    print("OK: test_disparar_lote_recusa_nao_regrava_arquivo_nem_pipeline")


def test_lote_anterior_a_sprint_a2_sem_total_valido_e_sem_total_clientes_mantem_comportamento(tmp_path, monkeypatch):
    # Fixture identica ao padrao legado usado pelos demais testes deste
    # arquivo - sem total_valido, sem total_clientes, apenas "clientes"
    # - como em lotes criados antes da Sprint A2. Fallback em cascata
    # (_contar_validos) deve chegar a len(clientes) e nao bloquear.
    lote_id = _criar_lote_de_teste(tmp_path, monkeypatch)
    monkeypatch.setattr(
        whatsapp, "enviar_template_d8",
        lambda telefone, nome, empresa, produto: {"status": 200, "resposta": {}},
    )

    resultado = scheduler.disparar_lote(lote_id)

    assert "recusado" not in resultado
    assert resultado["enviados"] == 2
    print("OK: test_lote_anterior_a_sprint_a2_sem_total_valido_e_sem_total_clientes_mantem_comportamento")


def test_lote_anterior_a_sprint_a2_com_total_clientes_mantem_comportamento(tmp_path, monkeypatch):
    # Lote legado que possui total_clientes (mas nao total_valido) -
    # fallback em cascata usa total_clientes, sem bloquear.
    lote_id = _criar_lote_arquivo(tmp_path, monkeypatch, "NSI-TESTE-LEGADO2", {
        "lote_id": "NSI-TESTE-LEGADO2", "empresa": "empresa teste",
        "status": "aguardando_d8", "total_clientes": 2,
        "status_pipeline": {"disparo_whatsapp": False},
        "clientes": [
            {"nome": "Cliente Um", "telefone": "5511999990000", "produto": "Produto X"},
            {"nome": "Cliente Dois", "telefone": "5511999990001", "produto": "Produto Y"},
        ],
    })
    monkeypatch.setattr(
        whatsapp, "enviar_template_d8",
        lambda telefone, nome, empresa, produto: {"status": 200, "resposta": {}},
    )

    resultado = scheduler.disparar_lote(lote_id)

    assert "recusado" not in resultado
    assert resultado["enviados"] == 2
    print("OK: test_lote_anterior_a_sprint_a2_com_total_clientes_mantem_comportamento")


if __name__ == "__main__":
    print("Rode com: pytest tests/unit/test_scheduler_disparar_lote.py")
