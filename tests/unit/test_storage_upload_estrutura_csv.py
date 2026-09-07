"""
tests/unit/test_storage_upload_estrutura_csv.py

Sprint A1 (Parte 4 do plano de implementacao - ADR-007 Secoes 6 e 7.1).

Valida exclusivamente a IDENTIDADE por linha e a validacao ESTRUTURAL
do cabecalho do CSV de upload:
  - apenas .csv e aceito;
  - cabecalho canonico exato (nome, whatsapp, produto), em qualquer
    ordem, sem duplicatas e sem colunas extras;
  - mapeamento por NOME de coluna, nunca por posicao;
  - cada linha recebe um registro_coleta_id (UUID4) proprio, mesmo
    quando linhas sao identicas entre si.

Normalizacao de whatsapp, validacao de conteudo, separacao de
validos/invalidos e versionamento NAO sao objeto deste arquivo -
pertencem as Sprints A2/A3.

Usa diretorios temporarios (tmp_path) via monkeypatch em Config - nunca
toca em data/ real.
"""

from __future__ import annotations

import io
import sys
import uuid as uuid_module
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config import Config
from adapters import storage


class _ArquivoCSVFake:
    """
    Simula o objeto de arquivo enviado pelo Flask (request.files['file']).
    Aceita 'conteudo' como str (codificado em UTF-8 puro, sem BOM) ou
    como bytes ja prontos (permite simular BOM ou bytes invalidos).
    """

    def __init__(self, conteudo, nome_arquivo: str = "clientes.csv"):
        dados = conteudo if isinstance(conteudo, bytes) else conteudo.encode("utf-8")
        self._buffer = io.BytesIO(dados)
        self.filename = nome_arquivo

    def __getattr__(self, item):
        return getattr(self._buffer, item)


class _ArquivoCSVFakeTexto:
    """
    Simula um objeto de upload cujo .read() retorna str diretamente,
    nao bytes - cobre implementacoes de armazenamento de arquivo que
    nao passam por um buffer binario.
    """

    def __init__(self, conteudo: str, nome_arquivo: str = "clientes.csv"):
        self._texto = conteudo
        self.filename = nome_arquivo

    def read(self):
        return self._texto


def _config_lotes_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "LOTES_DIR", tmp_path / "lotes")


def _nenhum_lote_criado() -> bool:
    """Confirma que nenhum diretorio de lote (vazio ou nao) foi deixado
    para tras por um upload rejeitado."""
    diretorio = Path(Config.LOTES_DIR)
    return not diretorio.exists() or not any(diretorio.iterdir())


def test_upload_aceita_cabecalho_canonico_em_qualquer_ordem(tmp_path, monkeypatch):
    _config_lotes_dir(tmp_path, monkeypatch)
    csv = "produto,nome,whatsapp\nTreinamento,Ana Silva,(11) 98765-4321\n"
    resultado = storage.salvar_lote(_ArquivoCSVFake(csv), empresa="Empresa Teste")

    assert "erro" not in resultado
    lote = storage.carregar_lote(resultado["lote_id"])
    cliente = lote["clientes"][0]
    assert cliente["nome"] == "Ana Silva"
    assert cliente["telefone"] == "(11) 98765-4321"
    assert cliente["produto"] == "Treinamento"
    print("OK: test_upload_aceita_cabecalho_canonico_em_qualquer_ordem")


def test_upload_rejeita_cabecalho_com_quarta_coluna(tmp_path, monkeypatch):
    _config_lotes_dir(tmp_path, monkeypatch)
    csv = "nome,whatsapp,produto,resposta\nAna,5511999990000,Produto X,Otimo!\n"
    resultado = storage.salvar_lote(_ArquivoCSVFake(csv), empresa="Empresa Teste")

    assert "erro" in resultado
    assert "nao reconhecidos" in resultado["erro"]
    assert _nenhum_lote_criado()
    print("OK: test_upload_rejeita_cabecalho_com_quarta_coluna")


def test_upload_rejeita_cabecalho_duplicado(tmp_path, monkeypatch):
    _config_lotes_dir(tmp_path, monkeypatch)
    csv = "nome,nome,whatsapp,produto\nAna,Ana,5511999990000,Produto X\n"
    resultado = storage.salvar_lote(_ArquivoCSVFake(csv), empresa="Empresa Teste")

    assert "erro" in resultado
    assert "duplicados" in resultado["erro"]
    assert _nenhum_lote_criado()
    print("OK: test_upload_rejeita_cabecalho_duplicado")


