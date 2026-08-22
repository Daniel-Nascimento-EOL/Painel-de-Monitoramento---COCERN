"""Carregamento e normalização dos dados de localização dos conjuntos eólicos."""

import re
from pathlib import Path

import pandas as pd
import streamlit as st

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "localizacao_conjuntos_ons_aneel.xlsx"

_COLUNAS_CONJUNTOS = {
    "Conjunto": "conjunto",
    "Localização (lat, long)": "localizacao",
    "Latitude": "latitude",
    "Longitude": "longitude",
    "Município(s)": "municipios",
    "Qtd. usinas": "qtd_usinas",
    "Observação": "observacao",
}

_COLUNAS_USINAS = {
    "Conjunto": "conjunto",
    "Usina integrante": "usina",
    "CEG": "ceg",
    "Latitude": "latitude",
    "Longitude": "longitude",
    "Município(s)": "municipios",
    "Fonte coordenada": "fonte_coordenada",
    "Observação": "observacao",
}


def _chave_conjunto(nome: str) -> str:
    """Normaliza o nome do conjunto para permitir o join entre as abas
    Localizacao ('Conjunto Eólico X') e Detalhamento ('CONJ. X' ou 'X')."""
    nome = re.sub(r"^Conjunto\s+E[oó]lico\s+", "", nome, flags=re.IGNORECASE)
    nome = re.sub(r"^CONJ\.\s+", "", nome, flags=re.IGNORECASE)
    return nome.strip().upper()


@st.cache_data
def load_conjuntos() -> pd.DataFrame:
    df = pd.read_excel(DATA_PATH, sheet_name="Localizacao")
    df = df.rename(columns=_COLUNAS_CONJUNTOS)
    df["qtd_usinas"] = df["qtd_usinas"].astype(int)
    df["chave"] = df["conjunto"].apply(_chave_conjunto)
    return df


@st.cache_data
def load_usinas() -> pd.DataFrame:
    df = pd.read_excel(DATA_PATH, sheet_name="Detalhamento")
    df = df.rename(columns=_COLUNAS_USINAS)
    df["chave"] = df["conjunto"].apply(_chave_conjunto)
    return df
