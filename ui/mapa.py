"""Página do mapa de localização dos conjuntos eólicos do RN."""

import streamlit as st
from streamlit_folium import st_folium

from datetime import date

from core import tema
from core.agentes import classe_css_logos, separar_agentes
from core.coff_cache import acumulado_do_ano
from core.data_loader import load_bays, load_cidades, load_conjuntos, load_usinas, municipios_unicos
from core.ons_rede import ler_linhas_rn, ler_subestacoes_rn
from viz.map_charts import CAMADAS_PADRAO, build_map_cacheable, df_para_key, ficha_conjunto_html
from viz.mapa_estatico import gerar_png_mapa_cache

_ROTULO_CAMADA = {
    "conjuntos": "Conjuntos eólicos",
    "usinas": "Usinas individuais",
    "subestacoes": "Subestações",
    "linhas_transmissao": "Linhas de transmissão (ONS)",
    "linhas_conexao": "Linhas de conexão conjunto–SE",
    "cidades": "Cidades de referência",
}

_CHAVE_CONJUNTO_SELECIONADO = "_conjunto_selecionado"


def _bloco_download_imagem(filtrado, usinas_filtradas, df_bays, df_cidades, df_linhas, df_ses, camadas) -> None:
    """Controle discreto para gerar e baixar a imagem PNG do mapa.

    A geração é sob demanda (baixa tiles do Esri, ~2 s a frio) — só roda
    quando o usuário clica; o resultado fica em session_state para o
    ``st.download_button`` seguinte.

    Ocupa uma coluna estreita à direita, alinhado ao canto do mapa, em vez
    de dois botões de meia largura: é ação acessória, não deve competir
    visualmente com o mapa.
    """
    # A imagem vale para os filtros/camadas de quando foi gerada; se algo
    # mudar, descarta-se para o botão voltar a ser "Gerar imagem".
    assinatura = (len(filtrado), len(usinas_filtradas), tuple(sorted(camadas.items())))
    if st.session_state.get("_mapa_png_assinatura") != assinatura:
        st.session_state.pop("_mapa_png", None)
        st.session_state["_mapa_png_assinatura"] = assinatura

    _, col = st.columns([3, 1])
    with col:
        png = st.session_state.get("_mapa_png")
        if png:
            st.download_button(
                "Baixar imagem",
                data=png,
                file_name=f"mapa_conjuntos_rn_{date.today():%Y%m%d}.png",
                mime="image/png",
                use_container_width=True,
            )
        elif st.button("Gerar imagem", use_container_width=True):
            st.session_state["_mapa_png"] = gerar_png_mapa_cache(
                df_para_key(filtrado),
                df_para_key(usinas_filtradas),
                df_para_key(df_bays),
                df_para_key(df_cidades),
                df_para_key(df_linhas),
                df_para_key(df_ses),
                tuple(sorted(camadas.items())),
                largura=1600,
                altura=1100,
            )
            st.rerun()


def _agentes_unicos(df, coluna: str) -> list[str]:
    todos = set()
    for valor in df[coluna].dropna():
        todos.update(separar_agentes(valor))
    return sorted(todos)


def _filtrar_por_agente(df, coluna: str, selecionados: list[str]):
    if not selecionados:
        return df
    return df[df[coluna].apply(lambda v: any(a in separar_agentes(v) for a in selecionados))]


def _renderizar_ficha(conjunto_nome, df_conjuntos, df_acumulado, ano_acumulado) -> None:
    """Card de detalhe do conjunto selecionado, na coluna à direita do mapa."""
    if not conjunto_nome:
        st.info("Clique num marcador de conjunto no mapa para ver a ficha de detalhe.")
        return

    linhas = df_conjuntos[df_conjuntos["conjunto"] == conjunto_nome]
    if linhas.empty:
        st.info("Conjunto fora do filtro atual — ajuste os filtros ou clique noutro marcador.")
        return

    row = linhas.iloc[0]
    acumulado = None
    if df_acumulado is not None and row.get("id_ons") in df_acumulado.index:
        acumulado = df_acumulado.loc[row["id_ons"]].to_dict()

    html = ficha_conjunto_html(row, acumulado, rotulo_periodo=f" em {ano_acumulado}")
    st.markdown(html, unsafe_allow_html=True)


