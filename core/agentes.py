"""Cadastro dos agentes (proprietários e operadores) dos conjuntos eólicos e
resolução das respectivas logomarcas.

Motivação
---------
As colunas ``Logo - Agente Proprietário`` / ``Logo - Agente Operador`` da
planilha ``data/localizacao_conjuntos_ons_aneel.xlsx`` apontavam para
miniaturas do cache de imagens do Google (``encrypted-tbn0.gstatic.com``).
Esses endereços são instáveis (expiram) e frequentemente trazem a marca
errada — era o caso da Simm Soluções, que exibia a logomarca da New Energy
Options em alguns conjuntos e a da V2i Energia em outros. Além disso, a
coluna do operador vinha vazia em boa parte das linhas, e conjuntos com
mais de um proprietário (ex.: ``Echoenergia / Elawan Energy``) traziam uma
única logomarca.

Este módulo substitui aquelas colunas por um cadastro versionado no
repositório: cada agente tem sua logomarca baixada da fonte oficial e
guardada em ``data/icons/agentes/`` (ver ``scripts/baixar_logos_agentes.py``),
servida ao mapa como ``data:`` URI. O campo de agente da planilha é
interpretado como lista separada por ``/``, de modo que todos os
proprietários de um conjunto aparecem na ficha.
"""

import base64
import io
import re
import unicodedata
from pathlib import Path

import pandas as pd
import streamlit as st
from PIL import Image

LOGOS_DIR = Path(__file__).resolve().parent.parent / "data" / "icons" / "agentes"

# Fonte oficial da logomarca de cada agente. A chave é o nome normalizado
# (ver _chave_agente); o valor é a URL de origem, usada apenas pelo script
# de atualização — em execução o painel lê o arquivo local correspondente.
#
# Preferência de fonte, nesta ordem:
#   1. arquivo de logomarca publicado no próprio site do agente;
#   2. logo.dev resolvendo o domínio institucional (marca verificada);
#   3. ícone de aplicativo (apple-touch-icon) do site oficial, quando a
#      logomarca do cabeçalho é SVG embutido no HTML e não tem URL própria.
FONTES_LOGO: dict[str, str] = {
    "2W ECOBANK": "https://img.logo.dev/2wenergia.com.br?token={token}&size=256&format=png",
    "ALIANCA ENERGIA": "https://img.logo.dev/aliancaenergia.com.br?token={token}&size=256&format=png",
    "ALUPAR": "https://img.logo.dev/alupar.com.br?token={token}&size=256&format=png",
    "AUREN ENERGIA": "https://img.logo.dev/aurenenergia.com.br?token={token}&size=256&format=png",
    "CGN BRASIL ENERGIA": "https://img.logo.dev/cgnbe.com.br?token={token}&size=256&format=png",
    "CPFL RENOVAVEIS": "https://img.logo.dev/cpfl.com.br?token={token}&size=256&format=png",
    "CASA DOS VENTOS ENERGIAS RENOVAVEIS": "https://img.logo.dev/casadosventos.com.br?token={token}&size=256&format=png",
    "COPEL": "https://img.logo.dev/copel.com?token={token}&size=256&format=png",
    "COTESA ENGENHARIA": "https://img.logo.dev/cotesa.com.br?token={token}&size=256&format=png",
    "EDP": "https://img.logo.dev/edp.com.br?token={token}&size=256&format=png",
    # Logomarca do cabeçalho é SVG embutido; usa-se o ícone oficial do site.
    "ECHOENERGIA": "https://echoenergia.com.br/wp-content/themes/app/assets/favicon/apple-touch-icon.png",
    "ELAWAN ENERGY": "https://img.logo.dev/elawan.com?token={token}&size=256&format=png",
    "ELERA RENOVAVEIS": "https://elera.com/wp-content/uploads/2020/06/logo_elera_xd@2x_tinyfied.png",
    "ENEL GREEN POWER": "https://img.logo.dev/enelgreenpower.com?token={token}&size=256&format=png",
    "ENGIE": "https://img.logo.dev/engie.com.br?token={token}&size=256&format=png",
    "ESSENTIA ENERGIA": "https://img.logo.dev/essentiaenergia.com.br?token={token}&size=256&format=png",
    "IBITU ENERGIA": "https://ibituenergia.com/wp-content/themes/ibitu/images/logo.png",
    "MULTINER S.A": "https://multiner.com.br/wp-content/themes/multinersa/images/favicon/apple-touch-icon.png",
    "NEOENERGIA": "https://img.logo.dev/neoenergia.com?token={token}&size=256&format=png",
    # Subsidiária integral da Multiner; sem marca nem domínio próprios ativos.
    "NEW ENERGY OPTIONS": "https://multiner.com.br/wp-content/themes/multinersa/images/favicon/apple-touch-icon.png",
    "POLIMIX ENERGIA": "https://img.logo.dev/polimix.com.br?token={token}&size=256&format=png",
    "QAIR": "https://img.logo.dev/qair.energy?token={token}&size=256&format=png",
    "SERVENG": "https://serveng.com.br/wp-content/uploads/2022/06/serveng-logo.png",
    "SIMM SOLUCOES": "https://img.logo.dev/simmsolucoes.com.br?token={token}&size=256&format=png",
    "STATKRAFT": "https://img.logo.dev/statkraft.com?token={token}&size=256&format=png",
    "TODA ENERGIA DO BRASIL": "https://img.logo.dev/toda.co.jp?token={token}&size=256&format=png",
    "TOTAL ENERGIES": "https://img.logo.dev/totalenergies.com?token={token}&size=256&format=png",
    "TRADENER": "https://img.logo.dev/tradener.com.br?token={token}&size=256&format=png",
    "V2I ENERGIA": "https://www.v2ienergia.com/wp-content/uploads/2024/03/MARCAS-V2I-02-1.png",
    "VOLTALIA ENERGIA DO BRASIL": "https://img.logo.dev/voltalia.com?token={token}&size=256&format=png",
}

