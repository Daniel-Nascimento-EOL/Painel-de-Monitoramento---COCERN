"""Download do SIGA (Sistema de Informações de Geração da ANEEL) — usado para
enriquecer cada usina individual do conjunto com a potência (MW), que não
consta na planilha de localização (lá só há contagem de usinas por conjunto).

Fonte: https://dadosabertos.aneel.gov.br/dataset/siga-sistema-de-informacoes-de-geracao-da-aneel
CSV diário (empreendimentos de geração). Chave de junção: ``CodCEG`` do SIGA
== coluna ``CEG`` da aba Detalhamento (ex.: 'EOL.CV.RN.028444-0.1').
"""

import pandas as pd
import requests
import streamlit as st

_URL_SIGA = (
    "https://dadosabertos.aneel.gov.br/dataset/6d90b77c-c5f5-4d81-bdec-7bc619494bb9/"
    "resource/2f65a1b0-19b8-4360-8238-b34ab4693d55/download/"
    "siga-empreendimentos-geracao-diario.csv"
)


def _kw_para_mw(valor: object) -> float:
    """'49300,00' (kW, decimal com vírgula) -> 49.3 (MW)."""
    if pd.isna(valor):
        return float("nan")
    texto = str(valor).strip().replace(".", "").replace(",", ".")
    try:
        return float(texto) / 1000.0
    except ValueError:
        return float("nan")


@st.cache_data(ttl=24 * 3600, show_spinner="Baixando potências das usinas (ANEEL SIGA)...")
def baixar_potencias_eol_rn() -> pd.DataFrame | None:
    """Baixa o SIGA, filtra eólicas do RN e devolve potência por CEG.

    Retorna ``None`` (fallback gracioso) se o download falhar — nesse caso a
    coluna de potência por usina simplesmente não aparece.
    Colunas: ``ceg``, ``potencia_outorgada_mw``, ``potencia_fiscalizada_mw``,
    ``fase_usina``, ``proprietario``.
    """
    try:
        resposta = requests.get(_URL_SIGA, timeout=90)
        resposta.raise_for_status()
        df = pd.read_csv(
            pd.io.common.BytesIO(resposta.content),
            sep=";",
            dtype=str,
            encoding="utf-8",
        )
    except Exception:
        return None

    df = df[(df["SigUFPrincipal"] == "RN") & (df["SigTipoGeracao"] == "EOL")].copy()
    if df.empty:
        return None

    saida = pd.DataFrame(
        {
            "ceg": df["CodCEG"].str.strip(),
            "potencia_outorgada_mw": df["MdaPotenciaOutorgadaKw"].apply(_kw_para_mw),
            "potencia_fiscalizada_mw": df["MdaPotenciaFiscalizadaKw"].apply(_kw_para_mw),
            "fase_usina": df["DscFaseUsina"].str.strip(),
            "proprietario": df["DscPropriRegimePariticipacao"].str.strip(),
        }
    )
    return saida.dropna(subset=["ceg"]).drop_duplicates(subset=["ceg"]).reset_index(drop=True)