def render() -> None:
    df_conjuntos = load_conjuntos()
    df_usinas = load_usinas()
    df_bays = load_bays()
    df_cidades = load_cidades()
    try:
        df_linhas = ler_linhas_rn()
    except Exception:
        df_linhas = None
    try:
        # Índice das SE de transmissão do RN — posiciona as pontas das linhas
        # de transmissão; os marcadores de SE continuam vindo de bays.xlsx.
        df_ses = ler_subestacoes_rn()
    except Exception:
        df_ses = None

    # Acumulado de constrained-off do ano corrente, exibido na ficha de cada
    # conjunto. Servido do cache em disco (core/coff_cache.py); uma falha do
    # ONS/CCEE apenas deixa a ficha sem os números, sem derrubar o mapa.
    ano_acumulado = date.today().year
    try:
        df_acumulado, meses_acumulados = acumulado_do_ano(
            ano_acumulado, somente_consolidados=True
        )
    except Exception:
        df_acumulado, meses_acumulados = None, []

    st.markdown("## Mapa de Conjuntos Eólicos — Rio Grande do Norte")
    st.markdown(
        # O container global (app.py) limita a 1200px pra deixar as demais
        # páginas confortáveis de ler; o mapa é a única que se beneficia de
        # mais largura — sobrava área em branco nas laterais e o mapa saía
        # pequeno em relação ao card de ficha ao lado.
        "<style>.block-container { max-width: 1600px; }</style>",
        unsafe_allow_html=True,
    )
    # As classes .logo-* das logomarcas de agente também precisam existir
    # aqui, fora do iframe do mapa: a ficha do conjunto virou card desta
    # página (ui/mapa.py), não popup dentro do HTML do Folium — declarar o
    # CSS só lá dentro (viz/map_charts.py::build_map) não alcança o card.
    css_logos, _ = classe_css_logos()
    st.markdown(css_logos, unsafe_allow_html=True)
    st.divider()

    st.sidebar.markdown("#### Filtros")
    with st.sidebar.container(border=True):
        municipios_disponiveis = municipios_unicos(df_conjuntos)
        municipios_selecionados = st.multiselect(
            "Município", municipios_disponiveis, placeholder="Todos"
        )
        proprietarios_disponiveis = _agentes_unicos(df_conjuntos, "agente_proprietario")
        proprietarios_selecionados = st.multiselect(
            "Agente Proprietário", proprietarios_disponiveis, placeholder="Todos"
        )
        operadores_disponiveis = _agentes_unicos(df_conjuntos, "agente_operador")
        operadores_selecionados = st.multiselect(
            "Agente Operador", operadores_disponiveis, placeholder="Todos"
        )
        busca = st.text_input("Buscar conjunto", placeholder="ex.: Acauã")

    with st.sidebar.expander("Camadas do mapa", expanded=False):
        camadas = {
            chave: st.checkbox(_ROTULO_CAMADA[chave], value=padrao, key=f"camada_{chave}")
            for chave, padrao in CAMADAS_PADRAO.items()
        }

    filtrado = df_conjuntos
    if municipios_selecionados:
        filtrado = filtrado[
            filtrado["municipios"].apply(
                lambda m: any(sel in m for sel in municipios_selecionados)
            )
        ]
    filtrado = _filtrar_por_agente(filtrado, "agente_proprietario", proprietarios_selecionados)
    filtrado = _filtrar_por_agente(filtrado, "agente_operador", operadores_selecionados)
    if busca:
        filtrado = filtrado[filtrado["conjunto"].str.contains(busca, case=False, na=False)]

    usinas_filtradas = df_usinas[df_usinas["chave"].isin(filtrado["chave"])]

    st.sidebar.divider()
    c1, c2 = st.sidebar.columns(2)
    c1.metric("Conjuntos", len(filtrado))
    c2.metric("Usinas", int(filtrado["qtd_usinas"].sum()))
    c3, c4 = st.sidebar.columns(2)
    c3.metric("Municípios", len(municipios_unicos(filtrado)))
    c4.metric("Capacidade", f"{filtrado['capacidade_mw'].sum():.0f} MW")

    col_mapa, col_ficha = st.columns([2.6, 1])
    with col_mapa:
        fmap = build_map_cacheable(
            df_para_key(filtrado),
            df_para_key(usinas_filtradas),
            df_para_key(df_bays),
            df_para_key(df_cidades),
            df_para_key(df_linhas),
            df_para_key(df_ses),
            tuple(sorted(camadas.items())),
            acumulado_json=df_para_key(
                df_acumulado.reset_index() if df_acumulado is not None else None
            ),
            rotulo_periodo=f" em {ano_acumulado}",
            tema_escuro=tema.escuro(),
        )
        evento = st_folium(
            fmap,
            height=780,
            use_container_width=True,
            returned_objects=["last_object_clicked_tooltip"],
            key="mapa_conjuntos",
        )
        clicado = evento.get("last_object_clicked_tooltip") if evento else None
        if clicado:
            st.session_state[_CHAVE_CONJUNTO_SELECIONADO] = clicado

    with col_ficha:
        _renderizar_ficha(
            st.session_state.get(_CHAVE_CONJUNTO_SELECIONADO),
            filtrado,
            df_acumulado,
            ano_acumulado,
        )

    if meses_acumulados:
        primeiro, ultimo = meses_acumulados[0], meses_acumulados[-1]
        st.caption(
            f"Os acumulados na ficha de cada conjunto cobrem "
            f"{primeiro[1]:02d}/{primeiro[0]} a {ultimo[1]:02d}/{ultimo[0]} "
            f"({len(meses_acumulados)} meses) · Fontes: ONS (constrained-off) e CCEE (PLD horário)"
        )
    else:
        st.caption(
            "Acumulado de constrained-off indisponível no momento — "
            "a ficha do conjunto exibe apenas os dados cadastrais."
        )

    _bloco_download_imagem(filtrado, usinas_filtradas, df_bays, df_cidades, df_linhas, df_ses, camadas)

    with st.expander(f"Tabela de conjuntos ({len(filtrado)})"):
        st.dataframe(
            filtrado[
                [
                    "conjunto",
                    "municipios",
                    "qtd_usinas",
                    "capacidade_mw",
                    "ponto_conexao",
                    "agente_proprietario",
                    "agente_operador",
                ]
            ].rename(
                columns={
                    "conjunto": "Conjunto",
                    "municipios": "Município(s)",
                    "qtd_usinas": "Qtd. usinas",
                    "capacidade_mw": "Capacidade (MW)",
                    "ponto_conexao": "Ponto de conexão",
                    "agente_proprietario": "Agente Proprietário",
                    "agente_operador": "Agente Operador",
                }
            ),
            width="stretch",
            hide_index=True,
        )
