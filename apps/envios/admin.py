from django.contrib import admin

from apps.core.auditoria import AuditoriaAdminMixin

from .models import Envio


@admin.register(Envio)
class EnvioAdmin(AuditoriaAdminMixin, admin.ModelAdmin):
    """Bastidor técnico, só leitura: etiquetas se compram e cancelam pelo painel (ficha da venda)."""

    list_display = ("pedido", "transportadora", "servico", "status", "rastreio", "preco", "ambiente", "criado_em")
    list_filter = ("status", "transportadora", "ambiente")
    search_fields = ("me_id", "rastreio", "pedido__numero")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
