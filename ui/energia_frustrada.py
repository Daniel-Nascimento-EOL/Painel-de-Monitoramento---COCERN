"""Página de Energia Frustrada — constrained-off eólico do RN.

Baixa os dados abertos do ONS (restrição/COFF, filtrados por RN), reproduz
as 5 metodologias de energia frustrada e valora o impacto financeiro pelo
PLD horário do submercado Nordeste (dados abertos da CCEE), exibindo
agregados por conjunto e ao longo do tempo.

A metodologia [1] vem pré-selecionada por ter sido validada contra o estudo
de referência do cliente; as demais ficam no seletor para comparação.
"""

from datetime import date

import plotly.express as px
import streamlit as st

from core.ccee_pld import anexar_pld, baixar_pld_nordeste
from core.data_loader import load_bays, load_conjuntos
from core.ons_coff import (
    METODOLOGIA_PADRAO,
    METODOLOGIAS,
    baixar_mes_rn,
    calcular_metodologias,
    meses_disponiveis,
)
from core.ons_rede import baixar_linhas_rn, baixar_subestacoes_rn
from core.relatorio_dados import montar_relatorio
from viz.mapa_estatico import gerar_png_mapa
from viz.pdf_relatorio import gerar_pdf

_NOMES_MES = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]


def _minimapas_por_conjunto(dossies, camadas) -> dict:
    """Gera o PNG recortado (conjunto + SE de conexão + linhas) de cada
    dossiê, para embutir no PDF. Falha graciosa: conjunto sem mapa apenas
    sai sem a figura."""
    df_conj = load_conjuntos()
    df_bays = load_bays()
    try:
        df_linhas = baixar_linhas_rn()
    except Exception:
        df_linhas = None
    try:
        df_ses = baixar_subestacoes_rn()
    except Exception:
        df_ses = None

    mapas: dict[str, bytes] = {}
    for d in dossies:
        try:
            linha_conj = df_conj[df_conj["conjunto"] == d.conjunto]
            se_chaves = set(linha_conj["chave_subestacao"])
            bays_conj = df_bays[df_bays["chave"].isin(se_chaves)]
            linhas_conj = (
                df_linhas[
                    df_linhas["chave_de"].isin(se_chaves) | df_linhas["chave_para"].isin(se_chaves)
                ]
                if df_linhas is not None else None
            )
            mapas[d.conjunto] = gerar_png_mapa(
                linha_conj, None, bays_conj, None, linhas_conj, df_ses,
                camadas=camadas, largura=760, altura=600,
                zoom=11, centro=(d.cadastro["longitude"], d.cadastro["latitude"]),
            )
        except Exception:
            continue
    return mapas


def _bloco_relatorio_pdf(df_conjuntos, conjuntos_selecionados, ano, mes, metodo) -> None:
    """Exporta um PDF consolidado (sumário executivo + seção por conjunto)."""
    st.divider()
    st.markdown("#### Exportar relatório PDF")
    alvo = conjuntos_selecionados or df_conjuntos["conjunto"].sort_values().tolist()
    escolha = st.multiselect(
        "Conjuntos no relatório",
        df_conjuntos["conjunto"].sort_values().tolist(),
        default=alvo,
        help="Vazio = todos os conjuntos do RN. Padrão segue o filtro de conjunto acima.",
    )
    incluir_mapa = st.checkbox("Incluir mini-mapa por conjunto (mais lento)", value=True)

    if st.button("📄 Gerar relatório PDF", type="primary"):
        alvo_final = tuple(escolha) if escolha else tuple(df_conjuntos["conjunto"])
        rel = montar_relatorio(alvo_final, ano, mes, metodo)
        mapas = {}
        if incluir_mapa:
            cam = {
                "conjuntos": True, "subestacoes": True, "linhas_transmissao": True,
                "linhas_conexao": True, "usinas": False, "cidades": False,
            }
            with st.spinner("Renderizando mini-mapas..."):
                mapas = _minimapas_por_conjunto(rel.dossies, cam)
        with st.spinner("Montando o PDF..."):
            st.session_state["_pdf_relatorio"] = gerar_pdf(rel, mapas)
            st.session_state["_pdf_relatorio_nome"] = (
                f"relatorio_constrained_off_{ano}{mes:02d}_metod{metodo}.pdf"
            )

    pdf = st.session_state.get("_pdf_relatorio")
    if pdf:
        st.download_button(
            "⬇️ Baixar PDF",
            data=pdf,
            file_name=st.session_state.get("_pdf_relatorio_nome", "relatorio.pdf"),
            mime="application/pdf",
        )
        st.caption(f"Gerado em {date.today():%d/%m/%Y}. Reabra o gerador após trocar mês, conjuntos ou metodologia.")


def render() -> None:
    st.markdown("## Energia Frustrada — Constrained-off Eólico do RN")
    st.caption(
        "Constrained-off eólico dos dados abertos do ONS (atualizado 2x ao dia) "
        "valorado pelo PLD horário do submercado Nordeste (CCEE)"
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

        chaves = list(METODOLOGIAS.keys())
        metodo = st.selectbox(
            "Metodologia de cálculo",
            chaves,
            index=chaves.index(METODOLOGIA_PADRAO),
            format_func=lambda n: (
                f"Metodologia {n}" + (" (referência)" if n == METODOLOGIA_PADRAO else "")
            ),
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
    df_calc = anexar_pld(df_calc, baixar_pld_nordeste(ano))
    coluna_ef, _ = METODOLOGIAS[metodo]
    df_calc["impacto_financeiro"] = df_calc[coluna_ef] * df_calc["pld_horario"]
    pld_disponivel = bool(df_calc["pld_horario"].notna().any())

    df_calc = df_calc.merge(
        df_conjuntos[["id_ons", "conjunto"]], on="id_ons", how="left"
    )
    df_calc["conjunto"] = df_calc["conjunto"].fillna(df_calc["nom_usina"])

    if conjuntos_selecionados:
        df_calc = df_calc[df_calc["conjunto"].isin(conjuntos_selecionados)]

    if not pld_disponivel:
        st.warning(
            "PLD horário indisponível para o período — exibindo apenas a "
            "energia frustrada em MWh, sem o impacto financeiro."
        )

    total_mwh = df_calc[coluna_ef].sum()
    c1, c2 = st.columns(2)
    c1.metric("Energia frustrada no período", f"{total_mwh:,.0f} MWh".replace(",", "."))
    if pld_disponivel:
        total_financeiro = df_calc["impacto_financeiro"].sum()
        c2.metric(
            "Impacto financeiro no período",
            f"R$ {total_financeiro:,.0f}".replace(",", "."),
            help="Energia frustrada valorada pelo PLD horário do submercado Nordeste (CCEE).",
        )
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

    _bloco_relatorio_pdf(df_conjuntos, conjuntos_selecionados, ano, mes, metodo)

    with st.expander("Tabela detalhada"):
        colunas_tabela = ["din_instante", "conjunto", "val_geracao", "val_geracaolimitada", coluna_ef]
        renomeio = {
            "din_instante": "Instante", "conjunto": "Conjunto",
            "val_geracao": "Geração (MW)", "val_geracaolimitada": "Geração limitada (MW)",
            coluna_ef: "Energia frustrada (MWh)",
        }
        if pld_disponivel:
            colunas_tabela += ["pld_horario", "impacto_financeiro"]
            renomeio["pld_horario"] = "PLD (R$/MWh)"
            renomeio["impacto_financeiro"] = "Impacto financeiro (R$)"
        st.dataframe(
            df_calc[colunas_tabela].rename(columns=renomeio),
            width="stretch",
            hide_index=True,
        )
