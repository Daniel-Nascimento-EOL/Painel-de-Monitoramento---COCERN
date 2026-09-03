"""Cache em disco do constrained-off agregado por conjunto e mês.

Problema
--------
Cada mês de constrained-off do ONS é um CSV do Brasil inteiro (dezenas de
MB). Compor o acumulado de um ano exige baixar e processar um arquivo por
mês — minutos no primeiro acesso. O ``@st.cache_data`` só vive na memória do
processo, então esse custo se repete a cada reinício (no Streamlit Community
Cloud, com frequência).

Solução
-------
Como o CSV de um mês fechado é imutável, o agregado **por conjunto** daquele
mês também é. Este módulo persiste esse agregado em Parquet
(``data/cache_coff/coff_{ano}_{mes:02d}.parquet``): 54 linhas por mês, uma por
conjunto, com as 5 metodologias em MWh e o impacto financeiro correspondente
em R$ — cerca de 30 KB por ano, versionável no repositório.

O que **não** é persistido: os dados semi-horários brutos (80 mil linhas/mês)
e os meses ainda sujeitos a revisão (ver ``_DIAS_ATE_CONSOLIDAR``).

Por que gravar o impacto financeiro junto, e não só os MWh
-----------------------------------------------------------
O impacto tem de ser somado hora a hora (``energia × PLD daquela hora``). A
energia frustrada se concentra justamente nas horas de PLD baixo, então
recompor o valor depois, multiplicando o total de MWh por um PLD médio,
superestimaria o prejuízo — o produto das médias não é a média dos produtos.

Invalidação
-----------
Cada arquivo guarda ``VERSAO_AGREGADO`` no seu metadata. Ao alterar as
fórmulas de ``core/ons_coff.py::calcular_metodologias`` (ou a forma como o
PLD é aplicado), **incremente essa constante**: todo Parquet gravado com
versão anterior passa a ser ignorado e recalculado, em vez de servir um
número desatualizado indefinidamente.

O cache se preenche sozinho conforme o painel é usado; o script
``scripts/atualizar_cache_coff.py`` apenas o pré-aquece antes de um deploy.
"""

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import streamlit as st

from core.ons_coff import baixar_mes_rn, calcular_metodologias, meses_disponiveis

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache_coff"

# Versão do esquema/semântica do agregado. Incrementar sempre que mudar as
# fórmulas das metodologias, o conjunto de colunas gravadas ou a forma de
# aplicar o PLD — arquivos de versão anterior são descartados e recalculados.
VERSAO_AGREGADO = 1

# Um mês só é considerado definitivo depois desta folga a partir do seu
# encerramento: o ONS ainda revisa medições e a CCEE reprocessa o PLD nos
# primeiros dias do mês seguinte. Antes disso o mês é recalculado ao vivo
# (com o cache de sessão do Streamlit) e não vai para o disco.
_DIAS_ATE_CONSOLIDAR = 15

COLUNAS_ENERGIA = [f"energia_frustrada_{n}" for n in range(1, 6)]
COLUNAS_IMPACTO = [f"impacto_financeiro_{n}" for n in range(1, 6)]
COLUNAS_AGREGADO = COLUNAS_ENERGIA + COLUNAS_IMPACTO


def _fim_do_mes(ano: int, mes: int) -> date:
    return date(ano + (mes == 12), mes % 12 + 1, 1) - timedelta(days=1)


def mes_consolidado(ano: int, mes: int, hoje: date | None = None) -> bool:
    """Indica se o mês já pode ser considerado fechado e persistido."""
    hoje = hoje or date.today()
    return (hoje - _fim_do_mes(ano, mes)).days >= _DIAS_ATE_CONSOLIDAR


def _caminho(ano: int, mes: int) -> Path:
    return CACHE_DIR / f"coff_{ano}_{mes:02d}.parquet"


def _ler_cache(ano: int, mes: int) -> pd.DataFrame | None:
    """Lê o agregado do mês do disco, ou ``None`` se ausente, ilegível ou
    gravado por uma versão anterior do esquema."""
    caminho = _caminho(ano, mes)
    if not caminho.exists():
        return None
    try:
        tabela = pq.read_table(caminho)
        metadados = tabela.schema.metadata or {}
        if int(metadados.get(b"versao_agregado", b"0")) != VERSAO_AGREGADO:
            return None
        return tabela.to_pandas().set_index("id_ons")
    except Exception:
        return None  # arquivo corrompido: recalcula e regrava


def _gravar_cache(ano: int, mes: int, agregado: pd.DataFrame) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tabela = pa.Table.from_pandas(agregado.reset_index(), preserve_index=False)
    tabela = tabela.replace_schema_metadata(
        {
            b"versao_agregado": str(VERSAO_AGREGADO).encode(),
            b"ano": str(ano).encode(),
            b"mes": str(mes).encode(),
        }
    )
    pq.write_table(tabela, _caminho(ano, mes), compression="zstd")


