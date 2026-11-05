from .carrinho import Carrinho


def carrinho(request):
    """Só o número de itens para o ícone do topo (não consulta o banco de produtos)."""
    if not hasattr(request, "session"):
        return {"carrinho_quantidade": 0}
    return {"carrinho_quantidade": len(Carrinho(request))}
