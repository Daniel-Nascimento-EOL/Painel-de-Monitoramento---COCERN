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

from core.agentes import separar_agentes
from core.data_loader import load_conjuntos, municipios_unicos
from core.formatos import numero_br

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


def _metricas_painel() -> list[tuple[str, str]]:
    """(valor formatado, rótulo) das 7 métricas gerais exibidas na capa."""
    df = load_conjuntos()
    proprietarios: set[str] = set()
    for valor in df["agente_proprietario"].dropna():
        proprietarios.update(separar_agentes(valor))
    operadores: set[str] = set()
    for valor in df["agente_operador"].dropna():
        operadores.update(separar_agentes(valor))

    return [
        (str(len(df)), "Conjuntos eólicos"),
        (f"{numero_br(df['capacidade_mw'].sum(), 0)} MW", "Capacidade instalada"),
        (numero_br(int(df["qtd_usinas"].sum()), 0), "Usinas"),
        (numero_br(int(df["qtd_aerogeradores"].sum()), 0), "Aerogeradores"),
        (str(len(municipios_unicos(df))), "Municípios"),
        (str(len(proprietarios)), "Agentes Proprietários"),
        (str(len(operadores)), "Agentes Operadores"),
    ]


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
        /* O fundo escuro vale SÓ enquanto a capa está no ar. O seletor é
           ancorado em :has(.capa): quando o painel entra, a .capa deixa de
           existir no DOM e a regra para de casar sozinha. Sem isso, o CSS
           injetado ficava valendo depois de entrar e o painel — que é claro
           por decisão de design — aparecia travado no escuro. */
        body:has(.capa) [data-testid="stAppViewContainer"],
        body:has(.capa) [data-testid="stHeader"] {{
            background: #0d131b;
        }}
        body:has(.capa) [data-testid="stSidebar"] {{ display: none; }}
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
        .capa .metricas {{
            display: grid;
            grid-template-columns: repeat(7, 1fr);
            gap: 1.4rem;
            max-width: 44rem;
            margin-top: 1.7rem;
        }}
        .capa .metrica .valor {{
            font-family: Georgia, "Times New Roman", serif;
            font-size: 1.5rem;
            font-weight: 600;
            color: #f2f5f8;
            line-height: 1.2;
        }}
        .capa .metrica .rotulo {{
            font-size: .74rem;
            color: #8fa0b0;
            margin-top: .2rem;
        }}
        /* Afasta do card o bloco que traz o botão de entrada (o elemento
           logo após o markdown da capa), que sem isto encosta na borda. */
        body:has(.capa) div[data-testid="stHorizontalBlock"] {{
            margin-top: 1.6rem;
        }}
        @media (max-width: 640px) {{
            .capa {{ padding: 2.6rem 1.5rem; min-height: 20rem; }}
            .capa .sigla {{ font-size: 3rem; }}
            .capa .titulo {{ font-size: 1.05rem; }}
            .capa .metricas {{ grid-template-columns: repeat(2, 1fr); gap: 1rem; }}
        }}
        </style>
        <div class="capa">
            <p class="sigla">{SIGLA}</p>
            <div class="regua"></div>
            <p class="titulo">{TITULO}</p>
            <div class="metricas">
                {"".join(
                    f'<div class="metrica"><div class="valor">{valor}</div>'
                    f'<div class="rotulo">{rotulo}</div></div>'
                    for valor, rotulo in _metricas_painel()
                )}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    _, coluna = st.columns([3, 1])
    with coluna:
        if st.button("Entrar no painel", type="primary", use_container_width=True):
            marcar_vista()
            st.rerun()
