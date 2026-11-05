import importlib

from django.db import migrations, models

import apps.catalogo.models

_inicial = importlib.import_module("apps.catalogo.migrations.0001_initial")


class Migration(migrations.Migration):
    dependencies = [("catalogo", "0003_banner")]

    operations = [
        migrations.AlterField(
            model_name="banner",
            name="imagem",
            field=models.ImageField(
                help_text="Formato computador: 1920 x 800 px (proporção 12:5), JPG ou WEBP de até 500 KB.",
                upload_to=apps.catalogo.models.caminho_banner,
                validators=_inicial.validadores_imagem(),
                verbose_name="imagem (computador)",
            ),
        ),
        migrations.AlterField(
            model_name="banner",
            name="imagem_mobile",
            field=models.ImageField(
                help_text="Formato celular: 1080 x 1350 px (proporção 4:5, igual ao post vertical do Instagram).",
                upload_to=apps.catalogo.models.caminho_banner,
                validators=_inicial.validadores_imagem(),
                verbose_name="imagem (celular)",
            ),
        ),
    ]
