"""Geração do mapa dos conjuntos eólicos do RN como imagem PNG estática.

Espelha um subconjunto das camadas de ``viz/map_charts.build_map`` (que
produz um mapa Leaflet interativo) usando ``staticmap`` — baixa os mesmos
tiles Esri e desenha linhas/marcadores num PIL Image, sem navegador. Serve
o botão "baixar imagem do mapa" e o mini-mapa recortado do relatório PDF.
"""

from __future__ import annotations

import io
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st
from PIL import Image, ImageDraw, ImageFont
from staticmap import CircleMarker, IconMarker, Line, StaticMap

from core.ons_rede import _COR_POR_TENSAO, _COR_TENSAO_OUTRA, cor_tensao
from viz.map_charts import (
    ESRI_TILES_ATTR,
    ESRI_TILES_URL,
    ICONS_DIR,
    _COR_CIDADE,
    _COR_CONJUNTOS,
    _COR_CONTORNO,
    _COR_SUBESTACAO,
    _COR_USINAS,
    _carregar_contorno_rn,
    _tingir_icone_array,
)

# Camadas aceitas em `camadas` — mesmas chaves de viz/map_charts.CAMADAS_PADRAO,
# mas só estas têm efeito no PNG (rótulos de cidade e máscara do RN são
# aproximados ou omitidos).
_CAMADAS_SUPORTADAS = {
    "conjuntos",
    "usinas",
    "subestacoes",
    "linhas_transmissao",
    "linhas_conexao",
    "cidades",
}

_ICONE_SE_PX = 34
_ICONE_CONJUNTO_PX = 30
_DIR_ICONES_TMP = Path(tempfile.gettempdir()) / "painel_coff_icones_estaticos"


@st.cache_resource(show_spinner=False)
def _icone_tmp_path(caminho: str, cor_hex: str, largura_px: int) -> str:
    """Escreve o ícone tingido e redimensionado num PNG temporário (uma vez
    por arquivo/cor/tamanho) — ``staticmap.IconMarker`` precisa de um caminho
    em disco, não de um array."""
    _DIR_ICONES_TMP.mkdir(parents=True, exist_ok=True)
    rgba = _tingir_icone_array(caminho, cor_hex)
    img = Image.fromarray(rgba, mode="RGBA")
    altura_px = max(1, round(largura_px * img.height / img.width))
    img = img.resize((largura_px, altura_px), Image.LANCZOS)
    nome = f"{Path(caminho).stem}_{cor_hex.lstrip('#')}_{largura_px}.png"
    destino = _DIR_ICONES_TMP / nome
    img.save(destino, format="PNG")
    return str(destino)


def _contorno_rn_lonlat() -> list[list[tuple[float, float]]]:
    """Anéis do contorno do RN como listas de (lon, lat) — para desenhar a
    fronteira do estado por cima dos tiles."""
    contorno = _carregar_contorno_rn()
    geom = contorno["features"][0]["geometry"]
    poligonos = geom["coordinates"] if geom["type"] == "Polygon" else [
        anel for parte in geom["coordinates"] for anel in parte
    ]
    aneis: list[list[tuple[float, float]]] = []
    for anel in poligonos:
        pontos = anel if isinstance(anel[0][0], (int, float)) else anel[0]
        aneis.append([(float(x), float(y)) for x, y in pontos])
    return aneis


def _bays_por_chave(df_bays: pd.DataFrame | None) -> dict[str, dict]:
    if df_bays is None or df_bays.empty:
        return {}
    saida = {}
    for _, r in df_bays.iterrows():
        saida[r["chave"]] = {
            "pos": (r["longitude"], r["latitude"]),
            "tensao_max_kv": _tensao_max(r.get("tensoes_kv")),
        }
    return saida


def _ses_por_chave(df_ses: pd.DataFrame | None) -> dict[str, tuple[float, float]]:
    if df_ses is None or df_ses.empty:
        return {}
    return {
        r["chave_subestacao"]: (r["longitude"], r["latitude"])
        for _, r in df_ses.iterrows()
        if pd.notna(r["latitude"]) and pd.notna(r["longitude"])
    }


