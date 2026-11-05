from django.apps import AppConfig


class CatalogoConfig(AppConfig):
    name = "apps.catalogo"
    label = "catalogo"
    verbose_name = "Catálogo"

    def ready(self):
        from . import signals  # noqa: F401 (redireciona slugs antigos)
