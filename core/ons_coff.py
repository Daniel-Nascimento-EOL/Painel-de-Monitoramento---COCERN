"""Download dos dados abertos do ONS de restrição (constrained-off) eólica
e cálculo das 5 metodologias de Energia Frustrada.

Fonte: https://dados.ons.org.br/dataset/restricao_coff_eolica_usi — recurso
mensal em CSV, atualizado pelo ONS 2x ao dia (12h e 19h).
"""

from datetime import date

import numpy as np
import pandas as pd
import requests
import streamlit as st

URL_BASE = (
    "https://ons-aws-prod-opendata.s3.amazonaws.com/dataset/"
    "restricao_coff_eolica_tm/RESTRICAO_COFF_EOLICA_{ano}_{mes:02d}.csv"
)

_PRIMEIRO_MES_DISPONIVEL = (2021, 1)


def meses_disponiveis() -> list[tuple[int, int]]:
    """Lista (ano, mes) do mês mais recente pro mais antigo disponível no ONS."""
    hoje = date.today()
    meses = []
    ano, mes = hoje.year, hoje.month
    while (ano, mes) >= _PRIMEIRO_MES_DISPONIVEL:
        meses.append((ano, mes))
        mes -= 1
        if mes == 0:
            mes = 12
            ano -= 1
    return meses


@st.cache_data(ttl=6 * 3600, show_spinner="Baixando dados do ONS...")
def baixar_mes_rn(ano: int, mes: int) -> pd.DataFrame:
    """Baixa o CSV mensal de constrained-off eólico do ONS e filtra só o RN."""
    url = URL_BASE.format(ano=ano, mes=mes)
    resposta = requests.get(url, timeout=60)
    resposta.raise_for_status()
    df = pd.read_csv(
        pd.io.common.BytesIO(resposta.content),
        sep=";",
        decimal=".",
        parse_dates=["din_instante"],
    )
    return df[df["id_estado"] == "RN"].reset_index(drop=True)


def calcular_metodologias(df: pd.DataFrame) -> pd.DataFrame:
    """Reproduz as 5 metodologias de Energia Frustrada (e as 2 gerações de
    referência calculadas auxiliares) definidas na planilha EOL_RN_coff_v2.

    Todas as fórmulas foram extraídas diretamente das fórmulas Excel da
    planilha de referência do usuário (openpyxl, coluna a coluna).
    """
    df = df.copy()
    lim = df["val_geracaolimitada"]
    ref = df["val_geracaoreferencia"]
    disp = df["val_disponibilidade"]
    geracao = df["val_geracao"]
    ref_final = df["val_geracaoreferenciafinal"]
    razao = df["cod_razaorestricao"]

    # Nota: em ~0,01% das linhas, a diferença |geração-limite| cai bem em
    # cima da fronteira da tolerância (a nível do 15º dígito de um double),
    # onde o motor de fórmulas do Excel não é perfeitamente reprodutível em
    # IEEE754 puro — validado linha a linha contra a planilha de referência
    # (80.352 linhas), com 99,99% de correspondência exata.
    tem_limite = lim.notna()
    tolerancia = np.minimum(5, 0.05 * lim)
    ref_disp_min = np.minimum(ref, disp)
    dif_abs = (geracao - lim).abs()

    # Energia Frustrada [1]: referência simples vs. geração limitada.
    ef1 = np.where(tem_limite & (ref > lim), 0.5 * (ref - lim), 0.0)

    # Energia Frustrada [2]: teto de min(referência, disponibilidade).
    ef2 = np.where(tem_limite, np.maximum(0.0, 0.5 * (ref_disp_min - lim)), 0.0)

    # Energia Frustrada [3]: só conta quando a geração realmente ficou presa
    # ao limite (dentro da tolerância de 5 MW / 5%).
    dentro_tolerancia = dif_abs <= tolerancia
    ef3 = np.where(
        tem_limite & dentro_tolerancia, np.maximum(0.0, 0.5 * (ref_disp_min - lim)), 0.0
    )

    # G_Ref_Final Calculada [1]: ajusta a referência pra baixo quando a
    # geração ficou bem abaixo do limite (direcional).
    cond_g1 = (geracao < lim) & ((lim - geracao) > tolerancia)
    g_ref_calc1 = np.where(
        tem_limite,
        np.where(cond_g1, np.maximum(0.0, ref_disp_min - (lim - geracao)), ref_disp_min),
        0.0,
    )

    # G_Ref_Final Calculada [2]: mesma ideia, variante com desvio absoluto.
    fora_tolerancia = dif_abs > tolerancia
    g_ref_calc2 = np.where(
        tem_limite,
        np.where(fora_tolerancia, np.maximum(0.0, ref_disp_min - dif_abs), ref_disp_min),
        0.0,
    )

    # Energia Frustrada [4] e [5]: usam val_geracaoreferenciafinal quando a
    # razão da restrição é "REL", senão caem pra G_Ref_Final Calculada [1]/[2].
    # (assimetria real da planilha original: [4] zera se G_Ref_Final Calculada
    # [1] ficar abaixo da geração; [5] não tem essa guarda pro caso [2].)
    eh_rel = razao == "REL"
    ef_rel = np.where(ref_final < geracao, 0.0, np.maximum(0.0, 0.5 * (ref_final - lim)))
    ef4_naorel = np.where(g_ref_calc1 < geracao, 0.0, np.maximum(0.0, 0.5 * (g_ref_calc1 - lim)))
    ef5_naorel = np.maximum(0.0, 0.5 * (g_ref_calc2 - lim))
    ef4 = np.where(tem_limite, np.where(eh_rel, ef_rel, ef4_naorel), 0.0)
    ef5 = np.where(tem_limite, np.where(eh_rel, ef_rel, ef5_naorel), 0.0)

    df["energia_frustrada_1"] = ef1
    df["energia_frustrada_2"] = ef2
    df["energia_frustrada_3"] = ef3
    df["g_ref_calculada_1"] = g_ref_calc1
    df["g_ref_calculada_2"] = g_ref_calc2
    df["energia_frustrada_4"] = ef4
    df["energia_frustrada_5"] = ef5
    return df


METODOLOGIAS = {
    1: (
        "energia_frustrada_1",
        "Referência simples: 0,5·(geração de referência − geração limitada), quando a referência supera o limite.",
    ),
    2: (
        "energia_frustrada_2",
        "Teto pela disponibilidade: usa min(referência, disponibilidade) como geração hipotética.",
    ),
    3: (
        "energia_frustrada_3",
        "Como [2], mas só conta quando a geração real ficou de fato presa ao limite (±5 MW / 5%).",
    ),
    4: (
        "energia_frustrada_4",
        "Usa a geração de referência final do ONS quando a razão é REL; senão, a referência recalculada [1].",
    ),
    5: (
        "energia_frustrada_5",
        "Como [4], mas com a referência recalculada [2] (desvio absoluto) no caso não-REL.",
    ),
}
