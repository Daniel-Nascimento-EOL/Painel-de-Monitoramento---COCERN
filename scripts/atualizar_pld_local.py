"""Regenera ``data/historico_pld_ne.csv`` com a série completa da CCEE.

Esse CSV é o fallback offline de ``core/ccee_pld.py``. Ele existe porque o
**Streamlit Community Cloud não consegue baixar da CCEE** — o portal
bloqueia o IP de saída da nuvem, então em produção o painel lê deste
arquivo. Localmente a web funciona e o arquivo quase nunca é usado.

Consequência prática: **rode este script antes de cada deploy**, senão os
meses publicados depois da última atualização aparecem sem impacto
financeiro no painel público.

    python scripts/atualizar_pld_local.py

O arquivo só é sobrescrito se as horas em comum com a versão anterior
baterem exatamente — uma divergência aborta a gravação.
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.ccee_pld import (  # noqa: E402
    _baixar_curl,
    _baixar_httpx,
    _baixar_requests,
    _converter_csv_ccee,
    _urls_por_ano,
)

DESTINO = Path(__file__).resolve().parent.parent / "data" / "historico_pld_ne.csv"


def main() -> int:
    anterior = (
        pd.read_csv(DESTINO, parse_dates=["din_instante"]) if DESTINO.exists() else None
    )
    if anterior is not None:
        print(
            f"atual:  {len(anterior):,} horas | "
            f"{anterior.din_instante.min()} -> {anterior.din_instante.max()}\n"
        )

    urls = _urls_por_ano()
    print(f"anos no catálogo da CCEE: {sorted(urls)}\n")

    partes = []
    for ano in sorted(urls):
        conteudo = None
        for baixar in (_baixar_httpx, _baixar_curl, _baixar_requests):
            conteudo = baixar(urls[ano])
            if conteudo:
                break
        if not conteudo:
            print(f"  {ano}: falha no download")
            continue
        df = _converter_csv_ccee(conteudo)
        if df is None:
            print(f"  {ano}: falha na conversão")
            continue
        print(
            f"  {ano}: {len(df):>5} horas | "
            f"{df.din_instante.min()} -> {df.din_instante.max()}"
        )
        partes.append(df)

    if not partes:
        print("\nNenhum ano baixado — a CCEE está inacessível deste ambiente.")
        return 1

    novo = (
        pd.concat(partes)
        .drop_duplicates(subset="din_instante")
        .sort_values("din_instante")
        .reset_index(drop=True)
    )

    esperado = len(
        pd.date_range(novo.din_instante.min(), novo.din_instante.max(), freq="h")
    )
    print(
        f"\nnovo:   {len(novo):,} horas | "
        f"{novo.din_instante.min()} -> {novo.din_instante.max()}"
    )
    print(f"lacunas no período: {esperado - len(novo)}")
    print(f"nulos: {novo.pld_horario.isna().sum()} | zeros: {(novo.pld_horario == 0).sum()}")

    if anterior is not None:
        j = novo.merge(anterior, on="din_instante", how="inner", suffixes=("_novo", "_antigo"))
        dif = (j.pld_horario_novo - j.pld_horario_antigo).abs()
        divergentes = int((dif > 0.01).sum())
        print(
            f"conferência com a série anterior: {len(j):,} horas em comum, "
            f"{divergentes} divergentes"
        )
        if divergentes:
            print("Divergências encontradas — arquivo NÃO sobrescrito.")
            return 1

    novo.to_csv(DESTINO, index=False, date_format="%Y-%m-%d %H:%M:%S")
    print(f"\nsalvo: {DESTINO.name} ({DESTINO.stat().st_size / 1024:.0f} KB)")
    if anterior is not None:
        print(f"ganho: +{len(novo) - len(anterior):,} horas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
