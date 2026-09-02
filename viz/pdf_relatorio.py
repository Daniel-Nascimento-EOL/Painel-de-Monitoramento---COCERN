"""Relatório PDF consolidado de constrained-off por conjunto eólico.

Consome o :class:`core.relatorio_dados.Relatorio` e monta, com ReportLab,
um PDF com capa, sumário executivo do RN e uma seção por conjunto
(cadastro, mini-mapa, subestações/linhas, agregados de energia frustrada,
gráficos e anexo de usinas).
"""

from __future__ import annotations

import io
from datetime import datetime

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from core.ons_coff import METODOLOGIAS
from core.relatorio_dados import Relatorio

_SLATE = colors.HexColor("#3b5166")
_TERRACOTA = colors.HexColor("#c17a4f")
_CINZA = colors.HexColor("#5b6b74")
_CINZA_CLARO = colors.HexColor("#e7e9ec")
# Mesmas cores como strings hex, para o matplotlib.
_MPL_SLATE = "#3b5166"
_MPL_TERRACOTA = "#c17a4f"
_MPL_CINZA = "#5b6b74"
_NOMES_MES = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]

plt.rcParams.update({
    "font.size": 8,
    "axes.edgecolor": "#9aa5b1",
    "axes.labelcolor": "#3a444e",
    "text.color": "#3a444e",
    "xtick.color": "#5b6570",
    "ytick.color": "#5b6570",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "figure.dpi": 150,
})


# --------------------------------------------------------------------------- #
# Estilos                                                                     #
# --------------------------------------------------------------------------- #
def _estilos() -> dict:
    base = getSampleStyleSheet()
    return {
        "titulo": ParagraphStyle("titulo", parent=base["Title"], fontName="Times-Bold",
                                 fontSize=22, textColor=_SLATE, spaceAfter=6),
        "subtitulo": ParagraphStyle("subtitulo", parent=base["Normal"], fontSize=11,
                                    textColor=_CINZA, spaceAfter=2),
        "h1": ParagraphStyle("h1", parent=base["Heading1"], fontName="Times-Bold",
                             fontSize=16, textColor=_SLATE, spaceBefore=4, spaceAfter=8),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontName="Times-Bold",
                             fontSize=12, textColor=_CINZA, spaceBefore=10, spaceAfter=4),
        "corpo": ParagraphStyle("corpo", parent=base["Normal"], fontSize=9,
                                textColor=colors.HexColor("#3a444e"), leading=13),
        "nota": ParagraphStyle("nota", parent=base["Normal"], fontSize=7.5,
                               textColor=colors.HexColor("#8b939c"), leading=10),
        "cel": ParagraphStyle("cel", parent=base["Normal"], fontSize=8, leading=11),
    }


def _rotulo_mes(ano: int, mes: int) -> str:
    return f"{_NOMES_MES[mes - 1].capitalize()}/{ano}"


def _fmt(v: float, casas: int = 0, sufixo: str = "") -> str:
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    return f"{v:,.{casas}f}".replace(",", "§").replace(".", ",").replace("§", ".") + sufixo


# --------------------------------------------------------------------------- #
# Gráficos (matplotlib -> PNG -> reportlab Image)                             #
# --------------------------------------------------------------------------- #
def _fig_para_image(fig, largura_cm: float) -> Image:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    img = Image(buf)
    escala = (largura_cm * cm) / img.drawWidth
    img.drawWidth *= escala
    img.drawHeight *= escala
    return img


def _grafico_serie(serie: pd.DataFrame, metodologia_ref: int, largura_cm: float) -> Image | None:
    if serie is None or serie.empty:
        return None
    fig, ax1 = plt.subplots(figsize=(7.4, 2.6))
    dias = pd.to_datetime(serie["dia"])
    ax1.bar(dias, serie[f"ef{metodologia_ref}_mwh"], color=_MPL_TERRACOTA, width=0.7,
            label=f"Energia frustrada [{metodologia_ref}]")
    ax1.set_ylabel("Energia frustrada (MWh/dia)")
    ax2 = ax1.twinx()
    ax2.plot(dias, serie["geracao_verificada_mwh"], color=_MPL_SLATE, lw=1.3,
             label="Geração verificada")
    ax2.plot(dias, serie["geracao_referencia_mwh"], color=_MPL_CINZA, lw=1.0,
             ls="--", label="Geração de referência")
    ax2.set_ylabel("Geração (MWh/dia)")
    ax2.spines["right"].set_visible(True)
    linhas1, rot1 = ax1.get_legend_handles_labels()
    linhas2, rot2 = ax2.get_legend_handles_labels()
    ax1.legend(linhas1 + linhas2, rot1 + rot2, loc="upper center", ncol=3,
               frameon=False, fontsize=7, bbox_to_anchor=(0.5, 1.22))
    fig.autofmt_xdate()
    return _fig_para_image(fig, largura_cm)


