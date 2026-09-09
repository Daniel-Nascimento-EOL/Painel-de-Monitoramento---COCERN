"""Página de inspeção, edição e exportação dos dados que alimentam o mapa.

Reúne num só lugar todas as tabelas de origem do mapa — as cadastrais
(conjuntos, usinas, subestações, cidades) e as de rede geradas por
``scripts/atualizar_dados_mapa.py`` (SE de transmissão, linhas, potências
do SIGA) — além da tabela derivada de linhas de conexão conjunto→SE.

Cada tabela pode ser:

* **conferida** na grade, com destaque para linhas suspeitas (coordenada
  fora do RN, linha de conexão muito longa);
* **editada** na própria grade (``st.data_editor``) e salva de volta no
  arquivo de origem — funciona ao rodar localmente; no ambiente publicado
  o disco é efêmero e a alteração dura só até o próximo reinício, então o
  fluxo recomendado lá é baixar o CSV, editar e versionar;
* **exportada** em CSV (UTF-8 com BOM) ou, para o conjunto todo, em GeoJSON
  para cruzar as posições com imagem de satélite.

Ver ``docs/editar_dados_do_mapa.md`` para o passo a passo de cada arquivo.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from core.data_loader import (
    BAYS_PATH,
    DATA_PATH,
    load_bays,
    load_cidades,
    load_conjuntos,
    load_usinas,
)
from core.ons_rede import _ARQ_LINHAS, _ARQ_SUBESTACOES, _chave_subestacao_ons

_ARQ_SIGA = Path(__file__).resolve().parent.parent / "data" / "rede" / "siga_potencias_eol_rn.csv"

# Bounding box do RN (com folga) — coordenada fora disso é sinalizada.
_LAT_RN = (-7.3, -4.5)
_LON_RN = (-39.0, -34.5)
# Acima deste comprimento, a linha de conexão conjunto→SE merece conferência.
_LIMITE_LINHA_KM = 60.0


# --------------------------------------------------------------------------
# Utilidades de serialização e validação
# --------------------------------------------------------------------------
def _csv_bytes(df: pd.DataFrame) -> bytes:
    """Serializa o DataFrame em CSV UTF-8 com BOM (abre direto no Excel do
    Windows sem corromper acentuação)."""
    return df.to_csv(index=False).encode("utf-8-sig")


def _distancia_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distância de Haversine em quilômetros entre dois pontos."""
    from math import asin, cos, radians, sin, sqrt

    r = 6371.0
    d_lat = radians(lat2 - lat1)
    d_lon = radians(lon2 - lon1)
    a = (
        sin(d_lat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lon / 2) ** 2
    )
    return 2 * r * asin(sqrt(a))


def _fora_do_rn(lat: float, lon: float) -> bool:
    return not (
        _LAT_RN[0] <= lat <= _LAT_RN[1] and _LON_RN[0] <= lon <= _LON_RN[1]
    )


def _linhas_conexao(df_conjuntos: pd.DataFrame, df_bays: pd.DataFrame) -> pd.DataFrame:
    """Reconstrói a tabela das linhas conjunto→subestação de conexão, com o
    comprimento em linha reta de cada uma. Mesma junção que o mapa usa para
    desenhar as linhas fixas de conexão."""
    ses = {
        _chave_subestacao_ons(row["subestacao"]): row
        for _, row in df_bays.iterrows()
    }
    registros: list[dict] = []
    for _, c in df_conjuntos.iterrows():
        chave = _chave_subestacao_ons(str(c["ponto_conexao"]))
        se = ses.get(chave)
        if se is None:
            registros.append(
                {
                    "conjunto": c["conjunto"],
                    "ponto_conexao": c["ponto_conexao"],
                    "subestacao": None,
                    "lat_conjunto": c["latitude"],
                    "long_conjunto": c["longitude"],
                    "lat_subestacao": None,
                    "long_subestacao": None,
                    "distancia_km": None,
                }
            )
            continue
        dist = _distancia_km(
            c["latitude"], c["longitude"], se["latitude"], se["longitude"]
        )
        registros.append(
            {
                "conjunto": c["conjunto"],
                "ponto_conexao": c["ponto_conexao"],
                "subestacao": se["subestacao"],
                "lat_conjunto": c["latitude"],
                "long_conjunto": c["longitude"],
                "lat_subestacao": se["latitude"],
                "long_subestacao": se["longitude"],
                "distancia_km": round(dist, 1),
            }
        )
    return pd.DataFrame(registros)


