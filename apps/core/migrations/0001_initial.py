import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Parametro",
            fields=[
                ("criado_em", models.DateTimeField(auto_now_add=True, verbose_name="criado em")),
                ("atualizado_em", models.DateTimeField(auto_now=True, verbose_name="atualizado em")),
                (
                    "chave",
                    models.CharField(
                        max_length=60,
                        primary_key=True,
                        serialize=False,
                        validators=[
                            django.core.validators.RegexValidator(
                                "^[A-Z][A-Z0-9_]*$", "Use MAIÚSCULAS_COM_UNDERSCORE."
                            )
                        ],
                        verbose_name="chave",
                    ),
                ),
                ("valor", models.CharField(max_length=255, verbose_name="valor")),
                (
                    "tipo",
                    models.CharField(
                        choices=[
                            ("texto", "Texto"),
                            ("inteiro", "Inteiro"),
                            ("decimal", "Decimal"),
                            ("booleano", "Sim/Não"),
                        ],
                        default="texto",
                        max_length=10,
                        verbose_name="tipo",
                    ),
                ),
                ("descricao", models.CharField(max_length=255, verbose_name="descrição")),
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
                "verbose_name": "parâmetro da loja",
                "verbose_name_plural": "parâmetros da loja",
                "ordering": ["chave"],
            },
        ),
        migrations.CreateModel(
            name="RegistroAuditoria",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("quando", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="quando")),
                ("usuario_nome", models.CharField(blank=True, max_length=150, verbose_name="usuário (texto)")),
                ("ip", models.GenericIPAddressField(blank=True, null=True, verbose_name="IP")),
                (
                    "acao",
                    models.CharField(
                        choices=[
                            ("I", "Criação"),
                            ("U", "Alteração"),
                            ("D", "Exclusão"),
                            ("A", "Acesso a dado pessoal"),
                            ("E", "Exportação de dados"),
                            ("N", "Anonimização"),
                        ],
                        max_length=1,
                        verbose_name="ação",
                    ),
                ),
                ("modelo", models.CharField(db_index=True, max_length=100, verbose_name="modelo")),
                ("objeto_id", models.CharField(db_index=True, max_length=64, verbose_name="ID do objeto")),
                ("objeto_repr", models.CharField(blank=True, max_length=200, verbose_name="objeto")),
                ("antes", models.JSONField(blank=True, null=True, verbose_name="antes")),
                ("depois", models.JSONField(blank=True, null=True, verbose_name="depois")),
                (
                    "usuario",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="usuário",
                    ),
                ),
            ],
            options={
                "verbose_name": "registro de auditoria",
                "verbose_name_plural": "registros de auditoria",
                "ordering": ["-quando"],
                "indexes": [models.Index(fields=["modelo", "objeto_id"], name="core_audit_modelo_obj_idx")],
            },
        ),
    ]
