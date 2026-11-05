import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.core.crypto import hash_busca
from apps.core.fields import EncryptedTextField
from apps.core.models import AuditModel
from apps.core.validators import so_digitos, validar_cnpj, validar_cpf, validar_whatsapp


class Cliente(AuditModel):
    """Titular de dados. Coletamos só o necessário (minimização, art. 6º, III da LGPD)."""

    class Tipo(models.TextChoices):
        PESSOA_FISICA = "PF", "Pessoa física"
        PESSOA_JURIDICA = "PJ", "Pessoa jurídica"

    CAMPOS_SENSIVEIS_AUDITORIA = ("documento", "documento_hash")

    uuid = models.UUIDField("identificador público", default=uuid.uuid4, unique=True, editable=False)
    tipo = models.CharField("tipo", max_length=2, choices=Tipo.choices, default=Tipo.PESSOA_FISICA)
    nome = models.CharField("nome", max_length=150)
    razao_social = models.CharField("razão social", max_length=200, blank=True)
    email = models.EmailField("e-mail", blank=True)
    whatsapp = models.CharField("WhatsApp", max_length=16, blank=True, validators=[validar_whatsapp])
    documento = EncryptedTextField(
        "CPF/CNPJ",
        blank=True,
        help_text="Guardado criptografado. Peça só quando necessário (ex.: nota fiscal para PJ).",
    )
    documento_hash = models.CharField("hash do documento", max_length=64, blank=True, editable=False)
    anonimizado_em = models.DateTimeField("anonimizado em", null=True, blank=True, editable=False)
    nuvemshop_id = models.BigIntegerField("ID na Nuvemshop", null=True, blank=True, unique=True, editable=False)

    class Meta:
        ordering = ["-criado_em"]
        verbose_name = "cliente"
        verbose_name_plural = "clientes"
        constraints = [
            models.UniqueConstraint(fields=["email"], condition=~Q(email=""), name="cliente_email_unico"),
            models.UniqueConstraint(
                fields=["documento_hash"], condition=~Q(documento_hash=""), name="cliente_documento_unico"
            ),
        ]

    def __str__(self):
        return self.nome

    def clean(self):
        super().clean()
        if self.anonimizado_em is None and not (self.email or self.whatsapp):
            raise ValidationError("Informe pelo menos um contato: e-mail ou WhatsApp.")
        if self.documento:
            digitos = so_digitos(self.documento)
            if self.tipo == self.Tipo.PESSOA_FISICA:
                validar_cpf(digitos)
            else:
                validar_cnpj(digitos)

    def save(self, *args, **kwargs):
        self.email = (self.email or "").strip().lower()
        self.documento = so_digitos(self.documento) if self.documento else ""
        self.documento_hash = hash_busca(self.documento) if self.documento else ""
        super().save(*args, **kwargs)

    @property
    def documento_mascarado(self) -> str:
        if not self.documento:
            return ""
        return "•" * (len(self.documento) - 2) + self.documento[-2:]

    def tem_consentimento(self, finalidade: str) -> bool:
        return self.consentimentos.filter(finalidade=finalidade, concedido=True, revogado_em__isnull=True).exists()


class Consentimento(models.Model):
    """Prova de consentimento (art. 8º da LGPD). Registros não são editados: revogar
    preenche `revogado_em` e um novo aceite gera um novo registro."""

    class Finalidade(models.TextChoices):
        MARKETING_EMAIL = "marketing_email", "Ofertas por e-mail"
        MARKETING_WHATSAPP = "marketing_whatsapp", "Ofertas por WhatsApp"
        POLITICA = "politica", "Ciência da política de privacidade"

    class Origem(models.TextChoices):
        POPUP = "popup", "Popup de boas-vindas"
        CADASTRO = "cadastro", "Cadastro"
        CHECKOUT = "checkout", "Checkout"
        PAINEL = "painel", "Registrado pela loja"
        IMPORTACAO = "importacao", "Importado da Nuvemshop"

    cliente = models.ForeignKey(
        Cliente, verbose_name="cliente", on_delete=models.CASCADE, related_name="consentimentos"
    )
    finalidade = models.CharField("finalidade", max_length=30, choices=Finalidade.choices)
    concedido = models.BooleanField("concedido", default=True)
    versao_politica = models.CharField("versão da política", max_length=20)
    origem = models.CharField("origem", max_length=10, choices=Origem.choices)
    ip = models.GenericIPAddressField("IP", null=True, blank=True)
    user_agent = models.CharField("navegador", max_length=255, blank=True)
    registrado_em = models.DateTimeField("registrado em", auto_now_add=True, db_index=True)
    revogado_em = models.DateTimeField("revogado em", null=True, blank=True)

    class Meta:
        ordering = ["-registrado_em"]
        verbose_name = "consentimento"
        verbose_name_plural = "consentimentos"

    def __str__(self):
        return f"{self.get_finalidade_display()} ({'ativo' if self.ativo else 'inativo'})"

    @property
    def ativo(self) -> bool:
        return self.concedido and self.revogado_em is None
