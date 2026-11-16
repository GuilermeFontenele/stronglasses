from django.urls import path

from . import views

app_name = "pagamentos"

urlpatterns = [
    path("finalizar/", views.finalizar, name="finalizar"),
    path("finalizar/frete/", views.frete, name="frete"),
    path("pedido/<str:token>/", views.pedido, name="pedido"),
    path("pedido/<str:token>/situacao/", views.situacao, name="situacao"),
    path("pedido/<str:token>/pix/", views.gerar_pix, name="gerar_pix"),
    path("pedido/<str:token>/pagar/", views.pagar, name="pagar"),
    path("pedido/<str:token>/cartao/", views.cartao, name="cartao"),
    path("pedido/<str:token>/refazer/", views.refazer, name="refazer"),
    path("pagamentos/mercadopago/webhook/", views.webhook, name="webhook"),
]
