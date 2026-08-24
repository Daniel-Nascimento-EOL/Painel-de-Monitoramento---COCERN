"""Download do PLD horário (subsistema Nordeste) nos dados abertos da CCEE.

Fonte: https://dadosabertos.ccee.org.br/dataset/pld_horario

Aviso conhecido: o WAF da CCEE bloqueou o acesso automatizado a partir do
ambiente de desenvolvimento deste projeto (403 "acesso bloqueado — política
de segurança CCEE"). Pode funcionar normalmente a partir do ambiente de
deploy real — por isso a busca é tentada, mas com fallback gracioso: se
falhar, quem consome (ui/energia_frustrada.py) exibe a energia frustrada em
MWh normalmente e apenas omite as colunas de Impacto Financeiro (R$).
"""

from datetime import date

import pandas as pd
import requests
import streamlit as st

_URL_DATASET = "https://dadosabertos.ccee.org.br/api/3/action/package_show?id=pld_horario"
_SUBSISTEMA_NORDESTE = "Nordeste"


@st.cache_data(ttl=6 * 3600, show_spinner="Baixando PLD (CCEE)...")
def baixar_pld_nordeste(ano: int) -> pd.DataFrame | None:
    """Baixa o PLD horário do subsistema Nordeste pro ano informado.

    Retorna None (em vez de lançar exceção) se o download falhar por
    qualquer motivo — domínio bloqueado, formato inesperado, timeout etc.
    """
    try:
        metadados = requests.get(_URL_DATASET, timeout=20).json()
        recursos = metadados["result"]["resources"]
        recurso_ano = next(
            (r for r in recursos if str(ano) in r.get("name", "") and r["format"].upper() == "CSV"),
            None,
        )
        if recurso_ano is None:
            return None
        df = pd.read_csv(recurso_ano["url"], sep=";", decimal=",")
        df.columns = [c.strip().lower() for c in df.columns]
        col_subsistema = next((c for c in df.columns if "subsistema" in c or "submercado" in c), None)
        col_data = next((c for c in df.columns if "data" in c), None)
        col_hora = next((c for c in df.columns if "hora" in c), None)
        col_valor = next((c for c in df.columns if "valor" in c or "pld" in c), None)
        if not all([col_subsistema, col_data, col_valor]):
            return None
        df = df[df[col_subsistema].str.contains(_SUBSISTEMA_NORDESTE, case=False, na=False)]
        df["din_instante"] = pd.to_datetime(df[col_data]) + pd.to_timedelta(
            df[col_hora].fillna(0).astype(int), unit="h"
        ) if col_hora else pd.to_datetime(df[col_data])
        df["pld_horario"] = pd.to_numeric(df[col_valor], errors="coerce")
        return df[["din_instante", "pld_horario"]].dropna()
    except Exception:
        return None


def anexar_pld(df_coff: pd.DataFrame, df_pld: pd.DataFrame | None) -> pd.DataFrame:
    """Junta o PLD horário ao dataframe de constrained-off por instante.

    Se df_pld for None, retorna df_coff com a coluna 'pld_horario' ausente
    (NaN) — o impacto financeiro fica indisponível, mas a energia frustrada
    em MWh continua normalmente.
    """
    df = df_coff.copy()
    if df_pld is None or df_pld.empty:
        df["pld_horario"] = pd.NA
        return df
    df["_hora"] = df["din_instante"].dt.floor("h")
    pld = df_pld.rename(columns={"din_instante": "_hora"})
    return df.merge(pld, on="_hora", how="left").drop(columns="_hora")
