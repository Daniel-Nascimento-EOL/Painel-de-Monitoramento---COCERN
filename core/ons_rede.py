"""Dados cadastrais de rede do ONS (subestações e linhas de transmissão da
Rede de Operação) do Rio Grande do Norte, **lidos de arquivos versionados
em ``data/rede/``**.

O painel não baixa esses cadastros em tempo de execução. Os arquivos são
gerados fora do runtime por ``scripts/atualizar_dados_mapa.py`` (que usa
``core/fontes_online.py``), conferidos e versionados:

- ``data/rede/subestacoes_rn.csv`` — uma linha por subestação de
  transmissão do RN, com nível de tensão (kV) e lat/long;
- ``data/rede/linhas_transmissao_rn.csv`` — linhas da Rede de Operação que
  tocam o RN (sem geometria — só subestação de/para), com tensão e agente.

Este módulo mantém apenas a leitura desses arquivos e os utilitários de
normalização de nome de subestação, compartilhados com o resto do painel.
"""

import re
import unicodedata
from pathlib import Path

import pandas as pd

_REDE_DIR = Path(__file__).resolve().parent.parent / "data" / "rede"
_ARQ_SUBESTACOES = _REDE_DIR / "subestacoes_rn.csv"
_ARQ_LINHAS = _REDE_DIR / "linhas_transmissao_rn.csv"

# Paleta de tensão — pedido do usuário (áudio 2026-09-09, que corrige a
# atribuição anterior: o 230 kV era verde e o 69 kV não tinha faixa própria).
_COR_POR_TENSAO = {
    69: "#8bc34a",    # 69 kV — verde-limão
    138: "#2a2a2a",   # 138 kV — preto
    230: "#2b62b5",   # 230 kV — azul
    500: "#b5433a",   # 500 kV — vermelho
}
_COR_TENSAO_OUTRA = "#9aa5b1"  # tensão desconhecida ou fora das quatro faixas


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


