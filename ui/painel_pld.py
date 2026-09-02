"""Painel de Preço Horário (PLD) — submercado Nordeste.

Reproduz, com os dados abertos da CCEE, a leitura do Painel de Preços da
própria CCEE (https://www.ccee.org.br/precos/painel-precos): o preço da
hora corrente em destaque, a curva das 24 horas do dia escolhido e as
estatísticas do dia (máxima, mínima, média).

O PLD é publicado com um dia de antecedência, então o seletor oferece
Ontem / Hoje / Amanhã conforme a cobertura da série.
"""

from datetime import date, datetime, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core.ccee_pld import baixar_pld_nordeste

_SLATE = "#3b5166"
_TERRACOTA = "#c17a4f"
_CINZA = "#5b6b74"
_VERDE = "#3f7d5c"
_VERMELHO = "#b4534b"

_NOMES_MES = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]
_DIAS_SEMANA = [
    "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
    "sexta-feira", "sábado", "domingo",
]


def _reais(valor: float, casas: int = 2) -> str:
    """Formata em reais no padrão brasileiro (1.234,56)."""
    return f"{valor:,.{casas}f}".replace(",", "§").replace(".", ",").replace("§", ".")


def _rotulo_data(d: date) -> str:
    return f"{_DIAS_SEMANA[d.weekday()]}, {d.day} de {_NOMES_MES[d.month - 1]} de {d.year}"


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def _serie_nordeste(anos: tuple[int, ...]) -> pd.DataFrame | None:
    """Concatena a série de PLD dos anos informados."""
    partes = [df for ano in anos if (df := baixar_pld_nordeste(ano)) is not None]
    if not partes:
        return None
    return (
        pd.concat(partes)
        .drop_duplicates(subset="din_instante")
        .sort_values("din_instante")
        .reset_index(drop=True)
    )


def _grafico_dia(dia: pd.DataFrame, hora_atual: int | None) -> go.Figure:
    """Curva das 24 horas, no estilo do painel da CCEE."""
    horas = dia["din_instante"].dt.hour
    precos = dia["pld_horario"]
    media = float(precos.mean())

    fig = go.Figure()
    fig.add_hline(
        y=media, line=dict(color=_CINZA, width=1, dash="dot"),
        annotation_text=f"média R$ {_reais(media)}",
        annotation_position="top left",
        annotation_font=dict(size=11, color=_CINZA),
    )
    fig.add_trace(go.Scatter(
        x=horas, y=precos, mode="lines+markers",
        line=dict(color=_SLATE, width=2.5, shape="spline", smoothing=0.6),
        marker=dict(size=6, color=_SLATE),
        fill="tozeroy", fillcolor="rgba(59, 81, 102, 0.10)",
        hovertemplate="%{x:02d}h<br><b>R$ %{y:.2f}</b>/MWh<extra></extra>",
        name="PLD",
    ))

    if hora_atual is not None and hora_atual in set(horas):
        preco_agora = float(precos[horas == hora_atual].iloc[0])
        fig.add_trace(go.Scatter(
            x=[hora_atual], y=[preco_agora], mode="markers",
            marker=dict(size=15, color=_TERRACOTA, line=dict(color="white", width=2)),
            hovertemplate=f"agora ({hora_atual:02d}h)<br><b>R$ %{{y:.2f}}</b>/MWh<extra></extra>",
            name="agora", showlegend=False,
        ))

    fig.update_layout(
        height=340,
        margin=dict(l=10, r=10, t=30, b=10),
        showlegend=False,
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        hovermode="x unified",
        xaxis=dict(
            title="", tickmode="array",
            tickvals=list(range(0, 24, 2)),
            ticktext=[f"{h:02d}" for h in range(0, 24, 2)],
            showgrid=False, zeroline=False,
        ),
        yaxis=dict(
            title="R$/MWh", gridcolor="#eceef1",
            zeroline=False, rangemode="tozero",
        ),
    )
    return fig


def _grafico_historico(serie: pd.DataFrame, dias: int) -> go.Figure:
    """Média diária dos últimos N dias, com faixa de mínima e máxima."""
    corte = serie["din_instante"].max().normalize() - pd.Timedelta(days=dias - 1)
    recente = serie[serie["din_instante"] >= corte]
    diario = (
        recente.assign(dia=recente["din_instante"].dt.date)
        .groupby("dia")["pld_horario"]
        .agg(["min", "mean", "max"])
        .reset_index()
    )
    dias_x = pd.to_datetime(diario["dia"])

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dias_x, y=diario["max"], mode="lines",
        line=dict(width=0), showlegend=False, hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=dias_x, y=diario["min"], mode="lines",
        line=dict(width=0), fill="tonexty",
        fillcolor="rgba(59, 81, 102, 0.13)",
        name="faixa do dia",
        hovertemplate="mín R$ %{y:.2f}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=dias_x, y=diario["mean"], mode="lines",
        line=dict(color=_SLATE, width=2),
        name="média diária",
        hovertemplate="%{x|%d/%m/%Y}<br><b>R$ %{y:.2f}</b>/MWh<extra></extra>",
    ))
    fig.update_layout(
        height=280,
        margin=dict(l=10, r=10, t=10, b=10),
        showlegend=False,
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        hovermode="x unified",
        xaxis=dict(title="", showgrid=False),
        yaxis=dict(title="R$/MWh", gridcolor="#eceef1", zeroline=False, rangemode="tozero"),
    )
    return fig


