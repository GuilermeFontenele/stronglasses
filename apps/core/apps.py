from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "apps.core"
    label = "core"
    verbose_name = "Núcleo"

    def ready(self):
        from . import parametros  # noqa: F401 (conecta os sinais de cache)
