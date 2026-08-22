"""Construção do mapa (Folium/Leaflet) dos conjuntos eólicos do RN."""

import json
from pathlib import Path

import folium
import pandas as pd

RN_GEOJSON_PATH = Path(__file__).resolve().parent.parent / "data" / "rn_estado.geojson"

CENTRO_RN = (-5.6, -36.4)
_BOUNDS_RN = [[-7.35, -39.0], [-4.45, -34.5]]

_COR_CONJUNTOS = "#3b5166"
_COR_USINAS = "#c17a4f"
_COR_CONTORNO = "#9aa5b1"


def _icone_turbina(cor: str, tamanho: int) -> folium.DivIcon:
    """Ícone de aerogerador (torre + rotor de 3 pás) em SVG inline."""
    altura = int(tamanho * 1.35)
    svg = f"""
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 34" width="{tamanho}" height="{altura}"
         style="filter: drop-shadow(0 1px 1px rgba(0,0,0,0.25));">
        <line x1="12" y1="8" x2="12" y2="1" stroke="{cor}" stroke-width="1.8" stroke-linecap="round"/>
        <line x1="12" y1="8" x2="5" y2="13" stroke="{cor}" stroke-width="1.8" stroke-linecap="round"/>
        <line x1="12" y1="8" x2="19" y2="13" stroke="{cor}" stroke-width="1.8" stroke-linecap="round"/>
        <line x1="12" y1="8" x2="12" y2="32" stroke="{cor}" stroke-width="1.6" stroke-linecap="round"/>
        <line x1="9" y1="32" x2="15" y2="32" stroke="{cor}" stroke-width="1.8" stroke-linecap="round"/>
        <circle cx="12" cy="8" r="1.4" fill="{cor}"/>
    </svg>
    """
    return folium.DivIcon(html=svg, icon_size=(tamanho, altura), icon_anchor=(tamanho // 2, altura))


def _carregar_contorno_rn() -> dict:
    with open(RN_GEOJSON_PATH, encoding="utf-8") as f:
        return json.load(f)


def build_map(df_conjuntos: pd.DataFrame, df_usinas: pd.DataFrame | None = None, mostrar_usinas: bool = False) -> folium.Map:
    m = folium.Map(
        location=CENTRO_RN,
        zoom_start=7,
        min_zoom=7,
        tiles="CartoDB positron",
        control_scale=True,
        max_bounds=True,
        zoom_control=True,
    )

    folium.GeoJson(
        _carregar_contorno_rn(),
        name="Rio Grande do Norte",
        style_function=lambda _: {
            "fillColor": "transparent",
            "color": _COR_CONTORNO,
            "weight": 1.5,
            "fillOpacity": 0,
        },
    ).add_to(m)

    m.fit_bounds(_BOUNDS_RN)

    for _, row in df_conjuntos.iterrows():
        tamanho = int(min(16 + row["qtd_usinas"] * 1.1, 34))
        popup_html = (
            f"<b>{row['conjunto']}</b><br>"
            f"Município(s): {row['municipios']}<br>"
            f"Qtd. usinas: {row['qtd_usinas']}"
        )
        folium.Marker(
            location=[row["latitude"], row["longitude"]],
            icon=_icone_turbina(_COR_CONJUNTOS, tamanho),
            tooltip=row["conjunto"],
            popup=folium.Popup(popup_html, max_width=280),
        ).add_to(m)

    if mostrar_usinas and df_usinas is not None and not df_usinas.empty:
        for _, row in df_usinas.iterrows():
            popup_html = (
                f"<b>{row['usina']}</b><br>"
                f"Conjunto: {row['conjunto']}<br>"
                f"CEG: {row['ceg']}<br>"
                f"Município(s): {row['municipios']}"
            )
            folium.Marker(
                location=[row["latitude"], row["longitude"]],
                icon=_icone_turbina(_COR_USINAS, 15),
                tooltip=row["usina"],
                popup=folium.Popup(popup_html, max_width=280),
            ).add_to(m)

    return m
