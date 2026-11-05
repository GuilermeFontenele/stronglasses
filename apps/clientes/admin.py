import json

from django.contrib import admin
from django.http import HttpResponse

from apps.core.auditoria import AuditoriaAdminMixin
from apps.core.crypto import hash_busca
from apps.core.validators import so_digitos

from .lgpd import exportar_dados
from .models import Cliente, Consentimento, Endereco


class ConsentimentoInline(admin.TabularInline):
    model = Consentimento
    extra = 0
    can_delete = False
    fields = ("finalidade", "concedido", "versao_politica", "origem", "registrado_em", "revogado_em")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


class EnderecoInline(admin.StackedInline):
    model = Endereco
    extra = 0
    fields = (
        "padrao",
        "destinatario",
        ("cep", "pais"),
        ("logradouro", "numero"),
        ("complemento", "bairro"),
        ("cidade", "uf"),
    )


@admin.register(Cliente)
class ClienteAdmin(AuditoriaAdminMixin, admin.ModelAdmin):
    list_display = ("nome", "tipo", "email", "whatsapp", "documento_mascarado", "criado_em", "anonimizado_em")
    list_filter = ("tipo", "anonimizado_em")
    search_fields = ("nome", "email", "whatsapp")
    readonly_fields = ("uuid", "criado_em", "criado_por", "atualizado_em", "atualizado_por", "anonimizado_em")
    inlines = [EnderecoInline, ConsentimentoInline]
    actions = ["exportar_lgpd"]

    @admin.display(description="CPF/CNPJ")
    def documento_mascarado(self, obj):
        return obj.documento_mascarado

    def get_search_results(self, request, queryset, search_term):
        resultado, tem_duplicados = super().get_search_results(request, queryset, search_term)
        digitos = so_digitos(search_term)
        if len(digitos) in (11, 14):
            # Busca por CPF/CNPJ via hash: o documento nunca é comparado em claro.
            resultado |= queryset.filter(documento_hash=hash_busca(digitos))
        return resultado, tem_duplicados

    @admin.action(description="Exportar dados do titular (LGPD)")
    def exportar_lgpd(self, request, queryset):
        dados = [exportar_dados(cliente, request.user) for cliente in queryset]
        resposta = HttpResponse(
            json.dumps(dados, ensure_ascii=False, indent=2), content_type="application/json; charset=utf-8"
        )
        resposta["Content-Disposition"] = 'attachment; filename="dados-titular.json"'
        resposta["Cache-Control"] = "no-store"
        return resposta
