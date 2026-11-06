from django.contrib import admin

from apps.core.auditoria import AuditoriaAdminMixin

from .models import ItemPedido, Pedido


class ItemPedidoInline(admin.TabularInline):
    model = ItemPedido
    extra = 0
    readonly_fields = ("variacao", "produto", "nome", "cor", "sku", "quantidade", "preco_unitario")
    can_delete = False


@admin.register(Pedido)
class PedidoAdmin(AuditoriaAdminMixin, admin.ModelAdmin):
    """Bastidor técnico: vendas se lançam e se alteram pelo painel (/gestao/vendas/), que cuida do estoque."""

    list_display = ("codigo", "realizado_em", "cliente", "canal", "situacao", "total")
    list_filter = ("situacao", "canal", "forma_pagamento")
    search_fields = ("numero", "cliente__nome", "parceiro", "codigo_rastreio")
    inlines = [ItemPedidoInline]
    readonly_fields = ("numero", "subtotal", "desconto_pix", "total", "estoque_baixado", "pago_em", "enviado_em")

    def has_add_permission(self, request):
        return False
