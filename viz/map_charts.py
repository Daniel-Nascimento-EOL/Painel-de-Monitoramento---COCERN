"""Construção do mapa (Folium/Leaflet) dos conjuntos eólicos do RN."""

import base64
import io
import json
import re
from pathlib import Path

import folium
import numpy as np
import pandas as pd
import streamlit as st
from PIL import Image
from shapely.geometry import shape

from core.ons_rede import cor_tensao

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

# Ícone do marcador de conjunto — tamanho fixo (sem proporcionalidade à qtd. de usinas).
_TAMANHO_ICONE_CONJUNTO = 24


def _nome_subestacao(nome: str) -> str:
    """Garante o prefixo 'SE ' no nome da subestação (ex.: 'Açu II' -> 'SE Açu II')."""
    nome = str(nome).strip()
    return nome if re.match(r"^SE\s+", nome, flags=re.IGNORECASE) else f"SE {nome}"


# Os ícones de origem são 512x512 mas renderizam a ~24 px no mapa. Redimensionar
# para esta resolução antes de codificar derruba o PNG embutido de ~51 KB para
# ~2 KB por marcador (x69 marcadores => HTML ~1,5 MB mais leve), mantendo nitidez
# folgada para telas retina.
_RESOLUCAO_ICONE = 64


@st.cache_resource
def _tingir_icone_array(caminho: str, cor_hex: str) -> "np.ndarray":
    """Torna transparente o fundo claro do ícone (linha preta sobre fundo
    quase branco) e tinge os traços com a cor da paleta do projeto."""
    img = Image.open(caminho).convert("L")
    if max(img.size) > _RESOLUCAO_ICONE:
        img = img.resize((_RESOLUCAO_ICONE, _RESOLUCAO_ICONE), Image.LANCZOS)
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


@st.cache_resource
def _icone_data_uri(caminho: str, cor_hex: str) -> str:
    """PNG do ícone tingido, codificado uma única vez como ``data:`` URI.

    Sem isto, ``folium.CustomIcon`` recomprimia o PNG do ícone com
    ``zlib.compress`` a cada um dos ~69 marcadores (54 conjuntos + 15
    subestações) — 84% do tempo de construção do mapa. Como só há dois
    ícones distintos (conjunto e subestação), o resultado é cacheado por
    (arquivo, cor).
    """
    rgba = _tingir_icone_array(caminho, cor_hex)
    buffer = io.BytesIO()
    Image.fromarray(rgba, mode="RGBA").save(buffer, format="PNG", optimize=False, compress_level=1)
    b64 = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def _icone_customizado(caminho: Path, cor_hex: str, tamanho: int) -> folium.CustomIcon:
    altura = int(tamanho * 1.35)
    return folium.CustomIcon(
        icon_image=_icone_data_uri(str(caminho), cor_hex),
        icon_size=(tamanho, altura),
    )


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


# Camadas do mapa que o usuário pode ligar/desligar no filtro da sidebar.
CAMADAS_PADRAO = {
    "conjuntos": True,
    "usinas": False,
    "subestacoes": True,
    "linhas_transmissao": True,
    "linhas_conexao": True,
    "cidades": True,
}


def _legenda_tensao_html() -> str:
    """Legenda flutuante das cores de tensão (canto inferior esquerdo)."""
    itens = "".join(
        f'<div style="display:flex;align-items:center;gap:6px;margin:2px 0;">'
        f'<span style="width:16px;height:3px;background:{cor};display:inline-block;"></span>'
        f'<span>{rotulo}</span></div>'
        for rotulo, cor in [
            ("138 kV", cor_tensao(138)),
            ("230 kV", cor_tensao(230)),
            ("500 kV", cor_tensao(500)),
            ("69 kV / outra", cor_tensao(69)),
        ]
    )
    return (
        '<div style="position:fixed;bottom:22px;left:12px;z-index:9999;'
        f'background:rgba(255,255,255,0.92);border:1px solid #d7dbe0;border-radius:6px;'
        f'padding:8px 10px;font-family:{_FONTE_TEXTO};font-size:11px;color:#4a545e;'
        'box-shadow:0 1px 4px rgba(0,0,0,0.12);">'
        '<div style="font-weight:600;margin-bottom:4px;">Nível de tensão</div>'
        f"{itens}</div>"
    )


