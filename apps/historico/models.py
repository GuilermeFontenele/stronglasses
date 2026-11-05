"""Vendas e métricas anteriores ao sistema próprio (importadas da Nuvemshop).

Ficam separadas dos pedidos novos: são só leitura, servem para relatórios, para o
limite de faturamento do MEI e para atender pedidos de acesso do titular (LGPD).
Por minimização, guardamos apenas cidade/UF da entrega, nunca o endereço completo.
"""

from decimal import Decimal

from django.db import models

from apps.core.models import AuditModel

STATUS_PAGOS = {"paid", "partially_paid", "partially_refunded"}


class PedidoHistorico(AuditModel):
    nuvemshop_id = models.BigIntegerField("ID na Nuvemshop", unique=True, editable=False)
    numero = models.PositiveIntegerField("número", db_index=True)
    cliente = models.ForeignKey(
        "clientes.Cliente",
        verbose_name="cliente",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pedidos_historicos",
    )
    realizado_em = models.DateTimeField("realizado em", db_index=True)
    pago_em = models.DateTimeField("pago em", null=True, blank=True)
    cancelado_em = models.DateTimeField("cancelado em", null=True, blank=True)
    status = models.CharField("status", max_length=20, blank=True)
    status_pagamento = models.CharField("pagamento", max_length=30, blank=True)
    status_envio = models.CharField("envio", max_length=30, blank=True)
    canal = models.CharField("canal", max_length=30, blank=True)
    forma_pagamento = models.CharField("forma de pagamento", max_length=80, blank=True)
    cupom = models.CharField("cupom", max_length=60, blank=True, db_index=True)
    subtotal = models.DecimalField("subtotal", max_digits=10, decimal_places=2, default=Decimal("0"))
    desconto = models.DecimalField("desconto", max_digits=10, decimal_places=2, default=Decimal("0"))
    frete = models.DecimalField("frete", max_digits=10, decimal_places=2, null=True, blank=True)
    total = models.DecimalField("total", max_digits=10, decimal_places=2, default=Decimal("0"))
    cidade = models.CharField("cidade", max_length=80, blank=True)
    uf = models.CharField("estado", max_length=40, blank=True)

    class Meta:
        ordering = ["-realizado_em"]
        verbose_name = "pedido (Nuvemshop)"
        verbose_name_plural = "pedidos (Nuvemshop)"

    def __str__(self):
        return f"#{self.numero}"

    @property
    def pago(self) -> bool:
        return self.status != "cancelled" and self.status_pagamento in STATUS_PAGOS


class ItemPedidoHistorico(models.Model):
    pedido = models.ForeignKey(PedidoHistorico, verbose_name="pedido", on_delete=models.CASCADE, related_name="itens")
    produto = models.ForeignKey(
        "catalogo.Produto",
        verbose_name="produto",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="itens_historicos",
    )
    variacao = models.ForeignKey(
        "catalogo.Variacao",
        verbose_name="variação",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="itens_historicos",
    )
    nome = models.CharField("nome", max_length=200)
    variante = models.CharField("variante", max_length=120, blank=True)
    sku = models.CharField("SKU", max_length=60, blank=True)
    quantidade = models.PositiveIntegerField("quantidade", default=1)
    preco_unitario = models.DecimalField("preço unitário", max_digits=10, decimal_places=2)

    class Meta:
        ordering = ["pedido", "id"]
        verbose_name = "item do pedido"
        verbose_name_plural = "itens do pedido"

    def __str__(self):
        return f"{self.quantidade}x {self.nome}"


class MetricaMensal(AuditModel):
    """Funil e vendas por mês, como a Nuvemshop calculava (visitas não vêm da API)."""

    mes = models.DateField("mês", unique=True, help_text="Primeiro dia do mês.")
    visitas = models.PositiveIntegerField("visitas", default=0)
    visualizacoes_produto = models.PositiveIntegerField("visitas que viram produto", default=0)
    carrinhos = models.PositiveIntegerField("carrinhos criados", default=0)
    checkouts = models.PositiveIntegerField("checkouts iniciados", default=0)
    vendas = models.PositiveIntegerField("vendas pagas", default=0)
    receita = models.DecimalField("receita", max_digits=12, decimal_places=2, default=Decimal("0"))
    ticket_medio = models.DecimalField("ticket médio", max_digits=10, decimal_places=2, null=True, blank=True)
    conversao = models.DecimalField("conversão (%)", max_digits=6, decimal_places=2, null=True, blank=True)
    fonte = models.CharField("fonte", max_length=30, default="nuvemshop")

    class Meta:
        ordering = ["-mes"]
        verbose_name = "métrica mensal"
        verbose_name_plural = "métricas mensais"

    def __str__(self):
        return self.mes.strftime("%m/%Y")


class VisitasPorDimensao(AuditModel):
    """Visitas agregadas no período por origem do tráfego ou dispositivo."""

    class Dimensao(models.TextChoices):
        ORIGEM = "origem", "Origem do tráfego"
        DISPOSITIVO = "dispositivo", "Dispositivo"

    dimensao = models.CharField("dimensão", max_length=12, choices=Dimensao.choices)
    valor = models.CharField("valor", max_length=80)
    tipo = models.CharField("tipo", max_length=20, blank=True, help_text="organic / paid")
    visitas = models.PositiveIntegerField("visitas", default=0)
    periodo_inicio = models.DateField("início do período")
    periodo_fim = models.DateField("fim do período")

    class Meta:
        ordering = ["dimensao", "-visitas"]
        verbose_name = "visitas por origem/dispositivo"
        verbose_name_plural = "visitas por origem/dispositivo"
        constraints = [
            models.UniqueConstraint(
                fields=["dimensao", "valor", "tipo", "periodo_inicio", "periodo_fim"],
                name="visitas_dimensao_unica",
            )
        ]

    def __str__(self):
        return f"{self.valor} ({self.visitas})"
