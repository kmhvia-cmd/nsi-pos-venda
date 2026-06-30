from __future__ import annotations
from dataclasses import dataclass
from services.ai_classifier import ClienteIA, ErroIAIndisponivel, RequisicaoIA, RespostaIA

@dataclass
class ResultadoComFallback:
    sucesso: bool
    resposta: RespostaIA | None
    motivo_falha: str | None

def chamar_com_fallback(cliente: ClienteIA, requisicao: RequisicaoIA) -> ResultadoComFallback:
    try:
        resposta = cliente.classificar(requisicao)
        return ResultadoComFallback(sucesso=True, resposta=resposta, motivo_falha=None)
    except ErroIAIndisponivel as exc:
        return ResultadoComFallback(sucesso=False, resposta=None, motivo_falha=exc.motivo)
    except Exception as exc:
        return ResultadoComFallback(sucesso=False, resposta=None, motivo_falha=f"falha nao classificada: {exc}")

def determinar_status_semantico(resultado: ResultadoComFallback) -> str:
    return "concluido" if resultado.sucesso else "pendente"
