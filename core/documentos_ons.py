"""Documentos normativos do ONS vinculados a cada conjunto eólico.

A planilha de conjuntos traz, por conjunto, o código do **Ajustamento
Operativo** aplicável (``AO-CE.NE.2LE`` para a Área 230 kV Leste,
``AO-CE.NE.2NO`` para a Área 230 kV Norte). Este módulo transforma esse
código no link para o PDF publicado no Manual de Procedimentos da Operação
(MPO) do ONS.

Gotcha da revisão no nome do arquivo
------------------------------------
O ONS publica cada documento com o número da revisão embutido no nome
(``AO-CE.NE.2LE_Rev.32.pdf``) e **remove a revisão anterior** ao publicar
uma nova — uma URL fixa passa a devolver 404 poucos meses depois. Por isso
a revisão vigente é descoberta por sondagem (uma requisição ``HEAD`` por
candidato, a partir da última revisão conhecida), com o resultado em cache
de 24 h. Se a sondagem não achar nenhuma, o link cai na página de busca do
MPO, que nunca quebra.
"""

import streamlit as st
import requests

_BASE_MPO = (
    "https://www.ons.org.br/MPO/Documento%20Normativo/"
    "5.%20Ajustamentos%20Operativos%20-%20SM%205.14/5.2.%20Regi%C3%A3o%20Nordeste"
)

# Página de busca do MPO — usada quando a sondagem da revisão vigente falha.
_BUSCA_MPO = "https://www.ons.org.br/paginas/sobre-o-ons/procedimentos-de-rede/mpo"

# Um registro por código de ajustamento operativo presente na planilha:
# título do documento, pasta da área no MPO e a última revisão conhecida
# (ponto de partida da sondagem — ver o cabeçalho do módulo).
_DOCUMENTOS = {
    "AO-CE.NE.2LE": {
        "titulo": "Operação dos Conjuntos Eólicos da Área 230 kV Leste da Região Nordeste",
        "pasta": "5.2.2.%20%C3%81rea%20230%20kV%20Leste",
        "revisao_conhecida": 32,
    },
    "AO-CE.NE.2NO": {
        "titulo": "Operação dos Conjuntos Eólicos da Área 230 kV Norte da Região Nordeste",
        "pasta": "5.2.4.%20%C3%81rea%20230%20kV%20Norte",
        "revisao_conhecida": 20,
    },
}

# Quantas revisões acima da conhecida a sondagem tenta antes de desistir. A
# revisão registrada aqui é a vigente no momento em que o código foi escrito,
# então o caso comum resolve na primeira tentativa; a janela cobre as
# publicações posteriores, e ``revisao_conhecida`` deve ser atualizada de
# tempos em tempos para que a sondagem continue barata.
_JANELA_SONDAGEM = 8


def _url_revisao(pasta: str, codigo: str, revisao: int) -> str:
    return f"{_BASE_MPO}/{pasta}/{codigo}_Rev.{revisao:02d}.pdf"


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def _url_vigente(codigo: str) -> str | None:
    """Sonda o MPO em busca da revisão vigente do documento.

    Tenta primeiro a revisão conhecida (acerto imediato no caso comum) e
    depois as posteriores, da mais nova para a mais antiga, para encontrar
    uma publicação recente sem varrer revisões que já foram removidas.
    """
    registro = _DOCUMENTOS.get(codigo)
    if registro is None:
        return None
    base = registro["revisao_conhecida"]
    candidatas = [base] + list(range(base + _JANELA_SONDAGEM, base, -1))
    for revisao in candidatas:
        url = _url_revisao(registro["pasta"], codigo, revisao)
        try:
            resposta = requests.head(url, timeout=8, allow_redirects=True)
        except requests.RequestException:
            continue
        if resposta.status_code == 200:
            return url
    return None


def documentos_do_conjunto(codigo_ajustamento) -> list[dict]:
    """Documentos vinculados a um conjunto, a partir do seu ajustamento operativo.

    Cada item traz ``codigo``, ``titulo`` e ``url`` (o PDF da revisão vigente
    ou, se a sondagem falhar, a página de busca do MPO).
    """
    codigo = str(codigo_ajustamento or "").strip()
    registro = _DOCUMENTOS.get(codigo)
    if not registro:
        return []
    return [
        {
            "codigo": codigo,
            "titulo": registro["titulo"],
            "url": _url_vigente(codigo) or _BUSCA_MPO,
        }
    ]
