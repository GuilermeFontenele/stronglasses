"""Vendas da loja nova: lançadas no painel (WhatsApp, hotel, barbearia...) e, depois, as do checkout do site."""

from decimal import Decimal

from django.core.validators import MinValueValidator, RegexValidator
from django.db import models

from apps.catalogo.models import Produto, Variacao
from apps.clientes.models import Cliente
from apps.core.models import AuditModel

UFS = {
    "AC": "Acre", "AL": "Alagoas", "AP": "Amapá", "AM": "Amazonas", "BA": "Bahia", "CE": "Ceará",
    "DF": "Distrito Federal", "ES": "Espírito Santo", "GO": "Goiás", "MA": "Maranhão", "MT": "Mato Grosso",
    "MS": "Mato Grosso do Sul", "MG": "Minas Gerais", "PA": "Pará", "PB": "Paraíba", "PR": "Paraná",
    "PE": "Pernambuco", "PI": "Piauí", "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte",
    "RS": "Rio Grande do Sul", "RO": "Rondônia", "RR": "Roraima", "SC": "Santa Catarina", "SP": "São Paulo",
    "SE": "Sergipe", "TO": "Tocantins",
}  # fmt: skip
ZERO = Decimal("0.00")
_SIGLA_POR_NOME = {nome.lower(): sigla for sigla, nome in UFS.items()}


def sigla_uf(texto: str) -> str:
    """'CE', 'ce' ou 'Ceará' -> 'CE'. Vazio se não reconhecer (endereços importados vêm por extenso)."""
    texto = " ".join((texto or "").split())
    if texto.upper() in UFS:
        return texto.upper()
    return _SIGLA_POR_NOME.get(texto.lower(), "")


