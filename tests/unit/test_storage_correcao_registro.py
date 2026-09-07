"""
tests/unit/test_storage_correcao_registro.py

Sprint A3 (ADR-007 SS9) - funcoes de camada de dados do fluxo de
correcao: parser do CSV de correcao, validacao de codigo_tecnico
(UUID4), historico append-only (inicializacao tardia e nova versao),
reprojecao de clientes/clientes_invalidos, geracao do relatorio CSV e
auditoria de tentativas recusadas.

Nenhuma rota HTTP e testada aqui - nao existem nesta sprint. Usa
diretorios temporarios (tmp_path) via monkeypatch em Config - nunca
toca em data/ real.
"""

from __future__ import annotations

import io
import json
import sys
import uuid as uuid_module
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config import Config
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


def _lote_com_um_invalido(tmp_path, monkeypatch, codigo: str, criado_em: str | None = None) -> str:
    return _criar_lote_bruto(tmp_path, monkeypatch, "NSI-TESTE-CORR1", {
        "lote_id": "NSI-TESTE-CORR1", "empresa": "Empresa Teste",
        "criado_em": criado_em or datetime.now().isoformat(),
        "status": "sem_registros_validos",
        "total_recebido": 1, "total_valido": 0, "total_invalido": 1, "total_clientes": 0,
        "clientes": [],
        "clientes_invalidos": [{
            "registro_coleta_id": codigo,
            "nome_bruto": "Ana", "whatsapp_bruto": "abc", "produto_bruto": "Produto X",
            "motivos": ["whatsapp_caracteres_invalidos"],
        }],
    })


# ============================================================
# Parser do CSV de correcao
# ============================================================

def test_parser_aceita_cabecalho_em_qualquer_ordem():
    codigo = str(uuid_module.uuid4())
    csv_texto = f"produto,codigo_tecnico,whatsapp,nome\nProduto X,{codigo},5511987654321,Ana\n"
    linhas, erro = storage._parsear_csv_correcao(csv_texto)
    assert erro is None
    assert linhas == [{"codigo_tecnico": codigo, "nome": "Ana", "whatsapp": "5511987654321", "produto": "Produto X"}]
    print("OK: test_parser_aceita_cabecalho_em_qualquer_ordem")


def test_parser_rejeita_coluna_extra():
    csv_texto = "codigo_tecnico,nome,whatsapp,produto,extra\nx,Ana,551199999,Produto X,Sobra\n"
    linhas, erro = storage._parsear_csv_correcao(csv_texto)
    assert linhas == []
    assert "nao reconhecidos" in erro
    print("OK: test_parser_rejeita_coluna_extra")


def test_parser_rejeita_cabecalho_duplicado():
    csv_texto = "codigo_tecnico,codigo_tecnico,whatsapp,produto\nx,y,551199999,Produto X\n"
    linhas, erro = storage._parsear_csv_correcao(csv_texto)
    assert linhas == []
    assert "duplicados" in erro
    print("OK: test_parser_rejeita_cabecalho_duplicado")


def test_parser_rejeita_cabecalho_faltando():
    csv_texto = "codigo_tecnico,nome,whatsapp\nx,Ana,551199999\n"
    linhas, erro = storage._parsear_csv_correcao(csv_texto)
    assert linhas == []
    assert "faltando" in erro and "produto" in erro
    print("OK: test_parser_rejeita_cabecalho_faltando")


def test_parser_rejeita_linha_com_campo_count_errado():
    csv_texto = "codigo_tecnico,nome,whatsapp,produto\nx,Ana,551199999,Produto X,Extra\n"
    linhas, erro = storage._parsear_csv_correcao(csv_texto)
    assert linhas == []
    assert "esperado exatamente 4" in erro
    print("OK: test_parser_rejeita_linha_com_campo_count_errado")


def test_parser_preserva_virgula_entre_aspas():
    csv_texto = 'codigo_tecnico,nome,whatsapp,produto\nx,Ana,551199999,"Treinamento, Nivel 2"\n'
    linhas, erro = storage._parsear_csv_correcao(csv_texto)
    assert erro is None
    assert linhas[0]["produto"] == "Treinamento, Nivel 2"
    print("OK: test_parser_preserva_virgula_entre_aspas")


