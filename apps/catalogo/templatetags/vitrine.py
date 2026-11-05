from decimal import Decimal

from django import template

from apps.catalogo import vitrine

register = template.Library()


@register.filter
def brl(valor) -> str:
    """Decimal('1234.5') -> 'R$ 1.234,50'."""
    if valor in (None, ""):
        return ""
    texto = f"{Decimal(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


@register.filter
def preco_pix(valor):
    return vitrine.preco_pix(Decimal(valor))


@register.inclusion_tag("catalogo/partials/precos.html")
def precos(preco, comparativo=None):
    vezes, valor_parcela = vitrine.parcela(Decimal(preco))
    return {
        "preco": preco,
        "comparativo": comparativo,
        "pix": vitrine.preco_pix(Decimal(preco)),
        "vezes": vezes,
        "parcela": valor_parcela,
    }
