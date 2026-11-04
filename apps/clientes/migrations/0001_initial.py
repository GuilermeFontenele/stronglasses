import uuid

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import apps.core.fields


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Cliente",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("criado_em", models.DateTimeField(auto_now_add=True, verbose_name="criado em")),
                ("atualizado_em", models.DateTimeField(auto_now=True, verbose_name="atualizado em")),
                (
                    "uuid",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, unique=True, verbose_name="identificador público"
                    ),
                ),
                (
                    "tipo",
                    models.CharField(
                        choices=[("PF", "Pessoa física"), ("PJ", "Pessoa jurídica")],
                        default="PF",
                        max_length=2,
                        verbose_name="tipo",
                    ),
                ),
                ("nome", models.CharField(max_length=150, verbose_name="nome")),
                ("razao_social", models.CharField(blank=True, max_length=200, verbose_name="razão social")),
                ("email", models.EmailField(blank=True, max_length=254, verbose_name="e-mail")),
                (
                    "whatsapp",
                    models.CharField(
                        blank=True,
                        max_length=16,
                        validators=[
                            django.core.validators.RegexValidator(
                                "^\\+[1-9]\\d{7,14}$", "Use o formato internacional, ex.: +5585999998888."
                            )
                        ],
                        verbose_name="WhatsApp",
                    ),
                ),
                (
                    "documento",
                    apps.core.fields.EncryptedTextField(
                        blank=True,
                        help_text="Guardado criptografado. Peça só quando necessário (ex.: nota fiscal para PJ).",
                        verbose_name="CPF/CNPJ",
                    ),
                ),
                (
                    "documento_hash",
                    models.CharField(blank=True, editable=False, max_length=64, verbose_name="hash do documento"),
                ),
                (
                    "anonimizado_em",
                    models.DateTimeField(blank=True, editable=False, null=True, verbose_name="anonimizado em"),
                ),
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
            ],
            options={
                "verbose_name": "cliente",
                "verbose_name_plural": "clientes",
                "ordering": ["-criado_em"],
                "constraints": [
                    models.UniqueConstraint(
                        condition=models.Q(("email", ""), _negated=True),
                        fields=("email",),
                        name="cliente_email_unico",
                    ),
                    models.UniqueConstraint(
                        condition=models.Q(("documento_hash", ""), _negated=True),
                        fields=("documento_hash",),
                        name="cliente_documento_unico",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="Consentimento",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "finalidade",
                    models.CharField(
                        choices=[
                            ("marketing_email", "Ofertas por e-mail"),
                            ("marketing_whatsapp", "Ofertas por WhatsApp"),
                            ("politica", "Ciência da política de privacidade"),
                        ],
                        max_length=30,
                        verbose_name="finalidade",
                    ),
                ),
                ("concedido", models.BooleanField(default=True, verbose_name="concedido")),
                ("versao_politica", models.CharField(max_length=20, verbose_name="versão da política")),
                (
                    "origem",
                    models.CharField(
                        choices=[
                            ("popup", "Popup de boas-vindas"),
                            ("cadastro", "Cadastro"),
                            ("checkout", "Checkout"),
                            ("painel", "Registrado pela loja"),
                        ],
                        max_length=10,
                        verbose_name="origem",
                    ),
                ),
                ("ip", models.GenericIPAddressField(blank=True, null=True, verbose_name="IP")),
                ("user_agent", models.CharField(blank=True, max_length=255, verbose_name="navegador")),
                ("registrado_em", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="registrado em")),
                ("revogado_em", models.DateTimeField(blank=True, null=True, verbose_name="revogado em")),
                (
                    "cliente",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="consentimentos",
                        to="clientes.cliente",
                        verbose_name="cliente",
                    ),
                ),
            ],
            options={
                "verbose_name": "consentimento",
                "verbose_name_plural": "consentimentos",
                "ordering": ["-registrado_em"],
            },
        ),
    ]
