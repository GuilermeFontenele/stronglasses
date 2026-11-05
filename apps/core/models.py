from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models

from .middleware import get_usuario_atual


class AuditModel(models.Model):
    """Campos de auditoria preenchidos automaticamente a partir da requisição."""

    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="criado por",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
        related_name="+",
    )
    atualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="atualizado por",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
        related_name="+",
    )

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        usuario = get_usuario_atual()
        if usuario is not None:
            if self._state.adding and self.criado_por_id is None:
                self.criado_por = usuario
            self.atualizado_por = usuario
            update_fields = kwargs.get("update_fields")
            if update_fields is not None:
                kwargs["update_fields"] = {*update_fields, "atualizado_por", "atualizado_em"}
        super().save(*args, **kwargs)


class Parametro(AuditModel):
    """Configuração da loja editável pelo painel (ex.: % de desconto no Pix)."""

    class Tipo(models.TextChoices):
        TEXTO = "texto", "Texto"
        INTEIRO = "inteiro", "Inteiro"
        DECIMAL = "decimal", "Decimal"
        BOOLEANO = "booleano", "Sim/Não"

    chave = models.CharField(
        "chave",
        max_length=60,
        primary_key=True,
        validators=[RegexValidator(r"^[A-Z][A-Z0-9_]*$", "Use MAIÚSCULAS_COM_UNDERSCORE.")],
    )
    valor = models.CharField("valor", max_length=255)
    tipo = models.CharField("tipo", max_length=10, choices=Tipo.choices, default=Tipo.TEXTO)
    descricao = models.CharField("descrição", max_length=255)

    class Meta:
        ordering = ["chave"]
        verbose_name = "parâmetro da loja"
        verbose_name_plural = "parâmetros da loja"

    def __str__(self):
        return self.chave

    def valor_tipado(self):
        bruto = self.valor.strip()
        if self.tipo == self.Tipo.INTEIRO:
            return int(bruto)
        if self.tipo == self.Tipo.DECIMAL:
            return Decimal(bruto.replace(",", "."))
        if self.tipo == self.Tipo.BOOLEANO:
            return bruto.lower() in {"1", "true", "sim", "s", "yes"}
        return bruto

    def clean(self):
        try:
            self.valor_tipado()
        except (ValueError, InvalidOperation) as exc:
            raise ValidationError({"valor": f"Valor incompatível com o tipo {self.get_tipo_display()}."}) from exc


class RegistroAuditoria(models.Model):
    """Trilha de auditoria imutável: quem alterou o quê, quando e de onde."""

    class Acao(models.TextChoices):
        CRIACAO = "I", "Criação"
        ALTERACAO = "U", "Alteração"
        EXCLUSAO = "D", "Exclusão"
        ACESSO = "A", "Acesso a dado pessoal"
        EXPORTACAO = "E", "Exportação de dados"
        ANONIMIZACAO = "N", "Anonimização"

    quando = models.DateTimeField("quando", auto_now_add=True, db_index=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="usuário",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    usuario_nome = models.CharField("usuário (texto)", max_length=150, blank=True)
    ip = models.GenericIPAddressField("IP", null=True, blank=True)
    acao = models.CharField("ação", max_length=1, choices=Acao.choices)
    modelo = models.CharField("modelo", max_length=100, db_index=True)
    objeto_id = models.CharField("ID do objeto", max_length=64, db_index=True)
    objeto_repr = models.CharField("objeto", max_length=200, blank=True)
    antes = models.JSONField("antes", null=True, blank=True)
    depois = models.JSONField("depois", null=True, blank=True)

    class Meta:
        ordering = ["-quando"]
        verbose_name = "registro de auditoria"
        verbose_name_plural = "registros de auditoria"
        indexes = [models.Index(fields=["modelo", "objeto_id"], name="core_audit_modelo_obj_idx")]

    def __str__(self):
        return f"{self.get_acao_display()} {self.modelo}#{self.objeto_id}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Registros de auditoria não podem ser alterados.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Registros de auditoria não podem ser excluídos.")


class Redirecionamento(AuditModel):
    """Redirecionamento 301/302 de URLs antigas (preserva SEO e links já divulgados)."""

    origem = models.CharField(
        "URL antiga",
        max_length=255,
        unique=True,
        help_text="Só o caminho, começando com /. Ex.: /produtos/oculos-antigo/",
    )
    destino = models.CharField(
        "URL nova", max_length=500, help_text="Caminho (/produtos/novo/) ou endereço completo https://"
    )
    permanente = models.BooleanField("permanente (301)", default=True)
    ativo = models.BooleanField("ativo", default=True)
    acessos = models.PositiveIntegerField("acessos", default=0, editable=False)

    class Meta:
        ordering = ["origem"]
        verbose_name = "redirecionamento"
        verbose_name_plural = "redirecionamentos"

    def __str__(self):
        return f"{self.origem} → {self.destino}"

    @staticmethod
    def normalizar(caminho: str) -> str:
        caminho = "/" + (caminho or "").strip().lstrip("/")
        return caminho.split("?", 1)[0].split("#", 1)[0]

    def clean(self):
        self.origem = self.normalizar(self.origem)
        if "://" in self.origem:
            raise ValidationError({"origem": "Informe só o caminho, sem domínio."})
        if not (self.destino.startswith("/") or self.destino.startswith("https://")):
            raise ValidationError({"destino": "Use um caminho começando com / ou um endereço https://."})
        if self.destino.rstrip("/") == self.origem.rstrip("/"):
            raise ValidationError({"destino": "O destino é igual à origem."})


class Pagina(AuditModel):
    """Página institucional editável no painel (ex.: /trocas-e-devolucoes/, mesmo endereço da Nuvemshop)."""

    titulo = models.CharField("título", max_length=120)
    slug = models.SlugField(
        "endereço (slug)",
        max_length=120,
        unique=True,
        help_text="Fica em /<slug>/. Não use o mesmo endereço de uma categoria (a categoria tem prioridade).",
    )
    conteudo = models.TextField(
        "conteúdo",
        help_text="Texto simples. Deixe uma linha em branco entre parágrafos e comece um subtítulo com ## .",
    )
    seo_descricao = models.CharField("descrição para o Google", max_length=160, blank=True)
    publicada = models.BooleanField("publicada", default=True)

    class Meta:
        ordering = ["titulo"]
        verbose_name = "página"
        verbose_name_plural = "páginas"

    def __str__(self):
        return self.titulo

    def get_absolute_url(self):
        return f"/{self.slug}/"
