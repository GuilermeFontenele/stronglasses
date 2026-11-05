from django.db import migrations, models


def campo():
    return models.BigIntegerField(blank=True, editable=False, null=True, unique=True, verbose_name="ID na Nuvemshop")


class Migration(migrations.Migration):
    dependencies = [("catalogo", "0001_initial")]

    operations = [
        migrations.AddField(model_name="categoria", name="nuvemshop_id", field=campo()),
        migrations.AddField(model_name="produto", name="nuvemshop_id", field=campo()),
        migrations.AddField(model_name="variacao", name="nuvemshop_id", field=campo()),
        migrations.AddField(model_name="imagemproduto", name="nuvemshop_id", field=campo()),
    ]
