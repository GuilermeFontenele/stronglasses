from django.urls import path

from . import views, views_vendas

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
    path("clientes/novo/", views_vendas.cliente_novo, name="cliente_novo"),
    path("clientes/<int:pk>/", views.cliente, name="cliente"),
    path("clientes/<int:pk>/documento/", views.cliente_documento, name="cliente_documento"),
    path("clientes/<int:pk>/exportar/", views.cliente_exportar, name="cliente_exportar"),
    path("clientes/<int:pk>/anonimizar/", views.cliente_anonimizar, name="cliente_anonimizar"),
    path("vendas/", views_vendas.vendas, name="vendas"),
    path("vendas/nova/", views_vendas.venda_nova, name="venda_nova"),
    path("vendas/<int:pk>/", views_vendas.venda, name="venda"),
    path("vendas/<int:pk>/etiqueta/", views_vendas.venda_etiqueta, name="venda_etiqueta"),
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
