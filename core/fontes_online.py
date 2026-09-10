"""Consulta às fontes de dados abertos (ONS, ANEEL) que alimentam o mapa.

Este módulo **não é importado pelo aplicativo**. O painel lê exclusivamente
os arquivos versionados em ``data/`` (ver ``core/ons_rede.py``,
``core/aneel_siga.py`` e ``core/data_loader.py``). As funções aqui existem
apenas para o script ``scripts/atualizar_dados_mapa.py``, que baixa os
cadastros, valida e regrava esses arquivos — deixando-os prontos para
conferência e ``commit``.

Nenhuma dependência de Streamlit: o script roda fora do runtime.

Fontes (S3 público do ONS e portal de dados abertos da ANEEL):
- subestações da Rede de Operação (tensão base >= 69 kV, com lat/long);
- linhas de transmissão da Rede de Operação (sem geometria — só de/para);
- SIGA da ANEEL (potência por empreendimento de geração, chave ``CodCEG``).
"""

from __future__ import annotations

import pandas as pd
import requests

from core.ons_rede import (
    _chave_subestacao_ons,
    _CHAVES_SEMPRE_MANTIDAS,
    _e_transmissora,
    nome_exibicao_subestacao,
)

_URL_SUBESTACOES = (
    "https://ons-aws-prod-opendata.s3.amazonaws.com/dataset/subestacao/SUBESTACAO.csv"
)
_URL_LINHAS = (
    "https://ons-aws-prod-opendata.s3.amazonaws.com/dataset/"
    "linha_transmissao/LINHA_TRANSMISSAO.csv"
)
_URL_SIGA = (
    "https://dadosabertos.aneel.gov.br/dataset/6d90b77c-c5f5-4d81-bdec-7bc619494bb9/"
    "resource/2f65a1b0-19b8-4360-8238-b34ab4693d55/download/"
    "siga-empreendimentos-geracao-diario.csv"
)

_NOME_ESTADO_RN = "RIO GRANDE DO NORTE"


def baixar_subestacoes_rn() -> pd.DataFrame:
    """Baixa o cadastro de subestações do ONS e filtra o Rio Grande do Norte.

    Retorna uma linha por subestação (agregada sobre os níveis de tensão),
    já restrita às subestações da rede de transmissão (as coletoras das
    próprias SPE são descartadas — ver ``core/ons_rede._e_transmissora``).
    Colunas: ``chave_subestacao``, ``nom_subestacao``, ``agente_principal``,
    ``latitude``, ``longitude``, ``tensao_max_kv``, ``tensoes_kv``,
    ``nome_exibicao``.
    """
    resposta = requests.get(_URL_SUBESTACOES, timeout=60)
    resposta.raise_for_status()
    df = pd.read_csv(pd.io.common.BytesIO(resposta.content), sep=";", decimal=".")
    df["chave_subestacao"] = df["nom_subestacao"].apply(_chave_subestacao_ons)
    # Mantém o RN e, além dele, as SE de outros estados que são ponto de
    # conexão de conjuntos do RN (Riachão II e Santa Luzia II, na PB) — sem
    # elas o cadastro fica sem a tensão e o agente dessas subestações, que
    # aparecem no mapa porque um conjunto do RN se liga a elas.
    df = df[
        (df["id_estado"] == "RN")
        | df["chave_subestacao"].isin(_CHAVES_SEMPRE_MANTIDAS)
    ].copy()
    df["val_niveltensao"] = pd.to_numeric(df["val_niveltensao"], errors="coerce")

    agregado = (
        df.groupby("chave_subestacao")
        .agg(
            nom_subestacao=("nom_subestacao", "first"),
            agente_principal=("nom_agente_principal", "first"),
            latitude=("val_latitude", "first"),
            longitude=("val_longitude", "first"),
            tensao_max_kv=("val_niveltensao", "max"),
            tensoes_kv=(
                "val_niveltensao",
                lambda s: ";".join(str(int(v)) for v in sorted({int(x) for x in s.dropna()})),
            ),
        )
        .reset_index()
    )
    manter = agregado["agente_principal"].apply(_e_transmissora) | agregado[
        "chave_subestacao"
    ].isin(_CHAVES_SEMPRE_MANTIDAS)
    agregado = agregado[manter].copy()
    agregado["nome_exibicao"] = agregado["nom_subestacao"].apply(nome_exibicao_subestacao)
    return agregado.reset_index(drop=True)


