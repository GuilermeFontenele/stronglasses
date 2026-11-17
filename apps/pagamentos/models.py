"""Tentativas de pagamento de um pedido no Mercado Pago (Pix ou cartão)."""

from decimal import Decimal

from django.db import models

from apps.core.models import AuditModel
from apps.vendas.models import Pedido


class Pagamento(AuditModel):
    # O QR Code é uma imagem grande e o copia e cola é um meio de pagamento: não vão para a trilha de auditoria.
    CAMPOS_SENSIVEIS_AUDITORIA = ("pix_qr_base64", "pix_copia_e_cola")

    class Metodo(models.TextChoices):
        PIX = "pix", "Pix"
        CARTAO = "credito", "Cartão de crédito"

    class Status(models.TextChoices):
        PENDENTE = "pending", "Aguardando pagamento"
        AUTORIZADO = "authorized", "Autorizado"
        EM_ANALISE = "in_process", "Em análise"
        EM_MEDIACAO = "in_mediation", "Em disputa"
        APROVADO = "approved", "Aprovado"
        RECUSADO = "rejected", "Recusado"
        CANCELADO = "cancelled", "Cancelado"
        ESTORNADO = "refunded", "Estornado"
        CONTESTADO = "charged_back", "Contestado"

    TONS = {
        "approved": "ok",
        "pending": "aviso",
        "in_process": "aviso",
        "authorized": "aviso",
        "in_mediation": "erro",
        "rejected": "erro",
        "cancelled": "neutro",
        "refunded": "erro",
        "charged_back": "erro",
    }

    pedido = models.ForeignKey(Pedido, verbose_name="pedido", on_delete=models.PROTECT, related_name="pagamentos")
    provedor_id = models.CharField("ID no Mercado Pago", max_length=40, unique=True)
    metodo = models.CharField("forma", max_length=10, choices=Metodo.choices)
    status = models.CharField("situação", max_length=20, choices=Status.choices, default=Status.PENDENTE)
    status_detalhe = models.CharField("detalhe", max_length=80, blank=True)
    valor = models.DecimalField("valor", max_digits=10, decimal_places=2, default=Decimal("0.00"))
    parcelas = models.PositiveSmallIntegerField("parcelas", default=1)
    bandeira = models.CharField("bandeira", max_length=30, blank=True)
    pix_copia_e_cola = models.TextField("Pix copia e cola", blank=True)
    pix_qr_base64 = models.TextField("QR Code do Pix (imagem)", blank=True)
    expira_em = models.DateTimeField("expira em", null=True, blank=True)
    aprovado_em = models.DateTimeField("aprovado em", null=True, blank=True)

    class Meta:
        ordering = ["-criado_em"]
        verbose_name = "pagamento"
        verbose_name_plural = "pagamentos"

    def __str__(self):
        return f"{self.get_metodo_display()} {self.provedor_id} · {self.pedido.codigo}"

    @property
    def tom(self) -> str:
        return self.TONS.get(self.status, "neutro")

    @property
    def aprovado(self) -> bool:
        return self.status == self.Status.APROVADO

    @property
    def aguardando(self) -> bool:
        return self.status in (self.Status.PENDENTE, self.Status.EM_ANALISE, self.Status.AUTORIZADO)
