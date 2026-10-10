# -*- coding: utf-8 -*-
"""
NSI - tests/apoio_b5.py

Apoio compartilhado pelos testes de integracao da migration 0006 (Sprint B,
B5.4 - ADR-010; Especificacao Tecnica, B5.2) - implementacao UNICA, em vez
de uma copia por arquivo:

    tests/integration/test_fn_iniciar_importacao_legado.py
    tests/integration/test_fn_importar_lote_legado.py
    tests/integration/test_fn_concluir_importacao_legado.py
    tests/integration/test_fn_verificar_paridade_legado.py
    tests/integration/test_invariante_claim_legado.py
    tests/integration/test_permissoes_b5.py
    tests/integration/test_migration_0006_upgrade_downgrade.py

Mesmo padrao de tests/apoio_b4_3.py: este modulo nao e um arquivo de teste
(nao comeca com 'test_') - nunca e coletado pelo pytest.

SOMENTE DADOS SINTETICOS (ADR-010, Secao 21): todo documento e construido
aqui ou lido de tests/fixtures/legado/ - nunca de data/. Os valores
pessoais sinteticos usam marcadores fixos (VALORES_PESSOAIS_SINTETICOS),
que os testes de privacidade procuram em retornos, registro tecnico,
manifesto e mensagens de erro.

O manifesto canonico e o SHA-256 daqui servem apenas aos testes da B5.4. A
implementacao canonica de producao (B5.2, item 13) pertence a B5.5
(core/importacao_legado.py); quando existir, estes testes passam a usa-la.
"""
import hashlib
import json
import os
import secrets
import uuid
from pathlib import Path

import psycopg
import pytest

from config import ConfiguracaoBancoAusente, resolver_url_banco_papel

DIRETORIO_FIXTURES = Path(__file__).parent / "fixtures" / "legado"

FUSO_PADRAO = "America/Sao_Paulo"

NOME_SINTETICO = "Pessoa Sintetica Legado"
PRODUTO_SINTETICO = "Produto Sintetico Legado"
PREFIXO_TELEFONE_SINTETICO = "55119876"
VALORES_PESSOAIS_SINTETICOS = (NOME_SINTETICO, PRODUTO_SINTETICO, PREFIXO_TELEFONE_SINTETICO)

TABELAS_0006 = ("importacoes_legado", "importacoes_legado_arquivos", "importacoes_legado_conclusoes",
                "lotes_legado", "registros_legado")
TABELAS_REGISTRO_TECNICO = TABELAS_0006[:3]
FUNCOES_DE_IMPORTACAO = ("fn_iniciar_importacao_legado", "fn_importar_lote_legado",
                         "fn_concluir_importacao_legado", "fn_verificar_paridade_legado")
FUNCOES_DE_TRIGGER_0006 = tuple(f"fn_bloquear_alteracao_{t}" for t in TABELAS_REGISTRO_TECNICO)
ASSINATURAS_DE_IMPORTACAO = {
    "fn_iniciar_importacao_legado": "(uuid, text)",
    "fn_importar_lote_legado": "(uuid, text, bytea, text)",
    "fn_concluir_importacao_legado": "(uuid, bytea, text, integer)",
    "fn_verificar_paridade_legado": "(uuid)",
}

STATUS_PIPELINE_SEM_DISPARO = {
    "upload": True, "lote_criado": True, "aguardando_d8": False, "disparo_whatsapp": False,
    "webhook": False, "analise_ia": False, "dashboard": False, "pdf": False,
}


# ============================================================
# Identificadores e serializacao
# ============================================================

def uuid_texto() -> str:
    return str(uuid.uuid4())


def novo_lote_id_legado() -> str:
    """Identificador legado sintetico no formato da aplicacao
    (NSI-AAAAMMDD-XXXXXX), aleatorio a cada chamada."""
    return f"NSI-20260105-{secrets.token_hex(3).upper()}"


