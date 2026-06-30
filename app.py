# -*- coding: utf-8 -*-
"""
NSI - Nucleo de Inteligencia Semantica
app.py - Servidor principal
"""
import os
from flask import Flask, request, jsonify, send_file, render_template, send_from_directory
from config import Config
from pathlib import Path

app = Flask(__name__, template_folder=os.path.abspath("."))

# ===== HEALTH =====
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "sistema": "NSI", "versao": "2.0"})

# ===== UPLOAD =====
@app.route("/upload", methods=["POST"])
def upload():
    from adapters.storage import salvar_lote
    if "file" not in request.files:
        return jsonify({"erro": "arquivo_nao_enviado"}), 400
    arquivo = request.files["file"]
    if not arquivo.filename.endswith((".csv", ".xlsx")):
        return jsonify({"erro": "formato_invalido"}), 400
    empresa = request.form.get('empresa', '')
    nome = request.form.get('nome', '')
    data_inicio = request.form.get('data_inicio', '')
    data_fim = request.form.get('data_fim', '')
    resultado = salvar_lote(arquivo, empresa=empresa, nome=nome, data_inicio=data_inicio, data_fim=data_fim)
    return jsonify(resultado), 200

# ===== PROCESSAR LOTE =====
@app.route("/lote/<lote_id>/analisar", methods=["POST"])
def analisar(lote_id):
    from core.dispatcher import processar_lote
    resultado = processar_lote(lote_id)
    return jsonify(resultado), 200

# ===== GERAR PDF =====
@app.route("/pdf/<lote_id>", methods=["GET"])
def gerar_pdf(lote_id):
    from services.pdf_report import gerar_pdf
    caminho = gerar_pdf(lote_id)
    return send_file(caminho, mimetype="application/pdf")

# ===== LISTAR LOTES =====
@app.route("/lotes", methods=["GET"])
def listar_lotes():
    from adapters.storage import listar_lotes
    lotes = listar_lotes()
    return jsonify({"total": len(lotes), "lotes": lotes}), 200



# ===== D+8 STATUS =====
@app.route('/api/lote/<lote_id>/d8')
def api_d8(lote_id):
    from core.scheduler import calcular_d8
    from adapters.storage import carregar_lote
    lote = carregar_lote(lote_id)
    d8 = calcular_d8(lote.get('criado_em', ''))
    return jsonify(d8)
# ===== FRONTEND OPERACIONAL =====
@app.route('/operacional')
def painel_operacional():
    return render_template('frontend/templates/operacional.html')

@app.route('/static/operacional/<path:filename>')
def static_operacional(filename):
    return send_from_directory('frontend/static', filename)
# ===== INTERFACE EXECUTIVA =====
@app.route("/empresa/<slug>")
def interface_executiva(slug):
    from adapters.storage import listar_lotes
    lotes = listar_lotes()
    relatorios = [{"id": l["id"], "label": l.get("label", l["id"])} for l in lotes if l.get("empresa") == slug]
    return render_template("interface_executiva/templates/dashboard.html",
        empresa=slug, relatorios=relatorios, data="", lote="")

@app.route("/api/relatorio/<relatorio_id>")
def api_relatorio(relatorio_id):
    from adapters.storage import carregar_lote
    dados = carregar_lote(relatorio_id)
    return jsonify(dados)

@app.route("/static/executiva/<path:filename>")
def static_executiva(filename):
    return send_from_directory("interface_executiva/static", filename)

@app.route("/api/lote/<lote_id>/disparar", methods=["POST"])
def disparar_lote_whatsapp(lote_id):
    from core.scheduler import disparar_lote
    try:
        resultado = disparar_lote(lote_id)
        return jsonify({"sucesso": True, "resultado": resultado})
    except Exception as e:
        return jsonify({"sucesso": False, "erro": str(e)}), 500
# ===== WEBHOOK WHATSAPP =====
WEBHOOK_VERIFY_TOKEN = "nsi_webhook_token_2026"

@app.route("/webhook", methods=["GET"])
def webhook_verificar():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and token == WEBHOOK_VERIFY_TOKEN:
        return challenge, 200
    return "Token invalido", 403

@app.route("/webhook", methods=["POST"])
def webhook_receber():
    from services.webhook_handler import processar_webhook
    payload = request.get_json(silent=True) or {}
    resultado = processar_webhook(payload)
    return jsonify(resultado), 200
# ===== MAIN =====
if __name__ == "__main__":
    print("=" * 40)
    print("NSI - Nucleo de Inteligencia Semantica")
    print(f"Iniciando na porta {Config.PORT}...")
    print("=" * 40)
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG)