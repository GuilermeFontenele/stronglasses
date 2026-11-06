from decimal import Decimal

from django import forms
from django.core.validators import FileExtensionValidator
from django.forms import inlineformset_factory, modelformset_factory

from apps.catalogo.models import (
    EXTENSOES_IMAGEM,
    Banner,
    Categoria,
    ImagemProduto,
    Produto,
    Variacao,
    validar_tamanho_imagem,
)
from apps.clientes.models import Cliente
from apps.core.models import Pagina, Parametro


class VariosArquivos(forms.ClearableFileInput):
    allow_multiple_selected = True


class VariasImagens(forms.ImageField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", VariosArquivos(attrs={"accept": "image/jpeg,image/png,image/webp"}))
        kwargs.setdefault("validators", [FileExtensionValidator(EXTENSOES_IMAGEM), validar_tamanho_imagem])
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        unico = super().clean
        if isinstance(data, (list, tuple)):
            return [unico(arquivo, initial) for arquivo in data if arquivo]
        resultado = unico(data, initial)
        return [resultado] if resultado else []


class ProdutoForm(forms.ModelForm):
    categorias = forms.ModelMultipleChoiceField(
        Categoria.objects.order_by("ordem", "nome"), required=False, widget=forms.CheckboxSelectMultiple
    )
    novas_fotos = VariasImagens(label="Adicionar fotos", required=False, help_text="JPG, PNG ou WEBP de até 5 MB.")

    class Meta:
        model = Produto
        fields = [
            "nome",
            "slug",
            "tipo",
            "publico",
            "formato",
            "descricao",
            "preco",
            "preco_comparativo",
            "categorias",
            "ativo",
            "destaque",
            "peso_g",
            "altura_cm",
            "largura_cm",
            "comprimento_cm",
            "seo_titulo",
            "seo_descricao",
        ]
        widgets = {"descricao": forms.Textarea(attrs={"rows": 8})}

    def clean(self):
        dados = super().clean()
        preco, comparativo = dados.get("preco"), dados.get("preco_comparativo")
        if preco and comparativo and comparativo <= preco:
            self.add_error("preco_comparativo", "O preço riscado precisa ser maior que o preço.")
        return dados


VariacaoFormSet = inlineformset_factory(
    Produto,
    Variacao,
    fields=["armacao", "lente", "sku", "preco", "estoque", "ativa", "ordem"],
    extra=1,
    can_delete=True,
)


class ImagemForm(forms.ModelForm):
    class Meta:
        model = ImagemProduto
        fields = ["texto_alternativo", "ordem", "variacao"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        produto = self.instance.produto if self.instance.produto_id else None
        variacoes = Variacao.objects.filter(produto=produto) if produto else Variacao.objects.none()
        self.fields["variacao"].queryset = variacoes.select_related("armacao", "lente")
        self.fields["variacao"].label_from_instance = lambda v: v.descricao_cor
        self.fields["variacao"].empty_label = "Todas as cores"


ImagemFormSet = inlineformset_factory(Produto, ImagemProduto, form=ImagemForm, extra=0, can_delete=True)

EstoqueFormSet = modelformset_factory(Variacao, fields=["estoque", "preco"], extra=0)


class BannerForm(forms.ModelForm):
    class Meta:
        model = Banner
        fields = [
            "titulo",
            "imagem",
            "imagem_mobile",
            "video",
            "video_mobile",
            "link",
            "ativo",
            "inicio",
            "fim",
            "ordem",
        ]
        widgets = {
            "inicio": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "fim": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        }


class PaginaForm(forms.ModelForm):
    class Meta:
        model = Pagina
        fields = ["titulo", "slug", "conteudo", "seo_descricao", "publicada"]
        widgets = {"conteudo": forms.Textarea(attrs={"rows": 18})}


class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ["tipo", "nome", "razao_social", "email", "whatsapp"]


# Parâmetros aparecem agrupados; os que não estão aqui ficam só no admin técnico.
GRUPOS_CONFIGURACAO = [
    ("Loja", ["WHATSAPP_LOJA", "INSTAGRAM_LOJA", "EMAIL_LOJA", "CNPJ_LOJA", "ENDERECO_LOJA"]),
    ("Vendas", ["PIX_DESCONTO_PERCENTUAL", "PARCELAS_SEM_JUROS", "FRETE_GRATIS_ACIMA", "PIX_EXPIRACAO_MINUTOS"]),
    (
        "Envio (padrão dos produtos)",
        ["PESO_PADRAO_G", "EMBALAGEM_ALTURA_CM", "EMBALAGEM_LARGURA_CM", "EMBALAGEM_COMPRIMENTO_CM"],
    ),
    ("Página inicial", ["OCULOS_ENTREGUES"]),
]


class ConfiguracoesForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        chaves = [chave for _, grupo in GRUPOS_CONFIGURACAO for chave in grupo]
        self.parametros = {p.chave: p for p in Parametro.objects.filter(chave__in=chaves)}
        self.grupos = []
        for titulo, grupo in GRUPOS_CONFIGURACAO:
            nomes = []
            for chave in grupo:
                parametro = self.parametros.get(chave)
                if parametro is None:
                    continue
                self.fields[chave] = self._campo(parametro)
                nomes.append(chave)
            if nomes:
                self.grupos.append((titulo, nomes))

    @staticmethod
    def _campo(parametro: Parametro) -> forms.Field:
        rotulo = parametro.chave.replace("_", " ").capitalize()
        comum = {"label": rotulo, "help_text": parametro.descricao}
        if parametro.tipo == Parametro.Tipo.INTEIRO:
            return forms.IntegerField(initial=parametro.valor_tipado(), **comum)
        if parametro.tipo == Parametro.Tipo.DECIMAL:
            return forms.DecimalField(initial=parametro.valor_tipado(), decimal_places=2, **comum)
        if parametro.tipo == Parametro.Tipo.BOOLEANO:
            return forms.BooleanField(initial=parametro.valor_tipado(), required=False, **comum)
        return forms.CharField(initial=parametro.valor, required=False, max_length=255, **comum)

    def grupos_com_campos(self):
        return [(titulo, [self[nome] for nome in nomes]) for titulo, nomes in self.grupos]

    def alterados(self) -> list[tuple[Parametro, str]]:
        mudancas = []
        for chave, parametro in self.parametros.items():
            if chave not in self.cleaned_data:
                continue
            valor = self.cleaned_data[chave]
            if isinstance(valor, bool):
                texto = "true" if valor else "false"
            elif isinstance(valor, Decimal):
                texto = format(valor.normalize(), "f")
            else:
                texto = "" if valor is None else str(valor).strip()
            if texto != parametro.valor:
                mudancas.append((parametro, texto))
        return mudancas