def _tensao_max(tensoes) -> float | None:
    if isinstance(tensoes, (list, tuple)) and len(tensoes):
        return max(tensoes)
    return None


def _desenhar_legenda(img: Image.Image) -> Image.Image:
    """Caixa de legenda de nível de tensão no canto inferior esquerdo."""
    linhas = [
        ("138 kV", _COR_POR_TENSAO.get(138, _COR_TENSAO_OUTRA)),
        ("230 kV", _COR_POR_TENSAO.get(230, _COR_TENSAO_OUTRA)),
        ("500 kV", _COR_POR_TENSAO.get(500, _COR_TENSAO_OUTRA)),
        ("69 kV / outra", _COR_TENSAO_OUTRA),
    ]
    try:
        fonte = ImageFont.truetype("arial.ttf", 15)
        fonte_tit = ImageFont.truetype("arialbd.ttf", 15)
    except OSError:
        fonte = ImageFont.load_default()
        fonte_tit = fonte

    pad, lin_h, amostra = 12, 24, 26
    larg = 190
    alt = pad * 2 + lin_h * (len(linhas) + 1)
    x0, y0 = 16, img.height - alt - 16

    camada = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(camada)
    d.rounded_rectangle([x0, y0, x0 + larg, y0 + alt], radius=8,
                        fill=(255, 255, 255, 235), outline=(0, 0, 0, 30), width=1)
    d.text((x0 + pad, y0 + pad), "Nível de tensão", font=fonte_tit, fill=(58, 68, 78, 255))
    for i, (rotulo, cor) in enumerate(linhas):
        ly = y0 + pad + lin_h * (i + 1)
        d.line([x0 + pad, ly + 8, x0 + pad + amostra, ly + 8], fill=cor, width=4)
        d.text((x0 + pad + amostra + 8, ly), rotulo, font=fonte, fill=(74, 84, 94, 255))

    return Image.alpha_composite(img.convert("RGBA"), camada)


def _rodape_credito(img: Image.Image) -> Image.Image:
    try:
        fonte = ImageFont.truetype("arial.ttf", 12)
    except OSError:
        fonte = ImageFont.load_default()
    camada = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(camada)
    texto = ESRI_TILES_ATTR
    caixa = d.textbbox((0, 0), texto, font=fonte)
    tw, th = caixa[2] - caixa[0], caixa[3] - caixa[1]
    d.rectangle([img.width - tw - 14, img.height - th - 12, img.width, img.height],
                fill=(255, 255, 255, 210))
    d.text((img.width - tw - 8, img.height - th - 8), texto, font=fonte, fill=(120, 120, 120, 255))
    return Image.alpha_composite(img.convert("RGBA"), camada)


