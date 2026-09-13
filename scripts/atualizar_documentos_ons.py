"""Resolve os códigos de "Documentos associados" da planilha de conjuntos
para o PDF vigente no MPO do ONS — **sem tocar no arquivo em uso**.

O painel lê apenas ``data/documentos_ons.csv`` (``core/documentos_ons.py``);
nada é baixado em tempo de execução. Este script é o único ponto que vai à
web: consulta a API REST do MPO (``core/fontes_ons_mpo.py``) para cada
código único presente na planilha, e grava o resultado em
``data/documentos_ons.novo.csv`` — o arquivo em uso nunca é alterado por
este script.

Uso::

    python scripts/atualizar_documentos_ons.py

Fluxo de aprovação (manual, fora do script):

    1. rodar este script;
    2. comparar: ``git diff --no-index data/documentos_ons.csv data/documentos_ons.novo.csv``;
    3. se aprovar, promover: ``mv data/documentos_ons.novo.csv data/documentos_ons.csv``;
    4. ``git add`` e commit. Se rejeitar, apagar o ``.novo.csv``.

Código da planilha sem resolução no MPO é avisado, não interrompe o
script — o painel cai para o link de busca do MPO nesses casos (ver
``core/documentos_ons.py``).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.data_loader import DATA_PATH, _COLUNAS_CONJUNTOS  # noqa: E402
from core.fontes_ons_mpo import resolver_documento  # noqa: E402

CAMINHO_VIGENTE = Path(__file__).resolve().parent.parent / "data" / "documentos_ons.csv"


def _codigos_da_planilha() -> list[str]:
    """Códigos únicos de "Documentos associados", em todos os conjuntos.

    Lê a planilha direto (sem passar por ``core.data_loader.load_conjuntos``,
    que é decorada com ``@st.cache_data`` e espera o runtime do Streamlit).
    """
    df = pd.read_excel(DATA_PATH, sheet_name="Localizacao")
    df = df.rename(columns=_COLUNAS_CONJUNTOS)
    codigos: set[str] = set()
    for valor in df["documentos_associados"].dropna():
        for codigo in str(valor).splitlines():
            codigo = codigo.strip()
            if codigo:
                codigos.add(codigo)
    return sorted(codigos)


def main() -> int:
    codigos = _codigos_da_planilha()
    print(f"{len(codigos)} código(s) único(s) na planilha.")
    if len(codigos) < 10:
        print(f"ABORTADO: apenas {len(codigos)} códigos — esperado uma centena.")
        return 1

    linhas = []
    nao_resolvidos = []
    for codigo in codigos:
        print(f"  {codigo} ...", end=" ", flush=True)
        try:
            resultado = resolver_documento(codigo)
        except Exception as erro:  # noqa: BLE001 — relata e segue para os demais
            print(f"ERRO ({erro})")
            nao_resolvidos.append(codigo)
            continue
        if resultado is None:
            print("não encontrado")
            nao_resolvidos.append(codigo)
            continue
        print(resultado["arquivo"])
        linhas.append(resultado)

    if not linhas:
        print("\nABORTADO: nenhum código resolvido — nada gravado.")
        return 1

    novo = pd.DataFrame(linhas, columns=["codigo", "arquivo", "url"])
    CAMINHO_VIGENTE.parent.mkdir(parents=True, exist_ok=True)
    destino = CAMINHO_VIGENTE.with_suffix(".novo.csv")
    novo.to_csv(destino, index=False, encoding="utf-8-sig")

    if CAMINHO_VIGENTE.exists():
        atual = pd.read_csv(CAMINHO_VIGENTE)
        print(f"\n{len(atual)} -> {len(novo)} documentos em relação ao vigente.")
    else:
        print(f"\n{len(novo)} documentos (primeira geração — ainda não há arquivo vigente).")

    print(f"Gerado: {destino.relative_to(destino.parent.parent.parent)}")
    if nao_resolvidos:
        print(
            f"\n{len(nao_resolvidos)} código(s) sem resolução no MPO "
            f"(painel cai para a busca do MPO nesses casos):"
        )
        for codigo in nao_resolvidos:
            print(f"  {codigo}")

    print(
        "\nCompare com:\n"
        "  git diff --no-index data/documentos_ons.csv data/documentos_ons.novo.csv\n"
        "Para promover:\n"
        "  mv data/documentos_ons.novo.csv data/documentos_ons.csv  (depois git add e commit)"
    )
    return 1 if nao_resolvidos else 0


if __name__ == "__main__":
    raise SystemExit(main())
