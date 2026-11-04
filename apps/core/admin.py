from django.contrib import admin

from .auditoria import AuditoriaAdminMixin, RegistroAuditoriaAdmin  # noqa: F401 (registra o admin)
from .models import Parametro


@admin.register(Parametro)
class ParametroAdmin(AuditoriaAdminMixin, admin.ModelAdmin):
    list_display = ("chave", "valor", "tipo", "descricao", "atualizado_em", "atualizado_por")
    search_fields = ("chave", "descricao")
    readonly_fields = ("criado_em", "criado_por", "atualizado_em", "atualizado_por")

    def get_readonly_fields(self, request, obj=None):
        campos = list(super().get_readonly_fields(request, obj))
        if obj is not None:
            campos.append("chave")
        return campos
