"""Gera a arte de fundo da tela de apresentação (``data/icons/capa_rn.png``).

A imagem alude à energia eólica do RN: o contorno real do estado (o mesmo
``data/rn_estado.geojson`` que o mapa usa) sobre um céu escuro em degradê,
com silhuetas de aerogeradores e as cores da bandeira estadual.

Gerada localmente, e não baixada: o endereço sugerido no pedido era uma
miniatura do cache de imagens do Google (``encrypted-tbn0.gstatic.com``), o
mesmo tipo de URL instável que já trouxe logomarca errada para as fichas dos
agentes (ver ``core/agentes.py``). Aqui o traçado do estado é o oficial do
IBGE, já versionado no repositório.

Rodar com: ``python scripts/gerar_arte_capa.py``
"""

import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

RAIZ = Path(__file__).resolve().parent.parent
GEOJSON = RAIZ / "data" / "rn_estado.geojson"
DESTINO = RAIZ / "data" / "icons" / "capa_rn.png"

LARGURA, ALTURA = 1600, 900

# Paleta: o slate do painel (§5) escurecido para servir de fundo, com o
# terracota como acento. As cores da bandeira do RN entram no horizonte.
_CEU_TOPO = (16, 24, 34)
_CEU_BASE = (34, 48, 63)
_HORIZONTE = (193, 122, 79)  # terracota do painel
_RN_PREENCHE = (59, 81, 102)
_RN_CONTORNO = (139, 168, 191)
_TORRE = (12, 18, 26)


def _degrade_vertical(tamanho, topo, base):
    """Faixa vertical de ``topo`` a ``base``, desenhada linha a linha."""
    largura, altura = tamanho
    img = Image.new("RGB", tamanho, topo)
    desenho = ImageDraw.Draw(img)
    for y in range(altura):
        t = y / max(1, altura - 1)
        cor = tuple(round(topo[i] + (base[i] - topo[i]) * t) for i in range(3))
        desenho.line([(0, y), (largura, y)], fill=cor)
    return img


def _pontos_rn():
    """Anel exterior do contorno do RN, em graus (lon, lat)."""
    dados = json.loads(GEOJSON.read_text(encoding="utf-8"))
    geometria = dados["features"][0]["geometry"]
    if geometria["type"] == "Polygon":
        aneis = geometria["coordinates"]
    else:  # MultiPolygon — fica o anel com mais vértices (o continental)
        aneis = [max((p[0] for p in geometria["coordinates"]), key=len)]
    return max(aneis, key=len)


def _projetar(pontos, caixa):
    """Projeta lon/lat na caixa (x0, y0, x1, y1), preservando a proporção."""
    x0, y0, x1, y1 = caixa
    lons = [p[0] for p in pontos]
    lats = [p[1] for p in pontos]
    escala = min((x1 - x0) / (max(lons) - min(lons)), (y1 - y0) / (max(lats) - min(lats)))
    largura = (max(lons) - min(lons)) * escala
    altura = (max(lats) - min(lats)) * escala
    dx = x0 + ((x1 - x0) - largura) / 2
    dy = y0 + ((y1 - y0) - altura) / 2
    return [
        (dx + (lon - min(lons)) * escala, dy + (max(lats) - lat) * escala)
        for lon, lat in pontos
    ]


def _aerogerador(desenho, x, base, altura, angulo, cor):
    """Silhueta de aerogerador: torre afilada e três pás a 120°."""
    largura_base = max(2, altura * 0.022)
    topo = base - altura
    desenho.polygon(
        [
            (x - largura_base, base),
            (x - largura_base * 0.42, topo),
            (x + largura_base * 0.42, topo),
            (x + largura_base, base),
        ],
        fill=cor,
    )
    raio = altura * 0.42
    for i in range(3):
        a = math.radians(angulo + i * 120)
        ponta = (x + math.cos(a) * raio, topo + math.sin(a) * raio)
        largura_pa = max(2, altura * 0.026)
        perpendicular = (-math.sin(a) * largura_pa, math.cos(a) * largura_pa)
        desenho.polygon(
            [
                (x + perpendicular[0], topo + perpendicular[1]),
                ponta,
                (x - perpendicular[0], topo - perpendicular[1]),
            ],
            fill=cor,
        )
    desenho.ellipse(
        [x - largura_base * 0.9, topo - largura_base * 0.9,
         x + largura_base * 0.9, topo + largura_base * 0.9],
        fill=cor,
    )


def gerar() -> Path:
    img = _degrade_vertical((LARGURA, ALTURA), _CEU_TOPO, _CEU_BASE)

    # Brilho quente no horizonte (nascente sobre o litoral).
    brilho = Image.new("RGB", (LARGURA, ALTURA), _CEU_BASE)
    ImageDraw.Draw(brilho).ellipse(
        [LARGURA * 0.18, ALTURA * 0.52, LARGURA * 1.02, ALTURA * 1.35],
        fill=_HORIZONTE,
    )
    brilho = brilho.filter(ImageFilter.GaussianBlur(150))
    img = Image.blend(img, brilho, 0.30)

    # Contorno do RN, recuado à direita, como marca d'água.
    camada = Image.new("RGBA", (LARGURA, ALTURA), (0, 0, 0, 0))
    desenho = ImageDraw.Draw(camada)
    pontos = _projetar(
        _pontos_rn(),
        (LARGURA * 0.50, ALTURA * 0.13, LARGURA * 0.94, ALTURA * 0.62),
    )
    desenho.polygon(pontos, fill=(*_RN_PREENCHE, 92))
    desenho.line(pontos + [pontos[0]], fill=(*_RN_CONTORNO, 150), width=3)
    img = Image.alpha_composite(img.convert("RGBA"), camada).convert("RGB")

    # Parque eólico em primeiro plano: alturas e ângulos variados, os mais
    # próximos maiores e mais escuros.
    desenho = ImageDraw.Draw(img)
    base = ALTURA * 0.965
    for x_rel, altura_rel, angulo in [
        (0.05, 0.26, 18), (0.14, 0.35, 62), (0.24, 0.22, 5),
        (0.33, 0.41, 40), (0.44, 0.27, 78), (0.56, 0.20, 25),
        (0.67, 0.31, 54), (0.79, 0.24, 12), (0.90, 0.36, 68),
    ]:
        _aerogerador(desenho, LARGURA * x_rel, base, ALTURA * altura_rel, angulo, _TORRE)

    # Faixa de solo, fechando a composição.
    desenho.rectangle([0, base, LARGURA, ALTURA], fill=_TORRE)

    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    img.save(DESTINO, format="PNG", optimize=True)
    return DESTINO


if __name__ == "__main__":
    caminho = gerar()
    print("arte gerada: %s (%.0f KB)" % (caminho, caminho.stat().st_size / 1024))