def _geojson_pontos(
    df_conjuntos: pd.DataFrame,
    df_usinas: pd.DataFrame,
    df_bays: pd.DataFrame,
    df_cidades: pd.DataFrame,
    df_linhas: pd.DataFrame,
) -> dict:
    """FeatureCollection com todos os pontos e linhas do mapa, para abrir no
    Google Earth ou no QGIS e cruzar as posições com imagem de satélite."""
    features: list[dict] = []

    for _, r in df_conjuntos.iterrows():
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [float(r["longitude"]), float(r["latitude"])],
                },
                "properties": {
                    "tipo": "conjunto",
                    "nome": r["conjunto"],
                    "id_ons": r.get("id_ons"),
                    "municipios": r.get("municipios"),
                    "capacidade_mw": r.get("capacidade_mw"),
                    "qtd_aerogeradores": r.get("qtd_aerogeradores"),
                    "ponto_conexao": r.get("ponto_conexao"),
                },
            }
        )

    for _, r in df_usinas.iterrows():
        if pd.isna(r.get("latitude")) or pd.isna(r.get("longitude")):
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [float(r["longitude"]), float(r["latitude"])],
                },
                "properties": {
                    "tipo": "usina",
                    "nome": r.get("usina"),
                    "conjunto": r.get("conjunto"),
                    "ceg": r.get("ceg"),
                    "fonte_coordenada": r.get("fonte_coordenada"),
                },
            }
        )

    for _, r in df_bays.iterrows():
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [float(r["longitude"]), float(r["latitude"])],
                },
                "properties": {
                    "tipo": "subestacao",
                    "nome": r["subestacao"],
                    "id_estado": r.get("id_estado"),
                    "agente_operador": r.get("agente_operador"),
                    "tensoes_kv": r.get("tensoes_kv"),
                },
            }
        )

    for _, r in df_cidades.iterrows():
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [float(r["longitude"]), float(r["latitude"])],
                },
                "properties": {"tipo": "cidade", "nome": r.get("cidade")},
            }
        )

    for _, r in df_linhas.iterrows():
        if pd.isna(r["lat_subestacao"]) or pd.isna(r["long_subestacao"]):
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [float(r["long_conjunto"]), float(r["lat_conjunto"])],
                        [float(r["long_subestacao"]), float(r["lat_subestacao"])],
                    ],
                },
                "properties": {
                    "tipo": "linha_conexao",
                    "conjunto": r["conjunto"],
                    "subestacao": r["subestacao"],
                    "distancia_km": r["distancia_km"],
                },
            }
        )

    return {"type": "FeatureCollection", "features": features}


# --------------------------------------------------------------------------
# Persistência da edição inline
# --------------------------------------------------------------------------
def _salvar_csv(df: pd.DataFrame, caminho: Path) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(caminho, index=False, encoding="utf-8-sig")


def _salvar_aba_xlsx(df: pd.DataFrame, caminho: Path, aba: str) -> None:
    """Regrava uma aba do .xlsx preservando as demais. As colunas gravadas
    são as originais da planilha (o data_loader renomeia na leitura); esta
    função recebe o DataFrame já com os nomes originais."""
    with pd.ExcelWriter(
        caminho, engine="openpyxl", mode="a", if_sheet_exists="replace"
    ) as escritor:
        df.to_excel(escritor, sheet_name=aba, index=False)


