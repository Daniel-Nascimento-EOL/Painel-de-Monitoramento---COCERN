"""Página do mapa de localização dos conjuntos eólicos do RN."""

import streamlit as st
from streamlit_folium import st_folium

from core.data_loader import load_bays, load_cidades, load_conjuntos, load_usinas
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
    df_bays = load_bays()
    df_cidades = load_cidades()

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
    c1, c2 = st.sidebar.columns(2)
    c1.metric("Conjuntos", len(filtrado))
    c2.metric("Usinas", int(filtrado["qtd_usinas"].sum()))
    c3, c4 = st.sidebar.columns(2)
    c3.metric("Municípios", len(_municipios_unicos(filtrado)))
    c4.metric("Capacidade", f"{filtrado['capacidade_mw'].sum():.0f} MW")

    mapa_fig = build_map(
        filtrado, usinas_filtradas, df_bays, df_cidades, mostrar_usinas=mostrar_usinas
    )
    st_folium(mapa_fig, height=650, use_container_width=True, returned_objects=[])

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
