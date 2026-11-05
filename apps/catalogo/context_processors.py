from apps.core.parametros import get_parametros

from .vitrine import categorias_menu


def navegacao(request):
    return {"categorias_menu": categorias_menu()}


def loja(request):
    """Dados públicos da loja usados no topo, rodapé e botão do WhatsApp (editáveis em Parâmetros)."""
    p = get_parametros(
        "WHATSAPP_LOJA",
        "INSTAGRAM_LOJA",
        "CNPJ_LOJA",
        "ENDERECO_LOJA",
        "PIX_DESCONTO_PERCENTUAL",
        "PARCELAS_SEM_JUROS",
    )
    return {
        "loja": {
            "whatsapp": "".join(c for c in str(p["WHATSAPP_LOJA"] or "") if c.isdigit()),
            "instagram": str(p["INSTAGRAM_LOJA"] or "").strip().lstrip("@"),
            "cnpj": str(p["CNPJ_LOJA"] or "").strip(),
            "endereco": str(p["ENDERECO_LOJA"] or "").strip(),
            "pix_percentual": p["PIX_DESCONTO_PERCENTUAL"] or 0,
            "parcelas": p["PARCELAS_SEM_JUROS"] or 1,
        }
    }
