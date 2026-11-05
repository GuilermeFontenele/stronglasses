import uuid
from decimal import Decimal
from pathlib import PurePath

from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q

from apps.core.models import AuditModel
from apps.core.validators import validar_hex

EXTENSOES_IMAGEM = ["jpg", "jpeg", "png", "webp"]
TAMANHO_MAXIMO_IMAGEM = 5 * 1024 * 1024  # 5 MB


def validar_tamanho_imagem(arquivo) -> None:
    if arquivo.size > TAMANHO_MAXIMO_IMAGEM:
        raise ValidationError("Imagem maior que 5 MB.")


def _nome_aleatorio(pasta: str, nome_original: str) -> str:
    """Nunca usa o nome enviado (evita path traversal e vazamento de informação)."""
    extensao = PurePath(nome_original).suffix.lower().lstrip(".") or "jpg"
    return f"{pasta}/{uuid.uuid4().hex}.{extensao}"


def caminho_imagem_produto(instance, filename: str) -> str:
    return _nome_aleatorio("produtos", filename)


def caminho_textura(instance, filename: str) -> str:
    return _nome_aleatorio("texturas", filename)


# Tamanhos ideais do banner principal (largura, altura).
BANNER_COMPUTADOR = (1920, 800)
BANNER_CELULAR = (1080, 1350)


def caminho_banner(instance, filename: str) -> str:
    return _nome_aleatorio("banners", filename)


def validar_link_banner(valor: str) -> None:
    """Só caminhos internos (/masculino/) ou https: nada de javascript: ou http."""
    if not (valor.startswith("/") and not valor.startswith("//")) and not valor.startswith("https://"):
        raise ValidationError("Use um caminho do site (ex.: /masculino/) ou um endereço https://.")


class Categoria(AuditModel):
    nome = models.CharField("nome", max_length=80)
    slug = models.SlugField("endereço (slug)", max_length=100, unique=True)
    descricao = models.TextField("descrição", blank=True)
    pai = models.ForeignKey(
        "self",
        verbose_name="categoria pai",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="filhas",
    )
    ativa = models.BooleanField("ativa", default=True)
    ordem = models.PositiveSmallIntegerField("ordem", default=0)
    nuvemshop_id = models.BigIntegerField("ID na Nuvemshop", null=True, blank=True, unique=True, editable=False)

    class Meta:
        ordering = ["ordem", "nome"]
        verbose_name = "categoria"
        verbose_name_plural = "categorias"

    def __str__(self):
        return f"{self.pai} > {self.nome}" if self.pai_id else self.nome


class AcabamentoArmacao(models.Model):
    """Cor/acabamento da armação: lado esquerdo da bolinha do seletor."""

    nome = models.CharField("nome", max_length=60, unique=True)
    cor_hex = models.CharField("cor", max_length=7, validators=[validar_hex], help_text="Ex.: #1A1A1A")
    textura = models.ImageField(
        "textura",
        upload_to=caminho_textura,
        blank=True,
        validators=[FileExtensionValidator(EXTENSOES_IMAGEM), validar_tamanho_imagem],
        help_text="Opcional: padrão tartaruga, transparente, degradê…",
    )
    ativo = models.BooleanField("ativo", default=True)

    class Meta:
        ordering = ["nome"]
        verbose_name = "acabamento de armação"
        verbose_name_plural = "acabamentos de armação"

    def __str__(self):
        return self.nome


class CorLente(models.Model):
    """Cor da lente: lado direito da bolinha do seletor."""

    nome = models.CharField("nome", max_length=60, unique=True)
    cor_hex = models.CharField("cor", max_length=7, validators=[validar_hex], help_text="Ex.: #2B3A67")
    ativo = models.BooleanField("ativo", default=True)

    class Meta:
        ordering = ["nome"]
        verbose_name = "cor de lente"
        verbose_name_plural = "cores de lente"

    def __str__(self):
        return self.nome


