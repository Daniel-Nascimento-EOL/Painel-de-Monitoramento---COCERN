"""Documentos normativos do ONS vinculados a cada conjunto eólico.

A planilha de conjuntos traz, por conjunto, a coluna "Documentos
associados": uma lista de códigos (um por linha, ex.: ``AO-CE.NE.2LE``,
``IO-OI.NE.LND``, ``IO-PM.NE.2LE``) que este módulo resolve para o PDF
vigente no Manual de Procedimentos da Operação (MPO) do ONS.

A resolução em si **não acontece aqui em tempo de execução** — o painel só
lê ``data/documentos_ons.csv``, espelho local gerado por
``scripts/atualizar_documentos_ons.py`` via a API REST do MPO
(``core/fontes_ons_mpo.py``). Mesmo princípio de ``core/ons_rede.py`` e
``core/aneel_siga.py``: nada de acesso à web no caminho do usuário.

Código sem entrada no CSV (documento novo na planilha que o script ainda
não resolveu, ou baixa temporária do MPO) cai no link de busca do MPO, em
vez de uma URL adivinhada.
"""

from pathlib import Path

import pandas as pd
import streamlit as st

CAMINHO_CSV = Path(__file__).resolve().parent.parent / "data" / "documentos_ons.csv"

# Página de busca do MPO — usada quando um código da planilha não tem
# entrada no CSV local (documento ainda não resolvido pelo script).
_BUSCA_MPO = "https://www.ons.org.br/paginas/sobre-o-ons/procedimentos-de-rede/mpo"


@st.cache_data(show_spinner=False)
def _ler_documentos() -> pd.DataFrame:
    """Lê o espelho local de documentos resolvidos, ou vazio se ausente."""
    if not CAMINHO_CSV.exists():
        return pd.DataFrame(columns=["codigo", "arquivo", "url"])
    return pd.read_csv(CAMINHO_CSV, dtype=str)


def documentos_do_conjunto(codigos_associados) -> list[dict]:
    """Documentos vinculados a um conjunto, a partir da coluna "Documentos
    associados" (códigos separados por quebra de linha).

    Cada item traz ``codigo``, ``titulo`` (nome do arquivo, com a revisão) e
    ``url`` — o PDF resolvido, ou a página de busca do MPO se o código
    ainda não tiver entrada no espelho local.
    """
    texto = str(codigos_associados or "").strip()
    if not texto:
        return []
    codigos = [c.strip() for c in texto.splitlines() if c.strip()]

    tabela = _ler_documentos().set_index("codigo")
    documentos = []
    for codigo in codigos:
        if codigo in tabela.index:
            linha = tabela.loc[codigo]
            documentos.append(
                {"codigo": codigo, "titulo": linha["arquivo"], "url": linha["url"]}
            )
        else:
            documentos.append({"codigo": codigo, "titulo": codigo, "url": _BUSCA_MPO})
    return documentos