def _agregar_mes(ano: int, mes: int) -> pd.DataFrame:
    """Baixa o mês do ONS, calcula as metodologias, aplica o PLD horário e
    agrega por conjunto (``id_ons``).

    O impacto financeiro é somado hora a hora antes da agregação; quando o
    PLD do período não está disponível, as colunas de impacto ficam nulas e
    apenas a energia em MWh é reportada.
    """
    from core.ccee_pld import anexar_pld, baixar_pld_nordeste

    bruto = baixar_mes_rn(ano, mes)
    if bruto.empty:
        return pd.DataFrame(columns=COLUNAS_AGREGADO).rename_axis("id_ons")

    try:
        pld = baixar_pld_nordeste(ano)
    except Exception:
        pld = None

    df = anexar_pld(calcular_metodologias(bruto), pld)
    preco = pd.to_numeric(df.get("pld_horario"), errors="coerce")
    tem_preco = preco.notna().any()
    for n in range(1, 6):
        df[f"impacto_financeiro_{n}"] = (
            df[f"energia_frustrada_{n}"] * preco if tem_preco else pd.NA
        )
    return df.groupby("id_ons")[COLUNAS_AGREGADO].sum(min_count=1)


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def agregado_do_mes(ano: int, mes: int) -> pd.DataFrame:
    """Agregado por conjunto de um mês, servido do disco quando possível.

    Mês consolidado: lê o Parquet; se não houver (ou for de versão anterior),
    calcula e grava. Mês ainda em revisão: recalcula, sem persistir.
    """
    if mes_consolidado(ano, mes):
        do_disco = _ler_cache(ano, mes)
        if do_disco is not None:
            return do_disco
        agregado = _agregar_mes(ano, mes)
        if not agregado.empty:
            _gravar_cache(ano, mes, agregado)
        return agregado
    return _agregar_mes(ano, mes)


def _meses_no_intervalo(inicio: tuple[int, int], fim: tuple[int, int]) -> list[tuple[int, int]]:
    return sorted(m for m in meses_disponiveis() if inicio <= m <= fim)


@st.cache_data(ttl=6 * 3600, show_spinner="Acumulando constrained-off...")
def acumulado_por_conjunto(
    inicio: tuple[int, int] | None = None,
    fim: tuple[int, int] | None = None,
    somente_consolidados: bool = False,
) -> tuple[pd.DataFrame, list[tuple[int, int]]]:
    """Energia frustrada e impacto financeiro acumulados por conjunto.

    ``inicio``/``fim`` são pares ``(ano, mes)`` inclusivos; omitidos, cobrem
    todo o histórico publicado pelo ONS. Retorna um DataFrame indexado por
    ``id_ons`` com ``energia_frustrada_1..5`` (MWh) e
    ``impacto_financeiro_1..5`` (R$).

    ``somente_consolidados`` restringe a soma aos meses já persistidos em
    disco, evitando baixar ao vivo o mês corrente e o recém-encerrado (que
    custam dezenas de segundos). É o modo usado pela ficha do mapa, onde o
    número serve de panorama; a página Energia Frustrada continua mostrando
    o mês corrente ao vivo.

    Meses cujo download falhar são ignorados, para que uma indisponibilidade
    pontual do ONS não derrube o painel inteiro. O segundo elemento da tupla
    devolvida lista os meses que de fato entraram na soma — devolvido à parte
    porque ``DataFrame.attrs`` não sobrevive à serialização do
    ``@st.cache_data``.
    """
    disponiveis = meses_disponiveis()
    if not disponiveis:
        return pd.DataFrame(columns=COLUNAS_AGREGADO).rename_axis("id_ons"), []

    alvo = _meses_no_intervalo(
        inicio or min(disponiveis), fim or max(disponiveis)
    )
    if somente_consolidados:
        alvo = [m for m in alvo if mes_consolidado(*m)]

    parciais = []
    considerados: list[tuple[int, int]] = []
    for ano, mes in alvo:
        try:
            parcial = agregado_do_mes(ano, mes)
        except Exception:
            continue
        if parcial.empty:
            continue
        parciais.append(parcial)
        considerados.append((ano, mes))

    if not parciais:
        return pd.DataFrame(columns=COLUNAS_AGREGADO).rename_axis("id_ons"), []

    acumulado = pd.concat(parciais).groupby(level=0).sum(min_count=1)
    return acumulado, considerados


def acumulado_do_ano(
    ano: int, somente_consolidados: bool = False
) -> tuple[pd.DataFrame, list[tuple[int, int]]]:
    """Atalho para o acumulado de um ano civil."""
    return acumulado_por_conjunto((ano, 1), (ano, 12), somente_consolidados)
