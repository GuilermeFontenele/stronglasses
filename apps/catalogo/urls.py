from django.urls import path

from . import views

app_name = "catalogo"

urlpatterns = [
    path("", views.home, name="home"),
    path("produtos/<slug:slug>/", views.produto, name="produto"),
    path("busca/", views.busca, name="busca"),
    # Mesmo formato de URL de categoria da Nuvemshop (/masculino/). Fica por último.
    path("<slug:slug>/", views.categoria, name="categoria"),
]
