"""Página de inspeção e exportação dos dados que alimentam o mapa.

Expõe, em uma superfície única, as três tabelas de origem do mapa
(conjuntos, subestações e cidades de referência) tal como são carregadas e
normalizadas por ``core/data_loader.py``, além das usinas individuais e das
linhas geográficas derivadas (conjunto -> subestação de conexão).

O objetivo é permitir a conferência dos dados — especialmente as coordenadas
— e a sua exportação em CSV e GeoJSON para edição externa ou cruzamento com
imagem de satélite (ver o GeoJSON de auditoria em ``docs/``). A importação
automática dos cadastros, quando entrar, alimentará estas mesmas tabelas.
"""

from __future__ import annotations

import json
from datetime import date

import pandas as pd
import streamlit as st

from core.data_loader import load_bays, load_cidades, load_conjuntos, load_usinas
from core.ons_rede import _chave_subestacao_ons


def _csv_bytes(df: pd.DataFrame) -> bytes:
    """Serializa o DataFrame em CSV UTF-8 com BOM (abre direto no Excel do
    Windows sem corromper acentuação)."""
    return df.to_csv(index=False).encode("utf-8-sig")


def _linhas_conexao(df_conjuntos: pd.DataFrame, df_bays: pd.DataFrame) -> pd.DataFrame:
    """Reconstrói a tabela das linhas conjunto -> subestação de conexão, com
    o comprimento em linha reta de cada uma. É a mesma junção que o mapa usa
    para desenhar as linhas fixas de conexão."""
    ses = {
        _chave_subestacao_ons(row["subestacao"]): row
        for _, row in df_bays.iterrows()
    }
    registros: list[dict] = []
    for _, c in df_conjuntos.iterrows():
        chave = _chave_subestacao_ons(str(c["ponto_conexao"]))
        se = ses.get(chave)
        if se is None:
            registros.append(
                {
                    "conjunto": c["conjunto"],
                    "ponto_conexao": c["ponto_conexao"],
                    "subestacao": None,
                    "lat_conjunto": c["latitude"],
                    "long_conjunto": c["longitude"],
                    "lat_subestacao": None,
                    "long_subestacao": None,
                    "distancia_km": None,
                }
            )
            continue
        dist = _distancia_km(
            c["latitude"], c["longitude"], se["latitude"], se["longitude"]
        )
        registros.append(
            {
                "conjunto": c["conjunto"],
                "ponto_conexao": c["ponto_conexao"],
                "subestacao": se["subestacao"],
                "lat_conjunto": c["latitude"],
                "long_conjunto": c["longitude"],
                "lat_subestacao": se["latitude"],
                "long_subestacao": se["longitude"],
                "distancia_km": round(dist, 1),
            }
        )
    return pd.DataFrame(registros)


