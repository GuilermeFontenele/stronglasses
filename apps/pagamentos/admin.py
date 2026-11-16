from django.contrib import admin

from apps.core.auditoria import AuditoriaAdminMixin

from .models import Pagamento


@admin.register(Pagamento)
class PagamentoAdmin(AuditoriaAdminMixin, admin.ModelAdmin):
    """Só leitura: quem muda a situação é o Mercado Pago (webhook e consulta)."""

    list_display = ("pedido", "metodo", "status", "valor", "parcelas", "provedor_id", "criado_em")
    list_filter = ("metodo", "status")
    search_fields = ("provedor_id", "pedido__numero")
    exclude = ("pix_qr_base64",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
