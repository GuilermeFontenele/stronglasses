import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("clientes", "0002_importacao_nuvemshop"),
    ]

    operations = [
        migrations.CreateModel(
            name="Endereco",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("criado_em", models.DateTimeField(auto_now_add=True, verbose_name="criado em")),
                ("atualizado_em", models.DateTimeField(auto_now=True, verbose_name="atualizado em")),
                ("destinatario", models.CharField(blank=True, max_length=150, verbose_name="destinatário")),
                (
                    "cep",
                    models.CharField(
                        max_length=8,
                        validators=[django.core.validators.RegexValidator("^\\d{8}$", "CEP com 8 dígitos.")],
                        verbose_name="CEP",
                    ),
                ),
                ("logradouro", models.CharField(max_length=200, verbose_name="logradouro")),
                ("numero", models.CharField(blank=True, max_length=20, verbose_name="número")),
                ("complemento", models.CharField(blank=True, max_length=120, verbose_name="complemento")),
                ("bairro", models.CharField(blank=True, max_length=100, verbose_name="bairro")),
                ("cidade", models.CharField(max_length=100, verbose_name="cidade")),
                ("uf", models.CharField(max_length=40, verbose_name="estado")),
                ("pais", models.CharField(default="BR", max_length=2, verbose_name="país")),
                ("padrao", models.BooleanField(default=False, verbose_name="endereço padrão")),
                (
                    "atualizado_por",
                    models.ForeignKey(
                        blank=True,
                        editable=False,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="atualizado por",
                    ),
                ),
                (
                    "cliente",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="enderecos",
                        to="clientes.cliente",
                        verbose_name="cliente",
                    ),
                ),
                (
                    "criado_por",
                    models.ForeignKey(
                        blank=True,
                        editable=False,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="criado por",
                    ),
                ),
            ],
            options={
                "verbose_name": "endereço",
                "verbose_name_plural": "endereços",
                "ordering": ["-padrao", "-atualizado_em"],
            },
        ),
    ]