def test_parser_aceita_bom_em_bytes():
    csv_bytes = "codigo_tecnico,nome,whatsapp,produto\nx,Ana,551199999,Produto X\n".encode("utf-8-sig")
    linhas, erro = storage._parsear_csv_correcao(csv_bytes)
    assert erro is None
    assert linhas[0]["nome"] == "Ana"
    print("OK: test_parser_aceita_bom_em_bytes")


def test_parser_aceita_bom_em_str():
    csv_texto = chr(0xFEFF) + "codigo_tecnico,nome,whatsapp,produto\nx,Ana,551199999,Produto X\n"
    linhas, erro = storage._parsear_csv_correcao(csv_texto)
    assert erro is None
    assert linhas[0]["nome"] == "Ana"
    print("OK: test_parser_aceita_bom_em_str")


def test_parser_rejeita_csv_vazio():
    linhas, erro = storage._parsear_csv_correcao("")
    assert linhas == []
    assert "vazio" in erro
    print("OK: test_parser_rejeita_csv_vazio")


def test_parser_rejeita_csv_somente_cabecalho():
    """Correcao obrigatoria: CSV so com cabecalho -> csv_correcao_sem_registros."""
    csv_texto = "codigo_tecnico,nome,whatsapp,produto\n"
    linhas, erro = storage._parsear_csv_correcao(csv_texto)
    assert linhas == []
    assert erro == "csv_correcao_sem_registros"
    print("OK: test_parser_rejeita_csv_somente_cabecalho")


def test_parser_rejeita_csv_com_apenas_linhas_em_branco():
    csv_texto = "codigo_tecnico,nome,whatsapp,produto\n\n\n"
    linhas, erro = storage._parsear_csv_correcao(csv_texto)
    assert linhas == []
    assert erro == "csv_correcao_sem_registros"
    print("OK: test_parser_rejeita_csv_com_apenas_linhas_em_branco")


# ============================================================
# Validacao de codigo_tecnico (UUID4)
# ============================================================

def test_codigo_tecnico_vazio():
    codigo, motivo = storage._normalizar_codigo_tecnico("")
    assert codigo is None
    assert motivo == "codigo_tecnico_ausente"
    print("OK: test_codigo_tecnico_vazio")


def test_codigo_tecnico_apenas_espacos():
    codigo, motivo = storage._normalizar_codigo_tecnico("   ")
    assert codigo is None
    assert motivo == "codigo_tecnico_ausente"
    print("OK: test_codigo_tecnico_apenas_espacos")


def test_codigo_tecnico_malformado():
    codigo, motivo = storage._normalizar_codigo_tecnico("nao-e-um-uuid")
    assert codigo is None
    assert motivo == "codigo_tecnico_invalido"
    print("OK: test_codigo_tecnico_malformado")


def test_codigo_tecnico_uuid_valido_mas_nao_versao_4():
    # UUID versao 1 (baseado em timestamp/MAC) - sintaticamente valido,
    # mas nao e versao 4.
    uuid_v1 = str(uuid_module.uuid1())
    codigo, motivo = storage._normalizar_codigo_tecnico(uuid_v1)
    assert codigo is None
    assert motivo == "codigo_tecnico_invalido"
    print("OK: test_codigo_tecnico_uuid_valido_mas_nao_versao_4")


def test_codigo_tecnico_uuid4_canonico_valido():
    uuid_v4 = str(uuid_module.uuid4())
    codigo, motivo = storage._normalizar_codigo_tecnico(f"  {uuid_v4}  ")
    assert motivo is None
    assert codigo == uuid_v4
    print("OK: test_codigo_tecnico_uuid4_canonico_valido")


# ============================================================
# Historico append-only
# ============================================================

def test_inicializar_historico_reconstroi_v1_com_recebido_por_legado(tmp_path, monkeypatch):
    codigo = str(uuid_module.uuid4())
    m0 = "2026-08-20T10:00:00"
    lote_id = _lote_com_um_invalido(tmp_path, monkeypatch, codigo, criado_em=m0)
    lote = storage.carregar_lote(lote_id)
    original = storage._buscar_em_clientes_invalidos(lote, codigo)

    storage._inicializar_historico_se_necessario(lote, codigo, original)
    v1 = lote["historico_versoes"][codigo][0]

    assert v1["numero_versao"] == 1
    assert v1["processo"] == "upload_original"
    assert v1["recebido_por"] == "nao_registrado_legado"
    assert v1["recebido_em"] == m0  # igual ao M0 do lote
    assert v1["representacao_historica_reconstituida"] is True
    # representacao_historica_criada_em e posterior/igual a M0
    assert v1["representacao_historica_criada_em"] >= m0
    assert v1["nome_bruto"] == "Ana"
    assert v1["motivos"] == ["whatsapp_caracteres_invalidos"]
    print("OK: test_inicializar_historico_reconstroi_v1_com_recebido_por_legado")


