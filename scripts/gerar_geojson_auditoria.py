"""Gera o GeoJSON de auditoria das posições do mapa.

Uso::

    python scripts/gerar_geojson_auditoria.py

Escreve ``docs/pontos_mapa.geojson`` com todos os pontos e linhas que o mapa
desenha — conjuntos, usinas individuais, subestações, cidades de referência
e as linhas de conexão conjunto -> subestação. O arquivo abre direto no
Google Earth Pro e no QGIS; a intenção é sobrepô-lo à imagem de satélite e
conferir, ponto a ponto, se cada marcador cai sobre a estrutura real.

É a mesma montagem que o botão "Baixar pontos_mapa.geojson" da página
"Dados do mapa" produz; este script versiona um retrato no repositório para
que a auditoria tenha uma referência fixa. Rodar novamente após qualquer
atualização dos cadastros de localização.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.data_loader import (  # noqa: E402
    load_bays,
    load_cidades,
    load_conjuntos,
    load_usinas,
)
from ui.dados import _geojson_pontos, _linhas_conexao  # noqa: E402

DESTINO = Path(__file__).resolve().parent.parent / "docs" / "pontos_mapa.geojson"


def main() -> None:
    df_conjuntos = load_conjuntos()
    df_usinas = load_usinas()
    df_bays = load_bays()
    df_cidades = load_cidades()
    df_linhas = _linhas_conexao(df_conjuntos, df_bays)

    geojson = _geojson_pontos(
        df_conjuntos, df_usinas, df_bays, df_cidades, df_linhas
    )

    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    DESTINO.write_text(
        json.dumps(geojson, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    tipos: dict[str, int] = {}
    for feature in geojson["features"]:
        tipo = feature["properties"]["tipo"]
        tipos[tipo] = tipos.get(tipo, 0) + 1

    print(f"Escrito {DESTINO.relative_to(DESTINO.parents[1])}")
    for tipo, n in sorted(tipos.items()):
        print(f"  {n:4d}  {tipo}")

    longas = df_linhas.dropna(subset=["distancia_km"]).nlargest(5, "distancia_km")
    print("\nLinhas de conexão mais longas (conferir com prioridade):")
    for _, r in longas.iterrows():
        print(f"  {r['distancia_km']:6.1f} km  {r['conjunto']} -> {r['subestacao']}")


if __name__ == "__main__":
    main()
