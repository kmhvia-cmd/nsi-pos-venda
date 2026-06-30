"""
services/ai_classifier.py

Interface única de IA do Motor NSI.
Contrato Oficial do Motor NSI v3.1, Seção 1.1.
Especificação Técnica v1, Seções 4 e 7.

PRINCÍPIO ARQUITETURAL (decisão aprovada, não-negociável):
Nenhum outro módulo do motor chama um provedor de IA diretamente.
Toda chamada passa por `ClienteIA`, uma interface abstrata. Existem duas
implementações desta interface:

    - `ClienteGroq`  -> provider oficial de produção, usa o SDK real da Groq.
    - `ClienteIAFalso` -> implementação de teste local, mesma interface,
                          usada apenas em testes automatizados.

Quando a GROQ_API_KEY estiver configurada no ambiente, a troca de
`ClienteIAFalso` para `ClienteGroq` é feita SOMENTE na composição (onde o
processor é instanciado), nunca dentro da lógica de negócio dos
processors. Nenhuma linha de `semantic_processor.py`, `experience_processor.py`
ou `executive_processor.py` (Fases 5, 7, 9) muda quando o provider muda.

Toda chamada registra `ModeloClassificacao` (Contrato Seção 1.1), usado
para auditoria e reprodutibilidade — nunca exibido ao cliente final.
"""

from __future__ import annotations

import json
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

from models.output_models import ModeloClassificacao

TipoTarefaIA = Literal[
    "classificacao_semantica",
    "experiencia_humana",
    "resumo_executivo",
    "acao_recomendada",
]


@dataclass
class RequisicaoIA:
    """
    Requisição padronizada enviada a qualquer provider de IA.
    Mesma estrutura, independente de quem implementa `ClienteIA`.
    """
    tarefa: TipoTarefaIA
    texto: str
    contexto: dict  # candidatos do catálogo, segmento, dados auxiliares — varia por tarefa
    prompt_sistema: str
    versao_prompt: str


@dataclass
class RespostaIA:
    """Resposta padronizada de qualquer provider de IA."""
    conteudo: dict  # JSON estruturado já parseado
    modelo_classificacao: ModeloClassificacao
    tempo_resposta_segundos: float


class ErroIAIndisponivel(Exception):
    """
    Levantada quando o provider de IA falha (timeout, erro externo,
    limite excedido). É o sinal que `services/fallback_handler.py`
    (Contrato Seção 1.2) observa para acionar o modo sem IA.
    """

    def __init__(self, motivo: str, causa_original: Exception | None = None):
        self.motivo = motivo
        self.causa_original = causa_original
        super().__init__(f"IA indisponível: {motivo}")


class ClienteIA(ABC):
    """
    Interface única entre o Motor NSI e qualquer provider de IA.
    Contrato Seção 1.1 — única porta de entrada para chamadas externas.
    """

    @abstractmethod
    def classificar(self, requisicao: RequisicaoIA) -> RespostaIA:
        """
        Envia uma requisição e retorna a resposta estruturada.
        Implementações devem levantar `ErroIAIndisponivel` em qualquer
        falha (timeout, erro HTTP, resposta malformada) — nunca deixar
        uma exceção de baixo nível (ex: `requests.Timeout`) escapar
        direto para quem chamou.
        """
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Implementação real — provider oficial: Groq
# ---------------------------------------------------------------------------