def _grafico_metodologias(ef_mwh: dict, ef_rs: dict, largura_cm: float) -> Image | None:
    if not ef_mwh:
        return None
    fig, ax = plt.subplots(figsize=(7.4, 2.2))
    xs = list(range(1, 6))
    ax.bar([x - 0.0 for x in xs], [ef_mwh[i] for i in xs], color=_MPL_TERRACOTA, width=0.55)
    ax.set_xticks(xs)
    ax.set_xticklabels([f"[{i}]" for i in xs])
    ax.set_ylabel("Energia frustrada (MWh)")
    ax.set_title("Comparativo das metodologias", fontsize=9, color="#3a444e")
    for i in xs:
        ax.text(i, ef_mwh[i], _fmt(ef_mwh[i]), ha="center", va="bottom", fontsize=6.5)
    return _fig_para_image(fig, largura_cm)


def _grafico_duracao(coff: pd.DataFrame, metodologia_ref: int, largura_cm: float) -> Image | None:
    col = METODOLOGIAS[metodologia_ref][0]
    if coff is None or coff.empty or col not in coff:
        return None
    horaria = (coff.assign(h=coff["din_instante"].dt.floor("h"))
               .groupby("h")[col].sum().sort_values(ascending=False).reset_index(drop=True))
    if horaria.empty or horaria.max() <= 0:
        return None
    fig, ax = plt.subplots(figsize=(7.4, 2.2))
    ax.fill_between(range(len(horaria)), horaria, color=_MPL_SLATE, alpha=0.85)
    ax.set_xlabel("Horas ordenadas por corte decrescente")
    ax.set_ylabel("Corte (MWh/h)")
    ax.set_title("Curva de duração do corte", fontsize=9, color="#3a444e")
    return _fig_para_image(fig, largura_cm)


def _grafico_ranking(ranking: pd.DataFrame, largura_cm: float, top: int = 12) -> Image | None:
    if ranking is None or ranking.empty:
        return None
    d = ranking.head(top).iloc[::-1]
    fig, ax = plt.subplots(figsize=(7.4, 0.32 * len(d) + 0.6))
    ax.barh(d["conjunto"].str.replace("CONJ. ", "", regex=False), d["energia_frustrada_mwh"],
            color=_MPL_TERRACOTA)
    ax.set_xlabel("Energia frustrada (MWh no mês)")
    return _fig_para_image(fig, largura_cm)