def _distancia_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distância de Haversine em quilômetros entre dois pontos."""
    from math import asin, cos, radians, sin, sqrt

    r = 6371.0
    d_lat = radians(lat2 - lat1)
    d_lon = radians(lon2 - lon1)
    a = (
        sin(d_lat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lon / 2) ** 2
    )
    return 2 * r * asin(sqrt(a))


def _geojson_pontos(
    df_conjuntos: pd.DataFrame,
    df_usinas: pd.DataFrame,
    df_bays: pd.DataFrame,
    df_cidades: pd.DataFrame,
    df_linhas: pd.DataFrame,
) -> dict:
    """Monta um FeatureCollection com todos os pontos e linhas do mapa, para
    abrir no Google Earth ou no QGIS e cruzar com imagem de satélite."""
    features: list[dict] = []

    for _, r in df_conjuntos.iterrows():
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [float(r["longitude"]), float(r["latitude"])],
                },
                "properties": {
                    "tipo": "conjunto",
                    "nome": r["conjunto"],
                    "id_ons": r.get("id_ons"),
                    "municipios": r.get("municipios"),
                    "capacidade_mw": r.get("capacidade_mw"),
                    "qtd_aerogeradores": r.get("qtd_aerogeradores"),
                    "ponto_conexao": r.get("ponto_conexao"),
                },
            }
        )

    for _, r in df_usinas.iterrows():
        if pd.isna(r.get("latitude")) or pd.isna(r.get("longitude")):
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [float(r["longitude"]), float(r["latitude"])],
                },
                "properties": {
                    "tipo": "usina",
                    "nome": r.get("usina"),
                    "conjunto": r.get("conjunto"),
                    "ceg": r.get("ceg"),
                    "fonte_coordenada": r.get("fonte_coordenada"),
                },
            }
        )

    for _, r in df_bays.iterrows():
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [float(r["longitude"]), float(r["latitude"])],
                },
                "properties": {
                    "tipo": "subestacao",
                    "nome": r["subestacao"],
                    "id_estado": r.get("id_estado"),
                    "agente_operador": r.get("agente_operador"),
                    "tensoes_kv": r.get("tensoes_kv"),
                },
            }
        )

    for _, r in df_cidades.iterrows():
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [float(r["longitude"]), float(r["latitude"])],
                },
                "properties": {"tipo": "cidade", "nome": r.get("cidade")},
            }
        )

    for _, r in df_linhas.iterrows():
        if pd.isna(r["lat_subestacao"]) or pd.isna(r["long_subestacao"]):
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [float(r["long_conjunto"]), float(r["lat_conjunto"])],
                        [float(r["long_subestacao"]), float(r["lat_subestacao"])],
                    ],
                },
                "properties": {
                    "tipo": "linha_conexao",
                    "conjunto": r["conjunto"],
                    "subestacao": r["subestacao"],
                    "distancia_km": r["distancia_km"],
                },
            }
        )

    return {"type": "FeatureCollection", "features": features}


def _tabela(titulo: str, descricao: str, df: pd.DataFrame, nome_arquivo: str) -> None:
    """Bloco padrão: título, descrição, tabela e botão de download CSV."""
    st.markdown(f"### {titulo}")
    st.caption(descricao)
    st.dataframe(df, width="stretch", hide_index=True)
    st.download_button(
        f"Baixar {nome_arquivo}.csv",
        data=_csv_bytes(df),
        file_name=f"{nome_arquivo}.csv",
        mime="text/csv",
        key=f"dl_{nome_arquivo}",
    )
    st.divider()


def render() -> None:
    df_conjuntos = load_conjuntos()
    df_usinas = load_usinas()
    df_bays = load_bays()
    df_cidades = load_cidades()
    df_linhas = _linhas_conexao(df_conjuntos, df_bays)

    st.markdown("## Dados do mapa")
    st.caption(
        "Tabelas de origem que alimentam o mapa, já normalizadas por "
        "`core/data_loader.py`. Use os botões de download para conferir ou "
        "editar externamente. Fontes: ONS SINMAPS, ONS (relação conjunto–usina), "
        "ANEEL SIGA, cadastro de subestações do RN/PB."
    )
    st.divider()

    st.markdown("#### Exportação completa")
    st.caption(
        "GeoJSON com todos os pontos (conjuntos, usinas, subestações, cidades) "
        "e as linhas de conexão — para abrir no Google Earth ou no QGIS e "
        "cruzar as posições com imagem de satélite."
    )
    geojson = _geojson_pontos(df_conjuntos, df_usinas, df_bays, df_cidades, df_linhas)
    st.download_button(
        "Baixar pontos_mapa.geojson",
        data=json.dumps(geojson, ensure_ascii=False, indent=2).encode("utf-8"),
        file_name=f"pontos_mapa_{date.today():%Y%m%d}.geojson",
        mime="application/geo+json",
        key="dl_geojson",
    )
    st.divider()

    _tabela(
        "Conjuntos eólicos",
        f"{len(df_conjuntos)} conjuntos. Coordenada em `latitude`/`longitude` "
        "(parseada da coluna combinada da planilha). Marcador de turbina no mapa.",
        df_conjuntos.drop(columns=["logo_proprietario", "logo_operador"], errors="ignore"),
        "conjuntos",
    )

    _tabela(
        "Subestações (bays)",
        f"{len(df_bays)} subestações do RN e da PB. Marcador de SE no mapa; "
        "também posiciona a ponta das linhas de conexão.",
        df_bays,
        "subestacoes",
    )

    _tabela(
        "Cidades de referência",
        f"{len(df_cidades)} cidades exibidas como rótulo fixo no mapa "
        "(sem interação).",
        df_cidades,
        "cidades_referencia",
    )

    _tabela(
        "Linhas de conexão conjunto–subestação",
        "Derivada: junção `Ponto de conexão` (conjunto) ↔ `Subestação` (bays), "
        "com o comprimento em linha reta. Linhas longas ou sem subestação "
        "correspondente merecem conferência.",
        df_linhas,
        "linhas_conexao",
    )

    _tabela(
        "Usinas individuais",
        f"{len(df_usinas)} usinas (aba Detalhamento). Não aparecem no mapa por "
        "padrão; a camada é opcional. Coordenada por usina, com a fonte na "
        "coluna `fonte_coordenada`.",
        df_usinas.drop(columns=["chave"], errors="ignore"),
        "usinas",
    )
