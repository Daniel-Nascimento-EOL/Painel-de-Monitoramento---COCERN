"""PLD horário do submercado Nordeste — fonte de preço para valoração do
constrained-off.

Fonte: **dados abertos da CCEE**, dataset ``pld_horario`` — um CSV por ano,
servido em ``pda-download.ccee.org.br``. Colunas: ``MES_REFERENCIA``
(AAAAMM), ``SUBMERCADO``, ``PERIODO_COMERCIALIZACAO``, ``DIA``, ``HORA``,
``PLD_HORA`` (R$/MWh).

Cadeia de fontes (a web é sempre a principal)
---------------------------------------------
1. **Catálogo da CCEE** (:func:`_urls_por_ano`) descobre a URL de cada ano:
   API CKAN → HTML da página do dataset → identificadores fixos no código.
   Anos novos passam a ser lidos assim que a CCEE os publica, sem alteração
   de código.
2. **Download do CSV do ano** por três transportes: httpx → curl → requests
   (ver a seção sobre o bloqueio, abaixo).
3. **Fallback offline**: ``data/historico_pld_ne.csv``, série de PLD horário
   do Nordeste de 17/10/2021 a 07/07/2025, extraída da planilha do estudo de
   referência. Só entra em cena se a web estiver inacessível.

Se nem o fallback cobrir o período, a função devolve None e a UI mostra a
energia frustrada em MWh sem o impacto financeiro.

Por que PLD e não CMO
---------------------
O **CMO** (Custo Marginal de Operação, publicado pelo ONS) é o custo de
gerar 1 MWh adicional naquela hora. Não tem piso nem teto e zera com
frequência no Nordeste, quando sobra geração renovável — em vários meses de
2024 a mediana do CMO ficou abaixo de R$ 2/MWh.

O **PLD** é o preço com que a CCEE liquida energia no mercado de curto
prazo: parte do CMO, mas aplica o piso e o teto regulatórios definidos
anualmente pela ANEEL (em 2024, piso R$ 61,07 e teto horário R$ 1.470,57)
e passa pelo processamento próprio da CCEE.

A energia cortada por constrained-off é energia que a usina **deixou de
liquidar**, portanto vale o PLD, não o custo marginal. Uma versão anterior
deste módulo usava o CMO do ONS como proxy e subestimava o impacto
financeiro em uma ordem de grandeza nos meses de CMO baixo — janeiro de
2024, por exemplo, rendia R$ 3 onde o valor correto é R$ 9.244.

Como o acesso é obtido (importante)
-----------------------------------
O perímetro da CCEE rejeita com 403 requisições que não pareçam vir de um
navegador, em duas camadas:

1. **Cabeçalhos** — só o ``User-Agent`` não basta; é preciso o conjunto
   ``Sec-Fetch-*`` / ``Sec-Ch-Ua`` que um Chrome envia numa navegação real.
   Não remover nada de ``_CABECALHOS``.
2. **Impressão digital TLS** — mesmo com os cabeçalhos corretos, a
   biblioteca ``requests`` (urllib3) leva 403, porque seu handshake TLS não
   se parece com o de um navegador. ``httpx`` e o binário ``curl`` passam.

Por isso o download tenta, em ordem: ``httpx`` → ``curl`` (subprocesso) →
``requests``. Foi essa combinação que destravou a fonte; a versão anterior
deste projeto concluiu que a CCEE estava "fora do ar" e migrou para o CMO
do ONS, quando na verdade era o bloqueio de automação.
"""

import io
import json
import re
import subprocess

import pandas as pd
import requests
import streamlit as st

try:
    import httpx
except ImportError:  # pragma: no cover - httpx é dependência declarada
    httpx = None

from pathlib import Path

_ARQUIVO_FALLBACK = Path(__file__).resolve().parent.parent / "data" / "historico_pld_ne.csv"

_URL_PLD = "https://pda-download.ccee.org.br/{recurso}/content"
_URL_CATALOGO = "https://dadosabertos.ccee.org.br/api/3/action/package_show?id=pld_horario"
_URL_DATASET = "https://dadosabertos.ccee.org.br/dataset/pld_horario"

