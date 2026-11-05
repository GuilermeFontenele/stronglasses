from django.contrib.sitemaps import Sitemap

from .models import Categoria
from .vitrine import produtos_visiveis


class HomeSitemap(Sitemap):
    priority = 1.0
    changefreq = "daily"

    def items(self):
        return ["/"]

    def location(self, item):
        return item


class ProdutoSitemap(Sitemap):
    priority = 0.8
    changefreq = "weekly"

    def items(self):
        return produtos_visiveis().order_by("pk")

    def lastmod(self, produto):
        return produto.atualizado_em


class CategoriaSitemap(Sitemap):
    priority = 0.6
    changefreq = "weekly"

    def items(self):
        return Categoria.objects.filter(ativa=True).order_by("pk")

    def location(self, categoria):
        return f"/{categoria.slug}/"


SITEMAPS = {"home": HomeSitemap, "produtos": ProdutoSitemap, "categorias": CategoriaSitemap}
