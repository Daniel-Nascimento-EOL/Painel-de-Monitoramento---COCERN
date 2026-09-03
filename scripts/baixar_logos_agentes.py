"""Baixa as logomarcas dos agentes para ``data/icons/agentes/``.

Uso::

    python scripts/baixar_logos_agentes.py

As fontes estão declaradas em ``core/agentes.py::FONTES_LOGO``. Os arquivos
resultantes são versionados no repositório, de modo que o painel não dependa
de domínios de terceiros em tempo de execução (era a causa das logomarcas
erradas e ausentes — ver o cabeçalho de ``core/agentes.py``).

Cada logomarca é normalizada: convertida para PNG, aparada na área útil,
redimensionada para caber em ``_LADO`` px e centralizada sobre fundo branco
(ou escuro, para as marcas em branco listadas em ``LOGOS_FUNDO_ESCURO``).
"""

import io
import sys
from pathlib import Path

import httpx
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.agentes import (  # noqa: E402
    FONTES_LOGO,
    LOGOS_DIR,
    LOGOS_FUNDO_ESCURO,
    _nome_arquivo,
)

# Chave pública (publishable) da API do logo.dev — pode ser versionada; serve
# só para resolver a logomarca a partir do domínio institucional do agente.
_TOKEN_LOGO_DEV = "pk_X-1ZO13GSgeOoUrIuJ6GMQ"

_CABECALHOS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/125"}

_LADO = 256
_FUNDO_CLARO = (255, 255, 255)
_FUNDO_ESCURO = (35, 43, 51)


def _aparar(img: Image.Image) -> Image.Image:
    """Recorta a moldura transparente/uniforme em volta da logomarca."""
    caixa = img.split()[-1].getbbox() if img.mode == "RGBA" else img.convert("RGB").getbbox()
    return img.crop(caixa) if caixa else img


def _normalizar(dados: bytes, fundo: tuple[int, int, int]) -> Image.Image:
    img = Image.open(io.BytesIO(dados))
    img = img.convert("RGBA")
    img = _aparar(img)
    img.thumbnail((_LADO, _LADO), Image.LANCZOS)
    tela = Image.new("RGB", (_LADO, _LADO), fundo)
    tela.paste(img, ((_LADO - img.width) // 2, (_LADO - img.height) // 2), img)
    return tela


def main() -> int:
    LOGOS_DIR.mkdir(parents=True, exist_ok=True)
    cliente = httpx.Client(timeout=30, follow_redirects=True, headers=_CABECALHOS)
    falhas = []

    for chave, url in FONTES_LOGO.items():
        destino = LOGOS_DIR / _nome_arquivo(chave)
        try:
            resposta = cliente.get(url.format(token=_TOKEN_LOGO_DEV))
            if resposta.status_code != 200 or len(resposta.content) < 500:
                falhas.append((chave, f"HTTP {resposta.status_code}"))
                continue
            fundo = _FUNDO_ESCURO if chave in LOGOS_FUNDO_ESCURO else _FUNDO_CLARO
            _normalizar(resposta.content, fundo).save(destino, format="PNG", optimize=True)
            print(f"OK   {chave} -> {destino.name}")
        except Exception as erro:  # noqa: BLE001 — o script relata e segue
            falhas.append((chave, f"{type(erro).__name__}: {erro}"))

    for chave, motivo in falhas:
        print(f"FALHA {chave}: {motivo}", file=sys.stderr)
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