def caminho_do_lote(lote_id_legado: str) -> str:
    return f"lotes/{lote_id_legado}/lote.json"


def serializar(documento) -> bytes:
    """Mesma forma gravada pela aplicacao legada (json.dump com indent=2 e
    ensure_ascii=False)."""
    return json.dumps(documento, ensure_ascii=False, indent=2).encode("utf-8")


def sha256_hex(conteudo: bytes) -> str:
    return hashlib.sha256(conteudo).hexdigest()


def manifesto_canonico(importacao_id: str, fuso, arquivos: list) -> bytes:
    """Manifesto do item 7, em serializacao canonica: chaves ordenadas,
    separadores sem espaco, UTF-8 sem escape, arquivos por caminho."""
    documento = {
        "formato": "nsi-manifesto-legado/1",
        "importacao_id": importacao_id,
        "fuso_declarado": fuso,
        "arquivos": sorted(arquivos, key=lambda a: a["caminho_relativo"]),
    }
    return json.dumps(documento, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def entrada_de_lote(caminho: str, conteudo: bytes, resultado: dict) -> dict:
    """Entrada de tipo 'lote' do manifesto, a partir do retorno de
    fn_importar_lote_legado."""
    return {
        "caminho_relativo": caminho, "tamanho_bytes": len(conteudo), "sha256": sha256_hex(conteudo),
        "tipo": "lote", "geracao": resultado["geracao"], "destino": resultado["destino"],
        "motivo": resultado["motivo"], "lote_id_legado": resultado["lote_id_legado"],
        "lote_id_promovido": resultado["lote_id_promovido"],
    }


def entrada_de_tentativa_recusada(caminho: str, conteudo: bytes) -> dict:
    return {
        "caminho_relativo": caminho, "tamanho_bytes": len(conteudo), "sha256": sha256_hex(conteudo),
        "tipo": "tentativa_recusada", "geracao": None, "destino": "somente_manifesto",
        "motivo": None, "lote_id_legado": None, "lote_id_promovido": None,
    }


# ============================================================
# Documentos sinteticos das quatro geracoes
# ============================================================

def cliente_valido(n: int = 1, com_identidade: bool = True) -> dict:
    registro = {
        "nome": f"{NOME_SINTETICO} {n}", "telefone": f"{PREFIXO_TELEFONE_SINTETICO}{n:05d}",
        "produto": PRODUTO_SINTETICO, "resposta": "",
    }
    if com_identidade:
        registro = {"registro_coleta_id": uuid_texto(), **registro}
    return registro


def cliente_invalido(n: int = 1, motivos=("whatsapp_comprimento_invalido",)) -> dict:
    """Registro invalido coerente com ck_registros_coleta_coerencia: o campo
    do motivo '*_ausente' fica vazio no legado e nulo na projecao."""
    motivos = list(motivos)
    return {
        "registro_coleta_id": uuid_texto(),
        "nome_bruto": "" if "nome_ausente" in motivos else f"{NOME_SINTETICO} Invalido {n}",
        "whatsapp_bruto": "" if "whatsapp_ausente" in motivos else f"{PREFIXO_TELEFONE_SINTETICO}{n}",
        "produto_bruto": "" if "produto_ausente" in motivos else PRODUTO_SINTETICO,
        "motivos": motivos,
    }


def _raiz(lote_id_legado: str, clientes: list, criado_em: str) -> dict:
    return {
        "lote_id": lote_id_legado, "empresa": "Empresa Sintetica", "nome_lote": "Lote Sintetico",
        "data_inicial": "2026-01-01", "data_final": "2026-01-31", "csv_original": "sintetico.csv",
        "criado_em": criado_em, "total_clientes": len(clientes), "status": "aguardando_d8",
        "data_disparo": "2026-01-13T10:30:00.123456", "status_pipeline": dict(STATUS_PIPELINE_SEM_DISPARO),
        "clientes": clientes,
    }


def doc_anterior_a1(lote_id_legado=None, n: int = 2, criado_em: str = "2026-01-05T10:30:00.123456") -> dict:
    lote_id_legado = lote_id_legado or novo_lote_id_legado()
    documento = _raiz(lote_id_legado, [cliente_valido(i, com_identidade=False) for i in range(1, n + 1)], criado_em)
    documento["status"] = "pendente"
    return documento


def doc_a1(lote_id_legado=None, n: int = 2, criado_em: str = "2026-01-05T10:30:00.123456") -> dict:
    lote_id_legado = lote_id_legado or novo_lote_id_legado()
    return _raiz(lote_id_legado, [cliente_valido(i) for i in range(1, n + 1)], criado_em)


def doc_a2(lote_id_legado=None, validos: int = 2, invalidos: int = 1,
           criado_em: str = "2026-01-05T10:30:00.123456") -> dict:
    lote_id_legado = lote_id_legado or novo_lote_id_legado()
    clientes = [cliente_valido(i) for i in range(1, validos + 1)]
    clientes_invalidos = [cliente_invalido(i) for i in range(1, invalidos + 1)]
    documento = _raiz(lote_id_legado, clientes, criado_em)
    documento.update({
        "total_recebido": validos + invalidos, "total_valido": validos, "total_invalido": invalidos,
        "clientes_invalidos": clientes_invalidos,
    })
    return documento


def versao_historico(numero: int, status: str) -> dict:
    return {
        "registro_coleta_versao_id": uuid_texto(), "numero_versao": numero, "status_versao": status,
        "processo": "upload_original" if numero == 1 else "upload_correcao_csv",
        "recebido_em": "2026-01-05T10:30:00.123456",
        "nome_bruto": f"{NOME_SINTETICO} Historico", "whatsapp_bruto": f"{PREFIXO_TELEFONE_SINTETICO}9",
        "produto_bruto": PRODUTO_SINTETICO, "motivos": [],
    }


def doc_a3(lote_id_legado=None, criado_em: str = "2026-01-05T10:30:00.123456") -> dict:
    """A2 mais historico_versoes: o primeiro valido foi corrigido uma vez
    (duas versoes, corrente valida) e o primeiro invalido recebeu duas
    correcoes ainda invalidas (tres versoes, corrente invalida)."""
    documento = doc_a2(lote_id_legado, validos=2, invalidos=2, criado_em=criado_em)
    corrigido = documento["clientes"][0]["registro_coleta_id"]
    ainda_invalido = documento["clientes_invalidos"][0]["registro_coleta_id"]
    documento["historico_versoes"] = {
        corrigido: [versao_historico(1, "invalida"), versao_historico(2, "valida")],
        ainda_invalido: [versao_historico(1, "invalida"), versao_historico(2, "invalida"),
                         versao_historico(3, "invalida")],
    }
    return documento


def ids_do_documento(documento: dict) -> list:
    return [r["registro_coleta_id"]
            for lista in ("clientes", "clientes_invalidos") for r in documento.get(lista, [])
            if "registro_coleta_id" in r]


def ler_fixture(caminho_relativo: str) -> bytes:
    return (DIRETORIO_FIXTURES / caminho_relativo).read_bytes()


# ============================================================
# Chamadas as funcoes (recebem o cursor do teste)
# ============================================================

def iniciar(cur, fuso=FUSO_PADRAO, importacao_id=None) -> str:
    importacao_id = importacao_id or uuid_texto()
    cur.execute("SELECT nsi_operacional.fn_iniciar_importacao_legado(%s, %s)", (importacao_id, fuso))
    assert cur.fetchone()[0]["importacao_id"] == importacao_id
    return importacao_id


def importar_bytes(cur, importacao_id: str, caminho: str, conteudo: bytes, sha256=None) -> dict:
    cur.execute(
        "SELECT nsi_operacional.fn_importar_lote_legado(%s, %s, %s, %s)",
        (importacao_id, caminho, conteudo, sha256 if sha256 is not None else sha256_hex(conteudo)),
    )
    return cur.fetchone()[0]


def importar(cur, importacao_id: str, documento: dict) -> dict:
    """Importa um documento sintetico pelo caminho derivado do seu proprio
    lote_id."""
    return importar_bytes(cur, importacao_id, caminho_do_lote(documento["lote_id"]), serializar(documento))


def concluir(cur, importacao_id: str, manifesto: bytes, total_arquivos: int, sha256=None) -> dict:
    cur.execute(
        "SELECT nsi_operacional.fn_concluir_importacao_legado(%s, %s, %s, %s)",
        (importacao_id, manifesto, sha256 if sha256 is not None else sha256_hex(manifesto), total_arquivos),
    )
    return cur.fetchone()[0]


def paridade(cur, importacao_id: str) -> dict:
    cur.execute("SELECT nsi_operacional.fn_verificar_paridade_legado(%s)", (importacao_id,))
    return cur.fetchone()[0]


def importar_e_concluir(cur, documentos: list, fuso=FUSO_PADRAO, extras_manifesto=()) -> tuple:
    """Execucao completa: abre, importa cada documento, monta o manifesto
    com os retornos e conclui. Devolve (importacao_id, resultados)."""
    importacao_id = iniciar(cur, fuso)
    resultados, entradas = [], list(extras_manifesto)
    for documento in documentos:
        conteudo = serializar(documento)
        resultado = importar_bytes(cur, importacao_id, caminho_do_lote(documento["lote_id"]), conteudo)
        resultados.append(resultado)
        entradas.append(entrada_de_lote(caminho_do_lote(documento["lote_id"]), conteudo, resultado))
    concluir(cur, importacao_id, manifesto_canonico(importacao_id, fuso, entradas), len(documentos))
    return importacao_id, resultados


def contar(cur, tabela: str, condicao: str = "TRUE", parametros=()) -> int:
    cur.execute(f"SELECT count(*) FROM nsi_operacional.{tabela} WHERE {condicao}", parametros)
    return cur.fetchone()[0]


# ============================================================
# Conexoes
# ============================================================

def conectar_como_owner(url: str):
    """Conexao do migrator de teste, com a transacao corrente sob
    nsi_eventos_owner (SET LOCAL - vale ate o proximo COMMIT/ROLLBACK)."""
    conn = psycopg.connect(url)
    conn.cursor().execute("SET LOCAL ROLE nsi_eventos_owner")
    return conn


def url_nsi_importacao() -> str:
    """URL da role nsi_importacao em nsi_test (TEST_DATABASE_URL_NSI_
    IMPORTACAO - dependencia operacional da B5.2, item 19.6). Ausente: o
    teste e pulado em desenvolvimento comum e FALHA no comando de aceite
    (NSI_REQUIRE_PG_TESTS=1) - mesma regra de tests/conftest.py."""
    try:
        return resolver_url_banco_papel("nsi_importacao", "test")
    except ConfiguracaoBancoAusente:
        mensagem = (
            "TEST_DATABASE_URL_NSI_IMPORTACAO ausente - a credencial da role nsi_importacao e "
            "dependencia operacional da B5.2 (item 19.6)."
        )
        if os.getenv("NSI_REQUIRE_PG_TESTS", "") == "1":
            pytest.fail(mensagem)
        pytest.skip(mensagem)


def assert_sem_valor_pessoal(texto: str, rotulo: str) -> None:
    """Falha com mensagem fixa - nunca exibe o texto inspecionado."""
    for valor in VALORES_PESSOAIS_SINTETICOS:
        if valor in texto:
            pytest.fail(f"Valor pessoal sintetico encontrado em {rotulo} (conteudo nao exibido).")
