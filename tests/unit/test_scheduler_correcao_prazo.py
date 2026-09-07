"""
tests/unit/test_scheduler_correcao_prazo.py

Sprint A3 (ADR-007 SS9) - orquestracao do fluxo de correcao:
processar_uma_correcao, processar_lote_correcoes, processar_correcao_csv.
Cobre prazo M0+192h (fronteira exata via relogio controlado), escopo
por Operacao (lote_id), estados de recusa, concorrencia/deadlock.
Nenhuma rota HTTP e testada - nao existem nesta sprint (app.py intocado).

Usa diretorios temporarios (tmp_path) via monkeypatch em Config - nunca
toca em data/ real.
"""

from __future__ import annotations

import json
import sys
import threading
import uuid as uuid_module
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config import Config
from core import scheduler
from adapters import storage


def _config_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(Config, "LOTES_DIR", tmp_path / "lotes")


def _criar_lote_bruto(tmp_path, monkeypatch, lote_id: str, dados: dict) -> str:
    _config_dirs(tmp_path, monkeypatch)
    lote_dir = Path(Config.LOTES_DIR) / lote_id
    lote_dir.mkdir(parents=True, exist_ok=True)
    with open(lote_dir / "lote.json", "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)
    return lote_id


def _lote_com_um_invalido(tmp_path, monkeypatch, codigo: str, criado_em: str) -> str:
    return _criar_lote_bruto(tmp_path, monkeypatch, "NSI-TESTE-SCHED1", {
        "lote_id": "NSI-TESTE-SCHED1", "empresa": "Empresa Teste",
        "criado_em": criado_em,
        "status": "sem_registros_validos",
        "total_recebido": 1, "total_valido": 0, "total_invalido": 1, "total_clientes": 0,
        "clientes": [],
        "clientes_invalidos": [{
            "registro_coleta_id": codigo,
            "nome_bruto": "Ana", "whatsapp_bruto": "abc", "produto_bruto": "Produto X",
            "motivos": ["whatsapp_caracteres_invalidos"],
        }],
    })


def _dentro_do_prazo() -> str:
    return (datetime.now() - timedelta(hours=1)).isoformat()


def _apos_o_prazo() -> str:
    return (datetime.now() - timedelta(hours=193)).isoformat()


def test_processar_uma_correcao_aceita(tmp_path, monkeypatch):
    codigo = str(uuid_module.uuid4())
    lote_id = _lote_com_um_invalido(tmp_path, monkeypatch, codigo, _dentro_do_prazo())

    resultado = scheduler.processar_uma_correcao(lote_id, codigo, "Ana Silva", "(11) 98765-4321", "Produto X")

    assert resultado["status"] == "aceita"
    lote = storage.carregar_lote(lote_id)
    assert storage._buscar_em_clientes(lote, codigo) is not None
    print("OK: test_processar_uma_correcao_aceita")


def test_processar_uma_correcao_ainda_invalida(tmp_path, monkeypatch):
    codigo = str(uuid_module.uuid4())
    lote_id = _lote_com_um_invalido(tmp_path, monkeypatch, codigo, _dentro_do_prazo())

    # 12 digitos (comprimento valido: 55 + DDD + 8 locais), DDD "00"
    # invalido - exercita especificamente whatsapp_ddd_invalido, nao
    # whatsapp_comprimento_invalido.
    resultado = scheduler.processar_uma_correcao(lote_id, codigo, "Ana", "550091234567", "Produto X")

    assert resultado["status"] == "ainda_invalida"
    assert "whatsapp_ddd_invalido" in resultado["motivos"]
    print("OK: test_processar_uma_correcao_ainda_invalida")


# ============================================================
# Fronteira temporal deterministica (relogio controlado via 'agora')
# ============================================================

def test_processar_uma_correcao_um_microssegundo_antes_da_fronteira_e_aceita(tmp_path, monkeypatch):
    m0 = datetime(2026, 1, 1, 0, 0, 0)
    fronteira = m0 + timedelta(hours=192)
    codigo = str(uuid_module.uuid4())
    lote_id = _lote_com_um_invalido(tmp_path, monkeypatch, codigo, m0.isoformat())

    resultado = scheduler.processar_uma_correcao(
        lote_id, codigo, "Ana", "(11) 98765-4321", "Produto X",
        agora=fronteira - timedelta(microseconds=1),
    )

    assert resultado["status"] == "aceita"
    print("OK: test_processar_uma_correcao_um_microssegundo_antes_da_fronteira_e_aceita")


def test_processar_uma_correcao_exatamente_na_fronteira_e_tardia(tmp_path, monkeypatch):
    m0 = datetime(2026, 1, 1, 0, 0, 0)
    fronteira = m0 + timedelta(hours=192)
    codigo = str(uuid_module.uuid4())
    lote_id = _lote_com_um_invalido(tmp_path, monkeypatch, codigo, m0.isoformat())

    resultado = scheduler.processar_uma_correcao(
        lote_id, codigo, "Ana", "(11) 98765-4321", "Produto X",
        agora=fronteira,
    )

    assert resultado["status"] == "correcao_tardia"
    lote = storage.carregar_lote(lote_id)
    assert "historico_versoes" not in lote  # nada foi tocado
    print("OK: test_processar_uma_correcao_exatamente_na_fronteira_e_tardia")


def test_processar_uma_correcao_um_microssegundo_depois_da_fronteira_e_tardia(tmp_path, monkeypatch):
    m0 = datetime(2026, 1, 1, 0, 0, 0)
    fronteira = m0 + timedelta(hours=192)
    codigo = str(uuid_module.uuid4())
    lote_id = _lote_com_um_invalido(tmp_path, monkeypatch, codigo, m0.isoformat())

    resultado = scheduler.processar_uma_correcao(
        lote_id, codigo, "Ana", "(11) 98765-4321", "Produto X",
        agora=fronteira + timedelta(microseconds=1),
    )

    assert resultado["status"] == "correcao_tardia"
    print("OK: test_processar_uma_correcao_um_microssegundo_depois_da_fronteira_e_tardia")


def test_processar_uma_correcao_apos_prazo_real(tmp_path, monkeypatch):
    codigo = str(uuid_module.uuid4())
    lote_id = _lote_com_um_invalido(tmp_path, monkeypatch, codigo, _apos_o_prazo())

    resultado = scheduler.processar_uma_correcao(lote_id, codigo, "Ana", "(11) 98765-4321", "Produto X")

    assert resultado["status"] == "correcao_tardia"
    print("OK: test_processar_uma_correcao_apos_prazo_real")


# ============================================================
# Escopo por Operacao / codigo inexistente / ja valido
# ============================================================

def test_processar_uma_correcao_codigo_inexistente(tmp_path, monkeypatch):
    lote_id = _lote_com_um_invalido(tmp_path, monkeypatch, str(uuid_module.uuid4()), _dentro_do_prazo())
    codigo_nunca_usado = str(uuid_module.uuid4())

    resultado = scheduler.processar_uma_correcao(lote_id, codigo_nunca_usado, "Ana", "5511987654321", "Produto X")

    assert resultado["status"] == "codigo_inexistente"
    print("OK: test_processar_uma_correcao_codigo_inexistente")


def test_processar_uma_correcao_registro_de_outra_operacao(tmp_path, monkeypatch):
    codigo_em_outro_lote = str(uuid_module.uuid4())
    _criar_lote_bruto(tmp_path, monkeypatch, "NSI-TESTE-SCHED2", {
        "lote_id": "NSI-TESTE-SCHED2", "empresa": "Outra Empresa", "criado_em": _dentro_do_prazo(),
        "clientes": [], "clientes_invalidos": [
            {"registro_coleta_id": codigo_em_outro_lote, "nome_bruto": "Bruno", "whatsapp_bruto": "x", "produto_bruto": "Y", "motivos": []},
        ],
    })
    lote_id = _lote_com_um_invalido(tmp_path, monkeypatch, str(uuid_module.uuid4()), _dentro_do_prazo())

    resultado = scheduler.processar_uma_correcao(lote_id, codigo_em_outro_lote, "Bruno", "5511987654321", "Y")

    assert resultado["status"] == "registro_de_outra_operacao"
    outro_lote = storage.carregar_lote("NSI-TESTE-SCHED2")
    assert "historico_versoes" not in outro_lote  # nunca aceito fora do lote informado
    print("OK: test_processar_uma_correcao_registro_de_outra_operacao")


def test_processar_uma_correcao_registro_ja_valido(tmp_path, monkeypatch):
    codigo = str(uuid_module.uuid4())
    lote_id = _criar_lote_bruto(tmp_path, monkeypatch, "NSI-TESTE-SCHED3", {
        "lote_id": "NSI-TESTE-SCHED3", "empresa": "E", "criado_em": _dentro_do_prazo(),
        "clientes": [{"registro_coleta_id": codigo, "nome": "Ana", "telefone": "5511987654321", "produto": "X", "resposta": ""}],
        "clientes_invalidos": [],
    })

    resultado = scheduler.processar_uma_correcao(lote_id, codigo, "Ana Nova", "5511987654322", "Y")

    assert resultado["status"] == "registro_ja_valido"
    lote = storage.carregar_lote(lote_id)
    assert lote["clientes"][0]["nome"] == "Ana"  # inalterado
    assert "historico_versoes" not in lote
    print("OK: test_processar_uma_correcao_registro_ja_valido")


def test_processar_uma_correcao_codigo_ausente_nao_faz_busca(tmp_path, monkeypatch):
    """Codigo ausente/malformado nunca dispara busca (local ou global)."""
    lote_id = _lote_com_um_invalido(tmp_path, monkeypatch, str(uuid_module.uuid4()), _dentro_do_prazo())

    def _falha_se_chamado(*args, **kwargs):
        raise AssertionError("_existe_em_outro_lote nao deveria ser chamado para codigo ausente/invalido")

    monkeypatch.setattr(storage, "_existe_em_outro_lote", _falha_se_chamado)

    resultado_vazio = scheduler.processar_uma_correcao(lote_id, "", "Ana", "5511987654321", "X")
    resultado_malformado = scheduler.processar_uma_correcao(lote_id, "abc-nao-e-uuid", "Ana", "5511987654321", "X")

    assert resultado_vazio["status"] == "codigo_tecnico_ausente"
    assert resultado_malformado["status"] == "codigo_tecnico_invalido"
    print("OK: test_processar_uma_correcao_codigo_ausente_nao_faz_busca")


# ============================================================
# Processamento em lote / CSV completo
# ============================================================

def test_processar_lote_correcoes_contagens_agregadas(tmp_path, monkeypatch):
    codigo_ok = str(uuid_module.uuid4())
    codigo_ainda_invalido = str(uuid_module.uuid4())
    lote_id = _criar_lote_bruto(tmp_path, monkeypatch, "NSI-TESTE-SCHED4", {
        "lote_id": "NSI-TESTE-SCHED4", "empresa": "E", "criado_em": _dentro_do_prazo(),
        "clientes": [], "clientes_invalidos": [
            {"registro_coleta_id": codigo_ok, "nome_bruto": "Ana", "whatsapp_bruto": "abc", "produto_bruto": "X", "motivos": ["whatsapp_caracteres_invalidos"]},
            {"registro_coleta_id": codigo_ainda_invalido, "nome_bruto": "Bruno", "whatsapp_bruto": "abc", "produto_bruto": "Y", "motivos": ["whatsapp_caracteres_invalidos"]},
        ],
    })

    linhas = [
        {"codigo_tecnico": codigo_ok, "nome": "Ana", "whatsapp": "(11) 98765-4321", "produto": "X"},
        {"codigo_tecnico": codigo_ainda_invalido, "nome": "Bruno", "whatsapp": "00123", "produto": "Y"},
        {"codigo_tecnico": str(uuid_module.uuid4()), "nome": "C", "whatsapp": "1", "produto": "Z"},  # inexistente
        {"codigo_tecnico": "", "nome": "D", "whatsapp": "1", "produto": "W"},  # ausente
    ]
    resultado = scheduler.processar_lote_correcoes(lote_id, linhas)

    assert resultado["total_recebido"] == 4
    assert resultado["total_aceito"] == 1
    assert resultado["total_ainda_invalido"] == 1
    assert resultado["total_recusado"] == 2
    print("OK: test_processar_lote_correcoes_contagens_agregadas")


def test_processar_correcao_csv_estrutural_invalido_nao_processa_nada(tmp_path, monkeypatch):
    lote_id = _lote_com_um_invalido(tmp_path, monkeypatch, str(uuid_module.uuid4()), _dentro_do_prazo())
    csv_invalido = "codigo_tecnico,nome,whatsapp\nx,Ana,551199999\n"  # falta 'produto'

    resultado = scheduler.processar_correcao_csv(lote_id, csv_invalido)

    assert "erro" in resultado
    lote = storage.carregar_lote(lote_id)
    assert "historico_versoes" not in lote
    assert not (Path(Config.DATA_DIR) / "correcoes_rejeitadas").exists()
    print("OK: test_processar_correcao_csv_estrutural_invalido_nao_processa_nada")


def test_processar_correcao_csv_somente_cabecalho_nao_cria_nada(tmp_path, monkeypatch):
    """CSV so com cabecalho -> csv_correcao_sem_registros, sem
    historico nem auditoria por linha."""
    lote_id = _lote_com_um_invalido(tmp_path, monkeypatch, str(uuid_module.uuid4()), _dentro_do_prazo())
    csv_so_cabecalho = "codigo_tecnico,nome,whatsapp,produto\n"

    resultado = scheduler.processar_correcao_csv(lote_id, csv_so_cabecalho)

    assert resultado == {"erro": "csv_correcao_sem_registros"}
    lote = storage.carregar_lote(lote_id)
    assert "historico_versoes" not in lote
    assert not (Path(Config.DATA_DIR) / "correcoes_rejeitadas").exists()
    print("OK: test_processar_correcao_csv_somente_cabecalho_nao_cria_nada")


# ============================================================
# Concorrencia
# ============================================================

def test_processar_uma_correcao_nao_causa_deadlock(tmp_path, monkeypatch):
    """
    Reproduz o cenario de deadlock corrigido: se _escrever_lote_em_disco
    nao existisse e o codigo chamasse salvar_lote_atomico (que readquire
    o mesmo threading.Lock, nao reentrante) de dentro da secao ja
    protegida, este teste travaria. Usa thread daemon + join(timeout)
    para detectar o travamento sem travar a suite inteira.
    """
    codigo = str(uuid_module.uuid4())
    lote_id = _lote_com_um_invalido(tmp_path, monkeypatch, codigo, _dentro_do_prazo())
    resultado_thread = {}

    def _executar():
        resultado_thread["valor"] = scheduler.processar_uma_correcao(
            lote_id, codigo, "Ana Silva", "(11) 98765-4321", "Produto X"
        )

    thread = threading.Thread(target=_executar, daemon=True)
    thread.start()
    thread.join(timeout=5)

    assert not thread.is_alive(), "processar_uma_correcao travou - possivel deadlock no lock do lote"
    assert resultado_thread.get("valor", {}).get("status") == "aceita"
    print("OK: test_processar_uma_correcao_nao_causa_deadlock")


def test_duas_correcoes_concorrentes_ao_mesmo_registro_sem_perda(tmp_path, monkeypatch):
    """
    Duas threads corrigem SIMULTANEAMENTE o mesmo registro, ambas com
    conteudo AINDA invalido (para que a primeira nunca transforme o
    registro em valido e cause registro_ja_valido na segunda). Prova:
    nenhuma trava, nenhuma atualizacao se perde, numero_versao sem
    repeticao/sem lacunas, cadeia versao_anterior_id correta, lote.json
    final valido, e o estado final corresponde a versao mais recente
    (qualquer que tenha sido a ultima serializada pelo lock).
    """
    codigo = str(uuid_module.uuid4())
    lote_id = _lote_com_um_invalido(tmp_path, monkeypatch, codigo, _dentro_do_prazo())
    resultados = {}

    def _corrigir(indice, whatsapp_bruto):
        resultados[indice] = scheduler.processar_uma_correcao(
            lote_id, codigo, f"Ana {indice}", whatsapp_bruto, "Produto X"
        )

    t1 = threading.Thread(target=_corrigir, args=(1, "00111"), daemon=True)  # DDD 00 invalido
    t2 = threading.Thread(target=_corrigir, args=(2, "10111"), daemon=True)  # DDD 10 invalido

    t1.start()
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)

    assert not t1.is_alive() and not t2.is_alive(), "uma das correcoes concorrentes travou"
    assert resultados[1]["status"] == "ainda_invalida"
    assert resultados[2]["status"] == "ainda_invalida"

    lote = storage.carregar_lote(lote_id)
    versoes = lote["historico_versoes"][codigo]

    # v1 (reconstruida) + duas correcoes concorrentes = 3 versoes, sem lacunas
    numeros = [v["numero_versao"] for v in versoes]
    assert numeros == [1, 2, 3]
    assert len(set(numeros)) == 3  # nenhuma repeticao

    # cadeia versao_anterior_id correta, em qualquer ordem de execucao
    for i in range(1, len(versoes)):
        assert versoes[i]["versao_anterior_id"] == versoes[i - 1]["registro_coleta_versao_id"]

    # lote.json final e valido - carregavel, unico registro em invalidos
    assert len(lote["clientes_invalidos"]) == 1
    assert len(lote["clientes"]) == 0

    # o estado final corresponde exatamente a versao mais recente (a
    # ultima efetivamente serializada pelo lock) - nunca uma mistura
    corrente = versoes[-1]
    assert corrente["whatsapp_bruto"] in ("00111", "10111")
    invalido_atual = lote["clientes_invalidos"][0]
    assert invalido_atual["whatsapp_bruto"] == corrente["whatsapp_bruto"]
    print("OK: test_duas_correcoes_concorrentes_ao_mesmo_registro_sem_perda")


if __name__ == "__main__":
    print("Rode com: pytest tests/unit/test_scheduler_correcao_prazo.py")
