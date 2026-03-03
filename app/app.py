import streamlit as st
from datetime import datetime
from core.lote import Lote

st.set_page_config(page_title="NSI - Núcleo Semântico de Inteligência", layout="wide")

st.title("🧠 NSI – Núcleo de Inteligência Semântica")

# ==============================
# INICIALIZAÇÃO DO LOTE
# ==============================

if "lote" not in st.session_state:
    st.session_state.lote = Lote(datetime.now())

lote = st.session_state.lote

# ==============================
# STATUS
# ==============================

st.subheader("Status do Lote")

dias = lote.dias_passados()
progresso = lote.progresso()

if lote.verificar_d8():
    status_texto = "🟢 PRONTO PARA DISPARO"
else:
    status_texto = "🟡 AGUARDANDO D+8"

st.markdown(f"### {status_texto}")
st.progress(progresso / 100)
st.write(f"{progresso}% concluído")
st.write(f"Dias passados desde criação: {dias}")

# ==============================
# BOTÃO DE RESET
# ==============================

if st.button("🔄 Reiniciar Lote"):
    st.session_state.lote = Lote(datetime.now())
    st.rerun()
