"""
tests/unit/test_storage_upload_estrutura_csv.py

Sprint A1 + Sprint A2 (Parte 4 do plano de implementacao - ADR-007
Secoes 6, 7.1 e 8).

Sprint A1: IDENTIDADE por linha e validacao ESTRUTURAL do cabecalho do
CSV de upload (apenas .csv; cabecalho canonico nome/whatsapp/produto
em qualquer ordem, sem duplicatas nem colunas extras; mapeamento por
nome de coluna; registro_coleta_id por linha).

Sprint A2: validacao de CONTEUDO por linha, isoladamente:
  - nome/produto vazios ou so com espacos = ausentes; textos literais
    "nan"/"none"/"null" sao PRESERVADOS como conteudo real;
  - whatsapp normalizado (remove formatacao; codigo do pais decidido
    pelo COMPRIMENTO, nunca por startswith("55") isoladamente - DDD 55
    existe) e validado contra os 67 DDDs oficiais da Anatel;
  - registros validos e invalidos sao separados, ambos preservando o
    registro_coleta_id da linha original; invalidos preservam os
    valores brutos exatamente como recebidos pelo csv.reader;
  - lote sem nenhum registro valido recebe status "sem_registros_validos",
    e e criado normalmente - nunca tratado como erro de upload.

Correcao, reenvio de CSV corrigido e versionamento pertencem a Sprint
A3 - nao sao objeto deste arquivo.

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
    # Atualizado na Sprint A2: telefone agora e normalizado (a asserção
    # original, da Sprint A1, verificava o valor bruto sem normalizacao,
    # que ainda nao existia). A finalidade do teste - ordem livre do
    # cabecalho mapeada corretamente por nome - permanece a mesma.
    assert cliente["telefone"] == "5511987654321"
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


# ============================================================
# Sprint A2 - validacao de conteudo, normalizacao e separacao
# ============================================================

def _linha_csv(nome, whatsapp, produto) -> str:
    """Monta uma linha de dados usando csv.writer, para respeitar
    corretamente aspas/virgulas se o valor exigir."""
    import io as io_module
    buf = io_module.StringIO()
    import csv as csv_module
    csv_module.writer(buf).writerow([nome, whatsapp, produto])
    return buf.getvalue()


def _upload_uma_linha(tmp_path, monkeypatch, nome, whatsapp, produto):
    _config_lotes_dir(tmp_path, monkeypatch)
    conteudo = "nome,whatsapp,produto\n" + _linha_csv(nome, whatsapp, produto)
    resultado = storage.salvar_lote(_ArquivoCSVFake(conteudo), empresa="Empresa Teste")
    return resultado


def test_nome_vazio_e_ausente(tmp_path, monkeypatch):
    resultado = _upload_uma_linha(tmp_path, monkeypatch, "", "5511987654321", "Produto X")
    lote = storage.carregar_lote(resultado["lote_id"])
    assert lote["clientes"] == []
    assert lote["clientes_invalidos"][0]["motivos"] == ["nome_ausente"]
    print("OK: test_nome_vazio_e_ausente")


def test_produto_somente_espacos_e_ausente(tmp_path, monkeypatch):
    resultado = _upload_uma_linha(tmp_path, monkeypatch, "Ana", "5511987654321", "   ")
    lote = storage.carregar_lote(resultado["lote_id"])
    assert lote["clientes_invalidos"][0]["motivos"] == ["produto_ausente"]
    print("OK: test_produto_somente_espacos_e_ausente")


def test_textos_nan_none_null_sao_preservados_como_conteudo_real(tmp_path, monkeypatch):
    resultado = _upload_uma_linha(tmp_path, monkeypatch, "Nan", "5511987654321", "None")
    lote = storage.carregar_lote(resultado["lote_id"])
    assert "erro" not in resultado
    cliente = lote["clientes"][0]
    assert cliente["nome"] == "Nan"
    assert cliente["produto"] == "None"
    print("OK: test_textos_nan_none_null_sao_preservados_como_conteudo_real")


def test_whatsapp_ausente(tmp_path, monkeypatch):
    resultado = _upload_uma_linha(tmp_path, monkeypatch, "Ana", "", "Produto X")
    lote = storage.carregar_lote(resultado["lote_id"])
    assert lote["clientes_invalidos"][0]["motivos"] == ["whatsapp_ausente"]
    print("OK: test_whatsapp_ausente")


def test_normalizacao_parenteses_espaco_hifen(tmp_path, monkeypatch):
    resultado = _upload_uma_linha(tmp_path, monkeypatch, "Ana", "(11) 98765-4321", "Produto X")
    lote = storage.carregar_lote(resultado["lote_id"])
    assert lote["clientes"][0]["telefone"] == "5511987654321"
    print("OK: test_normalizacao_parenteses_espaco_hifen")


def test_normalizacao_com_codigo_do_pais_explicito(tmp_path, monkeypatch):
    resultado = _upload_uma_linha(tmp_path, monkeypatch, "Ana", "+55 11 98765-4321", "Produto X")
    lote = storage.carregar_lote(resultado["lote_id"])
    assert lote["clientes"][0]["telefone"] == "5511987654321"
    print("OK: test_normalizacao_com_codigo_do_pais_explicito")


def test_normalizacao_numero_fixo_sem_nono_digito(tmp_path, monkeypatch):
    resultado = _upload_uma_linha(tmp_path, monkeypatch, "Ana", "11 3456-7890", "Produto X")
    lote = storage.carregar_lote(resultado["lote_id"])
    assert lote["clientes"][0]["telefone"] == "551134567890"
    print("OK: test_normalizacao_numero_fixo_sem_nono_digito")


def test_ddd_55_nacional_sem_codigo_do_pais(tmp_path, monkeypatch):
    resultado = _upload_uma_linha(tmp_path, monkeypatch, "Ana", "55 99765-4321", "Produto X")
    lote = storage.carregar_lote(resultado["lote_id"])
    assert "erro" not in resultado
    assert lote["clientes"][0]["telefone"] == "5555997654321"
    print("OK: test_ddd_55_nacional_sem_codigo_do_pais")


def test_ddd_55_com_codigo_do_pais_converge_ao_mesmo_resultado(tmp_path, monkeypatch):
    resultado = _upload_uma_linha(tmp_path, monkeypatch, "Ana", "+55 55 99765-4321", "Produto X")
    lote = storage.carregar_lote(resultado["lote_id"])
    assert lote["clientes"][0]["telefone"] == "5555997654321"
    print("OK: test_ddd_55_com_codigo_do_pais_converge_ao_mesmo_resultado")


def test_ddd_99_e_valido(tmp_path, monkeypatch):
    resultado = _upload_uma_linha(tmp_path, monkeypatch, "Ana", "99 98765-4321", "Produto X")
    lote = storage.carregar_lote(resultado["lote_id"])
    assert "erro" not in resultado
    assert lote["clientes"][0]["telefone"] == "5599987654321"
    print("OK: test_ddd_99_e_valido")


def test_ddd_00_e_invalido(tmp_path, monkeypatch):
    resultado = _upload_uma_linha(tmp_path, monkeypatch, "Ana", "00 98765-4321", "Produto X")
    lote = storage.carregar_lote(resultado["lote_id"])
    assert lote["clientes_invalidos"][0]["motivos"] == ["whatsapp_ddd_invalido"]
    print("OK: test_ddd_00_e_invalido")


def test_ddd_10_e_invalido(tmp_path, monkeypatch):
    resultado = _upload_uma_linha(tmp_path, monkeypatch, "Ana", "10 98765-4321", "Produto X")
    lote = storage.carregar_lote(resultado["lote_id"])
    assert lote["clientes_invalidos"][0]["motivos"] == ["whatsapp_ddd_invalido"]
    print("OK: test_ddd_10_e_invalido")


def test_whatsapp_com_letras_e_caracteres_invalidos(tmp_path, monkeypatch):
    resultado = _upload_uma_linha(tmp_path, monkeypatch, "Ana", "11ABCDE4321", "Produto X")
    lote = storage.carregar_lote(resultado["lote_id"])
    assert lote["clientes_invalidos"][0]["motivos"] == ["whatsapp_caracteres_invalidos"]
    print("OK: test_whatsapp_com_letras_e_caracteres_invalidos")


def test_whatsapp_comprimento_invalido_isolado_sem_cascata(tmp_path, monkeypatch):
    # 7 digitos - normalizado permanece com 7 (fora de 10/11/12/13) -
    # motivo unico de comprimento, nunca acompanhado de outro motivo
    # de whatsapp derivado dele.
    resultado = _upload_uma_linha(tmp_path, monkeypatch, "Ana", "1234567", "Produto X")
    lote = storage.carregar_lote(resultado["lote_id"])
    motivos = lote["clientes_invalidos"][0]["motivos"]
    assert motivos == ["whatsapp_comprimento_invalido"]
    print("OK: test_whatsapp_comprimento_invalido_isolado_sem_cascata")


def test_whatsapp_codigo_pais_invalido(tmp_path, monkeypatch):
    # 13 digitos, nao comeca com 55 - codigo do pais invalido, isolado.
    resultado = _upload_uma_linha(tmp_path, monkeypatch, "Ana", "1234567890123", "Produto X")
    lote = storage.carregar_lote(resultado["lote_id"])
    assert lote["clientes_invalidos"][0]["motivos"] == ["whatsapp_codigo_pais_invalido"]
    print("OK: test_whatsapp_codigo_pais_invalido")


def test_multiplos_motivos_na_mesma_linha(tmp_path, monkeypatch):
    resultado = _upload_uma_linha(tmp_path, monkeypatch, "", "00123", "")
    lote = storage.carregar_lote(resultado["lote_id"])
    motivos = lote["clientes_invalidos"][0]["motivos"]
    assert "nome_ausente" in motivos
    assert "produto_ausente" in motivos
    assert len(motivos) == 3  # nome, produto e whatsapp (comprimento)
    print("OK: test_multiplos_motivos_na_mesma_linha")


def test_registro_coleta_id_preservado_em_validos_e_invalidos(tmp_path, monkeypatch):
    _config_lotes_dir(tmp_path, monkeypatch)
    conteudo = (
        "nome,whatsapp,produto\n"
        + _linha_csv("Ana", "5511987654321", "Produto X")
        + _linha_csv("", "5511987654322", "Produto Y")
    )
    resultado = storage.salvar_lote(_ArquivoCSVFake(conteudo), empresa="Empresa Teste")
    lote = storage.carregar_lote(resultado["lote_id"])

    assert len(lote["clientes"]) == 1
    assert len(lote["clientes_invalidos"]) == 1
    id_valido = lote["clientes"][0]["registro_coleta_id"]
    id_invalido = lote["clientes_invalidos"][0]["registro_coleta_id"]
    uuid_module.UUID(id_valido, version=4)
    uuid_module.UUID(id_invalido, version=4)
    assert id_valido != id_invalido
    print("OK: test_registro_coleta_id_preservado_em_validos_e_invalidos")


def test_valores_brutos_preservados_exatamente(tmp_path, monkeypatch):
    resultado = _upload_uma_linha(tmp_path, monkeypatch, "  Ana  ", "abc", "  Produto X  ")
    lote = storage.carregar_lote(resultado["lote_id"])
    invalido = lote["clientes_invalidos"][0]
    # Preservados exatamente como o csv.reader entregou - inclusive
    # espacos internos/externos, sem qualquer conversao.
    assert invalido["nome_bruto"] == "  Ana  "
    assert invalido["whatsapp_bruto"] == "abc"
    assert invalido["produto_bruto"] == "  Produto X  "
    print("OK: test_valores_brutos_preservados_exatamente")


def test_separacao_e_contagens_com_validos_e_invalidos(tmp_path, monkeypatch):
    _config_lotes_dir(tmp_path, monkeypatch)
    conteudo = (
        "nome,whatsapp,produto\n"
        + _linha_csv("Ana", "5511987654321", "Produto X")
        + _linha_csv("Bruno", "5511987654322", "Produto Y")
        + _linha_csv("Carla", "5511987654323", "Produto Z")
        + _linha_csv("", "00123", "Produto W")
        + _linha_csv("Erro2", "abc", "Produto V")
    )
    resultado = storage.salvar_lote(_ArquivoCSVFake(conteudo), empresa="Empresa Teste")

    assert resultado["total_recebido"] == 5
    assert resultado["total_valido"] == 3
    assert resultado["total_invalido"] == 2
    assert resultado["total_clientes"] == 3  # legado = total_valido
    assert resultado["status"] == "aguardando_d8"

    lote = storage.carregar_lote(resultado["lote_id"])
    assert len(lote["clientes"]) == 3
    assert len(lote["clientes_invalidos"]) == 2
    assert lote["total_recebido"] == 5
    assert lote["total_valido"] == 3
    assert lote["total_invalido"] == 2
    assert lote["total_clientes"] == 3
    print("OK: test_separacao_e_contagens_com_validos_e_invalidos")


def test_lote_sem_nenhum_registro_valido_e_criado_com_status_proprio(tmp_path, monkeypatch):
    _config_lotes_dir(tmp_path, monkeypatch)
    conteudo = (
        "nome,whatsapp,produto\n"
        + _linha_csv("", "abc", "")
        + _linha_csv("Bruno", "00123", "")
    )
    resultado = storage.salvar_lote(_ArquivoCSVFake(conteudo), empresa="Empresa Teste")

    # NUNCA tratado como erro de upload - o arquivo foi estruturalmente
    # aceito e precisa permanecer auditavel.
    assert "erro" not in resultado
    assert resultado["status"] == "sem_registros_validos"
    assert resultado["total_recebido"] == 2
    assert resultado["total_valido"] == 0
    assert resultado["total_invalido"] == 2

    lote = storage.carregar_lote(resultado["lote_id"])
    assert lote["status"] == "sem_registros_validos"
    assert lote["clientes"] == []
    assert len(lote["clientes_invalidos"]) == 2
    for invalido in lote["clientes_invalidos"]:
        assert "registro_coleta_id" in invalido and invalido["registro_coleta_id"]
        assert invalido["motivos"]
    print("OK: test_lote_sem_nenhum_registro_valido_e_criado_com_status_proprio")


if __name__ == "__main__":
    print("Rode com: pytest tests/unit/test_storage_upload_estrutura_csv.py")