def render() -> None:
    st.markdown("## Preço Horário do Dia — Submercado Nordeste")
    st.caption(
        "PLD (Preço de Liquidação das Diferenças) horário · dados abertos da CCEE · "
        "mesma série usada para valorar o impacto financeiro do constrained-off"
    )
    st.divider()

    agora = datetime.now()
    anos = tuple(sorted({agora.year - 1, agora.year}))
    serie = _serie_nordeste(anos)

    if serie is None or serie.empty:
        st.error(
            "Não foi possível obter a série de PLD da CCEE no momento. "
            "Tente novamente mais tarde."
        )
        return

    ultimo = serie["din_instante"].max()
    hoje = agora.date()

    candidatos = [
        ("Ontem", hoje - timedelta(days=1)),
        ("Hoje", hoje),
        ("Amanhã", hoje + timedelta(days=1)),
    ]
    dias_com_dado = set(serie["din_instante"].dt.date)
    opcoes = [(r, d) for r, d in candidatos if d in dias_com_dado]

    if not opcoes:
        # Série não alcança o dia corrente: cai para o último dia publicado.
        opcoes = [("Último dia publicado", ultimo.date())]

    rotulos = [r for r, _ in opcoes]
    padrao = rotulos.index("Hoje") if "Hoje" in rotulos else len(rotulos) - 1

    esquerda, direita = st.columns([1, 2.4])
    with esquerda:
        escolha = st.radio("Dia", rotulos, index=padrao, horizontal=False)
    dia_escolhido = dict(opcoes)[escolha]

    dia = serie[serie["din_instante"].dt.date == dia_escolhido].sort_values("din_instante")
    with direita:
        st.markdown(f"**{_rotulo_data(dia_escolhido)}**")
        st.caption(
            f"Série da CCEE atualizada até {ultimo:%d/%m/%Y %Hh} · "
            f"{len(dia)} horas publicadas neste dia"
        )

    # --- Preço em destaque: a hora corrente, se o dia escolhido for hoje ---
    eh_hoje = dia_escolhido == hoje
    hora_ref = agora.hour if eh_hoje else None
    linha_ref = dia[dia["din_instante"].dt.hour == hora_ref] if hora_ref is not None else dia.iloc[0:0]

    if not linha_ref.empty:
        preco_agora = float(linha_ref["pld_horario"].iloc[0])
        anterior = dia[dia["din_instante"].dt.hour == hora_ref - 1]
        delta = (
            preco_agora - float(anterior["pld_horario"].iloc[0])
            if not anterior.empty else None
        )
        rotulo_destaque = f"PLD agora ({hora_ref:02d}h)"
    else:
        preco_agora = float(dia["pld_horario"].mean())
        delta = None
        rotulo_destaque = "PLD médio do dia"

    maxima = float(dia["pld_horario"].max())
    minima = float(dia["pld_horario"].min())
    media = float(dia["pld_horario"].mean())
    hora_max = int(dia.loc[dia["pld_horario"].idxmax(), "din_instante"].hour)
    hora_min = int(dia.loc[dia["pld_horario"].idxmin(), "din_instante"].hour)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        rotulo_destaque,
        f"R$ {_reais(preco_agora)}",
        delta=f"{_reais(delta)} vs. hora anterior" if delta is not None else None,
        delta_color="inverse",
        help="Preço de liquidação da energia no submercado Nordeste, em R$/MWh.",
    )
    c2.metric("Máxima do dia", f"R$ {_reais(maxima)}", delta=f"às {hora_max:02d}h", delta_color="off")
    c3.metric("Mínima do dia", f"R$ {_reais(minima)}", delta=f"às {hora_min:02d}h", delta_color="off")
    c4.metric("Média do dia", f"R$ {_reais(media)}")

    st.plotly_chart(_grafico_dia(dia, hora_ref), use_container_width=True)

    st.divider()
    st.markdown("#### Evolução recente")
    janela = st.radio(
        "Janela", [30, 90, 180, 365],
        index=1, horizontal=True,
        format_func=lambda d: f"{d} dias",
        label_visibility="collapsed",
    )
    st.plotly_chart(_grafico_historico(serie, janela), use_container_width=True)
    st.caption(
        "Linha: média diária do PLD horário. Faixa: mínima e máxima do dia. "
        "O piso e o teto do PLD são fixados anualmente pela ANEEL."
    )

    with st.expander("Tabela horária do dia"):
        tabela = dia.assign(
            Hora=dia["din_instante"].dt.strftime("%H:00"),
        )[["Hora", "pld_horario"]].rename(columns={"pld_horario": "PLD (R$/MWh)"})
        st.dataframe(tabela, width="stretch", hide_index=True)
