"""Carregamento e normalização dos dados de localização dos conjuntos eólicos."""

import re
from pathlib import Path

import pandas as pd
import streamlit as st

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "localizacao_conjuntos_ons_aneel.xlsx"
BAYS_PATH = Path(__file__).resolve().parent.parent / "data" / "bays.xlsx"

_COLUNAS_CONJUNTOS = {
    "Conjunto": "conjunto",
    "id_ons": "id_ons",
    "Localização (lat, long)": "localizacao",
    "Município(s)": "municipios",
    "Capacidade instalada": "capacidade_mw",
    "Qtd. usinas": "qtd_usinas",
    "Qtde. aerogeradores": "qtd_aerogeradores",
    "Ponto de conexão": "ponto_conexao",
    "Agente Proprietário": "agente_proprietario",
    "Agente Operador": "agente_operador",
    "Ajustamento Operativo": "ajustamento_operativo",
    "Logo - Agente Proprietário": "logo_proprietario",
    "Logo - Agente Operador": "logo_operador",
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

_COLUNAS_BAYS = {
    "Agente Operador": "agente_operador",
    "Subestação": "subestacao",
    "latitude": "latitude",
    "longitude": "longitude",
}

_COLUNAS_CIDADES = {
    "Cidade": "cidade",
    "Latitude": "latitude",
    "Longitude": "longitude",
}


def _chave_conjunto(nome: str) -> str:
    """Normaliza o nome do conjunto para permitir o join entre as abas
    Localizacao ('Conjunto Eólico X') e Detalhamento ('CONJ. X' ou 'X')."""
    nome = re.sub(r"^Conjunto\s+E[oó]lico\s+", "", nome, flags=re.IGNORECASE)
    nome = re.sub(r"^CONJ\.\s+", "", nome, flags=re.IGNORECASE)
    return nome.strip().upper()


def _chave_subestacao(nome: str) -> str:
    """Normaliza o nome da subestação para juntar 'Ponto de conexão' (conjuntos,
    ex.: 'SE Açu II') com 'Subestação' (Bays, ex.: 'Açu II')."""
    nome = re.sub(r"^SE\s+", "", nome, flags=re.IGNORECASE)
    return nome.strip().upper()


def _parse_capacidade(valor: str) -> float:
    """Converte '109,20 MW' -> 109.2 (tolera espaços soltos, ex.: '63 ,00MW')."""
    if pd.isna(valor):
        return float("nan")
    texto = str(valor).upper().replace("MW", "").replace(" ", "").replace(",", ".")
    return float(texto)


@st.cache_data
def load_conjuntos() -> pd.DataFrame:
    df = pd.read_excel(DATA_PATH, sheet_name="Localizacao")
    df = df.rename(columns=_COLUNAS_CONJUNTOS)
    df["qtd_usinas"] = df["qtd_usinas"].astype(int)
    df["chave"] = df["conjunto"].apply(_chave_conjunto)
    df["chave_subestacao"] = df["ponto_conexao"].apply(_chave_subestacao)
    df["capacidade_mw"] = df["capacidade_mw"].apply(_parse_capacidade)
    lat_long = df["localizacao"].str.split(",", expand=True)
    df["latitude"] = lat_long[0].astype(float)
    df["longitude"] = lat_long[1].astype(float)
    return df


@st.cache_data
def load_usinas() -> pd.DataFrame:
    df = pd.read_excel(DATA_PATH, sheet_name="Detalhamento")
    df = df.rename(columns=_COLUNAS_USINAS)
    df["chave"] = df["conjunto"].apply(_chave_conjunto)
    return df


@st.cache_data
def load_bays() -> pd.DataFrame:
    df = pd.read_excel(BAYS_PATH, sheet_name="Bays")
    df = df.rename(columns=_COLUNAS_BAYS)
    df["chave"] = df["subestacao"].apply(_chave_subestacao)
    return df


@st.cache_data
def load_cidades() -> pd.DataFrame:
    df = pd.read_excel(BAYS_PATH, sheet_name="Cidades_RN")
    df = df.rename(columns=_COLUNAS_CIDADES)
    return df
