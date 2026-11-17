from django.db import migrations, models

import apps.core.fields


class Migration(migrations.Migration):
    dependencies = [("vendas", "0003_pedido_site")]

    operations = [
        migrations.AddField(
            model_name="pedido",
            name="email",
            field=models.EmailField(blank=True, max_length=254, verbose_name="e-mail do comprador"),
        ),
        migrations.AddField(
            model_name="pedido",
            name="whatsapp",
            field=models.CharField(blank=True, max_length=16, verbose_name="WhatsApp do comprador"),
        ),
        migrations.AddField(
            model_name="pedido",
            name="documento",
            field=apps.core.fields.EncryptedTextField(
                blank=True, help_text="Guardado criptografado.", verbose_name="CPF/CNPJ do comprador"
            ),
        ),
    ]
