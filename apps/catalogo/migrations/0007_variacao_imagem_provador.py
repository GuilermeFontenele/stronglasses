from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("catalogo", "0006_categoria_acessorios")]

    operations = [
        migrations.AddField(
            model_name="variacao",
            name="imagem_provador",
            field=models.ImageField(
                blank=True,
                help_text="Foto de frente, sem fundo e sem hastes. Gerada sozinha a partir da primeira foto da cor.",
                upload_to="provador/",
                verbose_name="imagem do provador",
            ),
        ),
    ]
