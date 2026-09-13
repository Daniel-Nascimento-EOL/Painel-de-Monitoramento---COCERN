"""Formatação de números no padrão brasileiro, compartilhada entre páginas
e a ficha do mapa (evita duplicar a mesma lógica em ``viz/map_charts.py`` e
``ui/apresentacao.py``)."""


def numero_br(valor: float, casas: int = 2) -> str:
    """Formata no padrão brasileiro: milhar com ponto, decimal com vírgula."""
    inteiro, _, decimal = f"{valor:,.{casas}f}".partition(".")
    inteiro = inteiro.replace(",", ".")
    return f"{inteiro},{decimal}" if decimal else inteiro
