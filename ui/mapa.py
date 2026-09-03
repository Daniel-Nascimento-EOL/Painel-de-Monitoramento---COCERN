"""Página do mapa de localização dos conjuntos eólicos do RN."""

import streamlit as st
import streamlit.components.v1 as components

from datetime import date

from core.coff_cache import acumulado_do_ano
from core.data_loader import load_bays, load_cidades, load_conjuntos, load_usinas
from core.ons_rede import baixar_linhas_rn, baixar_subestacoes_rn
from viz.map_charts import CAMADAS_PADRAO, build_map_html, df_para_key
from viz.mapa_estatico import gerar_png_mapa_cache

_ROTULO_CAMADA = {
    "conjuntos": "Conjuntos eólicos",
    "usinas": "Usinas individuais",
    "subestacoes": "Subestações",
    "linhas_transmissao": "Linhas de transmissão (ONS)",
    "linhas_conexao": "Linhas de conexão conjunto–SE",
    "cidades": "Cidades de referência",
}


def _bloco_download_imagem(filtrado, usinas_filtradas, df_bays, df_cidades, df_linhas, df_ses, camadas) -> None:
    """Botão de gerar/baixar a imagem PNG do mapa com as camadas atuais.

    A geração é sob demanda (baixa tiles do Esri, ~2 s a frio) — só roda
    quando o usuário clica; o resultado fica em session_state para o
    ``st.download_button`` seguinte."""
    col_gerar, col_baixar = st.columns([1, 1])
    with col_gerar:
        if st.button("🖼️ Gerar imagem do mapa (PNG)", use_container_width=True):
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
    png = st.session_state.get("_mapa_png")
    if png:
        with col_baixar:
            st.download_button(
                "⬇️ Baixar PNG",
                data=png,
                file_name=f"mapa_conjuntos_rn_{date.today():%Y%m%d}.png",
                mime="image/png",
                use_container_width=True,
            )
        st.caption(
            "Imagem gerada com as camadas marcadas em **Camadas do mapa**. "
            "Reabra o gerador após mudar filtros ou camadas."
        )


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
    try:
        df_linhas = baixar_linhas_rn()
    except Exception:
        df_linhas = None
    try:
        # Índice das SE de transmissão do RN — posiciona as pontas das linhas
        # de transmissão; os marcadores de SE continuam vindo de bays.xlsx.
        df_ses = baixar_subestacoes_rn()
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

    mapa_html = build_map_html(
        df_para_key(filtrado),
        df_para_key(usinas_filtradas),
        df_para_key(df_bays),
        df_para_key(df_cidades),
        df_para_key(df_linhas),
        df_para_key(df_ses),
        tuple(sorted(camadas.items())),
        altura=650,
        acumulado_json=df_para_key(
            df_acumulado.reset_index() if df_acumulado is not None else None
        ),
        rotulo_periodo=f" em {ano_acumulado}",
    )
    components.html(mapa_html, height=665, scrolling=False)

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
