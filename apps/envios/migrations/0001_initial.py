import importlib
from decimal import Decimal

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import apps.core.fields

_catalogo = importlib.import_module("apps.catalogo.migrations.0001_initial")
AMBIENTES = [("sandbox", "Testes (sandbox)"), ("producao", "Produção")]


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("vendas", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ConexaoMelhorEnvio",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                *_catalogo.auditoria(),
                ("ambiente", models.CharField(choices=AMBIENTES, max_length=10, unique=True, verbose_name="ambiente")),
                ("access_token", apps.core.fields.EncryptedTextField(blank=True, verbose_name="token de acesso")),
                ("refresh_token", apps.core.fields.EncryptedTextField(blank=True, verbose_name="token de renovação")),
                ("expira_em", models.DateTimeField(blank=True, null=True, verbose_name="expira em")),
                (
                    "conta",
                    models.CharField(
                        blank=True, help_text="Nome da conta no Melhor Envio.", max_length=150, verbose_name="conta"
                    ),
                ),
            ],
            options={"verbose_name": "conexão com o Melhor Envio", "verbose_name_plural": "conexões com o Melhor Envio"},
        ),
        migrations.CreateModel(
            name="Envio",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                *_catalogo.auditoria(),
                ("ambiente", models.CharField(choices=AMBIENTES, max_length=10, verbose_name="ambiente")),
                ("me_id", models.CharField(max_length=64, unique=True, verbose_name="ID no Melhor Envio")),
                ("protocolo", models.CharField(blank=True, max_length=40, verbose_name="protocolo")),
                ("transportadora", models.CharField(max_length=60, verbose_name="transportadora")),
                ("servico", models.CharField(max_length=60, verbose_name="serviço")),
                ("servico_id", models.PositiveIntegerField(verbose_name="ID do serviço")),
                (
                    "preco",
                    models.DecimalField(
                        decimal_places=2, default=Decimal("0.00"), max_digits=10, verbose_name="preço da etiqueta"
                    ),
                ),
                ("prazo_dias", models.PositiveSmallIntegerField(blank=True, null=True, verbose_name="prazo (dias úteis)")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("carrinho", "Aguardando pagamento"),
                            ("pago", "Paga (gerando etiqueta)"),
                            ("gerado", "Etiqueta pronta"),
                            ("postado", "Postado"),
                            ("entregue", "Entregue"),
                            ("cancelado", "Cancelada"),
                        ],
                        default="carrinho",
                        max_length=10,
                        verbose_name="situação",
                    ),
                ),
                ("rastreio", models.CharField(blank=True, max_length=40, verbose_name="código de rastreio")),
                ("com_nota_fiscal", models.BooleanField(default=False, verbose_name="com nota fiscal")),
                ("erro", models.CharField(blank=True, max_length=255, verbose_name="último erro")),
                ("pago_em", models.DateTimeField(blank=True, null=True, verbose_name="paga em")),
                ("gerado_em", models.DateTimeField(blank=True, null=True, verbose_name="gerada em")),
                ("postado_em", models.DateTimeField(blank=True, null=True, verbose_name="postada em")),
                ("entregue_em", models.DateTimeField(blank=True, null=True, verbose_name="entregue em")),
                ("cancelado_em", models.DateTimeField(blank=True, null=True, verbose_name="cancelada em")),
                (
                    "pedido",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="envios",
                        to="vendas.pedido",
                        verbose_name="venda",
                    ),
                ),
            ],
            options={
                "verbose_name": "etiqueta de envio",
                "verbose_name_plural": "etiquetas de envio",
                "ordering": ["-criado_em"],
            },
        ),
    ]