def _bloco_tabela(
    titulo: str,
    descricao: str,
    df: pd.DataFrame,
    nome_arquivo: str,
    *,
    editavel: bool = False,
    on_salvar=None,
    realce=None,
) -> None:
    """Bloco padrão de uma tabela: título, descrição, grade (editável ou não),
    aviso de linhas suspeitas e botão de download CSV.

    ``on_salvar`` recebe o DataFrame editado e persiste no arquivo de origem.
    ``realce`` recebe o DataFrame e devolve uma máscara booleana das linhas a
    sinalizar.
    """
    st.markdown(f"### {titulo}")
    st.caption(descricao)

    if realce is not None:
        suspeitas = df[realce(df)]
        if not suspeitas.empty:
            st.warning(
                f"{len(suspeitas)} linha(s) merecem conferência — ver realce abaixo."
            )

    if editavel and on_salvar is not None:
        editado = st.data_editor(
            df,
            width="stretch",
            hide_index=True,
            num_rows="dynamic",
            key=f"editor_{nome_arquivo}",
        )
        col_salvar, col_baixar = st.columns([1, 1])
        with col_salvar:
            if st.button(f"Salvar alterações em {titulo.lower()}", key=f"save_{nome_arquivo}"):
                try:
                    on_salvar(editado)
                    st.cache_data.clear()
                    st.success(
                        "Salvo. Recarregue a página para ver o efeito no mapa. "
                        "Localmente, lembre de versionar o arquivo (`git add`)."
                    )
                except Exception as erro:  # noqa: BLE001
                    st.error(f"Não foi possível salvar: {erro}")
        with col_baixar:
            st.download_button(
                f"Baixar {nome_arquivo}.csv",
                data=_csv_bytes(editado),
                file_name=f"{nome_arquivo}.csv",
                mime="text/csv",
                key=f"dl_{nome_arquivo}",
            )
    else:
        st.dataframe(df, width="stretch", hide_index=True)
        st.download_button(
            f"Baixar {nome_arquivo}.csv",
            data=_csv_bytes(df),
            file_name=f"{nome_arquivo}.csv",
            mime="text/csv",
            key=f"dl_{nome_arquivo}",
        )
    st.divider()