def build_map(
    df_conjuntos: pd.DataFrame,
    df_usinas: pd.DataFrame | None = None,
    df_bays: pd.DataFrame | None = None,
    df_cidades: pd.DataFrame | None = None,
    df_linhas: pd.DataFrame | None = None,
    camadas: dict[str, bool] | None = None,
) -> folium.Map:
    camadas = {**CAMADAS_PADRAO, **(camadas or {})}
    # Basemap: Esri "World Gray Canvas" — estilo claro/minimalista equivalente
    # ao CartoDB positron, servido sem API key e sem marca d'água (o positron
    # da Carto passou a exigir chave e a estampar "API KEY REQUIRED" nos tiles).
    m = folium.Map(
        location=CENTRO_RN,
        zoom_start=7,
        min_zoom=7,
        tiles=(
            "https://server.arcgisonline.com/ArcGIS/rest/services/"
            "Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}"
        ),
        attr="Tiles &copy; Esri — Esri, DeLorme, NAVTEQ",
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

    # Cidades de referência — discretas, alternáveis pelo filtro de camadas.
    if camadas["cidades"] and df_cidades is not None and not df_cidades.empty:
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

    # Índice das subestações por chave (posição + tensão) — sempre montado,
    # pois as linhas de conexão dependem dele mesmo com o marcador oculto.
    bays_por_chave: dict[str, dict] = {}
    if df_bays is not None and not df_bays.empty:
        for _, row in df_bays.iterrows():
            tensao_max = row.get("tensao_max_kv")
            bays_por_chave[row["chave"]] = {
                "pos": (row["latitude"], row["longitude"]),
                "tensao_max_kv": tensao_max,
            }

    # Linhas de transmissão reais do ONS (>= 230 kV) — reta subestação -> subestação
    # (o dataset não traz geometria), coloridas pelo nível de tensão da linha.
    if (
        camadas["linhas_transmissao"]
        and df_linhas is not None
        and not df_linhas.empty
        and bays_por_chave
    ):
        for _, ln in df_linhas.iterrows():
            a = bays_por_chave.get(ln["chave_de"])
            b = bays_por_chave.get(ln["chave_para"])
            if a is None or b is None:
                continue  # linha entre SE fora do recorte do painel
            comprimento = ln.get("comprimento_km")
            comp_txt = f"{comprimento:.0f} km" if pd.notna(comprimento) else "—"
            popup_html = (
                f'<div style="font-family:{_FONTE_TEXTO};font-size:12px;color:#3a444e;">'
                f'<b>{ln["subestacao_de"]} — {ln["subestacao_para"]}</b><br>'
                f'{ln["tensao_kv"]:.0f} kV · {ln["tipo_rede"]}<br>'
                f'Extensão: {comp_txt}<br>'
                f'Agente: {ln["agente"]}</div>'
            )
            folium.PolyLine(
                locations=[a["pos"], b["pos"]],
                color=cor_tensao(ln["tensao_kv"]),
                weight=2.2,
                opacity=0.75,
                tooltip=f'{ln["subestacao_de"]} — {ln["subestacao_para"]} ({ln["tensao_kv"]:.0f} kV)',
                popup=folium.Popup(popup_html, max_width=280),
            ).add_to(m)

    # Linhas de conexão conjunto -> subestação — coloridas pela tensão máxima
    # da subestação de conexão (fallback cinza quando a tensão é desconhecida).
    if camadas["linhas_conexao"] and bays_por_chave:
        for _, row in df_conjuntos.iterrows():
            destino = bays_por_chave.get(row["chave_subestacao"])
            if destino is None:
                continue
            folium.PolyLine(
                locations=[[row["latitude"], row["longitude"]], destino["pos"]],
                color=cor_tensao(destino["tensao_max_kv"]),
                weight=1.6,
                opacity=0.55,
                dash_array="4,5",
            ).add_to(m)

    # Marcadores das subestações.
    if camadas["subestacoes"] and df_bays is not None and not df_bays.empty:
        for _, row in df_bays.iterrows():
            nome_se = _nome_subestacao(row["subestacao"])
            tensoes = row.get("tensoes_kv")
            if isinstance(tensoes, (list, tuple)) and len(tensoes):
                tensao_txt = " / ".join(f"{int(t)}" for t in tensoes) + " kV"
            else:
                tensao_txt = "tensão não cadastrada (ONS)"
            popup_html = (
                f'<div style="font-family:{_FONTE_TEXTO};font-size:12px;color:#3a444e;">'
                f"<b>{nome_se}</b><br>"
                f"Níveis de tensão: {tensao_txt}<br>"
                f'Agente Operador: {row["agente_operador"]}</div>'
            )
            folium.Marker(
                location=[row["latitude"], row["longitude"]],
                icon=_icone_customizado(ICONS_DIR / "logo_se.jpeg", _COR_SUBESTACAO, 26),
                tooltip=f"{nome_se} · {tensao_txt}",
                popup=folium.Popup(popup_html, max_width=260),
            ).add_to(m)

    for _, row in df_conjuntos.iterrows():
        if not camadas["conjuntos"]:
            break
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
            icon=_icone_customizado(ICONS_DIR / "logo_aero.jpg", _COR_CONJUNTOS, _TAMANHO_ICONE_CONJUNTO),
            tooltip=row["conjunto"],
            popup=folium.Popup(popup_html, max_width=300),
        ).add_to(m)

    if camadas["usinas"] and df_usinas is not None and not df_usinas.empty:
        for _, row in df_usinas.iterrows():
            pot = row.get("potencia_fiscalizada_mw")
            if pd.isna(pot):
                pot = row.get("potencia_outorgada_mw")
            pot_txt = f"{pot:.1f} MW" if pd.notna(pot) else "potência não localizada (SIGA)"
            popup_html = (
                f'<div style="font-family:{_FONTE_TEXTO};font-size:12px;color:#3a444e;">'
                f"<b>{row['usina']}</b><br>"
                f"Conjunto: {row['conjunto']}<br>"
                f"Potência: {pot_txt}<br>"
                f"CEG: {row['ceg']}<br>"
                f"Município(s): {row['municipios']}</div>"
            )
            folium.Marker(
                location=[row["latitude"], row["longitude"]],
                icon=_icone_turbina(_COR_USINAS, 15),
                tooltip=f"{row['usina']} · {pot_txt}",
                popup=folium.Popup(popup_html, max_width=280),
            ).add_to(m)

    if camadas["linhas_transmissao"] or camadas["linhas_conexao"]:
        m.get_root().html.add_child(folium.Element(_legenda_tensao_html()))

    return m