def test_upload_rejeita_produto_ausente(tmp_path, monkeypatch):
    _config_lotes_dir(tmp_path, monkeypatch)
    csv = "nome,whatsapp\nAna,5511999990000\n"
    resultado = storage.salvar_lote(_ArquivoCSVFake(csv), empresa="Empresa Teste")

    assert "erro" in resultado
    assert "faltando" in resultado["erro"]
    assert "produto" in resultado["erro"]
    assert _nenhum_lote_criado()
    print("OK: test_upload_rejeita_produto_ausente")


def test_upload_rejeita_arquivo_xlsx(tmp_path, monkeypatch):
    _config_lotes_dir(tmp_path, monkeypatch)
    arquivo_fake = _ArquivoCSVFake("nome,whatsapp,produto\nAna,5511999990000,X\n", nome_arquivo="clientes.xlsx")
    resultado = storage.salvar_lote(arquivo_fake, empresa="Empresa Teste")

    assert "erro" in resultado
    assert ".csv" in resultado["erro"]
    assert _nenhum_lote_criado()
    print("OK: test_upload_rejeita_arquivo_xlsx")


def test_cada_linha_recebe_registro_coleta_id_distinto(tmp_path, monkeypatch):
    _config_lotes_dir(tmp_path, monkeypatch)
    csv = (
        "nome,whatsapp,produto\n"
        "Ana,5511999990000,Produto X\n"
        "Bruno,5511999990001,Produto Y\n"
        "Carla,5511999990002,Produto Z\n"
    )
    resultado = storage.salvar_lote(_ArquivoCSVFake(csv), empresa="Empresa Teste")

    lote = storage.carregar_lote(resultado["lote_id"])
    ids = [c["registro_coleta_id"] for c in lote["clientes"]]
    assert len(ids) == 3
    assert len(set(ids)) == 3
    print("OK: test_cada_linha_recebe_registro_coleta_id_distinto")


def test_registro_coleta_id_e_uuid4_valido_sintaticamente(tmp_path, monkeypatch):
    _config_lotes_dir(tmp_path, monkeypatch)
    csv = "nome,whatsapp,produto\nAna,5511999990000,Produto X\n"
    resultado = storage.salvar_lote(_ArquivoCSVFake(csv), empresa="Empresa Teste")

    lote = storage.carregar_lote(resultado["lote_id"])
    valor = lote["clientes"][0]["registro_coleta_id"]
    id_parseado = uuid_module.UUID(valor, version=4)
    assert str(id_parseado) == valor
    print("OK: test_registro_coleta_id_e_uuid4_valido_sintaticamente")


def test_linhas_identicas_recebem_registro_coleta_id_diferentes(tmp_path, monkeypatch):
    _config_lotes_dir(tmp_path, monkeypatch)
    csv = (
        "nome,whatsapp,produto\n"
        "Ana,5511999990000,Produto X\n"
        "Ana,5511999990000,Produto X\n"
    )
    resultado = storage.salvar_lote(_ArquivoCSVFake(csv), empresa="Empresa Teste")

    lote = storage.carregar_lote(resultado["lote_id"])
    ids = [c["registro_coleta_id"] for c in lote["clientes"]]
    assert len(lote["clientes"]) == 2
    assert ids[0] != ids[1]
    print("OK: test_linhas_identicas_recebem_registro_coleta_id_diferentes")


def test_upload_rejeita_csv_vazio_sem_criar_lote(tmp_path, monkeypatch):
    _config_lotes_dir(tmp_path, monkeypatch)
    resultado = storage.salvar_lote(_ArquivoCSVFake(""), empresa="Empresa Teste")

    assert "erro" in resultado
    assert "vazio" in resultado["erro"]
    assert _nenhum_lote_criado()
    print("OK: test_upload_rejeita_csv_vazio_sem_criar_lote")


def test_upload_aceita_utf8_com_bom(tmp_path, monkeypatch):
    _config_lotes_dir(tmp_path, monkeypatch)
    # Simula uma exportacao do Excel: UTF-8 com BOM (bytes EF BB BF no
    # inicio do arquivo, antes do nome da primeira coluna).
    conteudo_com_bom = "nome,whatsapp,produto\nAna Silva,5511999990000,Produto X\n".encode("utf-8-sig")
    resultado = storage.salvar_lote(_ArquivoCSVFake(conteudo_com_bom), empresa="Empresa Teste")

    assert "erro" not in resultado
    lote = storage.carregar_lote(resultado["lote_id"])
    cliente = lote["clientes"][0]
    # O BOM nunca vira parte do nome da coluna nem do valor - "nome" e
    # reconhecido normalmente, e o valor real nao e alterado.
    assert cliente["nome"] == "Ana Silva"
    assert cliente["telefone"] == "5511999990000"
    assert cliente["produto"] == "Produto X"
    print("OK: test_upload_aceita_utf8_com_bom")


