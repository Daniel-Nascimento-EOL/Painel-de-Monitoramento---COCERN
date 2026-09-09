"""Roda, em sequência, todos os scripts que atualizam os arquivos de ``data/``.

É um atalho para preparar um deploy: encadeia as quatro atualizações
automáticas, cada uma no seu script dedicado, e ao final imprime um resumo
do que mudou (``git status`` da pasta ``data/``).

Uso::

    python scripts/atualizar_tudo.py                 # tudo
    python scripts/atualizar_tudo.py --sem-logos     # pula as logomarcas
    python scripts/atualizar_tudo.py rede pld        # só as etapas nomeadas

Etapas (nesta ordem):

    rede   scripts/atualizar_dados_mapa.py   -> data/rede/*.csv
    coff   scripts/atualizar_cache_coff.py   -> data/cache_coff/*.parquet
    pld    scripts/atualizar_pld_local.py    -> data/historico_pld_ne.csv
    logos  scripts/baixar_logos_agentes.py   -> data/icons/agentes/
    geojson scripts/gerar_geojson_auditoria.py -> docs/pontos_mapa.geojson

Cada etapa é isolada: se uma falhar, as demais ainda rodam e o script
encerra com código de saída != 0, listando o que falhou. Nada é
commitado — confira ``git diff`` e faça os commits (um por tipo de dado).

O que este script **não** toca: as planilhas curadas à mão
(``localizacao_conjuntos_ons_aneel.xlsx``, ``bays.xlsx``) e o contorno do
estado (``rn_estado.geojson``).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PYTHON = sys.executable

# nome -> (script, argumentos fixos, descrição do alvo)
_ETAPAS: dict[str, tuple[str, list[str], str]] = {
    "rede": ("scripts/atualizar_dados_mapa.py", [], "data/rede/*.csv"),
    "coff": ("scripts/atualizar_cache_coff.py", [], "data/cache_coff/*.parquet"),
    "pld": ("scripts/atualizar_pld_local.py", [], "data/historico_pld_ne.csv"),
    "logos": ("scripts/baixar_logos_agentes.py", [], "data/icons/agentes/"),
    "geojson": (
        "scripts/gerar_geojson_auditoria.py",
        [],
        "docs/pontos_mapa.geojson",
    ),
}
_ORDEM = ["rede", "coff", "pld", "logos", "geojson"]


def _rodar_etapa(nome: str) -> bool:
    script, args, alvo = _ETAPAS[nome]
    print(f"\n{'=' * 70}\n[{nome}]  {script}  ->  {alvo}\n{'=' * 70}", flush=True)
    resultado = subprocess.run(
        [PYTHON, str(RAIZ / script), *args], cwd=RAIZ, check=False
    )
    ok = resultado.returncode == 0
    print(f"[{nome}] {'OK' if ok else f'FALHOU (codigo {resultado.returncode})'}")
    return ok


def _resumo_git() -> None:
    print(f"\n{'=' * 70}\nAlteracoes em data/ e docs/ (git status)\n{'=' * 70}")
    resultado = subprocess.run(
        ["git", "status", "--porcelain", "data", "docs"],
        cwd=RAIZ,
        check=False,
        capture_output=True,
        text=True,
    )
    saida = resultado.stdout.strip()
    if saida:
        print(saida)
        print(
            "\nConfira com 'git diff' e faca os commits (um por tipo de dado). "
            "O painel publico so muda apos o push."
        )
    else:
        print("Nada mudou — os arquivos ja estavam atualizados.")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if {"-h", "--help"} & set(argv):
        print(__doc__)
        return 0

    pular_logos = "--sem-logos" in argv
    argv = [a for a in argv if a != "--sem-logos"]

    nomes = [a for a in argv if not a.startswith("-")]
    desconhecidas = [n for n in nomes if n not in _ETAPAS]
    if desconhecidas:
        print(f"Etapa(s) desconhecida(s): {', '.join(desconhecidas)}")
        print(f"Validas: {', '.join(_ORDEM)}")
        return 2

    escolhidas = nomes or _ORDEM
    if pular_logos:
        escolhidas = [n for n in escolhidas if n != "logos"]

    falhas: list[str] = []
    for nome in _ORDEM:
        if nome in escolhidas and not _rodar_etapa(nome):
            falhas.append(nome)

    _resumo_git()

    if falhas:
        print(f"\n{len(falhas)} etapa(s) falharam: {', '.join(falhas)}")
        return 1
    print("\nTodas as etapas concluidas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
