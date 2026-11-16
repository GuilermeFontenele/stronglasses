import importlib
from decimal import Decimal

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

_catalogo = importlib.import_module("apps.catalogo.migrations.0001_initial")


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("vendas", "0003_pedido_site"),
    ]

    operations = [
        migrations.CreateModel(
            name="Pagamento",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                *_catalogo.auditoria(),
                ("provedor_id", models.CharField(max_length=40, unique=True, verbose_name="ID no Mercado Pago")),
                (
                    "metodo",
                    models.CharField(
                        choices=[("pix", "Pix"), ("credito", "Cartão de crédito")], max_length=10, verbose_name="forma"
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Aguardando pagamento"),
                            ("authorized", "Autorizado"),
                            ("in_process", "Em análise"),
                            ("in_mediation", "Em disputa"),
                            ("approved", "Aprovado"),
                            ("rejected", "Recusado"),
                            ("cancelled", "Cancelado"),
                            ("refunded", "Estornado"),
                            ("charged_back", "Contestado"),
                        ],
                        default="pending",
                        max_length=20,
                        verbose_name="situação",
                    ),
                ),
                ("status_detalhe", models.CharField(blank=True, max_length=80, verbose_name="detalhe")),
                (
                    "valor",
                    models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=10, verbose_name="valor"),
                ),
                ("parcelas", models.PositiveSmallIntegerField(default=1, verbose_name="parcelas")),
                ("bandeira", models.CharField(blank=True, max_length=30, verbose_name="bandeira")),
                ("pix_copia_e_cola", models.TextField(blank=True, verbose_name="Pix copia e cola")),
                ("pix_qr_base64", models.TextField(blank=True, verbose_name="QR Code do Pix (imagem)")),
                ("expira_em", models.DateTimeField(blank=True, null=True, verbose_name="expira em")),
                ("aprovado_em", models.DateTimeField(blank=True, null=True, verbose_name="aprovado em")),
                (
                    "pedido",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="pagamentos",
                        to="vendas.pedido",
                        verbose_name="pedido",
                    ),
                ),
            ],
            options={"verbose_name": "pagamento", "verbose_name_plural": "pagamentos", "ordering": ["-criado_em"]},
        ),
    ]
