from django.contrib import admin
from django.db.models import Count, Sum
from django.db.models.functions import ExtractYear

from .models import ItemPedidoHistorico, MetricaMensal, PedidoHistorico, VisitasPorDimensao


class SomenteLeituraMixin:
    """Histórico importado não é editado pelo painel."""

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


class ItemInline(SomenteLeituraMixin, admin.TabularInline):
    model = ItemPedidoHistorico
    extra = 0
    fields = ("nome", "variante", "sku", "quantidade", "preco_unitario", "produto", "variacao")
    readonly_fields = fields


@admin.register(PedidoHistorico)
class PedidoHistoricoAdmin(SomenteLeituraMixin, admin.ModelAdmin):
    list_display = ("numero", "realizado_em", "cliente", "total", "status_pagamento", "status", "canal", "cupom")
    list_filter = ("status", "status_pagamento", "canal", "forma_pagamento")
    search_fields = ("=numero", "cupom", "cliente__nome", "cliente__email")
    date_hierarchy = "realizado_em"
    inlines = [ItemInline]
    list_select_related = ("cliente",)

    def changelist_view(self, request, extra_context=None):
        # Faturamento pago por ano: útil para acompanhar o teto do MEI.
        pagos = PedidoHistorico.objects.exclude(status="cancelled").filter(
            status_pagamento__in=["paid", "partially_paid", "partially_refunded"]
        )
        por_ano = (
            pagos.annotate(ano=ExtractYear("realizado_em"))
            .values("ano")
            .annotate(total=Sum("total"), pedidos=Count("id"))
            .order_by("-ano")
        )
        extra_context = {**(extra_context or {}), "faturamento_por_ano": list(por_ano)}
        return super().changelist_view(request, extra_context=extra_context)


@admin.register(MetricaMensal)
class MetricaMensalAdmin(SomenteLeituraMixin, admin.ModelAdmin):
    list_display = (
        "mes",
        "visitas",
        "visualizacoes_produto",
        "carrinhos",
        "checkouts",
        "vendas",
        "receita",
        "ticket_medio",
        "conversao",
    )
    date_hierarchy = "mes"


@admin.register(VisitasPorDimensao)
class VisitasPorDimensaoAdmin(SomenteLeituraMixin, admin.ModelAdmin):
    list_display = ("dimensao", "valor", "tipo", "visitas", "periodo_inicio", "periodo_fim")
    list_filter = ("dimensao", "tipo")