class ClienteGroq(ClienteIA):
    """
    Implementação real da interface `ClienteIA`, usando o SDK oficial
    da Groq. Provider oficial do Motor NSI (decisão de arquitetura).

    A GROQ_API_KEY é lida do ambiente. A ausência da chave não é tratada
    aqui como erro de configuração de código — é responsabilidade de
    quem compõe o motor (engine/pipeline.py) decidir se usa este cliente
    ou o `ClienteIAFalso`, conforme o ambiente disponível.
    """

    def __init__(self, modelo: str | None = None, timeout_segundos: float = 30.0):
        import groq  # import local: só carrega o SDK se este cliente for usado

        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ErroIAIndisponivel(
                "GROQ_API_KEY não configurada no ambiente. "
                "Isso é configuração de ambiente, não bloqueio de implementação "
                "(ver diretriz do projeto) — configure a variável e o motor "
                "funciona sem nenhuma mudança de código."
            )

        self._modelo = modelo or os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        self._timeout = timeout_segundos
        self._cliente = groq.Groq(api_key=api_key, timeout=timeout_segundos)

    def classificar(self, requisicao: RequisicaoIA) -> RespostaIA:
        import groq

        inicio = time.monotonic()
        try:
            completion = self._cliente.chat.completions.create(
                model=self._modelo,
                messages=[
                    {"role": "system", "content": requisicao.prompt_sistema},
                    {
                        "role": "user",
                        "content": json.dumps(
                            {"texto": requisicao.texto, "contexto": requisicao.contexto},
                            ensure_ascii=False,
                        ),
                    },
                ],
                response_format={"type": "json_object"},
                timeout=self._timeout,
            )
        except groq.APITimeoutError as exc:
            raise ErroIAIndisponivel("timeout na chamada à Groq", exc) from exc
        except groq.RateLimitError as exc:
            raise ErroIAIndisponivel("limite de uso excedido na Groq", exc) from exc
        except groq.APIError as exc:
            raise ErroIAIndisponivel(f"erro da API Groq: {exc}", exc) from exc
        except Exception as exc:  # noqa: BLE001 — fronteira externa, captura ampla deliberada
            raise ErroIAIndisponivel(f"erro inesperado ao chamar Groq: {exc}", exc) from exc

        tempo_resposta = time.monotonic() - inicio

        try:
            conteudo = json.loads(completion.choices[0].message.content)
        except (json.JSONDecodeError, IndexError, AttributeError) as exc:
            raise ErroIAIndisponivel(
                f"resposta da Groq não é JSON válido: {exc}", exc
            ) from exc

        return RespostaIA(
            conteudo=conteudo,
            modelo_classificacao=ModeloClassificacao(
                provider="groq",
                modelo=self._modelo,
                versao_prompt=requisicao.versao_prompt,
            ),
            tempo_resposta_segundos=round(tempo_resposta, 3),
        )


# ---------------------------------------------------------------------------
# Implementação de teste — mesma interface, sem chamada de rede
# ---------------------------------------------------------------------------

class ClienteIAFalso(ClienteIA):
    """
    Implementação de teste local da interface `ClienteIA`.

    NÃO é uma versão simplificada do motor — implementa exatamente a
    mesma interface que `ClienteGroq`, com o mesmo contrato de entrada
    e saída. Usada apenas em testes automatizados, para validar o
    pipeline sem depender de rede ou de uma chave de API real.

    Respostas pré-configuradas por tarefa; se nenhuma resposta for
    registrada para uma tarefa solicitada, levanta `ErroIAIndisponivel`
    (permite testar também o caminho de fallback).
    """

    def __init__(self):
        self._respostas_configuradas: dict[TipoTarefaIA, dict] = {}
        self._deve_falhar: set[TipoTarefaIA] = set()
        self.chamadas_recebidas: list[RequisicaoIA] = []

    def configurar_resposta(self, tarefa: TipoTarefaIA, conteudo: dict) -> None:
        """Define a resposta que este cliente fake retornará para uma tarefa."""
        self._respostas_configuradas[tarefa] = conteudo

    def configurar_falha(self, tarefa: TipoTarefaIA) -> None:
        """Faz este cliente simular indisponibilidade de IA para uma tarefa."""
        self._deve_falhar.add(tarefa)

    def classificar(self, requisicao: RequisicaoIA) -> RespostaIA:
        self.chamadas_recebidas.append(requisicao)

        if requisicao.tarefa in self._deve_falhar:
            raise ErroIAIndisponivel("falha simulada para teste")

        conteudo = self._respostas_configuradas.get(requisicao.tarefa)
        if conteudo is None:
            raise ErroIAIndisponivel(
                f"nenhuma resposta configurada para a tarefa {requisicao.tarefa!r} "
                f"neste ClienteIAFalso"
            )

        return RespostaIA(
            conteudo=conteudo,
            modelo_classificacao=ModeloClassificacao(
                provider="fake_teste_local",
                modelo="fake-v1",
                versao_prompt=requisicao.versao_prompt,
            ),
            tempo_resposta_segundos=0.0,
        )
