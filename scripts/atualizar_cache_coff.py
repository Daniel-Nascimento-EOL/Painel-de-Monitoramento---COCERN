"""Pré-aquece o cache em disco do constrained-off agregado.

Uso::

    python scripts/atualizar_cache_coff.py            # todos os meses consolidados
    python scripts/atualizar_cache_coff.py 2026       # apenas um ano

O painel preenche esse cache sozinho conforme é usado (ver
``core/coff_cache.py``); este script apenas antecipa o trabalho, para que um
deploy já suba com os Parquet prontos e o primeiro acesso seja imediato.
Rodar após o fechamento de cada mês, e sempre que ``VERSAO_AGREGADO`` for
incrementada — nesse caso os arquivos antigos são regravados.

Os arquivos gerados em ``data/cache_coff/`` são versionados no repositório.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.coff_cache import (  # noqa: E402
    _agregar_mes,
    _caminho,
    _gravar_cache,
    _ler_cache,
    mes_consolidado,
)
from core.ons_coff import meses_disponiveis  # noqa: E402


def main(argv: list[str]) -> int:
    ano_alvo = int(argv[0]) if argv else None
    meses = [
        (ano, mes)
        for ano, mes in sorted(meses_disponiveis())
        if mes_consolidado(ano, mes) and (ano_alvo is None or ano == ano_alvo)
    ]
    if not meses:
        print("Nenhum mês consolidado a processar.")
        return 0

    gravados = falhas = 0
    for ano, mes in meses:
        if _ler_cache(ano, mes) is not None:
            print(f"--   {ano}-{mes:02d} já em cache")
            continue
        try:
            agregado = _agregar_mes(ano, mes)
        except Exception as erro:  # noqa: BLE001 — relata e segue para o mês seguinte
            print(f"FALHA {ano}-{mes:02d}: {type(erro).__name__}: {erro}", file=sys.stderr)
            falhas += 1
            continue
        if agregado.empty:
            print(f"--   {ano}-{mes:02d} sem dados do RN")
            continue
        _gravar_cache(ano, mes, agregado)
        gravados += 1
        tamanho = _caminho(ano, mes).stat().st_size / 1024
        print(
            f"OK   {ano}-{mes:02d}: {len(agregado)} conjuntos, "
            f"{agregado['energia_frustrada_1'].sum():,.0f} MWh [1], {tamanho:.0f} KB"
        )

    print(f"\n{gravados} mês(es) gravado(s), {falhas} falha(s).")
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