# --------------------------------------------------------------------------- #
# Tabelas                                                                     #
# --------------------------------------------------------------------------- #
def _tabela(dados: list[list], larguras: list[float], cabecalho: bool = True) -> Table:
    t = Table(dados, colWidths=larguras)
    estilo = [
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#3a444e")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, _CINZA_CLARO),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if cabecalho:
        estilo += [
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("BACKGROUND", (0, 0), (-1, 0), _SLATE),
            ("LINEBELOW", (0, 0), (-1, 0), 0, colors.white),
        ]
    t.setStyle(TableStyle(estilo))
    return t


_ESTILO_CEL = ParagraphStyle(
    "cel_pdf", fontName="Helvetica", fontSize=8, leading=11,
    textColor=colors.HexColor("#3a444e"),
)


def _tabela_pares(pares: list[tuple[str, str]], larg_total: float) -> Table:
    dados = [
        [Paragraph(str(k), _ESTILO_CEL), Paragraph(str(v), _ESTILO_CEL)]
        for k, v in pares
    ]
    return _tabela(dados, [larg_total * 0.4, larg_total * 0.6], cabecalho=False)


# --------------------------------------------------------------------------- #
# Seções                                                                      #
# --------------------------------------------------------------------------- #
def _secao_capa(rel: Relatorio, S: dict) -> list:
    return [
        Spacer(1, 3 * cm),
        Paragraph("Relatório de Constrained-off", S["titulo"]),
        Paragraph("Conjuntos Eólicos do Rio Grande do Norte", S["subtitulo"]),
        Spacer(1, 0.6 * cm),
        Paragraph(f"Mês de referência: <b>{_rotulo_mes(rel.ano, rel.mes)}</b>", S["corpo"]),
        Paragraph(f"Conjuntos no relatório: <b>{len(rel.dossies)}</b>", S["corpo"]),
        Paragraph(f"Metodologia de energia frustrada em destaque: "
                  f"<b>[{rel.metodologia_ref}]</b> — {METODOLOGIAS[rel.metodologia_ref][1]}", S["corpo"]),
        Spacer(1, 0.6 * cm),
        Paragraph(f"Gerado em {datetime.now():%d/%m/%Y %H:%M}", S["nota"]),
        Paragraph("Fontes: ONS Dados Abertos (restrição/COFF eólica; CMO Semi-Horário NE), "
                  "ANEEL SIGA, cadastro de subestações/linhas do ONS.", S["nota"]),
    ] + ([Spacer(1, 0.4 * cm)] + [Paragraph("⚠ " + a, S["nota"]) for a in rel.avisos] if rel.avisos else [])


def _secao_resumo(rel: Relatorio, S: dict, larg: float) -> list:
    r = rel.resumo_rn
    tem_rs = bool(r.get("impacto_financeiro_rs"))
    flow = [PageBreak(), Paragraph("Sumário executivo — Rio Grande do Norte", S["h1"])]
    pares = [
        ("Conjuntos com corte no mês", f"{r['n_conjuntos_com_corte']} de {r['n_conjuntos_total']}"),
        ("Capacidade instalada total", _fmt(r["capacidade_instalada_total_mw"], 1, " MW")),
        ("Geração verificada no mês", _fmt(r["geracao_verificada_mwh"], 0, " MWh")),
        (f"Energia frustrada [{rel.metodologia_ref}]", _fmt(r["energia_frustrada_mwh"][rel.metodologia_ref], 0, " MWh")),
        ("Geração potencial frustrada", _fmt(r["pct_geracao_potencial_frustrada"], 1, " %")),
    ]
    if tem_rs:
        pares.append((f"Impacto financeiro [{rel.metodologia_ref}]",
                      "R$ " + _fmt(r["impacto_financeiro_rs"][rel.metodologia_ref], 0)))
    flow.append(_tabela_pares(pares, larg))
    flow.append(Spacer(1, 0.4 * cm))

    flow.append(Paragraph("Energia frustrada por metodologia (todo o RN)", S["h2"]))
    linhas = [["Metodologia", "MWh"] + (["R$"] if tem_rs else [])]
    for i in range(1, 6):
        row = [f"[{i}]", _fmt(r["energia_frustrada_mwh"][i], 0)]
        if tem_rs:
            row.append("R$ " + _fmt(r["impacto_financeiro_rs"][i], 0))
        linhas.append(row)
    flow.append(_tabela(linhas, [larg * 0.2] + [larg * (0.8 / (2 if tem_rs else 1))] * (2 if tem_rs else 1)))
    flow.append(Spacer(1, 0.4 * cm))

    flow.append(Paragraph("Conjuntos por energia frustrada no mês (top 12)", S["h2"]))
    g = _grafico_ranking(r["ranking_por_conjunto"], larg / cm)
    if g:
        flow.append(g)
    return flow


def _secao_conjunto(d, rel: Relatorio, S: dict, larg: float, png_mapa: bytes | None) -> list:
    ag = d.agregados
    tem_rs = d.tem_impacto_financeiro and bool(ag.get("impacto_financeiro_rs"))
    flow = [PageBreak(), Paragraph(d.conjunto, S["h1"])]

    cad = d.cadastro
    pares = [
        ("Municípios", str(cad["municipios"])),
        ("Capacidade instalada", _fmt(cad["capacidade_mw"], 2, " MW")),
        ("Usinas / aerogeradores", f"{cad['qtd_usinas']} / {cad['qtd_aerogeradores']}"),
        ("Ponto de conexão", f"SE {str(cad['ponto_conexao']).removeprefix('SE ')}"),
        ("Agente proprietário", str(cad["agente_proprietario"])),
        ("Agente operador", str(cad["agente_operador"])),
        ("Ajustamento operativo", str(cad["ajustamento_operativo"])),
        ("Coordenadas", f"{cad['latitude']:.5f}, {cad['longitude']:.5f}"),
        ("id_ONS", d.id_ons),
    ]
    if png_mapa:
        bloco_cad = _tabela_pares(pares, larg * 0.56)
        img = Image(io.BytesIO(png_mapa))
        escala = (larg * 0.40) / img.drawWidth
        img.drawWidth *= escala
        img.drawHeight *= escala
        linha = Table([[bloco_cad, img]], colWidths=[larg * 0.58, larg * 0.42])
        linha.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
        flow.append(linha)
    else:
        flow.append(_tabela_pares(pares, larg))
    flow.append(Spacer(1, 0.3 * cm))

    # Subestações e linhas
    flow.append(Paragraph("Conexão à rede", S["h2"]))
    if d.subestacoes:
        linhas = [["Subestação", "Níveis de tensão", "Agente operador"]]
        for s in d.subestacoes:
            t = s.get("tensoes_kv")
            t_txt = " / ".join(f"{int(x)}" for x in t) + " kV" if isinstance(t, (list, tuple)) and len(t) else "—"
            linhas.append([f"SE {str(s['nome']).removeprefix('SE ')}", t_txt, str(s.get("agente_operador") or "—")])
        flow.append(_tabela(linhas, [larg * 0.34, larg * 0.28, larg * 0.38]))
    if d.linhas is not None and not d.linhas.empty:
        flow.append(Spacer(1, 0.15 * cm))
        linhas = [["Linha de transmissão", "kV", "Extensão", "Tipo", "Agente"]]
        for _, ln in d.linhas.iterrows():
            comp = ln.get("comprimento_km")
            linhas.append([
                f"{ln['subestacao_de']} — {ln['subestacao_para']}",
                _fmt(ln["tensao_kv"], 0),
                _fmt(comp, 0, " km") if pd.notna(comp) else "—",
                str(ln.get("tipo_rede") or "—"),
                str(ln.get("agente") or "—"),
            ])
        flow.append(_tabela(linhas, [larg * 0.34, larg * 0.08, larg * 0.14, larg * 0.16, larg * 0.28]))

    # Constrained-off
    flow.append(Paragraph(f"Constrained-off — {_rotulo_mes(rel.ano, rel.mes)}", S["h2"]))
    if not ag:
        flow.append(Paragraph("Sem registro de restrição para este conjunto no mês.", S["corpo"]))
        return flow

    pares = [
        ("Horas no mês / com corte", f"{ag['horas_no_mes']} / {ag['horas_com_corte']}"),
        ("Geração verificada", _fmt(ag["geracao_verificada_mwh"], 0, " MWh")),
        ("Geração de referência", _fmt(ag["geracao_referencia_mwh"], 0, " MWh")),
        ("Geração limitada (imposta)", _fmt(ag["geracao_limitada_mwh"], 0, " MWh")),
        ("Disponibilidade média", _fmt(ag["disponibilidade_media_mw"], 1, " MW")),
        ("Fator de capacidade", _fmt(ag["fator_capacidade"] * 100, 1, " %")),
        ("Geração potencial frustrada", _fmt(ag["pct_geracao_potencial_frustrada"], 1, " %")),
    ]
    if ag.get("pld_medio_rs_mwh"):
        pares.append(("CMO médio no mês", "R$ " + _fmt(ag["pld_medio_rs_mwh"], 2) + " /MWh"))
    flow.append(_tabela_pares(pares, larg))
    flow.append(Spacer(1, 0.25 * cm))

    linhas = [["Metodologia", "Energia frustrada (MWh)"] + (["Impacto (R$)"] if tem_rs else [])]
    for i in range(1, 6):
        marca = " (ref.)" if i == rel.metodologia_ref else ""
        row = [f"[{i}]{marca}", _fmt(ag["energia_frustrada_mwh"][i], 0)]
        if tem_rs:
            row.append("R$ " + _fmt(ag["impacto_financeiro_rs"][i], 0))
        linhas.append(row)
    flow.append(_tabela(linhas, [larg * 0.24] + [larg * (0.76 / (2 if tem_rs else 1))] * (2 if tem_rs else 1)))
    flow.append(Spacer(1, 0.3 * cm))

    g = _grafico_serie(d.serie_diaria, rel.metodologia_ref, larg / cm)
    if g:
        flow.append(g)
        flow.append(Spacer(1, 0.2 * cm))
    for g in (_grafico_metodologias(ag["energia_frustrada_mwh"], ag.get("impacto_financeiro_rs", {}), larg / cm),
              _grafico_duracao(d.coff_mensal, rel.metodologia_ref, larg / cm)):
        if g:
            flow.append(g)
            flow.append(Spacer(1, 0.2 * cm))

    if not d.quebra_razao.empty:
        flow.append(Paragraph("Corte por razão da restrição", S["h2"]))
        linhas = [["Razão (cod_razaorestricao)", f"Energia frustrada [{rel.metodologia_ref}] (MWh)", "Horas"]]
        for _, q in d.quebra_razao.iterrows():
            linhas.append([str(q["cod_razaorestricao"]), _fmt(q["energia_frustrada_mwh"], 0), str(int(q["horas"]))])
        flow.append(_tabela(linhas, [larg * 0.4, larg * 0.4, larg * 0.2]))

    # Anexo usinas
    if d.usinas is not None and not d.usinas.empty:
        flow.append(Paragraph("Usinas integrantes", S["h2"]))
        linhas = [["Usina", "CEG", "Pot. fisc. (MW)", "Pot. out. (MW)", "Coordenadas"]]
        for _, u in d.usinas.iterrows():
            linhas.append([
                str(u["usina"]),
                str(u["ceg"]),
                _fmt(u.get("potencia_fiscalizada_mw"), 2),
                _fmt(u.get("potencia_outorgada_mw"), 2),
                f"{u['latitude']:.4f}, {u['longitude']:.4f}" if pd.notna(u.get("latitude")) else "—",
            ])
        flow.append(_tabela(linhas, [larg * 0.24, larg * 0.26, larg * 0.16, larg * 0.16, larg * 0.18]))
    return flow


# --------------------------------------------------------------------------- #
# Rodapé                                                                      #
# --------------------------------------------------------------------------- #
def _rodape(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor("#8b939c"))
    canvas.drawString(2 * cm, 1.2 * cm,
                      f"Painel de Monitoramento de Constrained-off — Conjuntos Eólicos do RN · "
                      f"gerado em {datetime.now():%d/%m/%Y}")
    canvas.drawRightString(A4[0] - 2 * cm, 1.2 * cm, f"página {doc.page}")
    canvas.restoreState()


# --------------------------------------------------------------------------- #
# API                                                                        #
# --------------------------------------------------------------------------- #
def gerar_pdf(rel: Relatorio, mapas_por_conjunto: dict[str, bytes] | None = None) -> bytes:
    """Monta o PDF do :class:`Relatorio` e devolve os bytes.

    ``mapas_por_conjunto`` mapeia ``conjunto -> PNG`` (mini-mapa recortado);
    quando ausente, as seções saem sem o mapa.
    """
    mapas_por_conjunto = mapas_por_conjunto or {}
    S = _estilos()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.8 * cm, bottomMargin=2 * cm,
        title=f"Constrained-off {_rotulo_mes(rel.ano, rel.mes)}",
        author="Painel de Monitoramento de Constrained-off — RN",
    )
    larg = A4[0] - 4 * cm

    flow: list = []
    flow += _secao_capa(rel, S)
    flow += _secao_resumo(rel, S, larg)
    for d in rel.dossies:
        flow += _secao_conjunto(d, rel, S, larg, mapas_por_conjunto.get(d.conjunto))

    doc.build(flow, onFirstPage=_rodape, onLaterPages=_rodape)
    return buf.getvalue()
