"""Download dos dados cadastrais de rede do ONS (subestações e linhas de
transmissão da Rede de Operação), filtrados para o Rio Grande do Norte.

Fontes (mesmo S3 público do ONS já usado em ``core/ons_coff.py``):
- https://dados.ons.org.br/dataset/subestacao — subestações com tensão base
  >= 69 kV, uma linha por nível de tensão, com latitude/longitude.
- https://dados.ons.org.br/dataset/linha-transmissao — linhas da Rede de
  Operação com tensão >= 230 kV (sem geometria — só subestação de/para).

Ambos os arquivos são snapshots (sem histórico), atualizados 2x ao dia
pelo ONS (12h e 19h). Cache ``@st.cache_data(ttl=24h)``.
"""

import re
import unicodedata

import pandas as pd
import requests
import streamlit as st

_URL_SUBESTACOES = (
    "https://ons-aws-prod-opendata.s3.amazonaws.com/dataset/subestacao/SUBESTACAO.csv"
)
_URL_LINHAS = (
    "https://ons-aws-prod-opendata.s3.amazonaws.com/dataset/"
    "linha_transmissao/LINHA_TRANSMISSAO.csv"
)

_NOME_ESTADO_RN = "RIO GRANDE DO NORTE"

# Paleta de tensão — pedido do usuário (áudio 2026-08-22).
_COR_POR_TENSAO = {
    138: "#2a2a2a",   # 138 kV — preto
    230: "#3f8a4f",   # 230 kV — verde
    500: "#b5433a",   # 500 kV — vermelho
}
_COR_TENSAO_OUTRA = "#9aa5b1"  # 69 kV e demais — cinza neutro


def cor_tensao(kv: float | int | None) -> str:
    """Cor da linha/subestação conforme o nível de tensão (kV)."""
    if kv is None or pd.isna(kv):
        return _COR_TENSAO_OUTRA
    return _COR_POR_TENSAO.get(int(round(kv)), _COR_TENSAO_OUTRA)


# Romanos <-> arábicos e abreviações que o ONS usa nos nomes de subestação
# mas a planilha bays.xlsx grafa por extenso (ex.: 'J. CAMARA' vs 'JOAO CAMARA').
_SUBSTITUICOES = [
    (r"\bJ\.\s*CAMARA\b", "JOAO CAMARA"),
    (r"\bCURR\s+NOVOS\b", "CURRAIS NOVOS"),
    (r"\bCOL\s+CUMARU\b", "COLONIA CUMARU"),
    (r"\bSER\s+TIGRE\b", "SERRA TIGRE"),
]
_ROMANO_PARA_ARABICO = {"II": "2", "III": "3", "IV": "4", "V": "5", "VI": "6"}