# Agentes cuja logomarca é branca (ou muito clara) e some sobre fundo claro —
# o arquivo é gravado sobre um fundo escuro no script de download.
LOGOS_FUNDO_ESCURO = {"SERVENG"}


def _sem_acento(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", str(texto))
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def chave_agente(nome: str) -> str:
    """Nome do agente normalizado: sem acento, caixa alta, espaços colapsados."""
    return re.sub(r"\s+", " ", _sem_acento(nome).strip()).upper()


def _nome_arquivo(chave: str) -> str:
    """Nome do arquivo da logomarca a partir da chave do agente."""
    return re.sub(r"[^a-z0-9]+", "_", chave.lower()).strip("_") + ".png"


def separar_agentes(valor) -> list[str]:
    """Divide o campo de agente da planilha em uma lista de nomes.

    A planilha registra co-propriedade com barra, ex.:
    ``'Voltalia Energia do Brasil / Copel / Toda Energia do Brasil'`` — a ficha
    do conjunto deve exibir os três, cada um com sua logomarca.
    """
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return []
    return [parte.strip() for parte in str(valor).split("/") if parte.strip()]


# Lado do ícone da logomarca dentro da ficha. Os arquivos são gravados em
# 256 px (bons para o relatório PDF); no mapa eles renderizam a ~30 px, então
# são reduzidos antes de virar ``data:`` URI — 30 logomarcas em 256 px somam
# ~820 KB de base64 no HTML, contra ~60 KB nesta resolução.
_LADO_LOGO_FICHA = 64


@st.cache_resource
def _logo_data_uri(caminho: str) -> str:
    """PNG da logomarca reduzido para a ficha e codificado como ``data:`` URI.

    Embutir (em vez de apontar para o site do agente) evita depender de
    domínios de terceiros no carregamento da página e mantém a ficha correta
    mesmo se a origem sair do ar.
    """
    img = Image.open(caminho).convert("RGB")
    img.thumbnail((_LADO_LOGO_FICHA, _LADO_LOGO_FICHA), Image.LANCZOS)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def logo_agente(nome: str) -> str | None:
    """URI da logomarca do agente, ou ``None`` se não houver arquivo local.

    Quando retorna ``None``, a ficha exibe o avatar com a inicial do nome.
    """
    caminho = LOGOS_DIR / _nome_arquivo(chave_agente(nome))
    if not caminho.exists():
        return None
    return _logo_data_uri(str(caminho))


@st.cache_resource
def classe_css_logos() -> tuple[str, dict[str, str]]:
    """CSS com uma classe por logomarca, e o mapa ``chave do agente -> classe``.

    As fichas dos 54 conjuntos repetem os mesmos ~30 agentes; embutir a
    ``data:`` URI em cada ``<img>`` multiplicava o mesmo base64 dezenas de
    vezes no HTML do mapa. Declarando cada logomarca uma única vez como
    ``background-image`` de uma classe, o HTML passa a referenciá-la pelo
    nome da classe.
    """
    regras = []
    classes = {}
    for caminho in sorted(LOGOS_DIR.glob("*.png")):
        classe = "logo-" + caminho.stem.replace("_", "-")
        classes[caminho.stem] = classe
        regras.append(
            f".{classe}{{background-image:url('{_logo_data_uri(str(caminho))}');}}"
        )
    css = (
        "<style>.logo-agente{width:30px;height:30px;background-size:contain;"
        "background-position:center;background-repeat:no-repeat;}"
        + "".join(regras)
        + "</style>"
    )
    return css, classes


def classe_logo(nome: str) -> str | None:
    """Classe CSS da logomarca do agente (ver ``classe_css_logos``)."""
    _, classes = classe_css_logos()
    return classes.get(_nome_arquivo(chave_agente(nome))[:-4])
