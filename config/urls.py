from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path, re_path
from django.views.static import serve

from apps.catalogo.sitemaps import SITEMAPS
from apps.catalogo.views import robots_txt

admin.site.site_header = "Strong Glasses · Painel"
admin.site.site_title = "Strong Glasses"
admin.site.index_title = "Administração da loja"

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    path("", include("apps.core.urls")),
    path("sitemap.xml", sitemap, {"sitemaps": SITEMAPS}, name="sitemap"),
    path("robots.txt", robots_txt, name="robots"),
    path("carrinho/", include("apps.carrinho.urls")),
    path("", include("apps.catalogo.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
elif settings.DJANGO_SERVIR_MEDIA:
    # static() não funciona com DEBUG=False; serve direto (bom o bastante para homologação e baixo tráfego).
    urlpatterns += [
        re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
    ]