# Identificadores conhecidos dos recursos anuais, usados apenas se a
# descoberta pelo catálogo falhar. A lista fica desatualizada quando a CCEE
# publica um ano novo — por isso a descoberta dinâmica vem primeiro.
_RECURSOS_CONHECIDOS = {
    2021: "SMpDR_R7SCOOj6pMbk1BJg",
    2022: "0YTnGY1jRb-tarnKnSNT9g",
    2023: "HH4Xegm7R56M_H4qPNOvaw",
    2024: "rMsBwN6TT-WUW2_LbGUvkw",
    2025: "korJMXwpSLGyVlpRMQWduA",
    2026: "6A5wq97KTCWv_bvs3CqsQQ",
}

_SUBMERCADO_NORDESTE = "NORDESTE"

_CABECALHOS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8",
    "Sec-Ch-Ua": '"Chromium";v="131", "Not_A Brand";v="24"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "Referer": "https://dadosabertos.ccee.org.br/dataset/pld_horario",
}


def _baixar_httpx(url: str) -> bytes | None:
    """Via httpx — a que costuma passar pelo filtro de automação da CCEE."""
    if httpx is None:
        return None
    try:
        resposta = httpx.get(
            url, headers=_CABECALHOS, timeout=180, follow_redirects=True
        )
        resposta.raise_for_status()
        return resposta.content
    except Exception:
        return None


def _baixar_curl(url: str) -> bytes | None:
    """Via binário curl — outra impressão digital TLS, caso httpx falhe."""
    try:
        argumentos = ["curl", "-sS", "--compressed", "-L", "--max-time", "180"]
        for chave, valor in _CABECALHOS.items():
            argumentos += ["-H", f"{chave}: {valor}"]
        argumentos.append(url)
        processo = subprocess.run(argumentos, capture_output=True, timeout=200)
        if processo.returncode != 0 or not processo.stdout:
            return None
        return processo.stdout
    except Exception:
        return None


def _baixar_requests(url: str) -> bytes | None:
    """Via requests — última tentativa; costuma levar 403 no perímetro atual."""
    try:
        resposta = requests.get(url, headers=_CABECALHOS, timeout=180)
        resposta.raise_for_status()
        return resposta.content
    except Exception:
        return None


def _converter_csv_ccee(conteudo: bytes) -> pd.DataFrame | None:
    """Converte o CSV anual da CCEE em (din_instante, pld_horario) do NE."""
    try:
        df = pd.read_csv(io.BytesIO(conteudo), sep=";", decimal=".")
    except Exception:
        return None

    df.columns = [c.strip().upper() for c in df.columns]
    obrigatorias = {"MES_REFERENCIA", "SUBMERCADO", "DIA", "HORA", "PLD_HORA"}
    if not obrigatorias.issubset(df.columns):
        return None

    df = df[df["SUBMERCADO"].astype(str).str.strip() == _SUBMERCADO_NORDESTE].copy()
    if df.empty:
        return None

    df["din_instante"] = pd.to_datetime(
        df["MES_REFERENCIA"].astype(str).str.zfill(6)
        + df["DIA"].astype(str).str.zfill(2)
        + df["HORA"].astype(str).str.zfill(2),
        format="%Y%m%d%H",
        errors="coerce",
    )
    df["pld_horario"] = pd.to_numeric(df["PLD_HORA"], errors="coerce")

    pld = df[["din_instante", "pld_horario"]].dropna()
    if pld.empty:
        return None
    # Horário de verão pode repetir a mesma hora; consolida pela média.
    return (
        pld.groupby("din_instante", as_index=False)["pld_horario"]
        .mean()
        .sort_values("din_instante")
        .reset_index(drop=True)
    )


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def _urls_por_ano() -> dict[int, str]:
    """Descobre a URL do CSV de cada ano no catálogo de dados abertos da CCEE.

    Anos novos entram sozinhos conforme a CCEE os publica — nada precisa ser
    alterado no código. Tenta a API CKAN, depois o HTML da página do dataset
    e, por fim, os identificadores conhecidos em ``_RECURSOS_CONHECIDOS``.
    """
    # 1) API CKAN: resposta estruturada, com nome e URL de cada recurso.
    conteudo = _baixar_httpx(_URL_CATALOGO) or _baixar_curl(_URL_CATALOGO)
    if conteudo:
        try:
            pacote = json.loads(conteudo)
            urls = {}
            for recurso in pacote["result"]["resources"]:
                achado = re.fullmatch(r"pld_horario_(\d{4})", str(recurso.get("name", "")).strip())
                url = str(recurso.get("url", ""))
                if achado and url:
                    urls[int(achado.group(1))] = url
            if urls:
                return urls
        except Exception:
            pass

    # 2) HTML da página do dataset: os links seguem o padrão do pda-download.
    conteudo = _baixar_httpx(_URL_DATASET) or _baixar_curl(_URL_DATASET)
    if conteudo:
        try:
            html = conteudo.decode("utf-8", errors="ignore")
            urls = {
                int(ano): f"https://pda-download.ccee.org.br/{recurso}/content"
                for ano, recurso in re.findall(
                    r"pld_horario_(\d{4}).{0,4000}?pda-download\.ccee\.org\.br/([A-Za-z0-9_-]{15,})/content",
                    html,
                    re.DOTALL,
                )
            }
            if urls:
                return urls
        except Exception:
            pass

    # 3) Identificadores fixados no código.
    return {ano: _URL_PLD.format(recurso=r) for ano, r in _RECURSOS_CONHECIDOS.items()}


