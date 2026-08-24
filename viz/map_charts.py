"""Construção do mapa (Folium/Leaflet) dos conjuntos eólicos do RN."""

import json
from pathlib import Path

import folium
import numpy as np
import pandas as pd
import streamlit as st
from PIL import Image
from shapely.geometry import shape

RN_GEOJSON_PATH = Path(__file__).resolve().parent.parent / "data" / "rn_estado.geojson"
ICONS_DIR = Path(__file__).resolve().parent.parent / "data" / "icons"

CENTRO_RN = (-5.6, -36.4)
# Bbox real do RN (data/rn_estado.geojson) + margem mínima — pan quase travado no estado.
_BOUNDS_RN = [[-7.10, -38.72], [-4.70, -34.83]]

_COR_CONJUNTOS = "#3b5166"
_COR_USINAS = "#c17a4f"
_COR_SUBESTACAO = "#5b6b74"
_COR_CONTORNO = "#9aa5b1"
_COR_CIDADE = "#8a8f98"
_COR_LINHA_CONEXAO = "#9aa5b1"


@st.cache_resource
def _tingir_icone_array(caminho: str, cor_hex: str) -> "np.ndarray":
    """Torna transparente o fundo claro do ícone (linha preta sobre fundo
    quase branco) e tinge os traços com a cor da paleta do projeto."""
    img = Image.open(caminho).convert("L")
    arr = np.array(img, dtype=np.float32)
    # traço escuro (L baixo) -> opaco; fundo claro (L alto) -> transparente,
    # com rampa suave entre os dois pra manter a borda anti-serrilhada.
    alpha = np.clip((225 - arr) / (225 - 20) * 255, 0, 255).astype(np.uint8)
    cor_hex = cor_hex.lstrip("#")
    r, g, b = (int(cor_hex[i : i + 2], 16) for i in (0, 2, 4))
    rgba = np.zeros((*arr.shape, 4), dtype=np.uint8)
    rgba[..., 0] = r
    rgba[..., 1] = g
    rgba[..., 2] = b
    rgba[..., 3] = alpha
    return rgba


def _icone_customizado(caminho: Path, cor_hex: str, tamanho: int) -> folium.CustomIcon:
    rgba = _tingir_icone_array(str(caminho), cor_hex)
    altura = int(tamanho * 1.35)
    return folium.CustomIcon(icon_image=rgba, icon_size=(tamanho, altura))


def _icone_turbina(cor: str, tamanho: int) -> folium.DivIcon:
    """Ícone de aerogerador (torre + rotor de 3 pás) em SVG inline — usado
    só para as usinas individuais (toggle secundário)."""
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


def _rotulo_cidade(nome: str) -> folium.DivIcon:
    html = (
        f'<div style="font-size:11px; font-style:italic; color:{_COR_CIDADE}; '
        f'white-space:nowrap; transform:translateX(-50%); '
        f'text-shadow:0 1px 2px rgba(255,255,255,0.9), 0 -1px 2px rgba(255,255,255,0.9);">'
        f"{nome}</div>"
    )
    return folium.DivIcon(html=html, icon_size=(0, 0), icon_anchor=(0, -6))


def _carregar_contorno_rn() -> dict:
    with open(RN_GEOJSON_PATH, encoding="utf-8") as f:
        return json.load(f)


_MARGEM_MASCARA_GRAUS = 0.06  # ~6 km — evita cortar rótulos do basemap (nomes de município) bem em cima da fronteira


def _mascara_fora_rn(contorno: dict) -> dict:
    """Polígono do mundo com um furo no formato do RN (com pequena folga) —
    pintado por cima do basemap, deixa visível apenas o recorte do estado
    sem cortar rótulos de cidades litorâneas bem na linha da fronteira."""
    poligono_rn = shape(contorno["features"][0]["geometry"])
    poligono_rn_com_folga = poligono_rn.buffer(_MARGEM_MASCARA_GRAUS)
    anel_rn = list(poligono_rn_com_folga.exterior.coords)
    anel_mundo = [[-179, -85], [179, -85], [179, 85], [-179, 85], [-179, -85]]
    return {
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [anel_mundo, anel_rn]},
    }


_FONTE_TEXTO = "-apple-system, 'Segoe UI', Arial, sans-serif"


def _linha_agente(rotulo: str, nome, url_logo, cor_avatar: str) -> str:
    """Linha com avatar (logo da empresa, ou inicial do nome se não houver
    logo) + rótulo pequeno em caixa alta + nome do agente."""
    nome = "" if pd.isna(nome) else str(nome).strip()
    if not pd.isna(url_logo) and str(url_logo).strip():
        avatar = (
            '<div style="width:34px; height:34px; flex-shrink:0; border-radius:8px; '
            'background:#f4f5f7; display:flex; align-items:center; justify-content:center; '
            'overflow:hidden;">'
            f'<img src="{url_logo}" style="max-width:28px; max-height:28px; object-fit:contain;">'
            "</div>"
        )
    else:
        inicial = (nome[:1] if nome else "?").upper()
        avatar = (
            f'<div style="width:34px; height:34px; flex-shrink:0; border-radius:8px; background:{cor_avatar}; '
            'display:flex; align-items:center; justify-content:center; color:#fff; '
            f'font-size:14px; font-weight:600;">{inicial}</div>'
        )
    return (
        '<div style="display:flex; align-items:center; gap:9px; margin-bottom:7px;">'
        f"{avatar}"
        '<div style="line-height:1.3;">'
        f'<div style="font-size:10px; text-transform:uppercase; letter-spacing:.04em; color:#9aa5b1;">{rotulo}</div>'
        f'<div style="font-size:12.5px; color:#2a3542; font-weight:500;">{nome or "—"}</div>'
        "</div></div>"
    )