def test_upload_malformado_nao_cria_lote(tmp_path, monkeypatch):
    _config_lotes_dir(tmp_path, monkeypatch)
    # Cabecalho valido, mas um campo com aspas nao fechadas - o parser C
    # do pandas nao consegue tokenizar o arquivo (ParserError: EOF
    # inside string), sem que a validacao de cabecalho por si detecte
    # o problema (o cabecalho, isolado, e valido).
    csv_malformado = 'nome,whatsapp,produto\n"Ana,5511999990000,Produto X\n'
    resultado = storage.salvar_lote(_ArquivoCSVFake(csv_malformado), empresa="Empresa Teste")

    assert "erro" in resultado
    # Nenhum detalhe interno do parser (traceback, nome de classe de
    # excecao, etc.) e exposto - apenas o fato estrutural.
    assert "Error tokenizing" not in resultado["erro"]
    assert "Traceback" not in resultado["erro"]
    assert _nenhum_lote_criado()
    print("OK: test_upload_malformado_nao_cria_lote")


def test_upload_rejeita_linha_com_campo_excedente_sem_criar_lote(tmp_path, monkeypatch):
    _config_lotes_dir(tmp_path, monkeypatch)
    # O pandas, se alimentado diretamente com este texto, reinterpreta
    # silenciosamente o campo excedente como indice implicito (ja
    # comprovado empiricamente) - o csv.reader, usado como parser
    # unico, expoe corretamente a linha com 4 campos, e ela e recusada
    # de forma estrutural, sem reinterpretacao.
    csv_conteudo = "nome,whatsapp,produto\nAna,5511999990000,Produto X,Extra\n"
    resultado = storage.salvar_lote(_ArquivoCSVFake(csv_conteudo), empresa="Empresa Teste")

    assert "erro" in resultado
    assert "esperado exatamente 3" in resultado["erro"]
    assert _nenhum_lote_criado()
    print("OK: test_upload_rejeita_linha_com_campo_excedente_sem_criar_lote")


def test_upload_aceita_produto_com_virgula_entre_aspas(tmp_path, monkeypatch):
    _config_lotes_dir(tmp_path, monkeypatch)
    # A virgula dentro do campo citado e parte do valor, nao um novo
    # campo - csv.reader respeita aspas corretamente, ao contrario de
    # um split(",") manual.
    csv_conteudo = 'nome,whatsapp,produto\nAna,5511999990000,"Treinamento, Nivel 2"\n'
    resultado = storage.salvar_lote(_ArquivoCSVFake(csv_conteudo), empresa="Empresa Teste")

    assert "erro" not in resultado
    lote = storage.carregar_lote(resultado["lote_id"])
    assert lote["clientes"][0]["produto"] == "Treinamento, Nivel 2"
    print("OK: test_upload_aceita_produto_com_virgula_entre_aspas")


def test_upload_com_read_retornando_str_nao_falha(tmp_path, monkeypatch):
    _config_lotes_dir(tmp_path, monkeypatch)
    # Inclui um BOM literal (U+FEFF) no INICIO do texto, para exercer
    # especificamente o ramo de codigo que trata arquivo.read() quando
    # ele ja retorna str (nao bytes) - o ramo que continha o defeito
    # corrigido nesta rodada (lstrip com argumento invalido/fragil).
    csv_texto = chr(0xFEFF) + "nome,whatsapp,produto\nAna Silva,5511999990000,Produto X\n"
    resultado = storage.salvar_lote(_ArquivoCSVFakeTexto(csv_texto), empresa="Empresa Teste")

    assert "erro" not in resultado
    lote = storage.carregar_lote(resultado["lote_id"])
    cliente = lote["clientes"][0]
    assert cliente["nome"] == "Ana Silva"
    assert cliente["telefone"] == "5511999990000"
    assert cliente["produto"] == "Produto X"
    print("OK: test_upload_com_read_retornando_str_nao_falha")


if __name__ == "__main__":
    print("Rode com: pytest tests/unit/test_storage_upload_estrutura_csv.py")
