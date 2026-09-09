"""Consulta as fontes de dados abertos e regrava os arquivos de rede do mapa.

O painel lê **apenas** os arquivos versionados em ``data/rede/``; nada é
baixado em tempo de execução. Este script é o único ponto que vai à web:
baixa os cadastros do ONS e da ANEEL, valida cada um e regrava o CSV
correspondente, deixando-o pronto para conferência (``git diff``) e commit.

Uso::

    python scripts/atualizar_dados_mapa.py                 # tudo
    python scripts/atualizar_dados_mapa.py --ses --linhas  # só o que for pedido
    python scripts/atualizar_dados_mapa.py --siga

Arquivos gerados (todos em ``data/rede/``):

    subestacoes_rn.csv          subestações de transmissão do RN + tensão (kV)
    linhas_transmissao_rn.csv   linhas da Rede de Operação que tocam o RN
    siga_potencias_eol_rn.csv   potência por CEG das eólicas do RN (ANEEL SIGA)

Cada seção é independente: se uma fonte estiver fora do ar, as demais ainda
são atualizadas e o arquivo da que falhou é mantido intacto (o script
encerra com código de saída != 0 para sinalizar).
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


def _resumo_diff(caminho: Path, novo: pd.DataFrame) -> str:
    """Descreve a mudança do arquivo: contagem de linhas antes/depois."""
    if not caminho.exists():
        return f"novo arquivo, {len(novo)} linhas"
    try:
        antigo = pd.read_csv(caminho)
    except Exception:
        return f"arquivo anterior ilegível — sera substituido por {len(novo)} linhas"
    delta = len(novo) - len(antigo)
    sinal = f"+{delta}" if delta > 0 else str(delta)
    return f"{len(antigo)} -> {len(novo)} linhas ({sinal})"


def _gravar(caminho: Path, df: pd.DataFrame) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    # UTF-8 com BOM: abre direto no Excel do Windows sem corromper acentuação.
    df.to_csv(caminho, index=False, encoding="utf-8-sig")


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
            f"não gravado. Primeiras: {fora.head(3).to_dict('records')}"
        )


def atualizar_ses() -> None:
    print("subestacoes_rn.csv ...", end=" ", flush=True)
    df = baixar_subestacoes_rn()
    if len(df) < 10:
        raise ValueError(f"apenas {len(df)} subestações — esperado ~17; abortado")
    _validar_coords(df, "subestações")
    caminho = REDE_DIR / "subestacoes_rn.csv"
    print(_resumo_diff(caminho, df))
    _gravar(caminho, df)


def atualizar_linhas() -> None:
    print("linhas_transmissao_rn.csv ...", end=" ", flush=True)
    df = baixar_linhas_rn()
    if len(df) < 10:
        raise ValueError(f"apenas {len(df)} linhas — esperado dezenas; abortado")
    if df["tensao_kv"].isna().all():
        raise ValueError("nenhuma linha com tensão — coluna de origem mudou?")
    caminho = REDE_DIR / "linhas_transmissao_rn.csv"
    print(_resumo_diff(caminho, df))
    _gravar(caminho, df)


def atualizar_siga() -> None:
    print("siga_potencias_eol_rn.csv ...", end=" ", flush=True)
    df = baixar_potencias_eol_rn()
    if len(df) < 50:
        raise ValueError(f"apenas {len(df)} CEGs — esperado ~300; abortado")
    if df["potencia_outorgada_mw"].isna().all():
        raise ValueError("nenhuma potência outorgada — coluna de origem mudou?")
    caminho = REDE_DIR / "siga_potencias_eol_rn.csv"
    print(_resumo_diff(caminho, df))
    _gravar(caminho, df)


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

    if falhas:
        print(f"\n{len(falhas)} seção(ões) falharam: {', '.join(falhas)}")
        print("Os arquivos correspondentes foram mantidos como estavam.")
        return 1
    print("\nTudo atualizado. Confira com 'git diff data/rede/' antes do commit.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