def build_map(
    df_conjuntos: pd.DataFrame,
    df_usinas: pd.DataFrame | None = None,
    df_bays: pd.DataFrame | None = None,
    df_cidades: pd.DataFrame | None = None,
    mostrar_usinas: bool = False,
) -> folium.Map:
    m = folium.Map(
        location=CENTRO_RN,
        zoom_start=7,
        min_zoom=7,
        tiles="CartoDB positron",
        control_scale=True,
        max_bounds=True,
        min_lat=_BOUNDS_RN[0][0],
        max_lat=_BOUNDS_RN[1][0],
        min_lon=_BOUNDS_RN[0][1],
        max_lon=_BOUNDS_RN[1][1],
        zoom_control=True,
    )

    contorno = _carregar_contorno_rn()

    folium.GeoJson(
        _mascara_fora_rn(contorno),
        style_function=lambda _: {
            "fillColor": "#ffffff",
            "color": "transparent",
            "fillOpacity": 1,
        },
        interactive=False,
    ).add_to(m)

    folium.GeoJson(
        contorno,
        name="Rio Grande do Norte",
        style_function=lambda _: {
            "fillColor": "transparent",
            "color": _COR_CONTORNO,
            "weight": 1.5,
            "fillOpacity": 0,
        },
    ).add_to(m)

    m.fit_bounds(_BOUNDS_RN)

    # Cidades de referência — fixas, sempre visíveis, discretas (não são filtráveis).
    if df_cidades is not None and not df_cidades.empty:
        for _, row in df_cidades.iterrows():
            folium.CircleMarker(
                location=[row["latitude"], row["longitude"]],
                radius=2.5,
                color=_COR_CIDADE,
                fill=True,
                fill_color=_COR_CIDADE,
                fill_opacity=0.8,
                weight=0,
            ).add_to(m)
            folium.Marker(
                location=[row["latitude"], row["longitude"]],
                icon=_rotulo_cidade(row["cidade"]),
            ).add_to(m)

    # Subestações / pontos de conexão — fixas, sempre visíveis.
    bays_por_chave = {}
    if df_bays is not None and not df_bays.empty:
        for _, row in df_bays.iterrows():
            bays_por_chave[row["chave"]] = (row["latitude"], row["longitude"])
            popup_html = f"<b>{row['subestacao']}</b><br>Agente Operador: {row['agente_operador']}"
            folium.Marker(
                location=[row["latitude"], row["longitude"]],
                icon=_icone_customizado(ICONS_DIR / "logo_se.jpeg", _COR_SUBESTACAO, 26),
                tooltip=row["subestacao"],
                popup=folium.Popup(popup_html, max_width=250),
            ).add_to(m)

    # Linhas de conexão conjunto -> subestação — fixas para os conjuntos exibidos.
    if bays_por_chave:
        for _, row in df_conjuntos.iterrows():
            destino = bays_por_chave.get(row["chave_subestacao"])
            if destino is None:
                continue
            folium.PolyLine(
                locations=[[row["latitude"], row["longitude"]], destino],
                color=_COR_LINHA_CONEXAO,
                weight=1.5,
                opacity=0.6,
            ).add_to(m)

    for _, row in df_conjuntos.iterrows():
        tamanho = int(min(16 + row["qtd_usinas"] * 1.1, 34))
        popup_html = (
            '<div style="min-width:236px; max-width:270px;">'
            f'<div style="font-family: Georgia, \'Times New Roman\', serif; font-size:15px; '
            f'font-weight:700; color:#1f2937; margin-bottom:6px;">{row["conjunto"]}</div>'
            f'<div style="font-family:{_FONTE_TEXTO}; font-size:12px; color:#5b6570; line-height:1.55; '
            'margin-bottom:9px;">'
            f'{row["municipios"]}<br>'
            f'{row["qtd_usinas"]} usinas · {row["qtd_aerogeradores"]} aerogeradores · '
            f'{row["capacidade_mw"]:.2f} MW'
            "</div>"
            '<div style="border-top:1px solid #e7e9ec; margin:8px 0;"></div>'
            + _linha_agente("Agente Proprietário", row["agente_proprietario"], row["logo_proprietario"], _COR_CONJUNTOS)
            + _linha_agente("Agente Operador", row["agente_operador"], row["logo_operador"], _COR_SUBESTACAO)
            + '<div style="border-top:1px solid #e7e9ec; margin:8px 0;"></div>'
            f'<div style="font-family:{_FONTE_TEXTO}; font-size:11px; color:#8b939c; line-height:1.6;">'
            f'Ponto de conexão: {row["ponto_conexao"]}<br>'
            f'Ajustamento Operativo: {row["ajustamento_operativo"]}'
            "</div></div>"
        )
        folium.Marker(
            location=[row["latitude"], row["longitude"]],
            icon=_icone_customizado(ICONS_DIR / "logo_aero.jpg", _COR_CONJUNTOS, tamanho),
            tooltip=row["conjunto"],
            popup=folium.Popup(popup_html, max_width=300),
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
