import streamlit as st

from ui import mapa

st.set_page_config(
    page_title="Constrained-off — Conjuntos Eólicos RN",
    page_icon="🌬️",
    layout="wide",
    initial_sidebar_state="expanded",
)

_CSS = """
<style>
#MainMenu, footer {visibility: hidden;}

.block-container {
    padding-top: 2.5rem;
    padding-bottom: 2rem;
    max-width: 1200px;
}

h1, h2, h3 {
    font-family: Georgia, "Times New Roman", serif;
    font-weight: 600;
    letter-spacing: -0.01em;
}

[data-testid="stSidebar"] h1 {
    font-size: 1.15rem;
    margin-bottom: 0;
}

[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {
    color: #6b7280;
}

hr {
    margin: 0.6rem 0 1.2rem 0;
    border-color: #e5e7eb;
}

[data-testid="stMetricValue"] {
    font-size: 1.4rem;
}
</style>
"""
st.markdown(_CSS, unsafe_allow_html=True)

st.sidebar.title("Painel COCERN")
st.sidebar.caption("Monitoramento de constrained-off — Conjuntos Eólicos do RN")
st.sidebar.divider()

mapa.render()
