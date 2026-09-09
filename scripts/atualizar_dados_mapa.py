"""Consulta as fontes de dados abertos e gera versões atualizadas dos
arquivos de rede do mapa — **sem tocar nos arquivos em uso**.

O painel lê **apenas** os arquivos versionados em ``data/rede/``; nada é
baixado em tempo de execução. Este script é o único ponto que vai à web:
baixa os cadastros do ONS e da ANEEL, valida cada um e grava o resultado
num arquivo **``.novo.csv`` ao lado** do vigente. O arquivo que o painel
usa nunca é alterado por este script.

Uso::

    python scripts/atualizar_dados_mapa.py                 # tudo
    python scripts/atualizar_dados_mapa.py --ses --linhas  # só o que for pedido
    python scripts/atualizar_dados_mapa.py --siga

Para cada seção, gera em ``data/rede/``:

    subestacoes_rn.novo.csv          <- comparar com subestacoes_rn.csv
    linhas_transmissao_rn.novo.csv   <- comparar com linhas_transmissao_rn.csv
    siga_potencias_eol_rn.novo.csv   <- comparar com siga_potencias_eol_rn.csv

Fluxo de aprovação (manual, fora do script):

    1. rodar este script;
    2. comparar cada par: ``git diff --no-index data/rede/X.csv data/rede/X.novo.csv``;
    3. se aprovar, promover: ``mv data/rede/X.novo.csv data/rede/X.csv``;
    4. ``git add`` e commit. Se rejeitar, apagar o ``.novo.csv``.

Cada seção é independente: se uma fonte estiver fora do ar, as demais ainda
geram o seu ``.novo.csv`` e o script encerra com código != 0 para sinalizar.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.fontes_online import (  # noqa: E402
    baixar_linhas_rn,
    baixar_potencias_eol_rn,
    baixar_subestacoes_rn,
)

REDE_DIR = Path(__file__).resolve().parent.parent / "data" / "rede"

# Bounding box do RN (com folga) — coordenada fora disso indica erro na fonte.
_LAT_RN = (-7.3, -4.5)
_LON_RN = (-39.0, -34.5)


def _caminho_novo(vigente: Path) -> Path:
    """``subestacoes_rn.csv`` -> ``subestacoes_rn.novo.csv``."""
    return vigente.with_suffix(".novo.csv")


def _resumo_comparacao(vigente: Path, novo: pd.DataFrame) -> str:
    """Compara a contagem de linhas do que foi baixado com o arquivo em uso."""
    if not vigente.exists():
        return f"{len(novo)} linhas (ainda não há '{vigente.name}' — primeira geração)"
    try:
        atual = pd.read_csv(vigente)
    except Exception:
        return f"{len(novo)} linhas (o '{vigente.name}' atual está ilegível)"
    delta = len(novo) - len(atual)
    sinal = f"+{delta}" if delta > 0 else str(delta)
    return f"{len(atual)} -> {len(novo)} linhas ({sinal}) em relação a '{vigente.name}'"


def _gravar_novo(vigente: Path, df: pd.DataFrame) -> Path:
    """Grava o DataFrame em ``<vigente>.novo.csv``; nunca toca ``<vigente>``."""
    destino = _caminho_novo(vigente)
    destino.parent.mkdir(parents=True, exist_ok=True)
    # UTF-8 com BOM: abre direto no Excel do Windows sem corromper acentuação.
    df.to_csv(destino, index=False, encoding="utf-8-sig")
    return destino


def _validar_coords(df: pd.DataFrame, rotulo: str) -> None:
    fora = df[
        (df["latitude"] < _LAT_RN[0])
        | (df["latitude"] > _LAT_RN[1])
        | (df["longitude"] < _LON_RN[0])
        | (df["longitude"] > _LON_RN[1])
    ]
    if not fora.empty:
        raise ValueError(
            f"{rotulo}: {len(fora)} linha(s) com coordenada fora do RN — "
            f"nada gravado. Primeiras: {fora.head(3).to_dict('records')}"
        )


def atualizar_ses() -> None:
    print("subestacoes_rn ...", end=" ", flush=True)
    df = baixar_subestacoes_rn()
    if len(df) < 10:
        raise ValueError(f"apenas {len(df)} subestações — esperado ~17; abortado")
    _validar_coords(df, "subestações")
    vigente = REDE_DIR / "subestacoes_rn.csv"
    print(_resumo_comparacao(vigente, df))
    destino = _gravar_novo(vigente, df)
    print(f"  gerado: {destino.name}")


def atualizar_linhas() -> None:
    print("linhas_transmissao_rn ...", end=" ", flush=True)
    df = baixar_linhas_rn()
    if len(df) < 10:
        raise ValueError(f"apenas {len(df)} linhas — esperado dezenas; abortado")
    if df["tensao_kv"].isna().all():
        raise ValueError("nenhuma linha com tensão — coluna de origem mudou?")
    vigente = REDE_DIR / "linhas_transmissao_rn.csv"
    print(_resumo_comparacao(vigente, df))
    destino = _gravar_novo(vigente, df)
    print(f"  gerado: {destino.name}")


def atualizar_siga() -> None:
    print("siga_potencias_eol_rn ...", end=" ", flush=True)
    df = baixar_potencias_eol_rn()
    if len(df) < 50:
        raise ValueError(f"apenas {len(df)} CEGs — esperado ~300; abortado")
    if df["potencia_outorgada_mw"].isna().all():
        raise ValueError("nenhuma potência outorgada — coluna de origem mudou?")
    vigente = REDE_DIR / "siga_potencias_eol_rn.csv"
    print(_resumo_comparacao(vigente, df))
    destino = _gravar_novo(vigente, df)
    print(f"  gerado: {destino.name}")


_SECOES = {
    "ses": atualizar_ses,
    "linhas": atualizar_linhas,
    "siga": atualizar_siga,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for nome in _SECOES:
        parser.add_argument(f"--{nome}", action="store_true", help=f"atualiza {nome}")
    args = parser.parse_args(argv)

    escolhidas = [nome for nome in _SECOES if getattr(args, nome)] or list(_SECOES)
    falhas: list[str] = []
    for nome in escolhidas:
        try:
            _SECOES[nome]()
        except Exception as erro:  # noqa: BLE001 — relata e segue para as demais
            print(f"FALHOU ({erro})")
            falhas.append(nome)

    print()
    if falhas:
        print(f"{len(falhas)} seção(ões) falharam: {', '.join(falhas)}")
    print(
        "Arquivos '.novo.csv' gerados ao lado dos vigentes — nenhum arquivo em "
        "uso foi alterado.\nCompare cada par com:\n"
        "  git diff --no-index data/rede/<nome>.csv data/rede/<nome>.novo.csv\n"
        "Para promover uma versão aprovada:\n"
        "  mv data/rede/<nome>.novo.csv data/rede/<nome>.csv  (depois git add e commit)"
    )
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
