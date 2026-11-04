from decimal import Decimal

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import apps.catalogo.models

_AUDITORIA = [
    ("criado_em", lambda: models.DateTimeField(auto_now_add=True, verbose_name="criado em")),
    ("atualizado_em", lambda: models.DateTimeField(auto_now=True, verbose_name="atualizado em")),
    (
        "atualizado_por",
        lambda: models.ForeignKey(
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
        lambda: models.ForeignKey(
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


def auditoria():
    return [(nome, fabrica()) for nome, fabrica in _AUDITORIA]


def validadores_imagem():
    return [
        django.core.validators.FileExtensionValidator(["jpg", "jpeg", "png", "webp"]),
        apps.catalogo.models.validar_tamanho_imagem,
    ]


def validador_hex():
    return [django.core.validators.RegexValidator("^#[0-9A-Fa-f]{6}$", "Use uma cor no formato #RRGGBB.")]


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AcabamentoArmacao",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nome", models.CharField(max_length=60, unique=True, verbose_name="nome")),
                (
                    "cor_hex",
                    models.CharField(
                        help_text="Ex.: #1A1A1A", max_length=7, validators=validador_hex(), verbose_name="cor"
                    ),
                ),
                (
                    "textura",
                    models.ImageField(
                        blank=True,
                        help_text="Opcional: padrão tartaruga, transparente, degradê…",
                        upload_to=apps.catalogo.models.caminho_textura,
                        validators=validadores_imagem(),
                        verbose_name="textura",
                    ),
                ),
                ("ativo", models.BooleanField(default=True, verbose_name="ativo")),
            ],
            options={
                "verbose_name": "acabamento de armação",
                "verbose_name_plural": "acabamentos de armação",
                "ordering": ["nome"],
            },
        ),
        migrations.CreateModel(
            name="CorLente",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nome", models.CharField(max_length=60, unique=True, verbose_name="nome")),
                (
                    "cor_hex",
                    models.CharField(
                        help_text="Ex.: #2B3A67", max_length=7, validators=validador_hex(), verbose_name="cor"
                    ),
                ),
                ("ativo", models.BooleanField(default=True, verbose_name="ativo")),
            ],
            options={
                "verbose_name": "cor de lente",
                "verbose_name_plural": "cores de lente",
                "ordering": ["nome"],
            },
        ),
        migrations.CreateModel(
            name="Categoria",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                *auditoria(),
                ("nome", models.CharField(max_length=80, verbose_name="nome")),
                ("slug", models.SlugField(max_length=100, unique=True, verbose_name="endereço (slug)")),
                ("descricao", models.TextField(blank=True, verbose_name="descrição")),
                ("ativa", models.BooleanField(default=True, verbose_name="ativa")),
                ("ordem", models.PositiveSmallIntegerField(default=0, verbose_name="ordem")),
                (
                    "pai",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="filhas",
                        to="catalogo.categoria",
                        verbose_name="categoria pai",
                    ),
                ),
            ],
            options={
                "verbose_name": "categoria",
                "verbose_name_plural": "categorias",
                "ordering": ["ordem", "nome"],
            },
        ),
        migrations.CreateModel(
            name="Produto",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                *auditoria(),
                ("nome", models.CharField(max_length=120, verbose_name="nome")),
                (
                    "slug",
                    models.SlugField(
                        help_text="Mantenha o mesmo da Nuvemshop para não perder SEO.",
                        max_length=140,
                        unique=True,
                        verbose_name="endereço (slug)",
                    ),
                ),
                (
                    "tipo",
                    models.CharField(
                        choices=[("sol", "Óculos de sol"), ("grau", "Armação de grau"), ("acessorio", "Acessório")],
                        default="sol",
                        max_length=10,
                        verbose_name="tipo",
                    ),
                ),
                (
                    "publico",
                    models.CharField(
                        choices=[
                            ("feminino", "Feminino"),
                            ("masculino", "Masculino"),
                            ("unissex", "Unissex"),
                            ("infantil", "Infantil"),
                        ],
                        default="unissex",
                        max_length=10,
                        verbose_name="público",
                    ),
                ),
                (
                    "formato",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("quadrado", "Quadrado"),
                            ("redondo", "Redondo"),
                            ("retangular", "Retangular"),
                            ("oval", "Oval"),
                            ("aviador", "Aviador"),
                            ("hexagonal", "Hexagonal"),
                            ("gatinho", "Gatinho"),
                            ("outro", "Outro"),
                        ],
                        max_length=12,
                        verbose_name="formato",
                    ),
                ),
                ("descricao", models.TextField(blank=True, verbose_name="descrição")),
                (
                    "preco",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=10,
                        validators=[django.core.validators.MinValueValidator(Decimal("0.01"))],
                        verbose_name="preço",
                    ),
                ),
                (
                    "preco_comparativo",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        help_text="Opcional. Precisa ser maior que o preço.",
                        max_digits=10,
                        null=True,
                        verbose_name="preço riscado (de)",
                    ),
                ),
                ("peso_g", models.PositiveIntegerField(blank=True, null=True, verbose_name="peso com embalagem (g)")),
                (
                    "altura_cm",
                    models.DecimalField(
                        blank=True, decimal_places=1, max_digits=5, null=True, verbose_name="altura da embalagem (cm)"
                    ),
                ),
                (
                    "largura_cm",
                    models.DecimalField(
                        blank=True, decimal_places=1, max_digits=5, null=True, verbose_name="largura da embalagem (cm)"
                    ),
                ),
                (
                    "comprimento_cm",
                    models.DecimalField(
                        blank=True,
                        decimal_places=1,
                        max_digits=5,
                        null=True,
                        verbose_name="comprimento da embalagem (cm)",
                    ),
                ),
                ("ativo", models.BooleanField(default=False, verbose_name="publicado")),
                ("destaque", models.BooleanField(default=False, verbose_name="destaque na home")),
                ("seo_titulo", models.CharField(blank=True, max_length=70, verbose_name="título para o Google")),
                (
                    "seo_descricao",
                    models.CharField(blank=True, max_length=160, verbose_name="descrição para o Google"),
                ),
                (
                    "categorias",
                    models.ManyToManyField(
                        blank=True, related_name="produtos", to="catalogo.categoria", verbose_name="categorias"
                    ),
                ),
            ],
            options={
                "verbose_name": "produto",
                "verbose_name_plural": "produtos",
                "ordering": ["nome"],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(
                            ("preco_comparativo__isnull", True),
                            ("preco_comparativo__gt", models.F("preco")),
                            _connector="OR",
                        ),
                        name="produto_preco_comparativo_maior",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="Variacao",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                *auditoria(),
                ("sku", models.CharField(max_length=40, unique=True, verbose_name="SKU")),
                (
                    "preco",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        help_text="Vazio = usa o preço do produto.",
                        max_digits=10,
                        null=True,
                        validators=[django.core.validators.MinValueValidator(Decimal("0.01"))],
                        verbose_name="preço específico",
                    ),
                ),
                ("estoque", models.PositiveIntegerField(default=0, verbose_name="estoque")),
                ("ativa", models.BooleanField(default=True, verbose_name="ativa")),
                ("ordem", models.PositiveSmallIntegerField(default=0, verbose_name="ordem")),
                (
                    "armacao",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="variacoes",
                        to="catalogo.acabamentoarmacao",
                        verbose_name="armação",
                    ),
                ),
                (
                    "lente",
                    models.ForeignKey(
                        blank=True,
                        help_text="Deixe vazio para armações de grau e acessórios.",
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="variacoes",
                        to="catalogo.corlente",
                        verbose_name="lente",
                    ),
                ),
                (
                    "produto",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="variacoes",
                        to="catalogo.produto",
                        verbose_name="produto",
                    ),
                ),
            ],
            options={
                "verbose_name": "variação",
                "verbose_name_plural": "variações",
                "ordering": ["produto", "ordem", "id"],
                "constraints": [
                    models.UniqueConstraint(
                        condition=models.Q(("lente__isnull", False)),
                        fields=("produto", "armacao", "lente"),
                        name="variacao_combinacao_unica",
                    ),
                    models.UniqueConstraint(
                        condition=models.Q(("lente__isnull", True)),
                        fields=("produto", "armacao"),
                        name="variacao_sem_lente_unica",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="ImagemProduto",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "imagem",
                    models.ImageField(
                        upload_to=apps.catalogo.models.caminho_imagem_produto,
                        validators=validadores_imagem(),
                        verbose_name="imagem",
                    ),
                ),
                (
                    "texto_alternativo",
                    models.CharField(
                        help_text="Descreva a foto (acessibilidade e Google).",
                        max_length=150,
                        verbose_name="texto alternativo",
                    ),
                ),
                ("ordem", models.PositiveSmallIntegerField(default=0, verbose_name="ordem")),
                (
                    "produto",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="imagens",
                        to="catalogo.produto",
                        verbose_name="produto",
                    ),
                ),
                (
                    "variacao",
                    models.ForeignKey(
                        blank=True,
                        help_text="Opcional: foto específica desta cor.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="imagens",
                        to="catalogo.variacao",
                        verbose_name="variação",
                    ),
                ),
            ],
            options={
                "verbose_name": "imagem do produto",
                "verbose_name_plural": "imagens do produto",
                "ordering": ["ordem", "id"],
            },
        ),
    ]