def baixar_linhas_rn() -> pd.DataFrame:
    """Baixa o cadastro de linhas de transmissão do ONS e mantém as que tocam
    o RN em qualquer terminal e estão ativas (sem data de desativação).

    Sem geometria: cada linha tem apenas ``subestacao_de`` / ``subestacao_para``
    (nomes), tensão (kV), tipo de rede e comprimento (km).
    """
    resposta = requests.get(_URL_LINHAS, timeout=60)
    resposta.raise_for_status()
    df = pd.read_csv(pd.io.common.BytesIO(resposta.content), sep=";", decimal=".")

    toca_rn = (df["nom_estado_de"] == _NOME_ESTADO_RN) | (
        df["nom_estado_para"] == _NOME_ESTADO_RN
    )
    ativa = df["dat_desativacao"].isna() | (
        df["dat_desativacao"].astype(str).str.strip() == ""
    )
    df = df[toca_rn & ativa].copy()

    df["subestacao_de"] = df["nom_subestacao_de"].str.strip()
    df["subestacao_para"] = df["nom_subestacao_para"].str.strip()
    df["chave_de"] = df["subestacao_de"].apply(_chave_subestacao_ons)
    df["chave_para"] = df["subestacao_para"].apply(_chave_subestacao_ons)
    df["tensao_kv"] = pd.to_numeric(df["val_niveltensao_kv"], errors="coerce")
    df["tipo_rede"] = df["nom_tipoderede"].str.strip().str.title()
    df["comprimento_km"] = pd.to_numeric(df["val_comprimento"], errors="coerce")
    df["agente"] = df["nom_agenteproprietario"].str.strip()

    colunas = [
        "subestacao_de", "subestacao_para", "chave_de", "chave_para",
        "tensao_kv", "tipo_rede", "comprimento_km", "agente",
    ]
    return df[colunas].drop_duplicates().reset_index(drop=True)


def _kw_para_mw(valor: object) -> float:
    """'49300,00' (kW, decimal com vírgula) -> 49.3 (MW)."""
    if pd.isna(valor):
        return float("nan")
    texto = str(valor).strip().replace(".", "").replace(",", ".")
    try:
        return float(texto) / 1000.0
    except ValueError:
        return float("nan")


def baixar_potencias_eol_rn() -> pd.DataFrame:
    """Baixa o SIGA da ANEEL, filtra eólicas do RN e devolve potência por CEG.

    Colunas: ``ceg``, ``potencia_outorgada_mw``, ``potencia_fiscalizada_mw``,
    ``fase_usina``, ``proprietario``.
    """
    resposta = requests.get(_URL_SIGA, timeout=90)
    resposta.raise_for_status()
    df = pd.read_csv(
        pd.io.common.BytesIO(resposta.content),
        sep=";",
        dtype=str,
        encoding="utf-8",
    )
    df = df[(df["SigUFPrincipal"] == "RN") & (df["SigTipoGeracao"] == "EOL")].copy()

    saida = pd.DataFrame(
        {
            "ceg": df["CodCEG"].str.strip(),
            "potencia_outorgada_mw": df["MdaPotenciaOutorgadaKw"].apply(_kw_para_mw),
            "potencia_fiscalizada_mw": df["MdaPotenciaFiscalizadaKw"].apply(_kw_para_mw),
            "fase_usina": df["DscFaseUsina"].str.strip(),
            "proprietario": df["DscPropriRegimePariticipacao"].str.strip(),
        }
    )
    return (
        saida.dropna(subset=["ceg"]).drop_duplicates(subset=["ceg"]).reset_index(drop=True)
    )
