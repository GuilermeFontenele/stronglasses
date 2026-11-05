from django import template
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def texto_pagina(texto: str):
    """Texto simples do painel em HTML seguro: '## ' vira subtítulo, linha em branco separa parágrafos."""
    blocos = [b.strip() for b in str(texto or "").replace("\r\n", "\n").split("\n\n") if b.strip()]
    partes = []
    for bloco in blocos:
        if bloco.startswith("## "):
            partes.append(format_html("<h2>{}</h2>", bloco[3:].strip()))
        else:
            linhas = format_html_join(mark_safe("<br>"), "{}", ((linha,) for linha in bloco.split("\n")))
            partes.append(format_html("<p>{}</p>", linhas))
    return mark_safe("".join(partes))  # noqa: S308 (cada parte já foi escapada por format_html)


@register.filter
def telefone(numero: str) -> str:
    """5585981809988 -> (85) 98180-9988."""
    digitos = "".join(c for c in str(numero or "") if c.isdigit())
    if digitos.startswith("55") and len(digitos) in (12, 13):
        digitos = digitos[2:]
    if len(digitos) == 11:
        return f"({digitos[:2]}) {digitos[2:7]}-{digitos[7:]}"
    if len(digitos) == 10:
        return f"({digitos[:2]}) {digitos[2:6]}-{digitos[6:]}"
    return digitos