def _tensoes_para_lista(valor: object) -> list[int]:
    """Converte a coluna ``tensoes_kv`` do CSV ('138;230') para ``[138, 230]``."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return []
    return [int(float(v)) for v in str(valor).split(";") if str(v).strip()]


def ler_subestacoes_rn() -> pd.DataFrame:
    """Lê ``data/rede/subestacoes_rn.csv`` — uma linha por subestação de
    transmissão do RN, com ``tensao_max_kv`` e ``tensoes_kv`` (lista de int).

    O arquivo é gerado por ``scripts/atualizar_dados_mapa.py`` a partir do
    cadastro de subestações do ONS; aqui só é lido e tipado.
    """
    df = pd.read_csv(_ARQ_SUBESTACOES)
    df["tensoes_kv"] = df["tensoes_kv"].apply(_tensoes_para_lista)
    df["tensao_max_kv"] = pd.to_numeric(df["tensao_max_kv"], errors="coerce")
    return df.reset_index(drop=True)


def ler_linhas_rn() -> pd.DataFrame:
    """Lê ``data/rede/linhas_transmissao_rn.csv`` — linhas da Rede de Operação
    que tocam o RN (sem geometria — só subestação de/para), com tensão (kV),
    tipo de rede, comprimento (km) e agente proprietário.

    O arquivo é gerado por ``scripts/atualizar_dados_mapa.py``.
    """
    df = pd.read_csv(_ARQ_LINHAS)
    df["tensao_kv"] = pd.to_numeric(df["tensao_kv"], errors="coerce")
    df["comprimento_km"] = pd.to_numeric(df["comprimento_km"], errors="coerce")
    return df.reset_index(drop=True)


# --- Classificação e nomenclatura das subestações --------------------------
#
# O cadastro do ONS mistura, no mesmo arquivo, dois tipos de subestação:
#
# 1. Subestações da rede de transmissão, operadas por transmissoras
#    (Axia Nordeste, Argo, Taesa...) — são as que interessam ao painel;
# 2. Subestações coletoras dos próprios conjuntos eólicos, cujo agente
#    principal é a SPE da usina (ex.: SE JERUSALEM/Statkraft,
#    SE RIO DO VENTO/CVER, SE ALEGRIA/New Energy). Essas duplicam o
#    marcador do conjunto e foram excluídas do mapa a pedido do usuário.
#
# A distinção é feita pelo agente principal: só entram as subestações cujo
# agente consta em ``_TRANSMISSORAS`` (comparação por prefixo, sem acento e
# em caixa alta, porque o ONS grafa razões sociais variadas — 'ARGO VI',
# 'ARGO ENERGIA TRANSMISSORA' etc.).
#
# A lista traz apenas os agentes efetivamente presentes no cadastro do RN.
# A versão anterior incluía transmissoras que não operam nada no estado
# (Chesf, Eletrobras, Cosern, Energisa, State Grid, ISA, CTEEP, Alupar,
# Neoenergia): nenhuma casava com uma linha sequer do cadastro, e como a
# comparação é por prefixo, cada entrada morta só aumentava a chance de
# deixar passar no futuro uma SE que não deveria entrar. Ao acrescentar uma
# transmissora aqui, conferir antes que ela aparece em
# ``data/rede/subestacoes_rn.csv`` ou ``linhas_transmissao_rn.csv``.
_TRANSMISSORAS = (
    "AXIA",
    "ARGO",
    "TAESA",
    "DUNAS",  # Dunas Transmissão (SE Caraúbas II)
    "LAGOA NOVA",  # SE Currais Novos II — transmissora, apesar do nome de SPE
    "DUNAMIS",  # SE Simplice — idem (operada pela Taesa)
)

# Subestações que estão em bays.xlsx (curadoria do cliente) e devem ser
# mantidas mesmo que o agente principal do ONS não bata com _TRANSMISSORAS.
# RIACHAO 2 e SANTA LUZIA 2 ficam na Paraíba, mas são ponto de conexão de
# conjuntos do RN (Umari em Riachão II; Oeste Seridó / Serra do Tigre em
# Santa Luzia II) — precisam sobreviver ao filtro id_estado == "RN".
_CHAVES_SEMPRE_MANTIDAS = {"CURRAIS NOVOS 2", "SANTA LUZIA 2", "RIACHAO 2"}


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
    "SIMPLICE": "Simplice",
    "TOUROS": "Touros",
}


# Agente proprietário e agente operador de cada subestação de transmissão.
#
# O cadastro do ONS traz apenas o ``agente principal``, quase sempre o nome da
# SPE ('ARGO VI', 'DUNAS', 'LAGOA NOVA', 'DUNAMIS'), que não identifica a marca
# a exibir na ficha. Estes pares vêm da planilha curada pelo usuário
# (``SUBESTACAO.xlsx``, set/2026) e são o que alimenta as logomarcas.
#
# Gotcha da Axia: na maioria das subestações do RN a Axia Nordeste é ao mesmo
# tempo proprietária e operadora — ela não opera ativos de terceiros nem tem os
# seus operados por outrem (informação do usuário, áudio 2026-09-09).
#
# A planilha marcava 'Proprietário: Argo Energia e Agente Operador: Cymi'
# também em João Câmara II e Mossoró II. O usuário confirmou que era
# preenchimento arrastado por engano: o par Argo/Cymi pertencia à Caraúbas II.
# As duas são Axia/Axia — não reintroduzir a Cymi nelas.
_AGENTES_SE = {
    "ACU 2": ("Axia Nordeste", "Axia Nordeste"),
    "ACU 3": ("Argo Energia", "Cymi"),
    "CARAUBAS 2": ("Argo Energia", "Cymi"),
    "CEARA MIRIM 2": ("Axia Nordeste", "Axia Nordeste"),
    "CURRAIS NOVOS 2": ("Taesa", "Taesa"),
    "EXTREMOZ 2": ("Axia Nordeste", "Axia Nordeste"),
    "JANDAIRA 2": ("Argo Energia", "Cymi"),
    "JOAO CAMARA 2": ("Axia Nordeste", "Axia Nordeste"),
    "JOAO CAMARA 3": ("Axia Nordeste", "Axia Nordeste"),
    "LAGOA NOVA 2": ("Axia Nordeste", "Axia Nordeste"),
    "MONTE VERDE": ("Argo Energia", "Cymi"),
    "MOSSORO 2": ("Axia Nordeste", "Axia Nordeste"),
    "MOSSORO 4": ("Axia Nordeste", "Axia Nordeste"),
    "NATAL 2": ("Axia Nordeste", "Axia Nordeste"),
    "NATAL 3": ("Axia Nordeste", "Axia Nordeste"),
    "PARAISO": ("Axia Nordeste", "Axia Nordeste"),
    "SIMPLICE": ("Taesa", "Taesa"),
    "TOUROS": ("Axia Nordeste", "Axia Nordeste"),
    # SE na Paraíba (id_estado == "PB"): não entram no cadastro do ONS
    # filtrado por RN, só existem em bays.xlsx. O agente vem daqui.
    "RIACHAO 2": ("Axia Nordeste", "Axia Nordeste"),
    "SANTA LUZIA 2": ("Neoenergia", "Neoenergia"),
}


def agentes_subestacao(nome: str) -> tuple[str | None, str | None]:
    """Par ``(proprietário, operador)`` da subestação, ou ``(None, None)`` se
    ela não constar do cadastro curado."""
    return _AGENTES_SE.get(_chave_subestacao_ons(nome), (None, None))


# Marca comercial por trás do nome de SPE que o ONS registra em
# ``nom_agente_principal`` nas linhas de transmissão. Mesma limitação do
# cadastro de subestações: a coluna traz a razão social do veículo detentor
# da concessão ('ARGO VI', 'DUNAS'), não a marca a exibir na ficha.
#
# Só entram aqui as SPEs de **transmissoras**, verificadas uma a uma. As SPEs
# de conjunto eólico ('EOL SERIDÓ X', 'SPE2 MUNDO NOVO', 'POTIGUAR B31',
# 'VDSF1'...) ficam de fora de propósito: são o agente da linha de conexão da
# própria usina, cuja marca já aparece na ficha do conjunto, e boa parte nem
# tem logomarca própria. Sem correspondência aqui, a ficha usa o avatar com a
# inicial do nome — comportamento normal para agente sem logomarca.
_MARCA_POR_SPE = {
    "ARGO VI": "Argo Energia",
    "ARGO VIII": "Argo Energia",
    "DUNAS": "Argo Energia",
    "DUNAMIS": "Taesa",
    "LAGOA NOVA": "Taesa",
}


def marca_agente_linha(agente: str | None) -> str | None:
    """Marca comercial do agente da linha, quando o ONS registra a SPE.

    Devolve o próprio nome quando não há correspondência — o agente já é a
    marca (caso de 'AXIA NORDESTE' e 'TAESA') ou é uma SPE de conjunto, que
    a ficha exibe como veio do cadastro.
    """
    if agente is None or (isinstance(agente, float) and pd.isna(agente)):
        return None
    return _MARCA_POR_SPE.get(_sem_acento(str(agente).strip()).upper(), str(agente))


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
    if not bruto.isupper():
        return f"SE {bruto}"
    # ``str.title()`` estragaria o numeral romano ('II' -> 'Ii'); as SE fora do
    # dicionário são as de outros estados, ponta de linha que entra no RN.
    palavras = [
        p if p in _ROMANO_PARA_ARABICO else p.title() for p in bruto.split(" ")
    ]
    return "SE " + " ".join(palavras)
