import streamlit as st

from ui import mapa

st.set_page_config(
    page_title="Constrained-off — Conjuntos Eólicos RN",
    page_icon="🌬️",
    layout="wide",
)

st.sidebar.title("Painel COCERN")
st.sidebar.caption("Monitoramento de constrained-off — Conjuntos Eólicos do RN")

st.title("Mapa de Conjuntos Eólicos — Rio Grande do Norte")
mapa.render()
