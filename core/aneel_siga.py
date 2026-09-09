"""Potência por usina do SIGA (Sistema de Informações de Geração da ANEEL),
usada para enriquecer cada usina individual do conjunto com a potência (MW)
— que não consta na planilha de localização (lá só há contagem de usinas
por conjunto).

O painel **não baixa** o SIGA em tempo de execução. O arquivo
``data/rede/siga_potencias_eol_rn.csv`` é gerado fora do runtime por
``scripts/atualizar_dados_mapa.py`` (via ``core/fontes_online.py``),
conferido e versionado. Chave de junção: ``ceg`` == coluna ``CEG`` da aba
Detalhamento (ex.: 'EOL.CV.RN.028444-0.1').
"""

from pathlib import Path

import pandas as pd

_ARQ_SIGA = (
    Path(__file__).resolve().parent.parent / "data" / "rede" / "siga_potencias_eol_rn.csv"
)


def ler_potencias_eol_rn() -> pd.DataFrame | None:
    """Lê a potência por CEG de ``data/rede/siga_potencias_eol_rn.csv``.

    Retorna ``None`` (fallback gracioso) se o arquivo não existir — nesse
    caso a coluna de potência por usina simplesmente não aparece no mapa.
    Colunas: ``ceg``, ``potencia_outorgada_mw``, ``potencia_fiscalizada_mw``,
    ``fase_usina``, ``proprietario``.
    """
    if not _ARQ_SIGA.exists():
        return None
    df = pd.read_csv(_ARQ_SIGA)
    df["ceg"] = df["ceg"].astype(str).str.strip()
    for col in ("potencia_outorgada_mw", "potencia_fiscalizada_mw"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna(subset=["ceg"]).drop_duplicates(subset=["ceg"]).reset_index(drop=True)
