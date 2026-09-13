"""Consulta ao Manual de Procedimentos da Operação (MPO) do ONS.

Este módulo **não é importado pelo aplicativo**. Existe só para
``scripts/atualizar_documentos_ons.py``, que resolve os códigos de
documento da coluna "Documentos associados" (``AO-CE.*``, ``IO-OI.*``,
``IO-PM.*``) para o PDF vigente e grava o resultado em
``data/documentos_ons.csv`` — o painel em si só lê esse CSV
(``core/documentos_ons.py``), sem acessar a web em tempo de execução.

Nenhuma dependência de Streamlit: o script roda fora do runtime.

Como funciona
-------------
O site do MPO (ons.org.br) é um SharePoint, e a biblioteca de documentos é
consultável por uma API REST **sem autenticação**::

    https://www.ons.org.br/_api/web/lists/getbytitle('MPO')/items
        ?$select=Title,FileLeafRef,FileRef
        &$filter=substringof('<codigo>',FileLeafRef)&$top=2000

O nome do arquivo (``FileLeafRef``) já traz a revisão vigente embutida
(``IO-OI.NE.LND_Rev.23.pdf``) — dispensa a sondagem HEAD por revisão que
``core/documentos_ons.py`` fazia antes só para o Ajustamento Operativo.
Filtrar pelo código **exato e completo** (não só o prefixo de família,
``IO-OI.NE.LND`` e não ``IO-OI``) evita estourar o ``$top=2000`` — a
família IO-OI sozinha tem mais de mil documentos, de todas as regiões.

Gotcha do ambiente "Programados"
---------------------------------
A mesma busca pode devolver, além do PDF publicado, uma revisão em
elaboração dentro de ``/MPO/Programados/...`` (observado com
``AO-CE.NE.2LE``: um ``.docx`` Rev.33 nos Programados ao lado do ``.pdf``
Rev.32 já publicado). Não é o documento vigente — filtrar por extensão
``.pdf`` e por caminho fora de ``/Programados/`` antes de escolher a maior
revisão.
"""

from __future__ import annotations

import re
import urllib.parse

import httpx

_BASE_SITE = "https://www.ons.org.br"
_URL_LISTA = f"{_BASE_SITE}/_api/web/lists/getbytitle('MPO')/items"
_CABECALHOS = {"Accept": "application/json;odata=nometadata"}

_RE_REVISAO = re.compile(r"_Rev\.(\d+)", re.IGNORECASE)


def _revisao(nome_arquivo: str) -> int:
    m = _RE_REVISAO.search(nome_arquivo)
    return int(m.group(1)) if m else -1


def consultar_mpo(codigo: str) -> list[dict]:
    """Consulta a API REST do MPO por um código exato de documento.

    Devolve a lista de itens candidatos (``FileLeafRef``, ``FileRef``),
    já restrita a PDFs publicados (exclui ``/Programados/`` e extensões
    que não sejam ``.pdf``). Vazia se o código não for encontrado.
    """
    params = {
        "$select": "Title,FileLeafRef,FileRef",
        "$filter": f"substringof('{codigo}',FileLeafRef)",
        "$top": "2000",
    }
    resposta = httpx.get(_URL_LISTA, params=params, headers=_CABECALHOS, timeout=30)
    resposta.raise_for_status()
    itens = resposta.json().get("value", [])
    return [
        item
        for item in itens
        if item["FileLeafRef"].lower().endswith(".pdf")
        and "/programados/" not in item["FileRef"].lower()
    ]


def resolver_documento(codigo: str) -> dict | None:
    """Resolve um código de documento (ex.: ``IO-OI.NE.LND``) para o PDF
    vigente: a maior revisão publicada entre os candidatos.

    Devolve ``{"codigo", "arquivo", "url"}`` ou ``None`` se não encontrado.
    """
    candidatos = consultar_mpo(codigo)
    if not candidatos:
        return None
    melhor = max(candidatos, key=lambda item: _revisao(item["FileLeafRef"]))
    url = _BASE_SITE + urllib.parse.quote(melhor["FileRef"], safe="/")
    return {"codigo": codigo, "arquivo": melhor["FileLeafRef"], "url": url}
