"""Descobre por conta própria quais documentos do MPO valem para cada
conjunto (sem depender da coluna "Documentos associados" da planilha) e
compara com o que está cadastrado — **só conferência**, não grava nada: o
painel continua lendo a coluna curada da planilha via
``core/documentos_ons.py``.

Como a descoberta funciona
--------------------------
1. Baixa todos os ``IO-OI.NE.*`` vigentes do Nordeste numa única consulta
   (``core.fontes_ons_mpo.listar_io_oi_nordeste``) — poucas centenas,
   cabe no limite da API sem paginação.
2. De cada um, extrai o nome da subestação do campo ``MpoAssunto`` da
   própria API ("Procedimentos Sistêmicos para a Operação da SE X" -> "X")
   — sem abrir PDF. Documentos de usina (EOL/UTE/UHE) não têm SE e são
   descartados.
3. Casa o nome da SE contra o ``ponto_conexao`` de cada conjunto (mesma
   normalização de ``core/ons_rede.py::_chave_subestacao_ons`` usada em
   todo o resto do painel para juntar planilha, bays.xlsx e cadastro ONS).
4. A área (Leste/Norte/500 kV) de cada conjunto sai de graça: é a mesma
   pasta onde o ``IO-OI`` da sua SE está publicado no MPO — dispensa um
   mapeamento próprio de área por conjunto, que não existe hoje.
5. Some o código de ajustamento operativo (AO-CE) e o de preparação para
   manobras (IO-PM) correspondentes à área descoberta.

Compara o conjunto de códigos descoberto com o da coluna "Documentos
associados" de cada conjunto e reporta divergências — nada é gravado, nem
em ``.novo.csv`` nem no arquivo em uso.

Uso::

    python scripts/conferir_documentos_ons.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.data_loader import DATA_PATH, _COLUNAS_CONJUNTOS  # noqa: E402
from core.fontes_ons_mpo import listar_io_oi_nordeste  # noqa: E402
from core.ons_rede import _chave_subestacao_ons  # noqa: E402

# Área (pasta do MPO) -> códigos de ajustamento operativo e preparação
# para manobras que valem para todo conjunto daquela área.
_CODIGOS_POR_AREA = {
    "leste": {"ao_ce": "AO-CE.NE.2LE", "io_pm": "IO-PM.NE.2LE"},
    "norte": {"ao_ce": "AO-CE.NE.2NO", "io_pm": "IO-PM.NE.2NO"},
}
_RE_AREA_PASTA = re.compile(r"Área\s+(?:\d+\s*)?kV\s+(Leste|Norte)", re.IGNORECASE)


def _area_da_pasta(pasta: str) -> str | None:
    """Extrai 'leste'/'norte' do caminho do documento no MPO (``FileRef``,
    sem percent-encoding), quando a pasta menciona a área explicitamente
    (ex.: ".../Área 230 kV Leste/..."). Pastas "500 kV da Região Nordeste"
    não mencionam Leste/Norte — ficam sem área conhecida (nem toda SE
    500 kV tem AO-CE/IO-PM próprios)."""
    m = _RE_AREA_PASTA.search(pasta)
    return m.group(1).lower() if m else None


def _conjuntos_da_planilha() -> pd.DataFrame:
    df = pd.read_excel(DATA_PATH, sheet_name="Localizacao")
    return df.rename(columns=_COLUNAS_CONJUNTOS)


def main() -> int:
    print("Baixando IO-OI.NE vigentes do MPO...")
    documentos = listar_io_oi_nordeste()
    print(f"{len(documentos)} documentos, {sum(1 for d in documentos if d['nome_se'])} com SE identificada.\n")

    # Índice por chave de SE normalizada -> lista de {codigo, area}. Uma SE
    # pode ter mais de um IO-OI (equipamentos/linhas diferentes na mesma
    # subestação) — descoberto empiricamente (Açu II, João Câmara III,
    # Touros e outras têm 2+ códigos na planilha do cliente).
    por_se: dict[str, list[dict]] = {}
    for doc in documentos:
        if not doc["nome_se"]:
            continue
        chave = _chave_subestacao_ons(doc["nome_se"])
        por_se.setdefault(chave, []).append(
            {"codigo": doc["codigo"], "area": _area_da_pasta(doc["pasta"])}
        )

    conjuntos = _conjuntos_da_planilha()

    divergencias = 0
    sem_se_descoberta = []
    for _, row in conjuntos.iterrows():
        conjunto = row["conjunto"]
        chave_se = _chave_subestacao_ons(row["ponto_conexao"])
        cadastrados = {
            c.strip() for c in str(row.get("documentos_associados") or "").splitlines() if c.strip()
        }

        infos_se = por_se.get(chave_se)
        if not infos_se:
            sem_se_descoberta.append((conjunto, row["ponto_conexao"]))
            continue

        descobertos = {info["codigo"] for info in infos_se}
        areas = {info["area"] for info in infos_se if info["area"] in _CODIGOS_POR_AREA}
        for area in areas:
            descobertos.add(_CODIGOS_POR_AREA[area]["ao_ce"])
            descobertos.add(_CODIGOS_POR_AREA[area]["io_pm"])

        so_planilha = cadastrados - descobertos
        so_descoberta = descobertos - cadastrados
        if so_planilha or so_descoberta:
            divergencias += 1
            print(f"DIVERGE  {conjunto} ({row['ponto_conexao']})")
            if so_planilha:
                print(f"  só na planilha:   {', '.join(sorted(so_planilha))}")
            if so_descoberta:
                print(f"  só na descoberta: {', '.join(sorted(so_descoberta))}")

    print(f"\n{len(conjuntos)} conjuntos conferidos, {divergencias} com divergência.")
    if divergencias:
        print(
            "A maioria das divergências 'só na planilha' de um único código\n"
            "IO-OI.NE.* costuma ser SE coletora do próprio conjunto (não a SE\n"
            "de transmissão do ponto_conexao) — o MpoAssunto não segue um\n"
            "padrão único ('SE X', 'X e Eólica Y', dois conjuntos no mesmo\n"
            "documento...) e casar isso por nome de forma confiável arriscaria\n"
            "falso positivo (ex.: IO-OI.NE.JAN é SE Jandaia/BA, não Jandaíra\n"
            "II/RN, mesmo a sigla parecendo bater). Conferir manualmente contra\n"
            "o MPO, não assumir bug do script."
        )
    if sem_se_descoberta:
        print(f"\n{len(sem_se_descoberta)} conjunto(s) cuja SE de conexão não bateu com nenhum IO-OI descoberto:")
        for conjunto, se in sem_se_descoberta:
            print(f"  {conjunto} -> {se}")
        print(
            "(pode ser SE 500 kV sem IO-OI próprio, nome grafado diferente do "
            "MPO, ou SE fora do Nordeste — não é necessariamente erro.)"
        )

    print("\nNada foi gravado — isto é só conferência.")
    return 1 if divergencias else 0


if __name__ == "__main__":
    raise SystemExit(main())
