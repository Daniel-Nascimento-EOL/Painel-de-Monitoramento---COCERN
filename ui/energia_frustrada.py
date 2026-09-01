"""Página de Energia Frustrada — constrained-off eólico do RN.

Baixa os dados abertos do ONS (restrição/COFF, filtrados por RN) e do PLD
horário da CCEE (subsistema Nordeste), reproduz as 5 metodologias de
cálculo de energia frustrada definidas pelo usuário e exibe agregados por
conjunto e ao longo do tempo.
"""

import plotly.express as px
import streamlit as st

from core.ccee_pld import anexar_pld, baixar_pld_nordeste
from core.data_loader import load_conjuntos
from core.ons_coff import METODOLOGIAS, baixar_mes_rn, calcular_metodologias, meses_disponiveis

_NOMES_MES = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]


def render() -> None:
    st.markdown("## Energia Frustrada — Constrained-off Eólico do RN")
    st.caption(
        "Dados abertos do ONS: restrição/COFF eólica e CMO Semi-Horário "
        "(preço de referência) · atualizado automaticamente 2x ao dia pelo ONS"
    )
    st.divider()

    df_conjuntos = load_conjuntos()

    st.sidebar.markdown("#### Filtros")
    with st.sidebar.container(border=True):
        meses = meses_disponiveis()
        rotulos_mes = [f"{_NOMES_MES[m - 1].capitalize()}/{a}" for a, m in meses]
        indice_mes = st.selectbox("Mês de referência", range(len(meses)), format_func=lambda i: rotulos_mes[i])
        ano, mes = meses[indice_mes]

        conjuntos_selecionados = st.multiselect(
            "Conjunto", df_conjuntos["conjunto"].sort_values().tolist(), placeholder="Todos"
        )

        metodo = st.selectbox(
            "Metodologia de cálculo", list(METODOLOGIAS.keys()), format_func=lambda n: f"Metodologia {n}"
        )
        st.caption(METODOLOGIAS[metodo][1])

    try:
        df_bruto = baixar_mes_rn(ano, mes)
    except Exception as exc:
        st.error(f"Não foi possível baixar os dados do ONS para {rotulos_mes[indice_mes]}: {exc}")
        return

    if df_bruto.empty:
        st.info(f"Sem dados de constrained-off do RN em {rotulos_mes[indice_mes]}.")
        return

    df_calc = calcular_metodologias(df_bruto)
    df_pld = baixar_pld_nordeste(ano)
    df_calc = anexar_pld(df_calc, df_pld)
    pld_disponivel = df_pld is not None

    coluna_ef, _ = METODOLOGIAS[metodo]
    df_calc["impacto_financeiro"] = df_calc[coluna_ef] * df_calc["pld_horario"]

    df_calc = df_calc.merge(
        df_conjuntos[["id_ons", "conjunto"]], on="id_ons", how="left"
    )
    df_calc["conjunto"] = df_calc["conjunto"].fillna(df_calc["nom_usina"])

    if conjuntos_selecionados:
        df_calc = df_calc[df_calc["conjunto"].isin(conjuntos_selecionados)]

    if not pld_disponivel:
        st.warning(
            "Preço horário indisponível no momento (falha no acesso ao CMO "
            "Semi-Horário do ONS) — exibindo apenas energia frustrada em MWh, "
            "sem impacto financeiro."
        )

    total_mwh = df_calc[coluna_ef].sum()
    c1, c2 = st.columns(2)
    c1.metric("Energia frustrada no período", f"{total_mwh:,.0f} MWh".replace(",", "."))
    if pld_disponivel:
        total_financeiro = df_calc["impacto_financeiro"].sum()
        c2.metric("Impacto financeiro no período", f"R$ {total_financeiro:,.0f}".replace(",", "."))
    else:
        c2.metric("Impacto financeiro no período", "indisponível")

    st.divider()

    ranking = (
        df_calc.groupby("conjunto")[coluna_ef].sum().sort_values(ascending=False).head(20).reset_index()
    )
    fig_ranking = px.bar(
        ranking, x=coluna_ef, y="conjunto", orientation="h",
        labels={coluna_ef: "Energia frustrada (MWh)", "conjunto": ""},
        title="Energia frustrada por conjunto (top 20)",
    )
    fig_ranking.update_layout(yaxis={"categoryorder": "total ascending"}, height=550)
    st.plotly_chart(fig_ranking, use_container_width=True)

    serie_diaria = (
        df_calc.assign(dia=df_calc["din_instante"].dt.date).groupby("dia")[coluna_ef].sum().reset_index()
    )
    fig_serie = px.line(
        serie_diaria, x="dia", y=coluna_ef,
        labels={coluna_ef: "Energia frustrada (MWh)", "dia": ""},
        title="Energia frustrada por dia",
    )
    st.plotly_chart(fig_serie, use_container_width=True)

    with st.expander("Tabela detalhada"):
        colunas_tabela = ["din_instante", "conjunto", "val_geracao", "val_geracaolimitada", coluna_ef]
        renomeio = {
            "din_instante": "Instante", "conjunto": "Conjunto",
            "val_geracao": "Geração (MW)", "val_geracaolimitada": "Geração limitada (MW)",
            coluna_ef: "Energia frustrada (MWh)",
        }
        if pld_disponivel:
            colunas_tabela.append("impacto_financeiro")
            renomeio["impacto_financeiro"] = "Impacto financeiro (R$)"
        st.dataframe(
            df_calc[colunas_tabela].rename(columns=renomeio),
            width="stretch",
            hide_index=True,
        )
