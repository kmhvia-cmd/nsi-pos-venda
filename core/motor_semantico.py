# -*- coding: utf-8 -*-
"""
NSI — core/motor_semantico.py
Responsabilidade: analisar resposta de cliente via Groq API
"""
import json
from groq import Groq
from config import Config

cliente_groq = Groq(api_key=Config.GROQ_API_KEY)

PROMPT_SISTEMA = """Voce e um especialista em analise semantica de experiencias de clientes.
Analise a resposta do cliente e retorne SOMENTE um JSON valido com esta estrutura exata:
{
  "sentimento_geral": "positivo|negativo|neutro",
  "score_experiencia": 0-100,
  "probabilidade_churn": 0-100,
  "probabilidade_recompra": 0-100,
  "intensidade_emocional": 0-10,
  "risco_operacional": "alto|moderado|baixo",
  "dores_identificadas": ["lista", "de", "dores"],
  "elogios_identificados": ["lista", "de", "elogios"],
  "acao_recomendada": "acao clara e objetiva",
  "categoria_principal": "categoria do problema ou elogio",
  "leitura_semantica": {
    "semantica": "o que o cliente disse literalmente",
    "hermeneutica": "o que o cliente quis dizer de verdade",
    "semiotica": "os simbolos e sinais presentes na fala",
    "metafora": "imagens e comparacoes usadas",
    "ironia": "criticas disfarcadas ou sarcasmo detectado",
    "intensidade": "nivel emocional descrito",
    "padroes": "comportamentos repetitivos detectados",
    "intencao_oculta": "o que o cliente nao disse mas sinalizou"
  }
}"""


def analisar_cliente(nome: str, produto: str, resposta: str) -> dict:
    prompt = f"Cliente: {nome}\nProduto: {produto}\nResposta: {resposta}"
    try:
        completion = cliente_groq.chat.completions.create(
            model=Config.GROQ_MODEL,
            messages=[
                {"role": "system", "content": PROMPT_SISTEMA},
                {"role": "user",   "content": prompt},
            ],
            temperature=0.3,
            max_tokens=1000,
        )
        texto = completion.choices[0].message.content.strip()
        if texto.startswith("```"):
            texto = texto.split("```")[1]
            if texto.startswith("json"):
                texto = texto[4:]
        return json.loads(texto)
    except Exception as e:
        return {
            "sentimento_geral": "neutro",
            "score_experiencia": 0,
            "probabilidade_churn": 50,
            "probabilidade_recompra": 50,
            "intensidade_emocional": 5,
            "risco_operacional": "moderado",
            "dores_identificadas": [],
            "elogios_identificados": [],
            "acao_recomendada": "revisar manualmente",
            "categoria_principal": "erro_analise",
            "leitura_semantica": {},
            "erro": str(e),
        }