def test_inicializar_historico_nunca_altera_original(tmp_path, monkeypatch):
    codigo = str(uuid_module.uuid4())
    lote_id = _lote_com_um_invalido(tmp_path, monkeypatch, codigo)
    lote = storage.carregar_lote(lote_id)
    original_antes = dict(storage._buscar_em_clientes_invalidos(lote, codigo))

    storage._inicializar_historico_se_necessario(lote, codigo, original_antes)

    original_depois = storage._buscar_em_clientes_invalidos(lote, codigo)
    assert original_depois == original_antes
    print("OK: test_inicializar_historico_nunca_altera_original")


def test_inicializar_historico_e_idempotente(tmp_path, monkeypatch):
    codigo = str(uuid_module.uuid4())
    lote_id = _lote_com_um_invalido(tmp_path, monkeypatch, codigo)
    lote = storage.carregar_lote(lote_id)
    original = storage._buscar_em_clientes_invalidos(lote, codigo)

    storage._inicializar_historico_se_necessario(lote, codigo, original)
    storage._inicializar_historico_se_necessario(lote, codigo, original)  # segunda chamada

    assert len(lote["historico_versoes"][codigo]) == 1  # nunca duplica v1
    print("OK: test_inicializar_historico_e_idempotente")


def test_aplicar_versao_correcao_usa_processo_operador_interno(tmp_path, monkeypatch):
    """Correcao nova (nao reconstruida) usa operador_interno_nao_autenticado
    / upload_correcao_csv."""
    codigo = str(uuid_module.uuid4())
    lote_id = _lote_com_um_invalido(tmp_path, monkeypatch, codigo)
    lote = storage.carregar_lote(lote_id)
    original = storage._buscar_em_clientes_invalidos(lote, codigo)
    storage._inicializar_historico_se_necessario(lote, codigo, original)

    versao = storage._aplicar_versao_correcao(lote, codigo, "Ana Silva", "(11) 98765-4321", "Produto X")

    assert versao["numero_versao"] == 2
    assert versao["processo"] == "upload_correcao_csv"
    assert versao["recebido_por"] == "operador_interno_nao_autenticado"
    assert versao["representacao_historica_reconstituida"] is False
    assert versao["status_versao"] == "valida"
    print("OK: test_aplicar_versao_correcao_usa_processo_operador_interno")


def test_aplicar_versao_correcao_valida_move_para_clientes(tmp_path, monkeypatch):
    codigo = str(uuid_module.uuid4())
    lote_id = _lote_com_um_invalido(tmp_path, monkeypatch, codigo)
    lote = storage.carregar_lote(lote_id)
    original = storage._buscar_em_clientes_invalidos(lote, codigo)
    storage._inicializar_historico_se_necessario(lote, codigo, original)

    storage._aplicar_versao_correcao(lote, codigo, "Ana Silva", "(11) 98765-4321", "Produto X")

    assert storage._buscar_em_clientes(lote, codigo) is not None
    assert storage._buscar_em_clientes_invalidos(lote, codigo) is None
    print("OK: test_aplicar_versao_correcao_valida_move_para_clientes")


def test_aplicar_versao_correcao_invalida_permanece_em_invalidos(tmp_path, monkeypatch):
    codigo = str(uuid_module.uuid4())
    lote_id = _lote_com_um_invalido(tmp_path, monkeypatch, codigo)
    lote = storage.carregar_lote(lote_id)
    original = storage._buscar_em_clientes_invalidos(lote, codigo)
    storage._inicializar_historico_se_necessario(lote, codigo, original)

    versao = storage._aplicar_versao_correcao(lote, codigo, "Ana", "00123", "Produto X")  # DDD 00 invalido

    assert versao["status_versao"] == "invalida"
    assert storage._buscar_em_clientes(lote, codigo) is None
    invalido = storage._buscar_em_clientes_invalidos(lote, codigo)
    assert invalido is not None
    assert invalido["whatsapp_bruto"] == "00123"  # reflete a tentativa mais recente
    print("OK: test_aplicar_versao_correcao_invalida_permanece_em_invalidos")


