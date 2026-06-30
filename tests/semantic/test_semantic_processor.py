"""
tests/semantic/test_semantic_processor.py

Testes da Camada Semântica completa.
Critérios de aceite — Plano de Implementação, Fase 5.

Usam exclusivamente ClienteIAFalso — mesma interface que ClienteGroq,
sem chamada de rede real (Fase 4).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from catalog.loader import carregar_catalogo
from confidence.confidence_rules import LIMITE_CATEGORIAS_POR_RESPOSTA
from processors.semantic_processor import agregar_semantica_lote, processar_semantica_resposta
from services.ai_classifier import ClienteIAFalso


def _resposta_ia_padrao(categorias: list[dict]) -> dict:
    return {"categorias": categorias}


def test_convivencia_forca_e_dor_na_mesma_resposta():
    """
    Contrato Seção 4.3: 'O atendimento foi ótimo, mas a entrega demorou'
    -> exatamente 1 força (ATENDIMENTO) + 1 dor (ENTREGA), nenhuma anulando a outra.
    """
    catalogo = carregar_catalogo()
    cliente = ClienteIAFalso()
    cliente.configurar_resposta(
        "classificacao_semantica",
        _resposta_ia_padrao(
            [
                {
                    "codigo_catalogo": "ATEND-006",
                    "confianca": 92.0,
                    "intensidade_semantica": 60.0,
                    "trecho_evidencia": "O atendimento foi ótimo",
                },
                {
                    "codigo_catalogo": "ENTR-001",
                    "confianca": 88.0,
                    "intensidade_semantica": 45.0,
                    "trecho_evidencia": "a entrega demorou",
                },
            ]
        ),
    )

    categorias, evidencias, sucesso = processar_semantica_resposta(
        "cliente1", "O atendimento foi ótimo, mas a entrega demorou.", catalogo, cliente
    )

    assert sucesso is True
    assert len(categorias) == 2
    tipos = {c.tipo for c in categorias}
    assert tipos == {"forca", "dor"}

    forca = next(c for c in categorias if c.tipo == "forca")
    dor = next(c for c in categorias if c.tipo == "dor")
    assert forca.familia == "ATENDIMENTO"
    assert dor.familia == "ENTREGA"
    print("OK: test_convivencia_forca_e_dor_na_mesma_resposta")


def test_toda_categoria_tem_evidencia_confianca_e_intensidade():
    """
    Toda categoria detectada carrega confianca, intensidade_semantica,
    area_responsavel e ao menos 1 evidência textual (Contrato Seção 0).
    """
    catalogo = carregar_catalogo()
    cliente = ClienteIAFalso()
    cliente.configurar_resposta(
        "classificacao_semantica",
        _resposta_ia_padrao(
            [
                {
                    "codigo_catalogo": "ATEND-006",
                    "confianca": 90.0,
                    "intensidade_semantica": 55.0,
                    "trecho_evidencia": "atendimento excelente",
                }
            ]
        ),
    )

    categorias, evidencias, sucesso = processar_semantica_resposta(
        "cliente1", "Atendimento excelente.", catalogo, cliente
    )

    assert len(categorias) == 1
    categoria = categorias[0]
    assert categoria.confianca > 0
    assert categoria.intensidade_semantica > 0
    assert categoria.area_responsavel
    assert len(evidencias) == 1
    assert evidencias[0].trecho
    print("OK: test_toda_categoria_tem_evidencia_confianca_e_intensidade")


def test_limite_de_5_respeitado_quando_ia_retorna_mais():
    """Se a IA retornar mais de 5 categorias, o limite de 5 (Fase 6) é aplicado."""
    catalogo = carregar_catalogo()
    cliente = ClienteIAFalso()

    codigos_amostra = ["ATEND-001", "ATEND-002", "PROD-001", "ENTR-001", "PRECO-001", "QUAL-001", "EXP-001"]
    categorias_simuladas = [
        {
            "codigo_catalogo": codigo,
            "confianca": 50.0 + i,
            "intensidade_semantica": 50.0,
            "trecho_evidencia": f"trecho {i}",
        }
        for i, codigo in enumerate(codigos_amostra)
    ]
    cliente.configurar_resposta("classificacao_semantica", _resposta_ia_padrao(categorias_simuladas))

    categorias, evidencias, sucesso = processar_semantica_resposta(
        "cliente1", "texto qualquer", catalogo, cliente
    )

    assert len(categorias) == LIMITE_CATEGORIAS_POR_RESPOSTA
    assert len(evidencias) == LIMITE_CATEGORIAS_POR_RESPOSTA
    # As 5 mantidas devem ser as de maior confiança (50+6=56 até 50+2=52, as 5 maiores)
    confiancas_mantidas = sorted([c.confianca for c in categorias], reverse=True)
    assert confiancas_mantidas == [56.0, 55.0, 54.0, 53.0, 52.0]
    print("OK: test_limite_de_5_respeitado_quando_ia_retorna_mais")


def test_codigo_fora_do_catalogo_e_descartado_sem_quebrar():
    """Se a IA retornar um código inexistente no catálogo, é descartado, sem exceção."""
    catalogo = carregar_catalogo()
    cliente = ClienteIAFalso()
    cliente.configurar_resposta(
        "classificacao_semantica",
        _resposta_ia_padrao(
            [
                {"codigo_catalogo": "CODIGO-INEXISTENTE-999", "confianca": 90.0,
                 "intensidade_semantica": 50.0, "trecho_evidencia": "texto qualquer"},
                {"codigo_catalogo": "ATEND-006", "confianca": 80.0,
                 "intensidade_semantica": 50.0, "trecho_evidencia": "atendimento bom"},
            ]
        ),
    )

    categorias, evidencias, sucesso = processar_semantica_resposta(
        "cliente1", "texto qualquer", catalogo, cliente
    )

    assert sucesso is True
    assert len(categorias) == 1
    assert categorias[0].codigo_catalogo == "ATEND-006"
    print("OK: test_codigo_fora_do_catalogo_e_descartado_sem_quebrar")


def test_falha_da_ia_retorna_sucesso_falso_sem_excecao():
    """Falha da IA -> sucesso=False, listas vazias, NUNCA lança exceção."""
    catalogo = carregar_catalogo()
    cliente = ClienteIAFalso()
    cliente.configurar_falha("classificacao_semantica")

    categorias, evidencias, sucesso = processar_semantica_resposta(
        "cliente1", "texto qualquer", catalogo, cliente
    )

    assert sucesso is False
    assert categorias == []
    assert evidencias == []
    print("OK: test_falha_da_ia_retorna_sucesso_falso_sem_excecao")


def test_tipo_vem_do_catalogo_nao_da_ia():
    """
    O tipo (força/dor) é determinado pela entrada do catálogo, não pelo
    que a IA eventualmente disser — protege contra inconsistência se a
    IA classificar errado o tipo de um código válido.
    """
    catalogo = carregar_catalogo()
    entrada_atend_006 = catalogo.buscar_por_codigo("ATEND-006")
    assert entrada_atend_006.tipo == "F"  # confirma pré-condição do catálogo real

    cliente = ClienteIAFalso()
    cliente.configurar_resposta(
        "classificacao_semantica",
        _resposta_ia_padrao(
            [
                {
                    "codigo_catalogo": "ATEND-006",
                    "tipo": "dor",  # IA "erra" o tipo de propósito neste teste
                    "confianca": 90.0,
                    "intensidade_semantica": 50.0,
                    "trecho_evidencia": "atendimento bom",
                }
            ]
        ),
    )

    categorias, _, _ = processar_semantica_resposta("cliente1", "texto", catalogo, cliente)

    assert categorias[0].tipo == "forca", "tipo deveria vir do catálogo (F->forca), não da IA"
    print("OK: test_tipo_vem_do_catalogo_nao_da_ia")


def test_agregacao_calcula_incidencia_confianca_e_ocorrencias():
    """agregar_semantica_lote calcula incidência, confiança média e ocorrências corretamente."""
    catalogo = carregar_catalogo()
    cliente = ClienteIAFalso()
    cliente.configurar_resposta(
        "classificacao_semantica",
        _resposta_ia_padrao(
            [{"codigo_catalogo": "ATEND-006", "confianca": 90.0,
              "intensidade_semantica": 50.0, "trecho_evidencia": "bom atendimento"}]
        ),
    )

    respostas_texto = [
        ("cliente1", "Atendimento bom."),
        ("cliente2", "Atendimento bom também."),
        ("cliente3", "Produto com defeito."),  # não vai gerar ATEND-006 (mesmo stub fixo, mas simula)
    ]

    categorias_por_resposta = []
    for cliente_id, texto in respostas_texto:
        categorias, evidencias, _ = processar_semantica_resposta(cliente_id, texto, catalogo, cliente)
        categorias_por_resposta.append((cliente_id, categorias, evidencias))

    resultado = agregar_semantica_lote(categorias_por_resposta, total_respostas=3)

    assert len(resultado.forcas_identificadas) == 1
    forca = resultado.forcas_identificadas[0]
    assert forca.codigo_catalogo == "ATEND-006"
    assert forca.ocorrencias == 3  # o stub retorna a mesma resposta fixa para as 3 chamadas
    assert forca.incidencia_percentual == 100.0
    assert forca.confianca_media == 90.0
    assert len(forca.evidencias) == 3
    print("OK: test_agregacao_calcula_incidencia_confianca_e_ocorrencias")


def test_agregacao_lote_vazio_nao_quebra():
    """Lote sem categorias detectadas não quebra a agregação."""
    resultado = agregar_semantica_lote([], total_respostas=0)
    assert resultado.dores_identificadas == []
    assert resultado.forcas_identificadas == []
    print("OK: test_agregacao_lote_vazio_nao_quebra")


def test_nenhuma_regra_semantica_codificada_em_python():
    """
    Verificação estática: o processor não contém mapeamento manual de
    texto->categoria (ex: if "demorou" in texto). Confirma que toda
    decisão semântica vem da IA, não de heurística codificada.
    """
    import processors.semantic_processor as mod

    codigo_fonte = Path(mod.__file__).read_text(encoding="utf-8")
    # Não deve haver nenhuma comparação direta de string de categoria
    # fora dos nomes de variável/comentário — checagem simplificada:
    # nenhuma ocorrência de "in texto" combinada com um código de catálogo
    # literal (ex: 'ATEND-001' in texto), que indicaria regra hardcoded.
    import re
    padrao_suspeito = re.compile(r'"[A-Z]+-\d+"\s+in\s+texto')
    assert not padrao_suspeito.search(codigo_fonte), (
        "Encontrada possível regra semântica hardcoded (código de catálogo "
        "comparado diretamente contra texto)"
    )
    print("OK: test_nenhuma_regra_semantica_codificada_em_python")


def test_usa_apenas_interface_clienteia():
    """Verificação estática: processor não importa Groq diretamente."""
    import processors.semantic_processor as mod

    codigo_fonte = Path(mod.__file__).read_text(encoding="utf-8")
    assert "import groq" not in codigo_fonte
    assert "from groq" not in codigo_fonte
    assert "from services.ai_classifier import" in codigo_fonte
    print("OK: test_usa_apenas_interface_clienteia")


if __name__ == "__main__":
    test_convivencia_forca_e_dor_na_mesma_resposta()
    test_toda_categoria_tem_evidencia_confianca_e_intensidade()
    test_limite_de_5_respeitado_quando_ia_retorna_mais()
    test_codigo_fora_do_catalogo_e_descartado_sem_quebrar()
    test_falha_da_ia_retorna_sucesso_falso_sem_excecao()
    test_tipo_vem_do_catalogo_nao_da_ia()
    test_agregacao_calcula_incidencia_confianca_e_ocorrencias()
    test_agregacao_lote_vazio_nao_quebra()
    test_nenhuma_regra_semantica_codificada_em_python()
    test_usa_apenas_interface_clienteia()
    print("\nTodos os testes da Fase 5 (Camada Semântica) passaram.")
