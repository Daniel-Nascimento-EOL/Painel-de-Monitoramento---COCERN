"""Construção das figuras Plotly do mapa de conjuntos eólicos."""

import pandas as pd
import plotly.graph_objects as go

CENTRO_RN = {"lat": -5.6, "lon": -36.4}
ZOOM_INICIAL = 7.2

_COR_CONJUNTOS = "#3b5166"
_COR_USINAS = "#c17a4f"
_FONTE = "Georgia, 'Times New Roman', serif"


def _tamanho_marcador(qtd_usinas: pd.Series) -> pd.Series:
    return (qtd_usinas * 2.2 + 10).clip(upper=40)


def build_map(df_conjuntos: pd.DataFrame, df_usinas: pd.DataFrame | None = None, mostrar_usinas: bool = False) -> go.Figure:
    fig = go.Figure()

    fig.add_trace(
        go.Scattermapbox(
            lat=df_conjuntos["latitude"],
            lon=df_conjuntos["longitude"],
            mode="markers",
            marker=dict(size=_tamanho_marcador(df_conjuntos["qtd_usinas"]), color=_COR_CONJUNTOS, opacity=0.88),
            text=df_conjuntos["conjunto"],
            customdata=df_conjuntos[["municipios", "qtd_usinas"]],
            hovertemplate=(
                "<b>%{text}</b><br>"
                "Município(s): %{customdata[0]}<br>"
                "Qtd. usinas: %{customdata[1]}"
                "<extra></extra>"
            ),
            name="Conjuntos",
        )
    )

    if mostrar_usinas and df_usinas is not None and not df_usinas.empty:
        fig.add_trace(
            go.Scattermapbox(
                lat=df_usinas["latitude"],
                lon=df_usinas["longitude"],
                mode="markers",
                marker=dict(size=7, color=_COR_USINAS, opacity=0.85),
                text=df_usinas["usina"],
                customdata=df_usinas[["conjunto", "ceg", "municipios"]],
                hovertemplate=(
                    "<b>%{text}</b><br>"
                    "Conjunto: %{customdata[0]}<br>"
                    "CEG: %{customdata[1]}<br>"
                    "Município(s): %{customdata[2]}"
                    "<extra></extra>"
                ),
                name="Usinas",
            )
        )

    fig.update_layout(
        mapbox=dict(style="carto-positron", center=CENTRO_RN, zoom=ZOOM_INICIAL),
        margin=dict(l=0, r=0, t=0, b=0),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=0.02,
            xanchor="left",
            x=0.02,
            bgcolor="rgba(255,255,255,0.9)",
            bordercolor="#e5e7eb",
            borderwidth=1,
            font=dict(size=11, color="#1f2933"),
        ),
        hoverlabel=dict(bgcolor="white", bordercolor="#3b5166", font=dict(family=_FONTE, size=12, color="#1f2933")),
        height=650,
    )
    return fig