def df_para_key(df: pd.DataFrame | None) -> str:
    """Serializa um DataFrame numa string estável, para servir de chave de
    ``@st.cache_data`` em ``build_map_html`` (DataFrame não é hashável)."""
    if df is None or df.empty:
        return ""
    return df.to_json(orient="split", date_format="iso")


@st.cache_data(show_spinner=False)
def build_map_html(
    conjuntos_json: str,
    usinas_json: str,
    bays_json: str,
    cidades_json: str,
    linhas_json: str,
    camadas_itens: tuple,
    altura: int = 650,
) -> str:
    """Versão cacheável de ``build_map``: recebe DataFrames serializados como
    JSON (chaves estáveis) e devolve o HTML do mapa já renderizado.

    Streamlit reroda ``render()`` inteira a cada clique de filtro/camada; sem
    este cache o folium.Map (54 conjuntos + subestações + linhas + máscara +
    ícones tingidos) era reconstruído e reserializado (~2 MB) toda vez. Com o
    cache, alternar uma camada reaproveita o HTML quando os dados de origem
    não mudaram — reconstrói só quando os conjuntos filtrados ou as flags de
    camada de fato mudam.
    """
    def _ler(js: str) -> pd.DataFrame | None:
        return pd.read_json(io.StringIO(js), orient="split") if js else None

    m = build_map(
        _ler(conjuntos_json),
        _ler(usinas_json),
        _ler(bays_json),
        _ler(cidades_json),
        df_linhas=_ler(linhas_json),
        camadas=dict(camadas_itens),
    )
    m.get_root().width = "100%"
    m.get_root().height = f"{altura}px"
    return m.get_root().render()