def gerar_png_mapa(
    df_conjuntos: pd.DataFrame,
    df_usinas: pd.DataFrame | None = None,
    df_bays: pd.DataFrame | None = None,
    df_cidades: pd.DataFrame | None = None,
    df_linhas: pd.DataFrame | None = None,
    df_ses: pd.DataFrame | None = None,
    camadas: dict[str, bool] | None = None,
    largura: int = 1400,
    altura: int = 1000,
    zoom: int | None = None,
    centro: tuple[float, float] | None = None,
) -> bytes:
    """Renderiza o mapa como PNG (bytes) respeitando as flags de `camadas`.

    `centro` é (lon, lat). Se `zoom`/`centro` forem None, o staticmap
    ajusta o enquadramento ao conjunto de feições desenhadas.
    """
    camadas = camadas or {c: True for c in _CAMADAS_SUPORTADAS}
    m = StaticMap(
        largura,
        altura,
        padding_x=24,
        padding_y=24,
        url_template=ESRI_TILES_URL,
        tile_size=256,
        tile_request_timeout=30,
        headers={"User-Agent": "PainelCOFF-RN/1.0"},
        background_color="#f5f5f5",
    )

    # Fronteira do estado (sempre) — cinza claro, por baixo das feições.
    for anel in _contorno_rn_lonlat():
        m.add_line(Line(anel, _COR_CONTORNO, 2))

    bays = _bays_por_chave(df_bays)
    ses = _ses_por_chave(df_ses)

    if camadas.get("linhas_transmissao") and df_linhas is not None and not df_linhas.empty:
        for _, ln in df_linhas.iterrows():
            a = ses.get(ln["chave_de"])
            b = ses.get(ln["chave_para"])
            if a and b:
                m.add_line(Line([a, b], cor_tensao(ln["tensao_kv"]), 3))

    if camadas.get("linhas_conexao") and bays is not None and df_conjuntos is not None:
        for _, r in df_conjuntos.iterrows():
            destino = bays.get(r["chave_subestacao"])
            if destino:
                m.add_line(Line(
                    [(r["longitude"], r["latitude"]), destino["pos"]],
                    cor_tensao(destino["tensao_max_kv"]),
                    2,
                ))

    if camadas.get("cidades") and df_cidades is not None and not df_cidades.empty:
        for _, r in df_cidades.iterrows():
            m.add_marker(CircleMarker((r["longitude"], r["latitude"]), _COR_CIDADE, 5))

    if camadas.get("usinas") and df_usinas is not None and not df_usinas.empty:
        for _, r in df_usinas.iterrows():
            if pd.notna(r.get("latitude")) and pd.notna(r.get("longitude")):
                m.add_marker(CircleMarker((r["longitude"], r["latitude"]), _COR_USINAS, 9))

    if camadas.get("subestacoes") and df_bays is not None and not df_bays.empty:
        icone_se = _icone_tmp_path(str(ICONS_DIR / "logo_se.png"), _COR_SUBESTACAO, _ICONE_SE_PX)
        for _, r in df_bays.iterrows():
            m.add_marker(IconMarker((r["longitude"], r["latitude"]), icone_se,
                                    _ICONE_SE_PX // 2, _ICONE_SE_PX // 2))

    if camadas.get("conjuntos", True) and df_conjuntos is not None and not df_conjuntos.empty:
        icone_cj = _icone_tmp_path(str(ICONS_DIR / "logo_aero.jpg"), _COR_CONJUNTOS, _ICONE_CONJUNTO_PX)
        for _, r in df_conjuntos.iterrows():
            m.add_marker(IconMarker((r["longitude"], r["latitude"]), icone_cj,
                                    _ICONE_CONJUNTO_PX // 2, _ICONE_CONJUNTO_PX // 2))

    imagem = m.render(zoom=zoom, center=centro)

    if camadas.get("linhas_transmissao") or camadas.get("linhas_conexao"):
        imagem = _desenhar_legenda(imagem)
    imagem = _rodape_credito(imagem)

    buffer = io.BytesIO()
    imagem.convert("RGB").save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


@st.cache_data(show_spinner="Gerando imagem do mapa...")
def gerar_png_mapa_cache(
    conjuntos_json: str,
    usinas_json: str,
    bays_json: str,
    cidades_json: str,
    linhas_json: str,
    ses_json: str,
    camadas_itens: tuple,
    largura: int = 1400,
    altura: int = 1000,
) -> bytes:
    """Versão cacheável de :func:`gerar_png_mapa` — recebe os DataFrames
    serializados como JSON (chaves estáveis para ``@st.cache_data``), do
    mesmo modo que ``viz.map_charts.build_map_html``. Evita rebaixar os
    tiles Esri a cada rerun quando os filtros/camadas não mudaram."""
    def _ler(js: str) -> pd.DataFrame | None:
        return pd.read_json(io.StringIO(js), orient="split") if js else None

    return gerar_png_mapa(
        _ler(conjuntos_json),
        _ler(usinas_json),
        _ler(bays_json),
        _ler(cidades_json),
        _ler(linhas_json),
        _ler(ses_json),
        camadas=dict(camadas_itens),
        largura=largura,
        altura=altura,
    )
