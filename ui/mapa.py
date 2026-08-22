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

    st.sidebar.header("Filtros")
    municipios_disponiveis = _municipios_unicos(df_conjuntos)
    municipios_selecionados = st.sidebar.multiselect("Município", municipios_disponiveis)
    busca = st.sidebar.text_input("Buscar conjunto")
    mostrar_usinas = st.sidebar.checkbox("Mostrar usinas individuais", value=False)

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

    col1, col2, col3 = st.columns(3)
    col1.metric("Conjuntos", len(filtrado))
    col2.metric("Usinas", int(filtrado["qtd_usinas"].sum()))
    col3.metric("Municípios", len(_municipios_unicos(filtrado)))

    fig = build_map(filtrado, usinas_filtradas, mostrar_usinas=mostrar_usinas)
    st.plotly_chart(fig, width="stretch")

    with st.expander(f"Conjuntos listados ({len(filtrado)})"):
        st.dataframe(
            filtrado[["conjunto", "municipios", "qtd_usinas", "observacao"]],
            width="stretch",
            hide_index=True,
        )
