import importlib
from decimal import Decimal

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

_catalogo = importlib.import_module("apps.catalogo.migrations.0001_initial")

UFS = [
    ("AC", "Acre"), ("AL", "Alagoas"), ("AM", "Amazonas"), ("AP", "Amapá"), ("BA", "Bahia"), ("CE", "Ceará"),
    ("DF", "Distrito Federal"), ("ES", "Espírito Santo"), ("GO", "Goiás"), ("MA", "Maranhão"),
    ("MG", "Minas Gerais"), ("MS", "Mato Grosso do Sul"), ("MT", "Mato Grosso"), ("PA", "Pará"),
    ("PB", "Paraíba"), ("PE", "Pernambuco"), ("PI", "Piauí"), ("PR", "Paraná"), ("RJ", "Rio de Janeiro"),
    ("RN", "Rio Grande do Norte"), ("RO", "Rondônia"), ("RR", "Roraima"), ("RS", "Rio Grande do Sul"),
    ("SC", "Santa Catarina"), ("SE", "Sergipe"), ("SP", "São Paulo"), ("TO", "Tocantins"),
]  # fmt: skip


def _dinheiro(nome, minimo=False):
    validadores = [django.core.validators.MinValueValidator(Decimal("0.00"))] if minimo else []
    return models.DecimalField(
        decimal_places=2, default=Decimal("0.00"), max_digits=10, validators=validadores, verbose_name=nome
    )


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("catalogo", "0006_categoria_acessorios"),
        ("clientes", "0003_endereco"),
    ]

    operations = [
        migrations.CreateModel(
            name="Pedido",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                *_catalogo.auditoria(),
                ("numero", models.PositiveIntegerField(editable=False, unique=True, verbose_name="número")),
                ("realizado_em", models.DateTimeField(verbose_name="data da venda")),
                (
                    "canal",
                    models.CharField(
                        choices=[
                            ("whatsapp", "WhatsApp"),
                            ("presencial", "Pessoalmente"),
                            ("hotel", "Hotel"),
                            ("barbearia", "Barbearia"),
                            ("instagram", "Instagram"),
                            ("site", "Site"),
                            ("outro", "Outro"),
                        ],
                        default="whatsapp",
                        max_length=20,
                        verbose_name="canal",
                    ),
                ),
                (
                    "parceiro",
                    models.CharField(
                        blank=True,
                        help_text="Hotel, barbearia ou pessoa que vendeu/indicou.",
                        max_length=120,
                        verbose_name="parceiro",
                    ),
                ),
                ("ref", models.CharField(blank=True, max_length=60, verbose_name="referência")),
                ("cupom", models.CharField(blank=True, max_length=40, verbose_name="cupom")),
                ("utm_source", models.CharField(blank=True, max_length=100, verbose_name="utm_source")),
                ("utm_medium", models.CharField(blank=True, max_length=100, verbose_name="utm_medium")),
                ("utm_campaign", models.CharField(blank=True, max_length=100, verbose_name="utm_campaign")),
                (
                    "situacao",
                    models.CharField(
                        choices=[
                            ("pendente", "Aguardando pagamento"),
                            ("pago", "Pago"),
                            ("enviado", "Enviado"),
                            ("entregue", "Entregue"),
                            ("cancelado", "Cancelado"),
                        ],
                        default="pago",
                        max_length=12,
                        verbose_name="situação",
                    ),
                ),
                (
                    "forma_pagamento",
                    models.CharField(
                        choices=[
                            ("pix", "Pix"),
                            ("dinheiro", "Dinheiro"),
                            ("credito", "Cartão de crédito"),
                            ("debito", "Cartão de débito"),
                            ("link", "Link de pagamento"),
                            ("outro", "Outro"),
                        ],
                        max_length=12,
                        verbose_name="forma de pagamento",
                    ),
                ),
                (
                    "parcelas",
                    models.PositiveSmallIntegerField(
                        default=1, validators=[django.core.validators.MinValueValidator(1)], verbose_name="parcelas"
                    ),
                ),
                ("subtotal", _dinheiro("subtotal")),
                ("desconto", _dinheiro("desconto", minimo=True)),
                ("desconto_pix", _dinheiro("desconto Pix")),
                ("frete", _dinheiro("frete", minimo=True)),
                ("total", _dinheiro("total")),
                (
                    "entrega",
                    models.CharField(
                        choices=[
                            ("maos", "Entregue em mãos"),
                            ("motoboy", "Motoboy"),
                            ("correios", "Correios"),
                            ("transportadora", "Transportadora"),
                        ],
                        default="maos",
                        max_length=16,
                        verbose_name="entrega",
                    ),
                ),
                ("destinatario", models.CharField(blank=True, max_length=150, verbose_name="destinatário")),
                (
                    "cep",
                    models.CharField(
                        blank=True,
                        max_length=8,
                        validators=[django.core.validators.RegexValidator("^\\d{8}$", "CEP com 8 dígitos.")],
                        verbose_name="CEP",
                    ),
                ),
                ("logradouro", models.CharField(blank=True, max_length=200, verbose_name="logradouro")),
                ("numero_endereco", models.CharField(blank=True, max_length=20, verbose_name="número")),
                ("complemento", models.CharField(blank=True, max_length=120, verbose_name="complemento")),
                ("bairro", models.CharField(blank=True, max_length=100, verbose_name="bairro")),
                ("cidade", models.CharField(blank=True, max_length=100, verbose_name="cidade")),
                ("uf", models.CharField(blank=True, choices=UFS, max_length=2, verbose_name="estado")),
                ("codigo_rastreio", models.CharField(blank=True, max_length=40, verbose_name="código de rastreio")),
                ("peso_g", models.PositiveIntegerField(blank=True, null=True, verbose_name="peso do pacote (g)")),
                ("observacoes", models.TextField(blank=True, verbose_name="observações")),
                ("estoque_baixado", models.BooleanField(default=False, editable=False, verbose_name="estoque baixado")),
                ("pago_em", models.DateTimeField(blank=True, editable=False, null=True, verbose_name="pago em")),
                ("enviado_em", models.DateTimeField(blank=True, editable=False, null=True, verbose_name="enviado em")),
                (
                    "cancelado_em",
                    models.DateTimeField(blank=True, editable=False, null=True, verbose_name="cancelado em"),
                ),
                (
                    "cliente",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="vendas",
                        to="clientes.cliente",
                        verbose_name="cliente",
                    ),
                ),
            ],
            options={
                "verbose_name": "venda",
                "verbose_name_plural": "vendas",
                "ordering": ["-realizado_em", "-numero"],
                "permissions": [("imprimir_etiqueta", "Pode imprimir etiqueta e declaração de conteúdo")],
            },
        ),
        migrations.CreateModel(
            name="ItemPedido",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                *_catalogo.auditoria(),
                ("nome", models.CharField(max_length=150, verbose_name="produto")),
                ("cor", models.CharField(blank=True, max_length=150, verbose_name="cor")),
                ("sku", models.CharField(blank=True, max_length=40, verbose_name="SKU")),
                (
                    "quantidade",
                    models.PositiveSmallIntegerField(
                        validators=[django.core.validators.MinValueValidator(1)], verbose_name="quantidade"
                    ),
                ),
                (
                    "preco_unitario",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=10,
                        validators=[django.core.validators.MinValueValidator(Decimal("0.00"))],
                        verbose_name="preço unitário",
                    ),
                ),
                (
                    "pedido",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="itens",
                        to="vendas.pedido",
                        verbose_name="venda",
                    ),
                ),
                (
                    "produto",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="catalogo.produto",
                        verbose_name="produto",
                    ),
                ),
                (
                    "variacao",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="catalogo.variacao",
                        verbose_name="variação",
                    ),
                ),
            ],
            options={"verbose_name": "item da venda", "verbose_name_plural": "itens da venda", "ordering": ["id"]},
        ),
    ]
