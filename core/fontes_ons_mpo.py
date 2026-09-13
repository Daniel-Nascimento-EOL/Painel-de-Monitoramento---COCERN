"""Consulta ao Manual de Procedimentos da Operação (MPO) do ONS.

Este módulo **não é importado pelo aplicativo**. Existe para dois scripts:
``scripts/atualizar_documentos_ons.py``, que resolve os códigos de
documento da coluna "Documentos associados" (``AO-CE.*``, ``IO-OI.*``,
``IO-PM.*``) para o PDF vigente e grava o resultado em
``data/documentos_ons.csv`` — o painel em si só lê esse CSV
(``core/documentos_ons.py``), sem acessar a web em tempo de execução — e
``scripts/conferir_documentos_ons.py``, que descobre por conta própria quais
documentos valem para cada conjunto (sem depender da coluna da planilha) e
compara com o que está cadastrado, como conferência.

Nenhuma dependência de Streamlit: os scripts rodam fora do runtime.

Como funciona
-------------
O site do MPO (ons.org.br) é um SharePoint, e a biblioteca de documentos é
consultável por uma API REST **sem autenticação**::

    https://www.ons.org.br/_api/web/lists/getbytitle('MPO')/items
        ?$select=Title,FileLeafRef,FileRef,MpoSituacao,MpoAssunto
        &$filter=substringof('<codigo>',FileLeafRef)&$top=2000

O nome do arquivo (``FileLeafRef``) já traz a revisão vigente embutida
(``IO-OI.NE.LND_Rev.23.pdf``) — dispensa a sondagem HEAD por revisão que
``core/documentos_ons.py`` fazia antes só para o Ajustamento Operativo.
Filtrar pelo código **exato e completo** (não só o prefixo de família,
``IO-OI.NE.LND`` e não ``IO-OI``) evita estourar o ``$top=2000`` quando se
quer só um código — a família ``IO-OI`` inteira (todo o Brasil) tem mais de
mil documentos; ``IO-OI.NE`` (só Nordeste) fica em ~300, dentro do limite.

``MpoAssunto`` identifica a instalação em texto livre, ex.: "Procedimentos
Sistêmicos para a Operação da SE Lagoa Nova II" — é o que permite descobrir
a qual subestação um ``IO-OI.NE.<sigla>`` pertence **sem abrir o PDF** (a
sigla sozinha não é confiável: ``IO-OI.NE.JAN`` é SE Jandaia (BA), não
Jandaíra II, que é ``JDD`` — ver ``descobrir_io_oi_por_se()``).

Gotcha do ambiente "Programados"
---------------------------------
A mesma busca pode devolver, além do PDF publicado, uma revisão em
elaboração dentro de ``/MPO/Programados/...`` (observado com
``AO-CE.NE.2LE``: um ``.docx`` Rev.33 nos Programados ao lado do ``.pdf``
Rev.32 já publicado, com ``MpoSituacao`` "Programado" em vez de "Vigente").
Filtrar por ``MpoSituacao == "Vigente"`` é mais confiável que checar o
caminho — usar isso quando o campo estiver disponível na consulta.
"""

from __future__ import annotations

import re
import urllib.parse

import httpx

_BASE_SITE = "https://www.ons.org.br"
_URL_LISTA = f"{_BASE_SITE}/_api/web/lists/getbytitle('MPO')/items"
_CABECALHOS = {"Accept": "application/json;odata=nometadata"}

_RE_REVISAO = re.compile(r"_Rev\.(\d+)", re.IGNORECASE)
_RE_ASSUNTO_SE = re.compile(r"\bSE\s+(.+)$")


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


def listar_io_oi_nordeste() -> list[dict]:
    """Lista todos os IO-OI vigentes da região Nordeste, numa única consulta.

    Devolve ``{"codigo", "arquivo", "url", "assunto", "nome_se"}`` por item —
    ``nome_se`` vem de ``MpoAssunto`` ("...Operação da SE X" -> "X") e é
    ``None`` quando o documento é de usina (EOL/UTE/UHE), não de
    subestação — esses não têm SE de conexão pra casar contra o cadastro.
    """
    params = {
        "$select": "MpoCodigo,MpoAssunto,MpoSituacao,FileLeafRef,FileRef",
        "$filter": "substringof('IO-OI.NE',FileLeafRef)",
        "$top": "2000",
    }
    resposta = httpx.get(_URL_LISTA, params=params, headers=_CABECALHOS, timeout=30)
    resposta.raise_for_status()
    itens = resposta.json().get("value", [])

    vigentes = [
        item
        for item in itens
        if item.get("MpoSituacao") == "Vigente"
        and item["FileLeafRef"].lower().endswith(".pdf")
    ]
    # Pode haver mais de um Vigente para o mesmo código momentaneamente
    # (transição de revisão) — fica com a maior.
    melhores: dict[str, dict] = {}
    for item in vigentes:
        codigo = item["MpoCodigo"]
        if codigo not in melhores or _revisao(item["FileLeafRef"]) > _revisao(
            melhores[codigo]["FileLeafRef"]
        ):
            melhores[codigo] = item

    saida = []
    for codigo, item in melhores.items():
        assunto = item.get("MpoAssunto") or ""
        m = _RE_ASSUNTO_SE.search(assunto)
        saida.append({
            "codigo": codigo,
            "arquivo": item["FileLeafRef"],
            "pasta": item["FileRef"],  # sem percent-encoding, útil pra achar a área
            "url": _BASE_SITE + urllib.parse.quote(item["FileRef"], safe="/"),
            "assunto": assunto,
            "nome_se": m.group(1).strip() if m else None,
        })
    return saida


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
