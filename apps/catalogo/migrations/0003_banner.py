import importlib

from django.conf import settings
from django.db import migrations, models

import apps.catalogo.models

_inicial = importlib.import_module("apps.catalogo.migrations.0001_initial")


class Migration(migrations.Migration):
    dependencies = [
        ("catalogo", "0002_nuvemshop_id"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Banner",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                *_inicial.auditoria(),
                (
                    "titulo",
                    models.CharField(
                        help_text="O que aparece na imagem (acessibilidade e Google).",
                        max_length=150,
                        verbose_name="descrição da imagem",
                    ),
                ),
                (
                    "imagem",
                    models.ImageField(
                        help_text="Sugestão: 1920 x 800 px.",
                        upload_to=apps.catalogo.models.caminho_banner,
                        validators=_inicial.validadores_imagem(),
                        verbose_name="imagem (computador)",
                    ),
                ),
                (
                    "imagem_mobile",
                    models.ImageField(
                        blank=True,
                        help_text="Opcional. Sugestão: 1080 x 1350 px. Vazio = usa a do computador.",
                        upload_to=apps.catalogo.models.caminho_banner,
                        validators=_inicial.validadores_imagem(),
                        verbose_name="imagem (celular)",
                    ),
                ),
                (
                    "link",
                    models.CharField(
                        blank=True,
                        help_text="Ex.: /masculino/",
                        max_length=300,
                        validators=[apps.catalogo.models.validar_link_banner],
                        verbose_name="link",
                    ),
                ),
                ("ativo", models.BooleanField(default=True, verbose_name="ativo")),
                ("inicio", models.DateTimeField(blank=True, null=True, verbose_name="mostrar a partir de")),
                ("fim", models.DateTimeField(blank=True, null=True, verbose_name="mostrar até")),
                ("ordem", models.PositiveSmallIntegerField(default=0, verbose_name="ordem")),
            ],
            options={"verbose_name": "banner", "verbose_name_plural": "banners", "ordering": ["ordem", "-id"]},
        ),
    ]
