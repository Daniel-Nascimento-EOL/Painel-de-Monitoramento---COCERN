"""Página do mapa de localização dos conjuntos eólicos do RN."""

import streamlit as st

from core.data_loader import load_conjuntos, load_usinas
from viz.map_charts import build_map


def _municipios_unicos(df) -> list[str]:
    todos = set()
    for valor in df["municipios"].dropna():
        for municipio in valor.split(";"):
            todos.add(municipio.strip())
    return sorted(todos)


def render() -> None:
    df_conjuntos = load_conjuntos()
    df_usinas = load_usinas()

    st.markdown("## Mapa de Conjuntos Eólicos — Rio Grande do Norte")
    st.caption(
        "Conjuntos eólicos Tipo II-C localizados no RN · "
        "Fontes: ONS SINMAPS, ONS (relação conjunto–usina), ANEEL SIGA"
    )
    st.divider()

    st.sidebar.markdown("#### Filtros")
    with st.sidebar.container(border=True):
        municipios_disponiveis = _municipios_unicos(df_conjuntos)
        municipios_selecionados = st.multiselect(
            "Município", municipios_disponiveis, placeholder="Todos"
        )
        busca = st.text_input("Buscar conjunto", placeholder="ex.: Acauã")
        mostrar_usinas = st.toggle("Mostrar usinas individuais", value=False)

    filtrado = df_conjuntos
    if municipios_selecionados:
        filtrado = filtrado[
            filtrado["municipios"].apply(
                lambda m: any(sel in m for sel in municipios_selecionados)
            )
        ]
    if busca:
        filtrado = filtrado[filtrado["conjunto"].str.contains(busca, case=False, na=False)]

    usinas_filtradas = df_usinas[df_usinas["chave"].isin(filtrado["chave"])]

    st.sidebar.divider()
    c1, c2, c3 = st.sidebar.columns(3)
    c1.metric("Conjuntos", len(filtrado))
    c2.metric("Usinas", int(filtrado["qtd_usinas"].sum()))
    c3.metric("Municípios", len(_municipios_unicos(filtrado)))

    fig = build_map(filtrado, usinas_filtradas, mostrar_usinas=mostrar_usinas)
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": "hover"})

    with st.expander(f"Tabela de conjuntos ({len(filtrado)})"):
        st.dataframe(
            filtrado[["conjunto", "municipios", "qtd_usinas", "observacao"]],
            width="stretch",
            hide_index=True,
        )
