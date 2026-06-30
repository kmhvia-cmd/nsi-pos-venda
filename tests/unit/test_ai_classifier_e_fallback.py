"""
tests/unit/test_ai_classifier_e_fallback.py

Testes da Fase 4 — Integração com IA e Fallback.
Critérios de aceite — Plano de Implementação, Fase 4.

Estes testes usam exclusivamente `ClienteIAFalso` (mesma interface que
`ClienteGroq`, sem chamada de rede real). Nenhum teste aqui depende de
GROQ_API_KEY configurada — isso é proposital: a interface é validada
independente do provider real estar disponível.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services.ai_classifier import (
    ClienteGroq,
    ClienteIAFalso,
    ErroIAIndisponivel,
    RequisicaoIA,
)
from services.fallback_handler import chamar_com_fallback, determinar_status_semantico


def _requisicao(tarefa: str = "classificacao_semantica") -> RequisicaoIA:
    return RequisicaoIA(
        tarefa=tarefa,
        texto="Gostei muito do atendimento, mas a entrega demorou.",
        contexto={"candidatos": ["ATEND-006", "ENTR-001"]},
        prompt_sistema="Classifique o texto conforme o catálogo fornecido.",
        versao_prompt="v1",
    )


def test_chamada_simulada_de_sucesso_retorna_estrutura_esperada():
    """Chamada simulada de sucesso retorna estrutura esperada + modelo_classificacao preenchido."""
    cliente = ClienteIAFalso()
    cliente.configurar_resposta(
        "classificacao_semantica",
        {"categorias": [{"codigo_catalogo": "ATEND-006", "confianca": 92.0}]},
    )

    resposta = cliente.classificar(_requisicao())

    assert resposta.conteudo["categorias"][0]["codigo_catalogo"] == "ATEND-006"
    assert resposta.modelo_classificacao.provider == "fake_teste_local"
    assert resposta.modelo_classificacao.versao_prompt == "v1"
    print("OK: test_chamada_simulada_de_sucesso_retorna_estrutura_esperada")


def test_chamada_simulada_de_falha_aciona_erro_classificado():
    """Chamada simulada de falha levanta ErroIAIndisponivel, tipo classificado."""
    cliente = ClienteIAFalso()
    cliente.configurar_falha("classificacao_semantica")

    erro_levantado = False
    try:
        cliente.classificar(_requisicao())
    except ErroIAIndisponivel:
        erro_levantado = True

    assert erro_levantado, "ErroIAIndisponivel não foi levantado"
    print("OK: test_chamada_simulada_de_falha_aciona_erro_classificado")


def test_fallback_handler_nao_propaga_excecao_em_falha():
    """fallback_handler nunca deixa exceção subir — sempre retorna ResultadoComFallback."""
    cliente = ClienteIAFalso()
    cliente.configurar_falha("classificacao_semantica")

    resultado = chamar_com_fallback(cliente, _requisicao())

    assert resultado.sucesso is False
    assert resultado.resposta is None
    assert resultado.motivo_falha == "falha simulada para teste"
    print("OK: test_fallback_handler_nao_propaga_excecao_em_falha")


def test_fallback_handler_sucesso_retorna_resposta():
    """Em caso de sucesso, fallback_handler retorna a resposta real, sem alteração."""
    cliente = ClienteIAFalso()
    cliente.configurar_resposta("classificacao_semantica", {"ok": True})

    resultado = chamar_com_fallback(cliente, _requisicao())

    assert resultado.sucesso is True
    assert resultado.resposta is not None
    assert resultado.resposta.conteudo == {"ok": True}
    print("OK: test_fallback_handler_sucesso_retorna_resposta")


def test_status_semantico_concluido_em_sucesso():
    """determinar_status_semantico retorna 'concluido' quando a chamada teve sucesso."""
    cliente = ClienteIAFalso()
    cliente.configurar_resposta("classificacao_semantica", {"ok": True})
    resultado = chamar_com_fallback(cliente, _requisicao())

    assert determinar_status_semantico(resultado) == "concluido"
    print("OK: test_status_semantico_concluido_em_sucesso")


def test_status_semantico_pendente_em_falha():
    """determinar_status_semantico retorna 'pendente' quando a chamada falhou."""
    cliente = ClienteIAFalso()
    cliente.configurar_falha("classificacao_semantica")
    resultado = chamar_com_fallback(cliente, _requisicao())

    assert determinar_status_semantico(resultado) == "pendente"
    print("OK: test_status_semantico_pendente_em_falha")


def test_ausencia_de_resposta_configurada_tambem_aciona_fallback():
    """Tarefa sem resposta configurada no fake levanta erro -> fallback funciona igual."""
    cliente = ClienteIAFalso()  # nenhuma tarefa configurada

    resultado = chamar_com_fallback(cliente, _requisicao())

    assert resultado.sucesso is False
    print("OK: test_ausencia_de_resposta_configurada_tambem_aciona_fallback")


def test_groq_client_levanta_erro_classificado_sem_api_key():
    """
    Sem GROQ_API_KEY no ambiente, ClienteGroq levanta ErroIAIndisponivel
    de forma classificada e clara — nunca uma exceção genérica não tratada.
    Este teste NÃO faz nenhuma chamada de rede.
    """
    chave_original = os.environ.pop("GROQ_API_KEY", None)
    try:
        erro_levantado = False
        try:
            ClienteGroq()
        except ErroIAIndisponivel as exc:
            erro_levantado = True
            assert "GROQ_API_KEY" in exc.motivo
        assert erro_levantado, "ErroIAIndisponivel não foi levantado sem API key"
    finally:
        if chave_original is not None:
            os.environ["GROQ_API_KEY"] = chave_original
    print("OK: test_groq_client_levanta_erro_classificado_sem_api_key")


def test_clientegroq_e_clienteiafalso_implementam_a_mesma_interface():
    """
    Verificação estrutural: ambos os clientes são subclasses de ClienteIA
    e expõem o método `classificar` com a mesma assinatura conceitual.
    Garante que trocar de provider não exige mudança de chamada.
    """
    from services.ai_classifier import ClienteIA

    assert issubclass(ClienteGroq, ClienteIA)
    assert issubclass(ClienteIAFalso, ClienteIA)
    assert hasattr(ClienteGroq, "classificar")
    assert hasattr(ClienteIAFalso, "classificar")
    print("OK: test_clientegroq_e_clienteiafalso_implementam_a_mesma_interface")


def test_nenhum_outro_modulo_chama_ia_diretamente():
    """
    Verificação estática: confirma que os processors já implementados
    (Fases 1, 2, 3, 6) não importam o SDK da Groq nem fazem chamada de
    rede diretamente — só services/ai_classifier.py tem essa permissão.
    """
    raiz = Path(__file__).resolve().parents[2]
    arquivos_processors = list((raiz / "processors").glob("*.py"))
    arquivos_confidence = list((raiz / "confidence").glob("*.py"))
    arquivos_catalog = list((raiz / "catalog").glob("*.py"))

    proibidos = ["import groq", "from groq"]
    for arquivo in arquivos_processors + arquivos_confidence + arquivos_catalog:
        codigo_fonte = arquivo.read_text(encoding="utf-8")
        for termo in proibidos:
            assert termo not in codigo_fonte, (
                f"{arquivo} importa Groq diretamente — violação da interface única"
            )
    print("OK: test_nenhum_outro_modulo_chama_ia_diretamente")


def test_groq_e_o_unico_provider_real_mencionado():
    """
    Confirma que ClienteGroq é a única implementação de produção presente
    no código — reforça que a arquitetura assume Groq como provider oficial,
    não um provider genérico hipotético.
    """
    import services.ai_classifier as mod

    codigo_fonte = Path(mod.__file__).read_text(encoding="utf-8")
    assert "class ClienteGroq" in codigo_fonte
    assert codigo_fonte.count("class Cliente") == 3  # ClienteIA (abstrata), ClienteGroq, ClienteIAFalso
    print("OK: test_groq_e_o_unico_provider_real_mencionado")


if __name__ == "__main__":
    test_chamada_simulada_de_sucesso_retorna_estrutura_esperada()
    test_chamada_simulada_de_falha_aciona_erro_classificado()
    test_fallback_handler_nao_propaga_excecao_em_falha()
    test_fallback_handler_sucesso_retorna_resposta()
    test_status_semantico_concluido_em_sucesso()
    test_status_semantico_pendente_em_falha()
    test_ausencia_de_resposta_configurada_tambem_aciona_fallback()
    test_groq_client_levanta_erro_classificado_sem_api_key()
    test_clientegroq_e_clienteiafalso_implementam_a_mesma_interface()
    test_nenhum_outro_modulo_chama_ia_diretamente()
    test_groq_e_o_unico_provider_real_mencionado()
    print("\nTodos os testes da Fase 4 (Integração com IA e Fallback) passaram.")
