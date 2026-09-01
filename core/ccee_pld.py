"""Download do preço horário de referência do subsistema Nordeste.

Fonte: **CMO Semi-Horário do ONS** (dados abertos, S3 público), dataset
`cmo-semi-horario` — recurso anual em CSV.

Histórico: a fonte original era o PLD horário da CCEE
(`dadosabertos.ccee.org.br`), mas o portal público da CCEE passou a
responder 403 "Bloqueio Manutenção" de forma persistente (não é filtro de
bot — o domínio inteiro fica fora do ar para acesso automatizado). Migrado
para o CMO Semi-Horário do ONS, que vem do mesmo S3 que já serve o
constrained-off e não tem bloqueio.

O CMO (Custo Marginal de Operação) é o preço que origina o PLD — o PLD é o
CMO com aplicação de teto e piso regulatórios (Resolução ANEEL). Para o
período recente os dois praticamente coincidem, exceto quando o CMO
ultrapassa os limites regulatórios. A coluna resultante mantém o nome
`pld_horario` por compatibilidade com o restante do código.

A interface pública (`baixar_pld_nordeste`, `anexar_pld`) é preservada,
inclusive o retorno `None` em caso de falha, para manter o fallback
gracioso em `ui/energia_frustrada.py` (exibe MWh sem impacto financeiro).
"""

import io

import pandas as pd
import requests
import streamlit as st

_URL_CMO = (
    "https://ons-aws-prod-opendata.s3.amazonaws.com/dataset/"
    "cmo_tm/CMO_SEMIHORARIO_{ano}.csv"
)
_SUBSISTEMA_NORDESTE = "NE"


@st.cache_data(ttl=6 * 3600, show_spinner="Baixando CMO horário (ONS)...")
def baixar_pld_nordeste(ano: int) -> pd.DataFrame | None:
    """Baixa o CMO semi-horário do subsistema Nordeste para o ano informado
    e agrega para base horária (média das duas meias-horas).

    Retorna None (em vez de lançar exceção) se o download falhar por
    qualquer motivo — arquivo do ano ainda não publicado, formato
    inesperado, timeout etc.
    """
    try:
        resposta = requests.get(_URL_CMO.format(ano=ano), timeout=60)
        resposta.raise_for_status()
        df = pd.read_csv(io.BytesIO(resposta.content), sep=";", decimal=".")
        df.columns = [c.strip().lower() for c in df.columns]
        if not {"id_subsistema", "din_instante", "val_cmo"}.issubset(df.columns):
            return None

        df = df[df["id_subsistema"] == _SUBSISTEMA_NORDESTE].copy()
        df["din_instante"] = pd.to_datetime(df["din_instante"])
        df["pld_horario"] = pd.to_numeric(df["val_cmo"], errors="coerce")

        # Semi-horário (00:00 e 00:30) -> horário: média das duas amostras.
        df["_hora"] = df["din_instante"].dt.floor("h")
        horario = (
            df.groupby("_hora", as_index=False)["pld_horario"]
            .mean()
            .rename(columns={"_hora": "din_instante"})
        )
        return horario.dropna()
    except Exception:
        return None


def anexar_pld(df_coff: pd.DataFrame, df_pld: pd.DataFrame | None) -> pd.DataFrame:
    """Junta o preço horário ao dataframe de constrained-off por instante.

    Se df_pld for None, retorna df_coff com a coluna 'pld_horario' ausente
    (NaN) — o impacto financeiro fica indisponível, mas a energia frustrada
    em MWh continua normalmente.
    """
    df = df_coff.copy()
    if df_pld is None or df_pld.empty:
        df["pld_horario"] = pd.NA
        return df
    df["_hora"] = df["din_instante"].dt.floor("h")
    pld = df_pld.rename(columns={"din_instante": "_hora"})
    return df.merge(pld, on="_hora", how="left").drop(columns="_hora")
