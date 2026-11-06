from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("vendas", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="pedido",
            name="frete_servico_id",
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name="serviço de frete (ID)"),
        ),
        migrations.AddField(
            model_name="pedido",
            name="frete_servico",
            field=models.CharField(blank=True, max_length=80, verbose_name="serviço de frete"),
        ),
    ]
