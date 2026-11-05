import django.core.validators
from django.db import migrations, models

import apps.catalogo.models


def _video(nome, ajuda):
    return models.FileField(
        blank=True,
        help_text=ajuda,
        upload_to=apps.catalogo.models.caminho_banner,
        validators=[
            django.core.validators.FileExtensionValidator(["mp4", "webm"]),
            apps.catalogo.models.validar_video,
        ],
        verbose_name=nome,
    )


class Migration(migrations.Migration):
    dependencies = [("catalogo", "0004_banner_mobile_obrigatorio")]

    operations = [
        migrations.AddField(
            model_name="banner",
            name="video",
            field=_video(
                "vídeo (computador)",
                "Opcional. MP4 de até 30 MB, 1920 x 800, sem som (toca mudo e em loop). "
                "As imagens acima viram a capa enquanto o vídeo carrega.",
            ),
        ),
        migrations.AddField(
            model_name="banner",
            name="video_mobile",
            field=_video(
                "vídeo (celular)",
                "Opcional. MP4 vertical 1080 x 1350. Vazio = o celular usa o vídeo do computador, centralizado.",
            ),
        ),
    ]
