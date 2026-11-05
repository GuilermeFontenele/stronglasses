from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("clientes", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="cliente",
            name="nuvemshop_id",
            field=models.BigIntegerField(
                blank=True, editable=False, null=True, unique=True, verbose_name="ID na Nuvemshop"
            ),
        ),
        migrations.AlterField(
            model_name="consentimento",
            name="origem",
            field=models.CharField(
                choices=[
                    ("popup", "Popup de boas-vindas"),
                    ("cadastro", "Cadastro"),
                    ("checkout", "Checkout"),
                    ("painel", "Registrado pela loja"),
                    ("importacao", "Importado da Nuvemshop"),
                ],
                max_length=10,
                verbose_name="origem",
            ),
        ),
    ]
