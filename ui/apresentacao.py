"""Tela de apresentação (entrada) do painel.

Precede as páginas de trabalho: fundo escuro com a arte alusiva à energia
eólica do RN (``data/icons/capa_rn.png``, gerada por
``scripts/gerar_arte_capa.py``), a sigla da ferramenta e o título por
extenso, e o botão que abre o painel.

O modo escuro fica **restrito a esta tela**: o painel em si segue claro, por
decisão de design (ver §5 do CLAUDE.md) e porque o mapa depende de um basemap
claro. O CSS abaixo é escopado ao contêiner da apresentação.
"""

import base64
from functools import lru_cache
from pathlib import Path

import streamlit as st

_CAPA = Path(__file__).resolve().parent.parent / "data" / "icons" / "capa_rn.png"

SIGLA = "COCERN"
TITULO = (
    "Painel de Monitoramento de Constrained-off "
    "dos Conjuntos Eólicos do Rio Grande do Norte"
)

# Chave de sessão que marca a apresentação como já vista.
_CHAVE_ENTRADA = "apresentacao_vista"


@lru_cache(maxsize=1)
def _capa_data_uri() -> str:
    """Arte de fundo embutida como ``data:`` URI (o Streamlit não serve
    arquivos estáticos por caminho no CSS)."""
    if not _CAPA.exists():
        return ""
    return "data:image/png;base64," + base64.b64encode(_CAPA.read_bytes()).decode("ascii")


def ja_vista() -> bool:
    """Indica se o usuário já passou pela tela de apresentação nesta sessão."""
    return bool(st.session_state.get(_CHAVE_ENTRADA))


def marcar_vista() -> None:
    st.session_state[_CHAVE_ENTRADA] = True


def voltar() -> None:
    """Reexibe a tela de apresentação (botão 'Tela inicial' da barra lateral)."""
    st.session_state[_CHAVE_ENTRADA] = False


def render() -> None:
    """Desenha a tela de apresentação e o botão de entrada."""
    fundo = _capa_data_uri()
    camada = (
        f"linear-gradient(100deg, rgba(13,19,27,0.97) 0%, rgba(13,19,27,0.82) 45%, "
        f"rgba(13,19,27,0.55) 100%), url('{fundo}')"
        if fundo
        else "linear-gradient(100deg, #0d131b 0%, #22303f 100%)"
    )
    st.markdown(
        f"""
        <style>
        /* Escurece a moldura do Streamlit apenas enquanto a capa está no ar. */
        [data-testid="stAppViewContainer"], [data-testid="stHeader"] {{
            background: #0d131b;
        }}
        [data-testid="stSidebar"] {{ display: none; }}
        .capa {{
            background: {camada};
            background-size: cover;
            background-position: center right;
            border-radius: 14px;
            padding: 4.4rem 3.2rem 4.0rem;
            min-height: 26rem;
            display: flex;
            flex-direction: column;
            justify-content: center;
            box-shadow: 0 18px 48px rgba(0,0,0,0.45);
        }}
        .capa .sigla {{
            font-family: Georgia, "Times New Roman", serif;
            font-size: 4.6rem;
            font-weight: 600;
            letter-spacing: .10em;
            line-height: 1;
            color: #f2f5f8;
            margin: 0;
        }}
        .capa .regua {{
            width: 74px; height: 3px;
            background: #c17a4f;
            margin: 1.1rem 0 1.4rem;
        }}
        .capa .titulo {{
            font-family: Georgia, "Times New Roman", serif;
            font-size: 1.32rem;
            font-weight: 400;
            line-height: 1.45;
            color: #dbe3ea;
            max-width: 34rem;
            margin: 0 0 .9rem;
        }}
        .capa .nota {{
            font-size: .86rem;
            color: #8fa0b0;
            max-width: 34rem;
            margin: 0;
        }}
        @media (max-width: 640px) {{
            .capa {{ padding: 2.6rem 1.5rem; min-height: 20rem; }}
            .capa .sigla {{ font-size: 3rem; }}
            .capa .titulo {{ font-size: 1.05rem; }}
        }}
        </style>
        <div class="capa">
            <p class="sigla">{SIGLA}</p>
            <div class="regua"></div>
            <p class="titulo">{TITULO}</p>
            <p class="nota">
                Energia frustrada por restrição operativa, preço horário do
                submercado Nordeste e a rede de transmissão que atende aos
                conjuntos — a partir dos dados abertos do ONS, da ANEEL e da CCEE.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    _, coluna = st.columns([3, 1])
    with coluna:
        if st.button("Entrar no painel", type="primary", use_container_width=True):
            marcar_vista()
            st.rerun()
