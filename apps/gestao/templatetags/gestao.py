from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from apps.catalogo.templatetags.vitrine import brl

register = template.Library()
register.filter("brl", brl)

# Ícones de traço (24x24). Só caminhos SVG fixos, nunca conteúdo vindo de usuário.
ICONES = {
    "painel": '<path d="M4 13h6V4H4zM14 20h6v-9h-6zM4 20h6v-4H4zM14 4v4h6V4z"/>',
    "produtos": '<path d="M3.5 8.5 12 4l8.5 4.5v7L12 20l-8.5-4.5z"/><path d="m3.5 8.5 8.5 4.5 8.5-4.5M12 13v7"/>',
    "estoque": '<path d="M4 7h16v13H4zM4 7l2-3h12l2 3M9.5 11h5"/>',
    "clientes": '<circle cx="9" cy="8.5" r="3.5"/><path d="M3 20c.5-3.5 3-5.5 6-5.5s5.5 2 6 5.5"/>'
    '<path d="M16 5.2a3.4 3.4 0 0 1 0 6.6M17.5 14.7c2 .7 3.2 2.5 3.5 5.3"/>',
    "pedidos": '<path d="M6 3h12v18l-3-2-3 2-3-2-3 2zM9 8h6M9 12h6M9 16h3"/>',
    "banners": '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 16 5-5 4 4 3-3 6 6"/>'
    '<circle cx="16" cy="9" r="1.5"/>',
    "paginas": '<path d="M7 3h7l5 5v13H7z"/><path d="M14 3v5h5M10 13h6M10 17h6"/>',
    "configuracoes": '<circle cx="12" cy="12" r="3"/><path d="M12 2.5v3M12 18.5v3M4.2 6.2l2.1 2.1M17.7 15.7l2.1 2.1'
    'M2.5 12h3M18.5 12h3M4.2 17.8l2.1-2.1M17.7 8.3l2.1-2.1"/>',
    "sair": '<path d="M14 4h5v16h-5M10 8l-4 4 4 4M6 12h10"/>',
    "loja": '<path d="M4 9.5 5.5 4h13L20 9.5M4 9.5V20h16V9.5M4 9.5c0 1.7 1.3 2.5 2.7 2.5S9.3 11.2 9.3 9.5'
    'c0 1.7 1.3 2.5 2.7 2.5s2.7-.8 2.7-2.5c0 1.7 1.3 2.5 2.6 2.5S20 11.2 20 9.5M10 20v-5h4v5"/>',
    "busca": '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m15.5 15.5 5 5"/>',
    "mais": '<path d="M12 5v14M5 12h14"/>',
    "alerta": '<path d="M12 3 2.5 20h19z"/><path d="M12 10v4M12 17v.5"/>',
    "seta": '<path d="m9 5 7 7-7 7"/>',
    "voltar": '<path d="m15 5-7 7 7 7"/>',
    "subiu": '<path d="m6 15 6-6 6 6"/>',
    "desceu": '<path d="m6 9 6 6 6-6"/>',
    "olho": '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/>'
    '<circle cx="12" cy="12" r="3"/>',
    "estrela": '<path d="m12 3.5 2.6 5.4 5.9.8-4.3 4.1 1 5.8-5.2-2.8-5.2 2.8 1-5.8-4.3-4.1 5.9-.8z"/>',
    "whatsapp": '<path d="M4 20l1.3-4A8 8 0 1 1 8.4 19z"/><path d="M9 9.5c.3 2.4 2.3 4.6 5 5.3l1-1.3-1.8-1-1 .8'
    'c-.9-.4-1.6-1.1-2-2l.8-1-1-1.8z"/>',
    "lixeira": '<path d="M4.5 7h15M9 7V4.5h6V7M6.5 7l1 13h9l1-13M10 11v5M14 11v5"/>',
    "baixar": '<path d="M12 4v11M7 10l5 5 5-5M5 20h14"/>',
}


@register.simple_tag
def icone(nome: str, classe: str = "icone"):
    caminho = ICONES.get(nome, "")
    return format_html(
        '<svg class="{}" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" '
        'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">'
        "{}</svg>",
        classe,
        mark_safe(caminho),  # noqa: S308 (constante do dicionário acima)
    )


@register.filter
def variacao_pct(valor) -> str:
    if valor is None:
        return ""
    sinal = "+" if valor > 0 else ""
    return f"{sinal}{valor:.1f}%".replace(".", ",")


@register.filter
def inteiro(valor) -> str:
    try:
        return f"{int(valor):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "0"


@register.filter
def digitos(valor) -> str:
    """+55 85 99999-8888 -> 5585999998888 (o wa.me não aceita +, espaço nem traço)."""
    return "".join(c for c in str(valor or "") if c.isdigit())
