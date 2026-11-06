"""Regras de exibição da vitrine (preços calculados sempre no servidor)."""

from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Prefetch

from apps.core.parametros import get_parametro

from .models import Categoria, ImagemProduto, Produto, Variacao

CENTAVO = Decimal("0.01")


def preco_pix(preco: Decimal) -> Decimal:
    percentual = Decimal(str(get_parametro("PIX_DESCONTO_PERCENTUAL", 0) or 0))
    return (preco * (1 - percentual / 100)).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def parcela(preco: Decimal) -> tuple[int, Decimal]:
    vezes = max(int(get_parametro("PARCELAS_SEM_JUROS", 1) or 1), 1)
    return vezes, (preco / vezes).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def produtos_visiveis():
    """Produtos publicados, com variações ativas e fotos já carregadas (evita N+1)."""
    return (
        Produto.objects.filter(ativo=True)
        .prefetch_related(
            Prefetch(
                "variacoes",
                queryset=Variacao.objects.filter(ativa=True).select_related("armacao", "lente"),
                to_attr="variacoes_ativas",
            ),
            Prefetch("imagens", queryset=ImagemProduto.objects.order_by("ordem", "id"), to_attr="fotos"),
        )
        .distinct()
    )


def categorias_menu():
    # Categoria vazia (sem produto publicado) não aparece no menu.
    return (
        Categoria.objects.filter(ativa=True, pai__isnull=True, produtos__ativo=True)
        .distinct()
        .order_by("ordem", "nome")
    )