class Produto(AuditModel):
    class Tipo(models.TextChoices):
        SOL = "sol", "Óculos de sol"
        GRAU = "grau", "Armação de grau"
        ACESSORIO = "acessorio", "Acessório"

    class Publico(models.TextChoices):
        FEMININO = "feminino", "Feminino"
        MASCULINO = "masculino", "Masculino"
        UNISSEX = "unissex", "Unissex"
        INFANTIL = "infantil", "Infantil"

    class Formato(models.TextChoices):
        QUADRADO = "quadrado", "Quadrado"
        REDONDO = "redondo", "Redondo"
        RETANGULAR = "retangular", "Retangular"
        OVAL = "oval", "Oval"
        AVIADOR = "aviador", "Aviador"
        HEXAGONAL = "hexagonal", "Hexagonal"
        GATINHO = "gatinho", "Gatinho"
        OUTRO = "outro", "Outro"

    nome = models.CharField("nome", max_length=120)
    slug = models.SlugField(
        "endereço (slug)", max_length=140, unique=True, help_text="Mantenha o mesmo da Nuvemshop para não perder SEO."
    )
    tipo = models.CharField("tipo", max_length=10, choices=Tipo.choices, default=Tipo.SOL)
    publico = models.CharField("público", max_length=10, choices=Publico.choices, default=Publico.UNISSEX)
    formato = models.CharField("formato", max_length=12, choices=Formato.choices, blank=True)
    descricao = models.TextField("descrição", blank=True)
    categorias = models.ManyToManyField(Categoria, verbose_name="categorias", related_name="produtos", blank=True)
    preco = models.DecimalField(
        "preço", max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    preco_comparativo = models.DecimalField(
        "preço riscado (de)",
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Opcional. Precisa ser maior que o preço.",
    )
    peso_g = models.PositiveIntegerField("peso com embalagem (g)", null=True, blank=True)
    altura_cm = models.DecimalField("altura da embalagem (cm)", max_digits=5, decimal_places=1, null=True, blank=True)
    largura_cm = models.DecimalField("largura da embalagem (cm)", max_digits=5, decimal_places=1, null=True, blank=True)
    comprimento_cm = models.DecimalField(
        "comprimento da embalagem (cm)", max_digits=5, decimal_places=1, null=True, blank=True
    )
    ativo = models.BooleanField("publicado", default=False)
    destaque = models.BooleanField("destaque na home", default=False)
    seo_titulo = models.CharField("título para o Google", max_length=70, blank=True)
    seo_descricao = models.CharField("descrição para o Google", max_length=160, blank=True)
    nuvemshop_id = models.BigIntegerField("ID na Nuvemshop", null=True, blank=True, unique=True, editable=False)

    class Meta:
        ordering = ["nome"]
        verbose_name = "produto"
        verbose_name_plural = "produtos"
        constraints = [
            models.CheckConstraint(
                condition=Q(preco_comparativo__isnull=True) | Q(preco_comparativo__gt=F("preco")),
                name="produto_preco_comparativo_maior",
            ),
        ]

    def __str__(self):
        return self.nome

    def get_absolute_url(self):
        return f"/produtos/{self.slug}/"

    @property
    def pronto_para_envio(self) -> bool:
        """Sem peso e medidas a cotação de frete sai errada."""
        return all(v is not None for v in (self.peso_g, self.altura_cm, self.largura_cm, self.comprimento_cm))


class Variacao(AuditModel):
    """Combinação vendável: armação + lente, com SKU e estoque próprios."""

    produto = models.ForeignKey(Produto, verbose_name="produto", on_delete=models.CASCADE, related_name="variacoes")
    armacao = models.ForeignKey(
        AcabamentoArmacao, verbose_name="armação", on_delete=models.PROTECT, related_name="variacoes"
    )
    lente = models.ForeignKey(
        CorLente,
        verbose_name="lente",
        on_delete=models.PROTECT,
        related_name="variacoes",
        null=True,
        blank=True,
        help_text="Deixe vazio para armações de grau e acessórios.",
    )
    sku = models.CharField("SKU", max_length=40, unique=True)
    preco = models.DecimalField(
        "preço específico",
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Vazio = usa o preço do produto.",
    )
    estoque = models.PositiveIntegerField("estoque", default=0)
    ativa = models.BooleanField("ativa", default=True)
    ordem = models.PositiveSmallIntegerField("ordem", default=0)
    nuvemshop_id = models.BigIntegerField("ID na Nuvemshop", null=True, blank=True, unique=True, editable=False)

    class Meta:
        ordering = ["produto", "ordem", "id"]
        verbose_name = "variação"
        verbose_name_plural = "variações"
        constraints = [
            models.UniqueConstraint(
                fields=["produto", "armacao", "lente"],
                condition=Q(lente__isnull=False),
                name="variacao_combinacao_unica",
            ),
            models.UniqueConstraint(
                fields=["produto", "armacao"],
                condition=Q(lente__isnull=True),
                name="variacao_sem_lente_unica",
            ),
        ]

    def __str__(self):
        return f"{self.produto} — {self.descricao_cor}"

    @property
    def descricao_cor(self) -> str:
        if self.lente_id:
            return f"Armação {self.armacao.nome.lower()}, lente {self.lente.nome.lower()}"
        return f"Armação {self.armacao.nome.lower()}"

    @property
    def preco_final(self) -> Decimal:
        return self.preco if self.preco is not None else self.produto.preco

    @property
    def disponivel(self) -> bool:
        return self.ativa and self.estoque > 0


class ImagemProduto(models.Model):
    produto = models.ForeignKey(Produto, verbose_name="produto", on_delete=models.CASCADE, related_name="imagens")
    variacao = models.ForeignKey(
        Variacao,
        verbose_name="variação",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="imagens",
        help_text="Opcional: foto específica desta cor.",
    )
    imagem = models.ImageField(
        "imagem",
        upload_to=caminho_imagem_produto,
        validators=[FileExtensionValidator(EXTENSOES_IMAGEM), validar_tamanho_imagem],
    )
    texto_alternativo = models.CharField(
        "texto alternativo", max_length=150, help_text="Descreva a foto (acessibilidade e Google)."
    )
    ordem = models.PositiveSmallIntegerField("ordem", default=0)
    nuvemshop_id = models.BigIntegerField("ID na Nuvemshop", null=True, blank=True, unique=True, editable=False)

    class Meta:
        ordering = ["ordem", "id"]
        verbose_name = "imagem do produto"
        verbose_name_plural = "imagens do produto"

    def __str__(self):
        return self.texto_alternativo


class Banner(AuditModel):
    """Banner principal da home. Vários ativos viram um carrossel (arrastar no celular)."""

    titulo = models.CharField(
        "descrição da imagem", max_length=150, help_text="O que aparece na imagem (acessibilidade e Google)."
    )
    imagem = models.ImageField(
        "imagem (computador)",
        upload_to=caminho_banner,
        validators=[FileExtensionValidator(EXTENSOES_IMAGEM), validar_tamanho_imagem],
        help_text="Formato computador: 1920 x 800 px (proporção 12:5), JPG ou WEBP de até 500 KB.",
    )
    imagem_mobile = models.ImageField(
        "imagem (celular)",
        upload_to=caminho_banner,
        validators=[FileExtensionValidator(EXTENSOES_IMAGEM), validar_tamanho_imagem],
        help_text="Formato celular: 1080 x 1350 px (proporção 4:5, igual ao post vertical do Instagram).",
    )
    link = models.CharField(
        "link", max_length=300, blank=True, validators=[validar_link_banner], help_text="Ex.: /masculino/"
    )
    ativo = models.BooleanField("ativo", default=True)
    inicio = models.DateTimeField("mostrar a partir de", null=True, blank=True)
    fim = models.DateTimeField("mostrar até", null=True, blank=True)
    ordem = models.PositiveSmallIntegerField("ordem", default=0)

    class Meta:
        ordering = ["ordem", "-id"]
        verbose_name = "banner"
        verbose_name_plural = "banners"

    def __str__(self):
        return self.titulo

    def clean(self):
        erros = {}
        for campo, (largura, altura), nome in (
            ("imagem", BANNER_COMPUTADOR, "do computador"),
            ("imagem_mobile", BANNER_CELULAR, "do celular"),
        ):
            arquivo = getattr(self, campo)
            try:
                tamanho = (arquivo.width, arquivo.height) if arquivo else None
            except (OSError, ValueError):
                tamanho = None  # arquivo ausente: os outros validadores cuidam
            if tamanho and abs(tamanho[0] / tamanho[1] - largura / altura) > (largura / altura) * 0.1:
                erros[campo] = (
                    f"A imagem {nome} tem {tamanho[0]} x {tamanho[1]} px. "
                    f"Use {largura} x {altura} px (ou a mesma proporção) para não cortar o banner."
                )
        if erros:
            raise ValidationError(erros)

    @classmethod
    def no_ar(cls):
        from django.utils import timezone

        agora = timezone.now()
        return cls.objects.filter(
            Q(ativo=True),
            Q(inicio__isnull=True) | Q(inicio__lte=agora),
            Q(fim__isnull=True) | Q(fim__gt=agora),
        )