class Pedido(AuditModel):
    class Situacao(models.TextChoices):
        PENDENTE = "pendente", "Aguardando pagamento"
        PAGO = "pago", "Pago"
        ENVIADO = "enviado", "Enviado"
        ENTREGUE = "entregue", "Entregue"
        CANCELADO = "cancelado", "Cancelado"

    class Canal(models.TextChoices):
        WHATSAPP = "whatsapp", "WhatsApp"
        PRESENCIAL = "presencial", "Pessoalmente"
        HOTEL = "hotel", "Hotel"
        BARBEARIA = "barbearia", "Barbearia"
        INSTAGRAM = "instagram", "Instagram"
        SITE = "site", "Site"
        OUTRO = "outro", "Outro"

    class FormaPagamento(models.TextChoices):
        PIX = "pix", "Pix"
        DINHEIRO = "dinheiro", "Dinheiro"
        CREDITO = "credito", "Cartão de crédito"
        DEBITO = "debito", "Cartão de débito"
        LINK = "link", "Link de pagamento"
        OUTRO = "outro", "Outro"

    class Entrega(models.TextChoices):
        MAOS = "maos", "Entregue em mãos"
        MOTOBOY = "motoboy", "Motoboy"
        CORREIOS = "correios", "Correios"
        TRANSPORTADORA = "transportadora", "Transportadora"

    PAGOS = (Situacao.PAGO, Situacao.ENVIADO, Situacao.ENTREGUE)
    TONS = {"pendente": "aviso", "pago": "ok", "enviado": "ok", "entregue": "ok", "cancelado": "erro"}

    numero = models.PositiveIntegerField("número", unique=True, editable=False)
    realizado_em = models.DateTimeField("data da venda")
    cliente = models.ForeignKey(
        Cliente, verbose_name="cliente", on_delete=models.SET_NULL, null=True, blank=True, related_name="vendas"
    )
    # Origem (para relatórios e afiliação futura)
    canal = models.CharField("canal", max_length=20, choices=Canal.choices, default=Canal.WHATSAPP)
    parceiro = models.CharField(
        "parceiro", max_length=120, blank=True, help_text="Hotel, barbearia ou pessoa que vendeu/indicou."
    )
    ref = models.CharField("referência", max_length=60, blank=True)
    cupom = models.CharField("cupom", max_length=40, blank=True)
    utm_source = models.CharField("utm_source", max_length=100, blank=True)
    utm_medium = models.CharField("utm_medium", max_length=100, blank=True)
    utm_campaign = models.CharField("utm_campaign", max_length=100, blank=True)
    # Pagamento (valores sempre calculados no servidor)
    situacao = models.CharField("situação", max_length=12, choices=Situacao.choices, default=Situacao.PAGO)
    forma_pagamento = models.CharField("forma de pagamento", max_length=12, choices=FormaPagamento.choices)
    parcelas = models.PositiveSmallIntegerField("parcelas", default=1, validators=[MinValueValidator(1)])
    subtotal = models.DecimalField("subtotal", max_digits=10, decimal_places=2, default=ZERO)
    desconto = models.DecimalField(
        "desconto", max_digits=10, decimal_places=2, default=ZERO, validators=[MinValueValidator(ZERO)]
    )
    desconto_pix = models.DecimalField("desconto Pix", max_digits=10, decimal_places=2, default=ZERO)
    frete = models.DecimalField(
        "frete", max_digits=10, decimal_places=2, default=ZERO, validators=[MinValueValidator(ZERO)]
    )
    total = models.DecimalField("total", max_digits=10, decimal_places=2, default=ZERO)
    # Entrega (cópia do endereço no momento da venda)
    entrega = models.CharField("entrega", max_length=16, choices=Entrega.choices, default=Entrega.MAOS)
    destinatario = models.CharField("destinatário", max_length=150, blank=True)
    cep = models.CharField(
        "CEP", max_length=8, blank=True, validators=[RegexValidator(r"^\d{8}$", "CEP com 8 dígitos.")]
    )
    logradouro = models.CharField("logradouro", max_length=200, blank=True)
    numero_endereco = models.CharField("número", max_length=20, blank=True)
    complemento = models.CharField("complemento", max_length=120, blank=True)
    bairro = models.CharField("bairro", max_length=100, blank=True)
    cidade = models.CharField("cidade", max_length=100, blank=True)
    uf = models.CharField("estado", max_length=2, blank=True, choices=sorted(UFS.items()))
    codigo_rastreio = models.CharField("código de rastreio", max_length=40, blank=True)
    peso_g = models.PositiveIntegerField("peso do pacote (g)", null=True, blank=True)
    observacoes = models.TextField("observações", blank=True)
    estoque_baixado = models.BooleanField("estoque baixado", default=False, editable=False)
    pago_em = models.DateTimeField("pago em", null=True, blank=True, editable=False)
    enviado_em = models.DateTimeField("enviado em", null=True, blank=True, editable=False)
    cancelado_em = models.DateTimeField("cancelado em", null=True, blank=True, editable=False)

    class Meta:
        ordering = ["-realizado_em", "-numero"]
        verbose_name = "venda"
        verbose_name_plural = "vendas"
        permissions = [("imprimir_etiqueta", "Pode imprimir etiqueta e declaração de conteúdo")]

    def __str__(self):
        return self.codigo

    @property
    def codigo(self) -> str:
        return f"SG{self.numero:05d}" if self.numero else "nova"

    @property
    def pago(self) -> bool:
        return self.situacao in self.PAGOS

    @property
    def tom(self) -> str:
        """Cor do selo da situação no painel."""
        return self.TONS.get(self.situacao, "neutro")

    @property
    def vai_por_envio(self) -> bool:
        return self.entrega in (self.Entrega.CORREIOS, self.Entrega.TRANSPORTADORA)

    @property
    def nome_estado(self) -> str:
        return UFS.get(self.uf, self.uf)

    @property
    def tem_endereco(self) -> bool:
        return bool(self.cep and self.logradouro and self.cidade)


class ItemPedido(AuditModel):
    pedido = models.ForeignKey(Pedido, verbose_name="venda", on_delete=models.CASCADE, related_name="itens")
    variacao = models.ForeignKey(
        Variacao, verbose_name="variação", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    produto = models.ForeignKey(
        Produto, verbose_name="produto", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    nome = models.CharField("produto", max_length=150)
    cor = models.CharField("cor", max_length=150, blank=True)
    sku = models.CharField("SKU", max_length=40, blank=True)
    quantidade = models.PositiveSmallIntegerField("quantidade", validators=[MinValueValidator(1)])
    preco_unitario = models.DecimalField(
        "preço unitário", max_digits=10, decimal_places=2, validators=[MinValueValidator(ZERO)]
    )

    class Meta:
        ordering = ["id"]
        verbose_name = "item da venda"
        verbose_name_plural = "itens da venda"

    def __str__(self):
        return f"{self.quantidade}x {self.nome}"

    @property
    def subtotal(self) -> Decimal:
        return self.preco_unitario * self.quantidade