def test_versionamento_sem_lacunas_em_correcoes_sucessivas(tmp_path, monkeypatch):
    codigo = str(uuid_module.uuid4())
    lote_id = _lote_com_um_invalido(tmp_path, monkeypatch, codigo)
    lote = storage.carregar_lote(lote_id)
    original = storage._buscar_em_clientes_invalidos(lote, codigo)
    storage._inicializar_historico_se_necessario(lote, codigo, original)

    storage._aplicar_versao_correcao(lote, codigo, "Ana", "00123", "Produto X")     # v2 invalida
    storage._aplicar_versao_correcao(lote, codigo, "Ana", "abc", "Produto X")       # v3 invalida
    storage._aplicar_versao_correcao(lote, codigo, "Ana", "(11) 98765-4321", "Produto X")  # v4 valida

    versoes = lote["historico_versoes"][codigo]
    assert [v["numero_versao"] for v in versoes] == [1, 2, 3, 4]
    assert versoes[-1]["status_versao"] == "valida"
    for i, v in enumerate(versoes[1:], start=1):
        assert v["versao_anterior_id"] == versoes[i - 1]["registro_coleta_versao_id"]
    for v in versoes:
        assert "substituida" not in v.values()  # nenhum campo mutavel "substituida"
    print("OK: test_versionamento_sem_lacunas_em_correcoes_sucessivas")


def test_recalcular_contagens_e_status(tmp_path, monkeypatch):
    codigo = str(uuid_module.uuid4())
    lote_id = _lote_com_um_invalido(tmp_path, monkeypatch, codigo)
    lote = storage.carregar_lote(lote_id)
    original = storage._buscar_em_clientes_invalidos(lote, codigo)
    storage._inicializar_historico_se_necessario(lote, codigo, original)
    storage._aplicar_versao_correcao(lote, codigo, "Ana", "(11) 98765-4321", "Produto X")

    total_recebido_antes = lote["total_recebido"]
    storage._recalcular_contagens_e_status(lote)

    assert lote["total_recebido"] == total_recebido_antes  # imutavel
    assert lote["total_valido"] == 1
    assert lote["total_invalido"] == 0
    assert lote["total_clientes"] == lote["total_valido"]
    assert lote["status"] == "aguardando_d8"
    print("OK: test_recalcular_contagens_e_status")


def test_registro_nunca_aparece_em_ambas_as_listas(tmp_path, monkeypatch):
    codigo = str(uuid_module.uuid4())
    lote_id = _lote_com_um_invalido(tmp_path, monkeypatch, codigo)
    lote = storage.carregar_lote(lote_id)
    original = storage._buscar_em_clientes_invalidos(lote, codigo)
    storage._inicializar_historico_se_necessario(lote, codigo, original)
    storage._aplicar_versao_correcao(lote, codigo, "Ana", "(11) 98765-4321", "Produto X")

    ids_validos = {c.get("registro_coleta_id") for c in lote["clientes"]}
    ids_invalidos = {c.get("registro_coleta_id") for c in lote["clientes_invalidos"]}
    assert ids_validos.isdisjoint(ids_invalidos)
    print("OK: test_registro_nunca_aparece_em_ambas_as_listas")


# ============================================================
# Busca em outro lote / relatorio / auditoria
# ============================================================

def test_existe_em_outro_lote_encontra_codigo(tmp_path, monkeypatch):
    codigo = str(uuid_module.uuid4())
    _lote_com_um_invalido(tmp_path, monkeypatch, codigo)
    outro_codigo = str(uuid_module.uuid4())
    _criar_lote_bruto(tmp_path, monkeypatch, "NSI-TESTE-CORR2", {
        "lote_id": "NSI-TESTE-CORR2", "empresa": "Outra Empresa",
        "criado_em": datetime.now().isoformat(), "clientes": [], "clientes_invalidos": [
            {"registro_coleta_id": outro_codigo, "nome_bruto": "Bruno", "whatsapp_bruto": "x", "produto_bruto": "Y", "motivos": []},
        ],
    })
    assert storage._existe_em_outro_lote("NSI-TESTE-CORR1", outro_codigo) is True
    assert storage._existe_em_outro_lote("NSI-TESTE-CORR1", str(uuid_module.uuid4())) is False
    print("OK: test_existe_em_outro_lote_encontra_codigo")


