from decimal import Decimal

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def auditoria():
    return [
        ("criado_em", models.DateTimeField(auto_now_add=True, verbose_name="criado em")),
        ("atualizado_em", models.DateTimeField(auto_now=True, verbose_name="atualizado em")),
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
    ]


def dinheiro(rotulo, **extra):
    return models.DecimalField(decimal_places=2, max_digits=extra.pop("max_digits", 10), verbose_name=rotulo, **extra)


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("catalogo", "0002_nuvemshop_id"),
        ("clientes", "0002_importacao_nuvemshop"),
    ]

    operations = [
        migrations.CreateModel(
            name="PedidoHistorico",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                *auditoria(),
                ("nuvemshop_id", models.BigIntegerField(editable=False, unique=True, verbose_name="ID na Nuvemshop")),
                ("numero", models.PositiveIntegerField(db_index=True, verbose_name="número")),
                ("realizado_em", models.DateTimeField(db_index=True, verbose_name="realizado em")),
                ("pago_em", models.DateTimeField(blank=True, null=True, verbose_name="pago em")),
                ("cancelado_em", models.DateTimeField(blank=True, null=True, verbose_name="cancelado em")),
                ("status", models.CharField(blank=True, max_length=20, verbose_name="status")),
                ("status_pagamento", models.CharField(blank=True, max_length=30, verbose_name="pagamento")),
                ("status_envio", models.CharField(blank=True, max_length=30, verbose_name="envio")),
                ("canal", models.CharField(blank=True, max_length=30, verbose_name="canal")),
                ("forma_pagamento", models.CharField(blank=True, max_length=80, verbose_name="forma de pagamento")),
                ("cupom", models.CharField(blank=True, db_index=True, max_length=60, verbose_name="cupom")),
                ("subtotal", dinheiro("subtotal", default=Decimal("0"))),
                ("desconto", dinheiro("desconto", default=Decimal("0"))),
                ("frete", dinheiro("frete", blank=True, null=True)),
                ("total", dinheiro("total", default=Decimal("0"))),
                ("cidade", models.CharField(blank=True, max_length=80, verbose_name="cidade")),
                ("uf", models.CharField(blank=True, max_length=40, verbose_name="estado")),
                (
                    "cliente",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="pedidos_historicos",
                        to="clientes.cliente",
                        verbose_name="cliente",
                    ),
                ),
            ],
            options={
                "verbose_name": "pedido (Nuvemshop)",
                "verbose_name_plural": "pedidos (Nuvemshop)",
                "ordering": ["-realizado_em"],
            },
        ),
        migrations.CreateModel(
            name="ItemPedidoHistorico",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nome", models.CharField(max_length=200, verbose_name="nome")),
                ("variante", models.CharField(blank=True, max_length=120, verbose_name="variante")),
                ("sku", models.CharField(blank=True, max_length=60, verbose_name="SKU")),
                ("quantidade", models.PositiveIntegerField(default=1, verbose_name="quantidade")),
                ("preco_unitario", dinheiro("preço unitário")),
                (
                    "pedido",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="itens",
                        to="historico.pedidohistorico",
                        verbose_name="pedido",
                    ),
                ),
                (
                    "produto",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="itens_historicos",
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
                        related_name="itens_historicos",
                        to="catalogo.variacao",
                        verbose_name="variação",
                    ),
                ),
            ],
            options={
                "verbose_name": "item do pedido",
                "verbose_name_plural": "itens do pedido",
                "ordering": ["pedido", "id"],
            },
        ),
        migrations.CreateModel(
            name="MetricaMensal",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                *auditoria(),
                ("mes", models.DateField(help_text="Primeiro dia do mês.", unique=True, verbose_name="mês")),
                ("visitas", models.PositiveIntegerField(default=0, verbose_name="visitas")),
                (
                    "visualizacoes_produto",
                    models.PositiveIntegerField(default=0, verbose_name="visitas que viram produto"),
                ),
                ("carrinhos", models.PositiveIntegerField(default=0, verbose_name="carrinhos criados")),
                ("checkouts", models.PositiveIntegerField(default=0, verbose_name="checkouts iniciados")),
                ("vendas", models.PositiveIntegerField(default=0, verbose_name="vendas pagas")),
                ("receita", dinheiro("receita", max_digits=12, default=Decimal("0"))),
                ("ticket_medio", dinheiro("ticket médio", blank=True, null=True)),
                (
                    "conversao",
                    models.DecimalField(
                        blank=True, decimal_places=2, max_digits=6, null=True, verbose_name="conversão (%)"
                    ),
                ),
                ("fonte", models.CharField(default="nuvemshop", max_length=30, verbose_name="fonte")),
            ],
            options={
                "verbose_name": "métrica mensal",
                "verbose_name_plural": "métricas mensais",
                "ordering": ["-mes"],
            },
        ),
        migrations.CreateModel(
            name="VisitasPorDimensao",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                *auditoria(),
                (
                    "dimensao",
                    models.CharField(
                        choices=[("origem", "Origem do tráfego"), ("dispositivo", "Dispositivo")],
                        max_length=12,
                        verbose_name="dimensão",
                    ),
                ),
                ("valor", models.CharField(max_length=80, verbose_name="valor")),
                (
                    "tipo",
                    models.CharField(blank=True, help_text="organic / paid", max_length=20, verbose_name="tipo"),
                ),
                ("visitas", models.PositiveIntegerField(default=0, verbose_name="visitas")),
                ("periodo_inicio", models.DateField(verbose_name="início do período")),
                ("periodo_fim", models.DateField(verbose_name="fim do período")),
            ],
            options={
                "verbose_name": "visitas por origem/dispositivo",
                "verbose_name_plural": "visitas por origem/dispositivo",
                "ordering": ["dimensao", "-visitas"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("dimensao", "valor", "tipo", "periodo_inicio", "periodo_fim"),
                        name="visitas_dimensao_unica",
                    )
                ],
            },
        ),
    ]
