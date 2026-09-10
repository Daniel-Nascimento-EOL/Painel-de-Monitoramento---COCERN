"""Tema claro/escuro do painel.

O Streamlit fixa o tema em ``.streamlit/config.toml``, que não muda em
tempo de execução. Aqui o tema é estado de sessão: o alternador da barra
lateral grava a escolha e o CSS injetado em ``app.py`` repinta a interface,
enquanto o mapa troca de basemap e de paleta de marcadores.

Por que não usar só o tema nativo do Streamlit: o mapa é um HTML do Leaflet
embutido por ``components.v1.html``, fora do alcance do CSS da página. Ele
precisa receber as cores explicitamente — daí ``paleta_mapa()``.
"""

import streamlit as st

_CHAVE = "tema_escuro"

# Basemaps Esri, ambos servidos sem API key e sem marca d'água.
_TILES_CLARO = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/"
    "Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}"
)
_TILES_ESCURO = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/"
    "Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}"
)

# Paleta do mapa por tema. As cores de nível de tensão NÃO entram aqui: são
# definidas pelo usuário (69 verde-limão, 138 preto, 230 azul, 500 vermelho)
# e valem nos dois temas — ver core/ons_rede.py::_COR_POR_TENSAO. A exceção
# é o 138 kV preto, ilegível sobre fundo escuro: ver cor_tensao_tema().
_PALETA = {
    False: {  # claro
        "tiles": _TILES_CLARO,
        "conjuntos": "#3b5166",
        "usinas": "#c17a4f",
        "subestacao": "#5b6b74",
        "contorno": "#9aa5b1",
        "cidade": "#8a8f98",
        "linha_conexao": "#9aa5b1",
        "mascara": "#ffffff",
        "texto_ficha": "#3a444e",
        "titulo_ficha": "#2a3542",
        "rotulo_ficha": "#9aa5b1",
        "fundo_ficha": "#ffffff",
        "fundo_legenda": "rgba(255,255,255,0.92)",
        "borda_legenda": "#d7dbe0",
    },
    True: {  # escuro
        "tiles": _TILES_ESCURO,
        "conjuntos": "#8fb3d9",
        "usinas": "#e0975f",
        "subestacao": "#9aabb5",
        "contorno": "#5c6874",
        "cidade": "#8b939c",
        "linha_conexao": "#6d7783",
        "mascara": "#11161d",
        "texto_ficha": "#c8d2dc",
        "titulo_ficha": "#eef2f6",
        "rotulo_ficha": "#7f8b98",
        "fundo_ficha": "#1b222c",
        "fundo_legenda": "rgba(27,34,44,0.94)",
        "borda_legenda": "#39424e",
    },
}

# 138 kV é preto por definição do usuário; sobre o basemap escuro fica
# invisível, então no tema escuro usa-se um cinza bem claro no lugar. As
# outras três faixas têm contraste suficiente nos dois fundos.
_TENSAO_ESCURO = {138: "#e8ecf0"}


def escuro() -> bool:
    """Indica se o tema escuro está ativo nesta sessão."""
    return bool(st.session_state.get(_CHAVE, False))


def alternar(valor: bool) -> None:
    st.session_state[_CHAVE] = bool(valor)


def paleta() -> dict:
    """Cores do tema corrente, para o mapa e as fichas."""
    return _PALETA[escuro()]


def cor_tensao_tema(kv, cor_base: str) -> str:
    """Cor da linha por nível de tensão, ajustada ao tema.

    ``cor_base`` é a cor definida pelo usuário (``core.ons_rede.cor_tensao``);
    só o 138 kV muda no escuro, para não sumir no fundo.
    """
    if not escuro() or kv is None:
        return cor_base
    try:
        return _TENSAO_ESCURO.get(int(round(float(kv))), cor_base)
    except (TypeError, ValueError):
        return cor_base


def aplicar_plotly(fig):
    """Ajusta a figura Plotly ao tema: fundo transparente (para herdar o da
    página) e texto/grades legíveis no escuro.

    Devolve a própria figura, para encadear com ``st.plotly_chart``.
    """
    p = paleta()
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font_color=p["texto_ficha"],
        legend_font_color=p["texto_ficha"],
        # O título tem cor própria no Plotly e não segue font_color.
        title_font_color=p["titulo_ficha"],
    )
    grade = "#39424e" if escuro() else "#e5e7eb"
    fig.update_xaxes(gridcolor=grade, zerolinecolor=grade, linecolor=grade)
    fig.update_yaxes(gridcolor=grade, zerolinecolor=grade, linecolor=grade)
    return fig


def css() -> str:
    """CSS que repinta a interface do Streamlit no tema escuro.

    No tema claro devolve string vazia: o padrão do
    ``.streamlit/config.toml`` já é o visual pretendido.
    """
    if not escuro():
        return ""
    p = _PALETA[True]
    return f"""
    <style>
    [data-testid="stAppViewContainer"], [data-testid="stHeader"] {{
        background: #11161d;
    }}
    [data-testid="stSidebar"] {{
        background: #171d26;
        border-right: 1px solid #2a323d;
    }}
    body, [data-testid="stAppViewContainer"], [data-testid="stSidebar"],
    p, li, label, .stMarkdown {{
        color: {p['texto_ficha']};
    }}
    h1, h2, h3, h4, h5, h6 {{ color: {p['titulo_ficha']}; }}
    [data-testid="stMetricValue"] {{ color: {p['titulo_ficha']}; }}
    [data-testid="stMetricLabel"], [data-testid="stCaptionContainer"],
    [data-testid="stCaptionContainer"] p {{ color: {p['rotulo_ficha']}; }}
    hr, [data-testid="stSidebar"] hr {{ border-color: #2a323d; }}
    /* Caixas com borda (filtros, expanders) e campos de entrada. */
    [data-testid="stExpander"], div[data-testid="stVerticalBlockBorderWrapper"] {{
        background: {p['fundo_ficha']};
        border-color: #2a323d;
    }}
    .stTextInput input, .stNumberInput input, .stDateInput input,
    [data-baseweb="select"] > div, [data-baseweb="input"] > div {{
        background: #222a35 !important;
        color: {p['texto_ficha']} !important;
        border-color: #39424e !important;
    }}
    /* O contorno de foco padrão do Streamlit é vermelho vivo e destoa da
       paleta neutra; no escuro fica ainda mais gritante. */
    .stTextInput input:focus, [data-baseweb="input"] > div:focus-within {{
        border-color: #5b6b74 !important;
        box-shadow: none !important;
    }}
    /* Botões secundários (Tela inicial) acompanham o fundo em vez de
       aparecerem como um bloco claro na barra lateral. */
    .stButton > button[kind="secondary"] {{
        background: #222a35;
        color: {p['texto_ficha']};
        border: 1px solid #39424e;
    }}
    .stButton > button[kind="secondary"]:hover {{
        background: #2a3340;
        color: {p['titulo_ficha']};
        border-color: #4a5563;
    }}
    [data-testid="stDataFrame"] {{ background: {p['fundo_ficha']}; }}
    </style>
    """