def test_existe_em_outro_lote_atravessa_lote_legado_sem_registro_coleta_id(tmp_path, monkeypatch):
    """
    Correcao obrigatoria: um lote legado (anterior a Sprint A1, sem
    registro_coleta_id em nenhum cliente) nunca deve lancar KeyError
    durante a busca diagnostica - _buscar_em_clientes/_invalidos usam
    .get(), nunca indexacao direta.
    """
    codigo = str(uuid_module.uuid4())
    _lote_com_um_invalido(tmp_path, monkeypatch, codigo)
    _criar_lote_bruto(tmp_path, monkeypatch, "NSI-TESTE-LEGADO", {
        "lote_id": "NSI-TESTE-LEGADO", "empresa": "Empresa Antiga",
        "criado_em": datetime.now().isoformat(),
        "clientes": [{"nome": "Sem Codigo", "telefone": "5511999990000", "produto": "X"}],
        # clientes_invalidos ausente de proposito - simula lote pre-A2
    })
    # Nao deve lancar excecao, e o codigo procurado nao existe em
    # nenhum lote real - resultado correto e False.
    assert storage._existe_em_outro_lote("NSI-TESTE-CORR1", str(uuid_module.uuid4())) is False
    print("OK: test_existe_em_outro_lote_atravessa_lote_legado_sem_registro_coleta_id")


def test_gerar_relatorio_correcao_csv_formato_e_escaping(tmp_path, monkeypatch):
    codigo = str(uuid_module.uuid4())
    lote_id = _lote_com_um_invalido(tmp_path, monkeypatch, codigo)
    lote = storage.carregar_lote(lote_id)
    lote["clientes_invalidos"][0]["produto_bruto"] = 'Treinamento, "Nivel 2"'
    storage.salvar_lote_atomico(lote_id, lote)

    csv_texto = storage.gerar_relatorio_correcao_csv(lote_id)

    assert csv_texto.splitlines()[0] == "codigo_tecnico,nome,whatsapp,produto"
    assert "lote_id" not in csv_texto
    assert "NSI-TESTE-CORR1" not in csv_texto
    # round-trip: reler com csv.reader reproduz o valor original
    import csv as csv_module
    linhas = list(csv_module.reader(io.StringIO(csv_texto)))
    assert linhas[1][3] == 'Treinamento, "Nivel 2"'
    print("OK: test_gerar_relatorio_correcao_csv_formato_e_escaping")


def test_gerar_relatorio_sem_invalidos_so_cabecalho(tmp_path, monkeypatch):
    lote_id = _criar_lote_bruto(tmp_path, monkeypatch, "NSI-TESTE-CORR3", {
        "lote_id": "NSI-TESTE-CORR3", "empresa": "E", "criado_em": datetime.now().isoformat(),
        "clientes": [], "clientes_invalidos": [],
    })
    csv_texto = storage.gerar_relatorio_correcao_csv(lote_id)
    assert csv_texto.strip() == "codigo_tecnico,nome,whatsapp,produto"
    print("OK: test_gerar_relatorio_sem_invalidos_so_cabecalho")


def test_relatorio_lote_legado_invalido_sem_registro_coleta_id_nao_causa_keyerror(tmp_path, monkeypatch):
    """
    Correcao obrigatoria: um invalido legado (anterior a Sprint A1, sem
    a chave registro_coleta_id) nunca pode lancar KeyError ao gerar o
    relatorio - acesso via .get(), nunca indexacao direta.
    """
    lote_id = _criar_lote_bruto(tmp_path, monkeypatch, "NSI-TESTE-LEGADO-REL1", {
        "lote_id": "NSI-TESTE-LEGADO-REL1", "empresa": "E", "criado_em": datetime.now().isoformat(),
        "clientes": [],
        "clientes_invalidos": [
            {"nome_bruto": "Legado", "whatsapp_bruto": "x", "produto_bruto": "Y", "motivos": ["algum"]},
            # registro_coleta_id AUSENTE de proposito
        ],
    })
    csv_texto = storage.gerar_relatorio_correcao_csv(lote_id)  # nao deve lancar KeyError
    print("OK: test_relatorio_lote_legado_invalido_sem_registro_coleta_id_nao_causa_keyerror")