def _pld_do_arquivo_local(ano: int) -> pd.DataFrame | None:
    """Fallback: recorta o ano da série local ``data/historico_pld_ne.csv``."""
    try:
        df = pd.read_csv(_ARQUIVO_FALLBACK, parse_dates=["din_instante"])
    except Exception:
        return None
    if not {"din_instante", "pld_horario"}.issubset(df.columns):
        return None
    df = df[df["din_instante"].dt.year == ano].dropna()
    return df.reset_index(drop=True) if not df.empty else None


@st.cache_data(ttl=6 * 3600, show_spinner="Baixando PLD horário (CCEE)...")
def baixar_pld_nordeste(ano: int) -> pd.DataFrame | None:
    """PLD horário do submercado Nordeste para o ano informado.

    Descobre a URL do ano no catálogo da CCEE (ver :func:`_urls_por_ano`),
    baixa por três transportes distintos (httpx, curl, requests) e, se tudo
    falhar, recorre à série local em ``data/historico_pld_ne.csv``.

    Retorna um DataFrame com ``din_instante`` (hora cheia) e ``pld_horario``
    (R$/MWh), ou None se nenhuma fonte cobrir o ano — mantendo o fallback
    gracioso da página de Energia Frustrada.
    """
    url = _urls_por_ano().get(ano)
    if url is not None:
        for baixar in (_baixar_httpx, _baixar_curl, _baixar_requests):
            conteudo = baixar(url)
            if conteudo is None:
                continue
            pld = _converter_csv_ccee(conteudo)
            if pld is not None:
                return pld
    return _pld_do_arquivo_local(ano)


def anos_disponiveis() -> list[int]:
    """Anos com PLD publicado, do mais recente para o mais antigo."""
    return sorted(_urls_por_ano(), reverse=True)


def anexar_pld(df_coff: pd.DataFrame, df_pld: pd.DataFrame | None) -> pd.DataFrame:
    """Junta o PLD horário ao dataframe de constrained-off por instante.

    O dataset do ONS é semi-horário (00:00 e 00:30); ambas as amostras da
    mesma hora recebem o PLD daquela hora cheia.

    Se ``df_pld`` for None, a coluna ``pld_horario`` fica nula e o impacto
    financeiro não é computado — a energia frustrada em MWh continua
    disponível normalmente.
    """
    df = df_coff.copy()
    if df_pld is None or df_pld.empty:
        df["pld_horario"] = pd.NA
        return df
    df["_hora"] = df["din_instante"].dt.floor("h")
    pld = df_pld.rename(columns={"din_instante": "_hora"})
    return df.merge(pld, on="_hora", how="left").drop(columns="_hora")
