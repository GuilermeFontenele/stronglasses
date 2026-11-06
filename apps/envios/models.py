"""Etiquetas compradas na transportadora (via Melhor Envio) e a conexão com a conta da loja."""

from datetime import timedelta
from decimal import Decimal

from django.db import models
from django.utils import timezone

from apps.core.fields import EncryptedTextField
from apps.core.models import AuditModel
from apps.vendas.models import Pedido


class Ambiente(models.TextChoices):
    SANDBOX = "sandbox", "Testes (sandbox)"
    PRODUCAO = "producao", "Produção"


class ConexaoMelhorEnvio(AuditModel):
    """Tokens OAuth da conta da loja, cifrados no banco. Um por ambiente (testes e produção não se misturam)."""

    CAMPOS_SENSIVEIS_AUDITORIA = ("access_token", "refresh_token")

    ambiente = models.CharField("ambiente", max_length=10, choices=Ambiente.choices, unique=True)
    access_token = EncryptedTextField("token de acesso", blank=True)
    refresh_token = EncryptedTextField("token de renovação", blank=True)
    expira_em = models.DateTimeField("expira em", null=True, blank=True)
    conta = models.CharField("conta", max_length=150, blank=True, help_text="Nome da conta no Melhor Envio.")

    class Meta:
        verbose_name = "conexão com o Melhor Envio"
        verbose_name_plural = "conexões com o Melhor Envio"

    def __str__(self):
        return f"Melhor Envio ({self.get_ambiente_display()})"

    @property
    def conectada(self) -> bool:
        return bool(self.access_token)

    @property
    def perto_de_expirar(self) -> bool:
        return bool(self.expira_em and self.expira_em - timezone.now() < timedelta(days=5))


class Envio(AuditModel):
    class Status(models.TextChoices):
        CARRINHO = "carrinho", "Aguardando pagamento"
        PAGO = "pago", "Paga (gerando etiqueta)"
        GERADO = "gerado", "Etiqueta pronta"
        POSTADO = "postado", "Postado"
        ENTREGUE = "entregue", "Entregue"
        CANCELADO = "cancelado", "Cancelada"

    TONS = {
        "carrinho": "aviso",
        "pago": "aviso",
        "gerado": "ok",
        "postado": "ok",
        "entregue": "ok",
        "cancelado": "erro",
    }
    ATIVOS = (Status.CARRINHO, Status.PAGO, Status.GERADO, Status.POSTADO, Status.ENTREGUE)

    pedido = models.ForeignKey(Pedido, verbose_name="venda", on_delete=models.PROTECT, related_name="envios")
    ambiente = models.CharField("ambiente", max_length=10, choices=Ambiente.choices)
    me_id = models.CharField("ID no Melhor Envio", max_length=64, unique=True)
    protocolo = models.CharField("protocolo", max_length=40, blank=True)
    transportadora = models.CharField("transportadora", max_length=60)
    servico = models.CharField("serviço", max_length=60)
    servico_id = models.PositiveIntegerField("ID do serviço")
    preco = models.DecimalField("preço da etiqueta", max_digits=10, decimal_places=2, default=Decimal("0.00"))
    prazo_dias = models.PositiveSmallIntegerField("prazo (dias úteis)", null=True, blank=True)
    status = models.CharField("situação", max_length=10, choices=Status.choices, default=Status.CARRINHO)
    rastreio = models.CharField("código de rastreio", max_length=40, blank=True)
    com_nota_fiscal = models.BooleanField("com nota fiscal", default=False)
    erro = models.CharField("último erro", max_length=255, blank=True)
    pago_em = models.DateTimeField("paga em", null=True, blank=True)
    gerado_em = models.DateTimeField("gerada em", null=True, blank=True)
    postado_em = models.DateTimeField("postada em", null=True, blank=True)
    entregue_em = models.DateTimeField("entregue em", null=True, blank=True)
    cancelado_em = models.DateTimeField("cancelada em", null=True, blank=True)

    class Meta:
        ordering = ["-criado_em"]
        verbose_name = "etiqueta de envio"
        verbose_name_plural = "etiquetas de envio"

    def __str__(self):
        return f"{self.transportadora} {self.servico} · {self.pedido.codigo}"

    @property
    def tom(self) -> str:
        return self.TONS.get(self.status, "neutro")

    @property
    def pode_imprimir(self) -> bool:
        return self.status in (self.Status.GERADO, self.Status.POSTADO)

    @property
    def pode_cancelar(self) -> bool:
        return self.status in (self.Status.CARRINHO, self.Status.PAGO, self.Status.GERADO)
