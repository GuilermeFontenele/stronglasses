from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("saude/", views.saude, name="saude"),
    path(".well-known/security.txt", views.security_txt, name="security_txt"),
]