def test_relatorio_omite_registro_legado_sem_codigo(tmp_path, monkeypatch):
    lote_id = _criar_lote_bruto(tmp_path, monkeypatch, "NSI-TESTE-LEGADO-REL2", {
        "lote_id": "NSI-TESTE-LEGADO-REL2", "empresa": "E", "criado_em": datetime.now().isoformat(),
        "clientes": [],
        "clientes_invalidos": [
            {"nome_bruto": "Legado", "whatsapp_bruto": "x", "produto_bruto": "Y", "motivos": ["algum"]},
        ],
    })
    csv_texto = storage.gerar_relatorio_correcao_csv(lote_id)
    assert "Legado" not in csv_texto
    print("OK: test_relatorio_omite_registro_legado_sem_codigo")


def test_relatorio_registro_a2_com_uuid4_continua_aparecendo(tmp_path, monkeypatch):
    codigo_a2 = str(uuid_module.uuid4())
    lote_id = _criar_lote_bruto(tmp_path, monkeypatch, "NSI-TESTE-LEGADO-REL3", {
        "lote_id": "NSI-TESTE-LEGADO-REL3", "empresa": "E", "criado_em": datetime.now().isoformat(),
        "clientes": [],
        "clientes_invalidos": [
            {"nome_bruto": "Legado", "whatsapp_bruto": "x", "produto_bruto": "Y", "motivos": ["algum"]},  # sem codigo
            {"registro_coleta_id": codigo_a2, "nome_bruto": "Ana", "whatsapp_bruto": "abc", "produto_bruto": "X", "motivos": ["whatsapp_caracteres_invalidos"]},
        ],
    })
    csv_texto = storage.gerar_relatorio_correcao_csv(lote_id)
    assert "Legado" not in csv_texto
    assert codigo_a2 in csv_texto
    assert "Ana" in csv_texto
    linhas = csv_texto.splitlines()
    assert len(linhas) == 2  # cabecalho + somente o registro A2
    print("OK: test_relatorio_registro_a2_com_uuid4_continua_aparecendo")


def test_relatorio_somente_legados_gera_apenas_cabecalho(tmp_path, monkeypatch):
    lote_id = _criar_lote_bruto(tmp_path, monkeypatch, "NSI-TESTE-LEGADO-REL4", {
        "lote_id": "NSI-TESTE-LEGADO-REL4", "empresa": "E", "criado_em": datetime.now().isoformat(),
        "clientes": [],
        "clientes_invalidos": [
            {"nome_bruto": "Legado 1", "whatsapp_bruto": "x", "produto_bruto": "Y", "motivos": ["algum"]},
            {"nome_bruto": "Legado 2", "whatsapp_bruto": "z", "produto_bruto": "W", "motivos": ["outro"]},
        ],
    })
    csv_texto = storage.gerar_relatorio_correcao_csv(lote_id)
    assert csv_texto.strip() == "codigo_tecnico,nome,whatsapp,produto"
    print("OK: test_relatorio_somente_legados_gera_apenas_cabecalho")


def test_registrar_tentativa_rejeitada_preserva_valor_bruto(tmp_path, monkeypatch):
    """Preservacao do codigo bruto na auditoria, mesmo malformado."""
    _config_dirs(tmp_path, monkeypatch)
    storage._registrar_tentativa_rejeitada(
        "NSI-TESTE-CORR1", "  nao-e-um-uuid  ", "Ana", "551199999", "Produto X", "codigo_tecnico_invalido"
    )
    arquivos = list((Path(Config.DATA_DIR) / "correcoes_rejeitadas").rglob("*.json"))
    assert len(arquivos) == 1
    with open(arquivos[0], encoding="utf-8") as f:
        evento = json.load(f)
    assert evento["codigo_tecnico_informado"] == "  nao-e-um-uuid  "
    assert evento["motivo"] == "codigo_tecnico_invalido"
    assert evento["processo"] == "upload_correcao_csv"
    assert evento["recebido_por"] == "operador_interno_nao_autenticado"
    print("OK: test_registrar_tentativa_rejeitada_preserva_valor_bruto")


if __name__ == "__main__":
    print("Rode com: pytest tests/unit/test_storage_correcao_registro.py")
