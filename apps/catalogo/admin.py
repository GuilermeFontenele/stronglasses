from django.contrib import admin
from django.template.loader import render_to_string
from django.utils.html import format_html

from apps.core.auditoria import AuditoriaAdminMixin

from .models import AcabamentoArmacao, Banner, Categoria, CorLente, ImagemProduto, Produto, Variacao
from .templatetags.catalogo import dados_swatch


def _amostra(armacao, lente=None):
    return render_to_string("catalogo/partials/swatch.html", dados_swatch(armacao, lente))


@admin.register(Categoria)
class CategoriaAdmin(AuditoriaAdminMixin, admin.ModelAdmin):
    list_display = ("nome", "pai", "ativa", "ordem")
    list_editable = ("ativa", "ordem")
    search_fields = ("nome",)
    prepopulated_fields = {"slug": ("nome",)}


@admin.register(AcabamentoArmacao)
class AcabamentoArmacaoAdmin(AuditoriaAdminMixin, admin.ModelAdmin):
    list_display = ("amostra", "nome", "cor_hex", "ativo")
    list_display_links = ("nome",)
    search_fields = ("nome",)

    @admin.display(description="")
    def amostra(self, obj):
        return _amostra(obj)


@admin.register(CorLente)
class CorLenteAdmin(AuditoriaAdminMixin, admin.ModelAdmin):
    list_display = ("nome", "cor_hex", "ativo")
    search_fields = ("nome",)


class VariacaoInline(admin.TabularInline):
    model = Variacao
    extra = 0
    fields = ("amostra", "armacao", "lente", "sku", "preco", "estoque", "ativa", "ordem")
    readonly_fields = ("amostra",)
    autocomplete_fields = ("armacao", "lente")

    @admin.display(description="")
    def amostra(self, obj):
        return _amostra(obj.armacao, obj.lente) if obj.pk else ""


class ImagemInline(admin.TabularInline):
    model = ImagemProduto
    extra = 0
    fields = ("imagem", "variacao", "texto_alternativo", "ordem")


@admin.register(Produto)
class ProdutoAdmin(AuditoriaAdminMixin, admin.ModelAdmin):
    list_display = ("nome", "tipo", "publico", "preco", "ativo", "destaque", "pronto_envio")
    list_filter = ("ativo", "destaque", "tipo", "publico", "categorias")
    search_fields = ("nome", "slug", "variacoes__sku")
    prepopulated_fields = {"slug": ("nome",)}
    filter_horizontal = ("categorias",)
    inlines = [VariacaoInline, ImagemInline]
    readonly_fields = ("criado_em", "criado_por", "atualizado_em", "atualizado_por")
    fieldsets = (
        (None, {"fields": ("nome", "slug", "tipo", "publico", "formato", "descricao", "categorias")}),
        ("Preço", {"fields": ("preco", "preco_comparativo")}),
        ("Envio", {"fields": ("peso_g", ("altura_cm", "largura_cm", "comprimento_cm"))}),
        ("Publicação", {"fields": ("ativo", "destaque", "seo_titulo", "seo_descricao")}),
        ("Auditoria", {"classes": ("collapse",), "fields": readonly_fields}),
    )

    @admin.display(boolean=True, description="Pronto p/ envio")
    def pronto_envio(self, obj):
        return obj.pronto_para_envio


@admin.register(Banner)
class BannerAdmin(AuditoriaAdminMixin, admin.ModelAdmin):
    list_display = ("miniatura", "titulo", "tem_versao_celular", "ativo", "ordem", "inicio", "fim")
    list_display_links = ("titulo",)
    list_editable = ("ativo", "ordem")
    list_filter = ("ativo",)

    @admin.display(description="imagem")
    def miniatura(self, obj):
        if not obj.imagem:
            return "—"
        return format_html('<img src="{}" alt="" width="120" height="50" class="miniatura-banner">', obj.imagem.url)

    @admin.display(description="versão celular", boolean=True)
    def tem_versao_celular(self, obj):
        return bool(obj.imagem_mobile)