def _sem_acento(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _chave_subestacao_ons(nome: str) -> str:
    """Normaliza o nome da subestação (do ONS ou da planilha) para uma chave
    de junção comum: sem acento, caixa alta, sem prefixo 'SE ', abreviações
    expandidas e numeral romano convertido para arábico.

    Ex.: 'Ceará Mirim II' e 'CEARA MIRIM 2' -> ambos 'CEARA MIRIM 2'.
         'João Câmara III' e 'J. CAMARA III' -> ambos 'JOAO CAMARA 3'.
    """
    nome = _sem_acento(str(nome).strip()).upper()
    nome = re.sub(r"^SE\s+", "", nome)
    nome = re.sub(r"\s+", " ", nome).strip()
    for padrao, troca in _SUBSTITUICOES:
        nome = re.sub(padrao, troca, nome)
    partes = nome.split(" ")
    if partes and partes[-1] in _ROMANO_PARA_ARABICO:
        partes[-1] = _ROMANO_PARA_ARABICO[partes[-1]]
    return " ".join(partes)


@st.cache_data(ttl=24 * 3600, show_spinner="Baixando subestações do ONS...")
def baixar_subestacoes_rn() -> pd.DataFrame:
    """Baixa o cadastro de subestações do ONS e filtra o RN.

    Retorna uma linha por subestação (agregada sobre os níveis de tensão),
    com a coluna ``tensao_max_kv`` e a lista ``tensoes_kv``.
    """
    resposta = requests.get(_URL_SUBESTACOES, timeout=60)
    resposta.raise_for_status()
    df = pd.read_csv(pd.io.common.BytesIO(resposta.content), sep=";", decimal=".")
    df = df[df["id_estado"] == "RN"].copy()
    df["val_niveltensao"] = pd.to_numeric(df["val_niveltensao"], errors="coerce")
    df["chave_subestacao"] = df["nom_subestacao"].apply(_chave_subestacao_ons)

    agregado = (
        df.groupby("chave_subestacao")
        .agg(
            nom_subestacao=("nom_subestacao", "first"),
            agente_principal=("nom_agente_principal", "first"),
            latitude=("val_latitude", "first"),
            longitude=("val_longitude", "first"),
            tensao_max_kv=("val_niveltensao", "max"),
            tensoes_kv=("val_niveltensao", lambda s: sorted({int(v) for v in s.dropna()})),
        )
        .reset_index()
    )
    # Mantém apenas as subestações da rede de transmissão. As coletoras dos
    # próprios conjuntos eólicos (agente = SPE da usina, ex.: SE JERUSALEM,
    # SE RIO DO VENTO) duplicariam o marcador do conjunto no mapa.
    manter = agregado["agente_principal"].apply(_e_transmissora) | agregado[
        "chave_subestacao"
    ].isin(_CHAVES_SEMPRE_MANTIDAS)
    agregado = agregado[manter].copy()
    agregado["nome_exibicao"] = agregado["nom_subestacao"].apply(nome_exibicao_subestacao)
    return agregado.reset_index(drop=True)


@st.cache_data(ttl=24 * 3600, show_spinner="Baixando linhas de transmissão do ONS...")
def baixar_linhas_rn() -> pd.DataFrame:
    """Baixa o cadastro de linhas de transmissão do ONS e filtra as que tocam
    o RN em qualquer terminal, mantendo só as ativas (sem data de desativação).

    Sem geometria: cada linha tem apenas ``subestacao_de`` / ``subestacao_para``
    (nomes), tensão (kV), tipo de rede e comprimento (km).
    """
    resposta = requests.get(_URL_LINHAS, timeout=60)
    resposta.raise_for_status()
    df = pd.read_csv(pd.io.common.BytesIO(resposta.content), sep=";", decimal=".")

    toca_rn = (df["nom_estado_de"] == _NOME_ESTADO_RN) | (
        df["nom_estado_para"] == _NOME_ESTADO_RN
    )
    ativa = df["dat_desativacao"].isna() | (df["dat_desativacao"].astype(str).str.strip() == "")
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


# --- Classificação e nomenclatura das subestações --------------------------
#
# O cadastro do ONS mistura, no mesmo arquivo, dois tipos de subestação:
#
# 1. Subestações da rede de transmissão, operadas por transmissoras
#    (Axia Nordeste, Argo, Taesa, Neoenergia, Chesf...) — são as que
#    interessam ao painel;
# 2. Subestações coletoras dos próprios conjuntos eólicos, cujo agente
#    principal é a SPE da usina (ex.: SE JERUSALEM/Statkraft,
#    SE RIO DO VENTO/CVER, SE ALEGRIA/New Energy). Essas duplicam o
#    marcador do conjunto e foram excluídas do mapa a pedido do usuário.
#
# A distinção é feita pelo agente principal: só entram as subestações cujo
# agente consta em ``_TRANSMISSORAS`` (comparação por prefixo, sem acento e
# em caixa alta, porque o ONS grafa razões sociais variadas — 'ARGO VI',
# 'ARGO ENERGIA TRANSMISSORA' etc.).
_TRANSMISSORAS = (
    "AXIA",
    "ARGO",
    "TAESA",
    "NEOENERGIA",
    "CHESF",
    "ELETROBRAS",
    "COSERN",
    "NEOENERGIA COSERN",
    "ENERGISA",
    "DUNAS",  # Dunas Transmissão (SE Caraúbas II)
    "STATE GRID",
    "ISA",
    "CTEEP",
    "ALUPAR",
    "LAGOA NOVA",  # SE Currais Novos II — transmissora, apesar do nome de SPE
)

# Subestações que estão em bays.xlsx (curadoria do cliente) e devem ser
# mantidas mesmo que o agente principal do ONS não bata com _TRANSMISSORAS.
_CHAVES_SEMPRE_MANTIDAS = {"CURRAIS NOVOS 2", "SANTA LUZIA 2"}


def _e_transmissora(agente) -> bool:
    """Indica se o agente principal da subestação é uma transmissora."""
    if agente is None or (isinstance(agente, float) and pd.isna(agente)):
        return False
    nome = _sem_acento(str(agente).strip()).upper()
    return any(nome.startswith(t) for t in _TRANSMISSORAS)


# Grafia por extenso das subestações da rede de transmissão. O cadastro do
# ONS usa caixa alta e abreviações ('J. CAMARA III', 'CURR NOVOS II',
# 'MOSSORO IV'); o painel exibe 'SE João Câmara III'. A chave é a normalizada
# por ``_chave_subestacao_ons``.
_NOME_EXIBICAO_SE = {
    "ACU 2": "Açu II",
    "ACU 3": "Açu III",
    "CARAUBAS 2": "Caraúbas II",
    "CEARA MIRIM 2": "Ceará Mirim II",
    "CURRAIS NOVOS 2": "Currais Novos II",
    "EXTREMOZ 2": "Extremoz II",
    "JANDAIRA 2": "Jandaíra II",
    "JOAO CAMARA 2": "João Câmara II",
    "JOAO CAMARA 3": "João Câmara III",
    "LAGOA NOVA 2": "Lagoa Nova II",
    "MONTE VERDE": "Monte Verde",
    "MOSSORO 2": "Mossoró II",
    "MOSSORO 4": "Mossoró IV",
    "NATAL 2": "Natal II",
    "NATAL 3": "Natal III",
    "PARAISO": "Paraíso",
    "RIACHAO 2": "Riachão II",
    "SANTA LUZIA 2": "Santa Luzia II",
    "TOUROS": "Touros",
}


def nome_exibicao_subestacao(nome: str) -> str:
    """Nome da subestação como o painel exibe: 'SE ' + grafia por extenso,
    sem o nível de tensão (que passa a constar apenas na ficha).

    Ex.: 'J. CAMARA III' -> 'SE João Câmara III'; 'CARAUBAS II' -> 'SE Caraúbas II'.
    Nomes fora do dicionário caem em ``str.title()`` sobre a grafia do ONS.
    """
    bruto = re.sub(r"^SE\s+", "", str(nome).strip(), flags=re.IGNORECASE)
    chave = _chave_subestacao_ons(bruto)
    if chave in _NOME_EXIBICAO_SE:
        return f"SE {_NOME_EXIBICAO_SE[chave]}"
    return f"SE {bruto.title()}" if bruto.isupper() else f"SE {bruto}"
