from django.urls import path

from . import views

app_name = "carrinho"

urlpatterns = [
    path("", views.ver, name="ver"),
    path("adicionar/", views.adicionar, name="adicionar"),
    path("atualizar/", views.atualizar, name="atualizar"),
    path("remover/", views.remover, name="remover"),
]
