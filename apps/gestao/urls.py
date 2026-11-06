from django.urls import path

from . import views

app_name = "gestao"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("entrar/", views.entrar, name="entrar"),
    path("sair/", views.sair, name="sair"),
    path("produtos/", views.produtos, name="produtos"),
    path("produtos/novo/", views.produto_editar, name="produto_novo"),
    path("produtos/<int:pk>/", views.produto_editar, name="produto"),
    path("estoque/", views.estoque, name="estoque"),
    path("clientes/", views.clientes, name="clientes"),
    path("clientes/<int:pk>/", views.cliente, name="cliente"),
    path("clientes/<int:pk>/documento/", views.cliente_documento, name="cliente_documento"),
    path("clientes/<int:pk>/exportar/", views.cliente_exportar, name="cliente_exportar"),
    path("clientes/<int:pk>/anonimizar/", views.cliente_anonimizar, name="cliente_anonimizar"),
    path("pedidos/", views.pedidos, name="pedidos"),
    path("pedidos/<int:pk>/", views.pedido, name="pedido"),
    path("banners/", views.banners, name="banners"),
    path("banners/novo/", views.banner_editar, name="banner_novo"),
    path("banners/<int:pk>/", views.banner_editar, name="banner"),
    path("paginas/", views.paginas, name="paginas"),
    path("paginas/nova/", views.pagina_editar, name="pagina_nova"),
    path("paginas/<int:pk>/", views.pagina_editar, name="pagina"),
    path("configuracoes/", views.configuracoes, name="configuracoes"),
]
