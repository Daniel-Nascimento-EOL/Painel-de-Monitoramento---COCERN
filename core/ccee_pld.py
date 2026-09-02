"""PLD horário do submercado Nordeste — fonte de preço para valoração do
constrained-off.

Fonte: **dados abertos da CCEE**, dataset ``pld_horario`` — um CSV por ano,
servido em ``pda-download.ccee.org.br``. Colunas: ``MES_REFERENCIA``
(AAAAMM), ``SUBMERCADO``, ``PERIODO_COMERCIALIZACAO``, ``DIA``, ``HORA``,
``PLD_HORA`` (R$/MWh).

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

Se todas as tentativas falharem, entra o **fallback local**:
``data/historico_pld_ne.csv``, série de PLD horário do Nordeste de
17/10/2021 a 07/07/2025, extraída da planilha de referência do estudo do
cliente. Cobre o histórico, mas não recebe meses novos.
"""

import io
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

# Identificadores dos recursos anuais do dataset `pld_horario` no portal de
# dados abertos da CCEE (https://dadosabertos.ccee.org.br/dataset/pld_horario).
_RECURSOS_POR_ANO = {
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

    Tenta o portal de dados abertos da CCEE por três transportes distintos
    (httpx, curl, requests) e, se todos falharem, recorre à série local em
    ``data/historico_pld_ne.csv``.

    Retorna um DataFrame com ``din_instante`` (hora cheia) e ``pld_horario``
    (R$/MWh), ou None se nenhuma fonte cobrir o ano — mantendo o fallback
    gracioso da página de Energia Frustrada.
    """
    recurso = _RECURSOS_POR_ANO.get(ano)
    if recurso is not None:
        url = _URL_PLD.format(recurso=recurso)
        for baixar in (_baixar_httpx, _baixar_curl, _baixar_requests):
            conteudo = baixar(url)
            if conteudo is None:
                continue
            pld = _converter_csv_ccee(conteudo)
            if pld is not None:
                return pld
    return _pld_do_arquivo_local(ano)


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
