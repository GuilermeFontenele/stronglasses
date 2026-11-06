from django.apps import AppConfig


class GestaoConfig(AppConfig):
    name = "apps.gestao"
    verbose_name = "Painel de gestão"

    def ready(self):
        from django.contrib import admin

        from .acesso import login_do_admin

        # O admin técnico usa o mesmo login do painel (com limite de tentativas).
        admin.site.login = login_do_admin
