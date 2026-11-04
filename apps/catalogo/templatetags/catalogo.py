"""Seletor de cor no estilo armação | lente.

Desenhado em SVG (atributos fill), não com style="" inline: assim funciona com a
CSP estrita sem precisar liberar estilos inline.
"""

import secrets

from django import template

register = template.Library()


def dados_swatch(armacao, lente=None) -> dict:
    return {
        "id_clip": f"sw-{secrets.token_hex(4)}",
        "armacao_hex": armacao.cor_hex,
        "armacao_textura": armacao.textura.url if armacao.textura else "",
        "lente_hex": lente.cor_hex if lente else armacao.cor_hex,
        "rotulo": f"Armação {armacao.nome.lower()}" + (f", lente {lente.nome.lower()}" if lente else ""),
    }


@register.inclusion_tag("catalogo/partials/swatch.html")
def swatch(variacao):
    return dados_swatch(variacao.armacao, variacao.lente)
