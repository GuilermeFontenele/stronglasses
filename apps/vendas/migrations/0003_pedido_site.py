from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("vendas", "0002_frete_servico")]

    operations = [
        migrations.AddField(
            model_name="pedido",
            name="token_acesso",
            field=models.CharField(
                blank=True,
                editable=False,
                max_length=64,
                null=True,
                unique=True,
                verbose_name="token de acompanhamento",
            ),
        ),
        migrations.AddField(
            model_name="pedido",
            name="expira_em",
            field=models.DateTimeField(blank=True, null=True, verbose_name="pagar até"),
        ),
    ]
