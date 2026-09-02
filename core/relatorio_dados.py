"""Montagem do "dossiê" de dados por conjunto eólico para o relatório PDF.

Junta o cadastro (conjuntos, usinas, subestações, linhas de transmissão)
com os dados de constrained-off do ONS do mês selecionado e os agregados
de Energia Frustrada / impacto financeiro, produzindo uma estrutura por
conjunto pronta para ``viz/pdf_relatorio.py`` consumir.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd
import streamlit as st

from core.ccee_pld import anexar_pld, baixar_pld_nordeste
from core.data_loader import load_bays, load_conjuntos, load_usinas
from core.ons_coff import METODOLOGIAS, baixar_mes_rn, calcular_metodologias
from core.ons_rede import baixar_linhas_rn

_COLS_EF = [f"energia_frustrada_{i}" for i in range(1, 6)]


def _intervalo_horas(df: pd.DataFrame) -> float:
    """Duração de cada amostra do dataset, em horas (0,5 para o passo
    semi-horário do ONS). As colunas ``energia_frustrada_*`` já saem em MWh
    (o fator 0,5 está embutido nas fórmulas), mas ``val_geracao`` e afins
    estão em MW médios — precisam ser multiplicados por este intervalo para
    virar MWh."""
    if len(df) < 2:
        return 0.5
    passos = df["din_instante"].sort_values().diff().dropna()
    if passos.empty:
        return 0.5
    segundos = passos.median().total_seconds()
    return segundos / 3600 if segundos > 0 else 0.5


@dataclass
class DossieConjunto:
    conjunto: str
    id_ons: str
    cadastro: dict
    usinas: pd.DataFrame
    subestacoes: list[dict]
    linhas: pd.DataFrame
    coff_mensal: pd.DataFrame            # linhas do ONS já com metodologias + pld
    agregados: dict                      # totais do mês (MWh, R$, geração, FC, ...)
    serie_diaria: pd.DataFrame           # por dia: ef por metodologia, geração
    quebra_razao: pd.DataFrame           # ef (metodologia ref.) por cod_razaorestricao
    tem_impacto_financeiro: bool


@dataclass
class Relatorio:
    ano: int
    mes: int
    metodologia_ref: int
    dossies: list[DossieConjunto]
    resumo_rn: dict                      # agregados de todo o RN no mês
    tem_impacto_financeiro: bool
    avisos: list[str] = field(default_factory=list)


def _agregar_conjunto(df: pd.DataFrame, capacidade_mw: float, metodologia_ref: int) -> dict:
    horas = int(df["din_instante"].dt.floor("h").nunique())
    dt_h = _intervalo_horas(df)
    ger_verif = float(df["val_geracao"].sum()) * dt_h
    ger_ref = float(df["val_geracaoreferencia"].sum()) * dt_h
    ger_lim = float(df["val_geracaolimitada"].sum(min_count=1) or 0.0) * dt_h
    disp_media = float(df["val_disponibilidade"].mean()) if "val_disponibilidade" in df else float("nan")

    ef_mwh = {i: float(df[f"energia_frustrada_{i}"].sum()) for i in range(1, 6)}
    if "pld_horario" in df and df["pld_horario"].notna().any():
        ef_rs = {
            i: float((df[f"energia_frustrada_{i}"] * df["pld_horario"]).sum())
            for i in range(1, 6)
        }
    else:
        ef_rs = {}

    col_ref = METODOLOGIAS[metodologia_ref][0]
    horas_com_corte = int((df[col_ref] > 0).sum())
    pld_medio = float(df["pld_horario"].mean()) if "pld_horario" in df and df["pld_horario"].notna().any() else None

    fator_capacidade = (
        ger_verif / (capacidade_mw * horas) if capacidade_mw and horas else float("nan")
    )
    potencial = capacidade_mw * horas if capacidade_mw and horas else float("nan")
    pct_frustrado = (
        ef_mwh[metodologia_ref] / potencial * 100 if potencial and potencial == potencial else float("nan")
    )

    return {
        "horas_no_mes": horas,
        "horas_com_corte": horas_com_corte,
        "geracao_verificada_mwh": ger_verif,
        "geracao_referencia_mwh": ger_ref,
        "geracao_limitada_mwh": ger_lim,
        "disponibilidade_media_mw": disp_media,
        "energia_frustrada_mwh": ef_mwh,
        "impacto_financeiro_rs": ef_rs,
        "pld_medio_rs_mwh": pld_medio,
        "fator_capacidade": fator_capacidade,
        "pct_geracao_potencial_frustrada": pct_frustrado,
        "capacidade_instalada_mw": capacidade_mw,
    }


def _serie_diaria(df: pd.DataFrame) -> pd.DataFrame:
    dt_h = _intervalo_horas(df)
    g = df.assign(dia=df["din_instante"].dt.date).groupby("dia", as_index=False).agg(
        geracao_verificada_mwh=("val_geracao", "sum"),
        geracao_referencia_mwh=("val_geracaoreferencia", "sum"),
        **{f"ef{i}_mwh": (f"energia_frustrada_{i}", "sum") for i in range(1, 6)},
    )
    for col in ("geracao_verificada_mwh", "geracao_referencia_mwh"):
        g[col] *= dt_h
    return g


def _quebra_razao(df: pd.DataFrame, metodologia_ref: int) -> pd.DataFrame:
    col = METODOLOGIAS[metodologia_ref][0]
    if "cod_razaorestricao" not in df:
        return pd.DataFrame(columns=["cod_razaorestricao", "energia_frustrada_mwh", "horas"])
    g = df.groupby("cod_razaorestricao", as_index=False).agg(
        energia_frustrada_mwh=(col, "sum"),
        horas=("din_instante", "nunique"),
    )
    return g.sort_values("energia_frustrada_mwh", ascending=False)


@st.cache_data(show_spinner="Compilando dados para o relatório...")
def montar_relatorio(
    conjuntos_selecionados: tuple[str, ...],
    ano: int,
    mes: int,
    metodologia_ref: int = 1,
) -> Relatorio:
    """Compila o :class:`Relatorio` para os conjuntos indicados no mês dado.

    ``conjuntos_selecionados`` vazio = todos os conjuntos do RN.
    """
    avisos: list[str] = []
    df_conj = load_conjuntos()
    df_usi = load_usinas()
    df_bays = load_bays()
    try:
        df_linhas = baixar_linhas_rn()
    except Exception:
        df_linhas = None
        avisos.append("Não foi possível baixar as linhas de transmissão do ONS.")

    coff = baixar_mes_rn(ano, mes)
    coff = calcular_metodologias(coff)
    df_pld = baixar_pld_nordeste(ano)
    coff = anexar_pld(coff, df_pld)
    tem_impacto = "pld_horario" in coff and coff["pld_horario"].notna().any()
    if not tem_impacto:
        avisos.append(
            "PLD horário da CCEE indisponível para o período — o relatório "
            "traz a energia frustrada em MWh, sem o impacto financeiro em R$."
        )

    if conjuntos_selecionados:
        df_conj = df_conj[df_conj["conjunto"].isin(conjuntos_selecionados)]

    dossies: list[DossieConjunto] = []
    for _, c in df_conj.iterrows():
        usinas = df_usi[df_usi["chave"] == c["chave"]].copy()
        se_chaves = {c["chave_subestacao"]}
        subestacoes = [
            {
                "nome": b["subestacao"],
                "agente_operador": b.get("agente_operador"),
                "tensoes_kv": b.get("tensoes_kv"),
                "tensao_max_kv": b.get("tensao_max_kv"),
                "latitude": b["latitude"],
                "longitude": b["longitude"],
            }
            for _, b in df_bays[df_bays["chave"].isin(se_chaves)].iterrows()
        ]
        if df_linhas is not None and not df_linhas.empty:
            linhas = df_linhas[
                df_linhas["chave_de"].isin(se_chaves) | df_linhas["chave_para"].isin(se_chaves)
            ].copy()
        else:
            linhas = pd.DataFrame()

        sub = coff[coff["id_ons"] == c["id_ons"]].copy()
        if sub.empty:
            agregados = {}
            serie = pd.DataFrame()
            quebra = pd.DataFrame()
        else:
            agregados = _agregar_conjunto(sub, float(c["capacidade_mw"]), metodologia_ref)
            serie = _serie_diaria(sub)
            quebra = _quebra_razao(sub, metodologia_ref)

        dossies.append(DossieConjunto(
            conjunto=c["conjunto"],
            id_ons=c["id_ons"],
            cadastro={
                "municipios": c["municipios"],
                "capacidade_mw": float(c["capacidade_mw"]),
                "qtd_usinas": int(c["qtd_usinas"]),
                "qtd_aerogeradores": int(c["qtd_aerogeradores"]),
                "ponto_conexao": c["ponto_conexao"],
                "agente_proprietario": c["agente_proprietario"],
                "agente_operador": c["agente_operador"],
                "ajustamento_operativo": c["ajustamento_operativo"],
                "latitude": c["latitude"],
                "longitude": c["longitude"],
            },
            usinas=usinas,
            subestacoes=subestacoes,
            linhas=linhas,
            coff_mensal=sub,
            agregados=agregados,
            serie_diaria=serie,
            quebra_razao=quebra,
            tem_impacto_financeiro=tem_impacto,
        ))

    resumo_rn = _resumo_rn(coff, load_conjuntos(), metodologia_ref)

    return Relatorio(
        ano=ano,
        mes=mes,
        metodologia_ref=metodologia_ref,
        dossies=dossies,
        resumo_rn=resumo_rn,
        tem_impacto_financeiro=tem_impacto,
        avisos=avisos,
    )


def _resumo_rn(coff: pd.DataFrame, df_conj: pd.DataFrame, metodologia_ref: int) -> dict:
    """Agregados de todo o RN no mês, para o sumário executivo."""
    col_ref = METODOLOGIAS[metodologia_ref][0]
    # Só linhas que casam com algum conjunto cadastrado (exclui usinas soltas do dataset ONS).
    so_conj = coff[coff["id_ons"].isin(df_conj["id_ons"])]
    horas = int(so_conj["din_instante"].dt.floor("h").nunique()) if not so_conj.empty else 0
    dt_h = _intervalo_horas(so_conj) if not so_conj.empty else 0.5
    capacidade_total = float(df_conj["capacidade_mw"].sum())
    potencial = capacidade_total * horas if horas else float("nan")

    ef_mwh = {i: float(so_conj[f"energia_frustrada_{i}"].sum()) for i in range(1, 6)}
    if "pld_horario" in so_conj and so_conj["pld_horario"].notna().any():
        ef_rs = {i: float((so_conj[f"energia_frustrada_{i}"] * so_conj["pld_horario"]).sum()) for i in range(1, 6)}
    else:
        ef_rs = {}

    por_conjunto = (
        so_conj.groupby("nom_usina", as_index=False)[col_ref].sum()
        .rename(columns={col_ref: "energia_frustrada_mwh", "nom_usina": "conjunto"})
        .sort_values("energia_frustrada_mwh", ascending=False)
    )

    return {
        "horas_no_mes": horas,
        "n_conjuntos_com_corte": int((por_conjunto["energia_frustrada_mwh"] > 0).sum()),
        "n_conjuntos_total": int(len(df_conj)),
        "geracao_verificada_mwh": float(so_conj["val_geracao"].sum()) * dt_h if not so_conj.empty else 0.0,
        "energia_frustrada_mwh": ef_mwh,
        "impacto_financeiro_rs": ef_rs,
        "capacidade_instalada_total_mw": capacidade_total,
        "pct_geracao_potencial_frustrada": (
            ef_mwh[metodologia_ref] / potencial * 100 if potencial == potencial and potencial else float("nan")
        ),
        "ranking_por_conjunto": por_conjunto,
    }