# --------------------------------------------------------------------------
# Página
# --------------------------------------------------------------------------
def render() -> None:
    df_conjuntos = load_conjuntos()
    df_usinas = load_usinas()
    df_bays = load_bays()
    df_cidades = load_cidades()
    df_linhas = _linhas_conexao(df_conjuntos, df_bays)

    st.markdown("## Dados do mapa")
    st.caption(
        "Todas as tabelas que alimentam o mapa, num só lugar. O painel lê "
        "exclusivamente os arquivos em `data/` — nada é baixado ao vivo. As "
        "tabelas de rede são geradas por `scripts/atualizar_dados_mapa.py`; "
        "as cadastrais são editadas aqui ou nas planilhas. Passo a passo em "
        "`docs/editar_dados_do_mapa.md`."
    )
    st.info(
        "A edição na grade grava direto no arquivo de origem. Ao rodar "
        "localmente, isso altera o repositório (lembre de versionar). No "
        "painel publicado o disco é temporário: a alteração vale só até o "
        "próximo reinício — lá, prefira baixar o CSV, editar e commitar.",
        icon="✏️",
    )
    st.divider()

    st.markdown("#### Exportação para conferência com satélite")
    st.caption(
        "GeoJSON com todos os pontos (conjuntos, usinas, subestações, cidades) "
        "e as linhas de conexão — abre no Google Earth ou no QGIS para cruzar "
        "as posições com imagem de satélite. O mesmo conteúdo está versionado "
        "em `docs/pontos_mapa.geojson`."
    )
    geojson = _geojson_pontos(df_conjuntos, df_usinas, df_bays, df_cidades, df_linhas)
    st.download_button(
        "Baixar pontos_mapa.geojson",
        data=json.dumps(geojson, ensure_ascii=False, indent=2).encode("utf-8"),
        file_name=f"pontos_mapa_{date.today():%Y%m%d}.geojson",
        mime="application/geo+json",
        key="dl_geojson",
    )
    st.divider()

    # --- Tabelas cadastrais (editáveis) -----------------------------------
    def _salvar_conjuntos(editado: pd.DataFrame) -> None:
        # Reescreve a aba Localizacao com os nomes de coluna originais.
        original = pd.read_excel(DATA_PATH, sheet_name="Localizacao")
        renome = {
            "conjunto": "Conjunto",
            "id_ons": "id_ons",
            "municipios": "Município(s)",
            "qtd_usinas": "Qtd. usinas",
            "qtd_aerogeradores": "Qtde. aerogeradores",
            "ponto_conexao": "Ponto de conexão",
            "agente_proprietario": "Agente Proprietário",
            "agente_operador": "Agente Operador",
            "ajustamento_operativo": "Ajustamento Operativo",
        }
        saida = editado.rename(columns=renome)
        # Recompõe a coluna combinada de coordenada e preserva as demais
        # colunas originais (logos etc.) a partir do arquivo atual.
        saida["Localização (lat, long)"] = (
            editado["latitude"].astype(str) + ", " + editado["longitude"].astype(str)
        )
        saida["Capacidade instalada"] = editado["capacidade_mw"].map(
            lambda v: f"{v:.2f} MW".replace(".", ",")
        )
        for col in original.columns:
            if col not in saida.columns:
                saida[col] = original.get(col)
        saida = saida[original.columns]
        _salvar_aba_xlsx(saida, DATA_PATH, "Localizacao")

    _bloco_tabela(
        "Conjuntos eólicos",
        f"{len(df_conjuntos)} conjuntos. `latitude`/`longitude` posicionam o "
        "marcador de turbina. Editável — a coordenada volta para a coluna "
        "combinada da planilha ao salvar.",
        df_conjuntos.drop(
            columns=["logo_proprietario", "logo_operador", "localizacao", "chave", "chave_subestacao"],
            errors="ignore",
        ),
        "conjuntos",
        editavel=True,
        on_salvar=_salvar_conjuntos,
        realce=lambda d: d.apply(
            lambda r: _fora_do_rn(r["latitude"], r["longitude"]), axis=1
        ),
    )

    def _salvar_bays(editado: pd.DataFrame) -> None:
        renome = {
            "agente_operador": "Agente Operador",
            "subestacao": "Subestação",
            "latitude": "latitude",
            "longitude": "longitude",
        }
        saida = editado.rename(columns=renome)
        original = pd.read_excel(BAYS_PATH, sheet_name="Bays")
        for col in original.columns:
            if col not in saida.columns:
                saida[col] = original.get(col)
        saida = saida[[c for c in original.columns if c in saida.columns]]
        _salvar_aba_xlsx(saida, BAYS_PATH, "Bays")

    _bloco_tabela(
        "Subestações (bays.xlsx)",
        f"{len(df_bays)} subestações do RN e da PB. Marcador de SE e ponta das "
        "linhas de conexão. As colunas de tensão vêm da tabela de rede e não "
        "são salvas aqui.",
        df_bays.drop(
            columns=["chave", "tensao_max_kv", "tensoes_kv", "agente_principal"],
            errors="ignore",
        ),
        "subestacoes_bays",
        editavel=True,
        on_salvar=_salvar_bays,
        realce=lambda d: d.apply(
            lambda r: _fora_do_rn(r["latitude"], r["longitude"]), axis=1
        ),
    )

    def _salvar_cidades(editado: pd.DataFrame) -> None:
        saida = editado.rename(
            columns={"cidade": "Cidade", "latitude": "Latitude", "longitude": "Longitude"}
        )
        _salvar_aba_xlsx(saida, BAYS_PATH, "Cidades_RN")

    _bloco_tabela(
        "Cidades de referência",
        f"{len(df_cidades)} cidades exibidas como rótulo fixo no mapa.",
        df_cidades,
        "cidades_referencia",
        editavel=True,
        on_salvar=_salvar_cidades,
        realce=lambda d: d.apply(
            lambda r: _fora_do_rn(r["latitude"], r["longitude"]), axis=1
        ),
    )

    # --- Tabela derivada (só leitura) -----------------------------------
    _bloco_tabela(
        "Linhas de conexão conjunto–subestação",
        "Derivada: junção `Ponto de conexão` (conjunto) ↔ `Subestação` (bays), "
        f"com o comprimento em linha reta. Acima de {_LIMITE_LINHA_KM:.0f} km "
        "ou sem subestação correspondente, conferir.",
        df_linhas,
        "linhas_conexao",
        realce=lambda d: d["distancia_km"].isna()
        | (d["distancia_km"] > _LIMITE_LINHA_KM),
    )

    # --- Tabelas de rede (geradas pelo script; editáveis nos CSV) --------
    st.markdown("### Tabelas de rede")
    st.caption(
        "Geradas por `python scripts/atualizar_dados_mapa.py` a partir dos "
        "cadastros do ONS e da ANEEL. Editáveis aqui para correção pontual; "
        "a próxima execução do script sobrescreve o arquivo."
    )

    try:
        df_ses = pd.read_csv(_ARQ_SUBESTACOES)
        _bloco_tabela(
            "Subestações de transmissão (ONS)",
            "Nível de tensão (kV), agente e coordenada de cada SE de "
            "transmissão do RN. Posiciona a ponta das linhas de transmissão.",
            df_ses,
            "subestacoes_rn",
            editavel=True,
            on_salvar=lambda ed: _salvar_csv(ed, _ARQ_SUBESTACOES),
            realce=lambda d: d.apply(
                lambda r: _fora_do_rn(r["latitude"], r["longitude"]), axis=1
            ),
        )
    except FileNotFoundError:
        st.warning("`data/rede/subestacoes_rn.csv` ausente — rode o script.")

    try:
        df_lt = pd.read_csv(_ARQ_LINHAS)
        _bloco_tabela(
            "Linhas de transmissão (ONS)",
            "Linhas da Rede de Operação que tocam o RN, com tensão (kV), tipo "
            "de rede, comprimento e agente. Sem geometria — só subestação de/para.",
            df_lt,
            "linhas_transmissao_rn",
            editavel=True,
            on_salvar=lambda ed: _salvar_csv(ed, _ARQ_LINHAS),
        )
    except FileNotFoundError:
        st.warning("`data/rede/linhas_transmissao_rn.csv` ausente — rode o script.")

    try:
        df_siga = pd.read_csv(_ARQ_SIGA)
        _bloco_tabela(
            "Potências por usina (ANEEL SIGA)",
            "Potência outorgada e fiscalizada por CEG das eólicas do RN. "
            "Junta com a aba Detalhamento pelo CEG e alimenta o popup da usina.",
            df_siga,
            "siga_potencias_eol_rn",
            editavel=True,
            on_salvar=lambda ed: _salvar_csv(ed, _ARQ_SIGA),
        )
    except FileNotFoundError:
        st.warning("`data/rede/siga_potencias_eol_rn.csv` ausente — rode o script.")

    # --- Usinas individuais (só leitura) --------------------------------
    _bloco_tabela(
        "Usinas individuais (aba Detalhamento)",
        f"{len(df_usinas)} usinas. Camada opcional no mapa. Coordenada por "
        "usina, com a origem na coluna `fonte_coordenada`. Editar na planilha.",
        df_usinas.drop(columns=["chave"], errors="ignore"),
        "usinas",
    )
