"""Pré-aquece o cache em disco do constrained-off agregado.

Uso::

    python scripts/atualizar_cache_coff.py                  # meses ainda sem cache
    python scripts/atualizar_cache_coff.py 2026              # idem, restrito a um ano
    python scripts/atualizar_cache_coff.py --forcar-tudo     # recalcula TODO mês consolidado

O painel preenche esse cache sozinho conforme é usado (ver
``core/coff_cache.py``); este script apenas antecipa o trabalho, para que um
deploy já suba com os Parquet prontos e o primeiro acesso seja imediato.

``--forcar-tudo`` existe porque o CSV de um mês "fechado" não é
necessariamente imutável na prática: um agente pode subir dado atrasado no
SAGER do ONS depois que o mês já virou Parquet, e o painel nunca mais
rebaixaria esse mês sozinho (``agregado_do_mes`` só recalcula o mês
corrente). Esse modo ignora o cache existente, recalcula cada mês a partir
do CSV atual do ONS e só regrava/relata o Parquet cujo conteúdo realmente
mudou — a maioria dos meses antigos não muda, então o commit resultante
tende a ficar pequeno mesmo varrendo o histórico inteiro. É o que o workflow
``.github/workflows/atualizar-coff.yml`` roda 2x ao dia, acompanhando a
publicação do ONS (ver ``core/ons_coff.py``).

Sem a flag, o script só preenche o que falta (comportamento original) —
rodar após o fechamento de cada mês, e sempre que ``VERSAO_AGREGADO`` for
incrementada (arquivos de versão antiga não contam como "já em cache").

Os arquivos gerados em ``data/cache_coff/`` são versionados no repositório.
"""

import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.coff_cache import (  # noqa: E402
    _agregar_mes,
    _caminho,
    _gravar_cache,
    _ler_cache,
    mes_consolidado,
)
from core.ons_coff import meses_disponiveis  # noqa: E402


def _e_404(erro: Exception) -> bool:
    """``meses_disponiveis()`` assume que todo mês desde 2021-01 tem CSV no
    ONS, mas alguns (ex.: mai–set/2021, antes do RN ter conjunto reportado)
    nunca existiram — 404 permanente, não uma falha transitória. Não deve
    contar como falha do workflow nem derrubar seu exit code."""
    return (
        isinstance(erro, requests.HTTPError)
        and erro.response is not None
        and erro.response.status_code == 404
    )


def main(argv: list[str]) -> int:
    forcar_tudo = "--forcar-tudo" in argv
    resto = [a for a in argv if a != "--forcar-tudo"]
    ano_alvo = int(resto[0]) if resto else None

    meses = [
        (ano, mes)
        for ano, mes in sorted(meses_disponiveis())
        if mes_consolidado(ano, mes) and (ano_alvo is None or ano == ano_alvo)
    ]
    if not meses:
        print("Nenhum mês consolidado a processar.")
        return 0

    gravados = inalterados = ausentes = falhas = 0
    for ano, mes in meses:
        existente = _ler_cache(ano, mes)
        if existente is not None and not forcar_tudo:
            print(f"--   {ano}-{mes:02d} já em cache")
            continue
        try:
            agregado = _agregar_mes(ano, mes)
        except Exception as erro:  # noqa: BLE001 — relata e segue para o mês seguinte
            if _e_404(erro):
                print(f"--   {ano}-{mes:02d} sem CSV publicado pelo ONS (404)")
                ausentes += 1
            else:
                print(f"FALHA {ano}-{mes:02d}: {type(erro).__name__}: {erro}", file=sys.stderr)
                falhas += 1
            continue
        if agregado.empty:
            print(f"--   {ano}-{mes:02d} sem dados do RN")
            continue
        if existente is not None and agregado.equals(existente):
            inalterados += 1
            continue
        mudou_revisao = existente is not None and not agregado.equals(existente)
        _gravar_cache(ano, mes, agregado)
        gravados += 1
        tamanho = _caminho(ano, mes).stat().st_size / 1024
        marca = "REV " if mudou_revisao else "OK  "
        print(
            f"{marca} {ano}-{mes:02d}: {len(agregado)} conjuntos, "
            f"{agregado['energia_frustrada_1'].sum():,.0f} MWh [1], {tamanho:.0f} KB"
        )

    print(
        f"\n{gravados} mês(es) gravado(s), {inalterados} sem mudança, "
        f"{ausentes} sem CSV no ONS, {falhas} falha(s)."
    )
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
