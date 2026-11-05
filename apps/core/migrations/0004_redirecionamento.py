import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core", "0003_peso_padrao"),
    ]

    operations = [
        migrations.CreateModel(
            name="Redirecionamento",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("criado_em", models.DateTimeField(auto_now_add=True, verbose_name="criado em")),
                ("atualizado_em", models.DateTimeField(auto_now=True, verbose_name="atualizado em")),
                (
                    "origem",
                    models.CharField(
                        help_text="Só o caminho, começando com /. Ex.: /produtos/oculos-antigo/",
                        max_length=255,
                        unique=True,
                        verbose_name="URL antiga",
                    ),
                ),
                (
                    "destino",
                    models.CharField(
                        help_text="Caminho (/produtos/novo/) ou endereço completo https://",
                        max_length=500,
                        verbose_name="URL nova",
                    ),
                ),
                ("permanente", models.BooleanField(default=True, verbose_name="permanente (301)")),
                ("ativo", models.BooleanField(default=True, verbose_name="ativo")),
                ("acessos", models.PositiveIntegerField(default=0, editable=False, verbose_name="acessos")),
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
                "verbose_name": "redirecionamento",
                "verbose_name_plural": "redirecionamentos",
                "ordering": ["origem"],
            },
        ),
    ]
