"""Construção das figuras Plotly do mapa de conjuntos eólicos."""

import pandas as pd
import plotly.graph_objects as go

CENTRO_RN = {"lat": -5.6, "lon": -36.4}
ZOOM_INICIAL = 7.2

_COR_CONJUNTOS = "#1f77b4"
_COR_USINAS = "#ff7f0e"


def _tamanho_marcador(qtd_usinas: pd.Series) -> pd.Series:
    return (qtd_usinas * 2.2 + 10).clip(upper=40)


def build_map(df_conjuntos: pd.DataFrame, df_usinas: pd.DataFrame | None = None, mostrar_usinas: bool = False) -> go.Figure:
    fig = go.Figure()

    fig.add_trace(
        go.Scattermapbox(
            lat=df_conjuntos["latitude"],
            lon=df_conjuntos["longitude"],
            mode="markers",
            marker=dict(size=_tamanho_marcador(df_conjuntos["qtd_usinas"]), color=_COR_CONJUNTOS, opacity=0.85),
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
                marker=dict(size=8, color=_COR_USINAS, opacity=0.8),
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
        mapbox=dict(style="open-street-map", center=CENTRO_RN, zoom=ZOOM_INICIAL),
        margin=dict(l=0, r=0, t=0, b=0),
        legend=dict(orientation="h", yanchor="bottom", y=0.01, xanchor="left", x=0.01, bgcolor="rgba(255,255,255,0.7)"),
        height=650,
    )
    return fig
