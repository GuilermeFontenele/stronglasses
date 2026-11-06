from datetime import timedelta
from decimal import Decimal

from django import forms
from django.core.validators import FileExtensionValidator
from django.forms import formset_factory, inlineformset_factory, modelformset_factory
from django.utils import timezone

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
from apps.core.crypto import hash_busca
from apps.core.models import Pagina, Parametro
from apps.core.validators import so_digitos
from apps.vendas.models import Pedido


class EstiloPainel:
    """Visual padrão do painel: Sim/Não vira interruptor e o "---------" do Django vira texto claro."""

    rotulos_vazios: dict[str, str] = {}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for nome, campo in self.fields.items():
            if isinstance(campo, forms.BooleanField) and nome != "DELETE":
                campo.widget.attrs["class"] = "interruptor"
            rotulo = self.rotulos_vazios.get(nome, "Selecione…")
            if isinstance(campo, forms.ModelChoiceField) and campo.empty_label is not None:
                campo.empty_label = rotulo
            elif isinstance(campo, forms.ChoiceField) and campo.choices and campo.choices[0][0] == "":
                campo.choices = [("", rotulo), *list(campo.choices)[1:]]


class ArquivoAtual(forms.ClearableFileInput):
    """Mostra o arquivo atual com prévia e um botão de trocar, sem o "Atualmente/Limpar/Modificar" do Django."""

    template_name = "gestao/widgets/arquivo.html"


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


class ProdutoForm(EstiloPainel, forms.ModelForm):
    rotulos_vazios = {"formato": "Não informado"}

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


class VariacaoForm(EstiloPainel, forms.ModelForm):
    rotulos_vazios = {"armacao": "Escolha a armação", "lente": "Sem lente"}

    class Meta:
        model = Variacao
        fields = ["armacao", "lente", "sku", "preco", "estoque", "ativa", "ordem"]
        widgets = {
            "ordem": forms.HiddenInput(attrs={"data-ordem": ""}),
            "preco": forms.NumberInput(attrs={"placeholder": "Padrão", "step": "0.01"}),
            "estoque": forms.NumberInput(attrs={"min": "0"}),
        }


# Produto existente: linhas novas entram pelo botão "Adicionar cor"; produto novo já abre com uma.
VariacaoFormSet = inlineformset_factory(Produto, Variacao, form=VariacaoForm, extra=0, can_delete=True)
VariacaoFormSetNovo = inlineformset_factory(Produto, Variacao, form=VariacaoForm, extra=1, can_delete=True)


class ImagemForm(EstiloPainel, forms.ModelForm):
    class Meta:
        model = ImagemProduto
        fields = ["texto_alternativo", "ordem", "variacao"]
        widgets = {"ordem": forms.HiddenInput(attrs={"data-ordem": ""})}
        labels = {"texto_alternativo": "Descrição da foto", "variacao": "Cor"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        produto = self.instance.produto if self.instance.produto_id else None
        variacoes = Variacao.objects.filter(produto=produto) if produto else Variacao.objects.none()
        self.fields["variacao"].queryset = variacoes.select_related("armacao", "lente")
        self.fields["variacao"].label_from_instance = lambda v: v.descricao_cor
        self.fields["variacao"].empty_label = "Todas as cores"


ImagemFormSet = inlineformset_factory(Produto, ImagemProduto, form=ImagemForm, extra=0, can_delete=True)

EstoqueFormSet = modelformset_factory(Variacao, fields=["estoque", "preco"], extra=0)


class BannerForm(EstiloPainel, forms.ModelForm):
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
            "imagem": ArquivoAtual(attrs={"accept": "image/jpeg,image/png,image/webp"}),
            "imagem_mobile": ArquivoAtual(attrs={"accept": "image/jpeg,image/png,image/webp"}),
            "video": ArquivoAtual(attrs={"accept": "video/mp4,video/webm"}),
            "video_mobile": ArquivoAtual(attrs={"accept": "video/mp4,video/webm"}),
            "inicio": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "fim": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        }


class PaginaForm(EstiloPainel, forms.ModelForm):
    class Meta:
        model = Pagina
        fields = ["titulo", "slug", "conteudo", "seo_descricao", "publicada"]
        widgets = {"conteudo": forms.Textarea(attrs={"rows": 18})}


class ClienteForm(EstiloPainel, forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ["tipo", "nome", "razao_social", "email", "whatsapp"]
        help_texts = {"razao_social": "Só para pessoa jurídica (ex.: hotéis)."}

    def clean(self):
        dados = super().clean()
        if dados.get("tipo") != Cliente.Tipo.PESSOA_JURIDICA:
            dados["razao_social"] = ""  # pessoa física não tem razão social
        return dados


# Parâmetros aparecem agrupados; os que não estão aqui ficam só no admin técnico.
GRUPOS_CONFIGURACAO = [
    ("Loja", ["WHATSAPP_LOJA", "INSTAGRAM_LOJA", "EMAIL_LOJA", "CNPJ_LOJA", "ENDERECO_LOJA"]),
    ("Vendas", ["PIX_DESCONTO_PERCENTUAL", "PARCELAS_SEM_JUROS", "FRETE_GRATIS_ACIMA", "PIX_EXPIRACAO_MINUTOS"]),
    (
        "Envio (padrão dos produtos)",
        ["PESO_PADRAO_G", "EMBALAGEM_ALTURA_CM", "EMBALAGEM_LARGURA_CM", "EMBALAGEM_COMPRIMENTO_CM"],
    ),
    (
        "Remetente (etiqueta e declaração de conteúdo)",
        [
            "REMETENTE_NOME",
            "REMETENTE_ENDERECO",
            "REMETENTE_NUMERO",
            "REMETENTE_COMPLEMENTO",
            "REMETENTE_BAIRRO",
            "REMETENTE_CIDADE",
            "REMETENTE_UF",
            "REMETENTE_CEP",
        ],
    ),
    ("Página inicial", ["OCULOS_ENTREGUES"]),
]


class ConfiguracoesForm(EstiloPainel, forms.Form):
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


# ---------------------------------------------------------------- clientes e vendas


class ClienteNovoForm(ClienteForm):
    class Meta(ClienteForm.Meta):
        fields = ["tipo", "nome", "razao_social", "whatsapp", "email", "documento"]
        widgets = {
            "whatsapp": forms.TextInput(attrs={"placeholder": "+55 85 99999-9999", "inputmode": "tel"}),
            "documento": forms.TextInput(attrs={"inputmode": "numeric", "autocomplete": "off"}),
        }
        help_texts = {
            "razao_social": "Só para pessoa jurídica (ex.: hotéis).",
            "whatsapp": "Com DDI e DDD, começando com +55.",
            "documento": "Opcional. Peça só se precisar: nota fiscal para empresa ou declaração de conteúdo. "
            "Fica guardado criptografado.",
        }

    def clean_documento(self):
        documento = so_digitos(self.cleaned_data.get("documento") or "")
        if documento and Cliente.objects.filter(documento_hash=hash_busca(documento)).exists():
            raise forms.ValidationError("Já existe um cliente com este CPF/CNPJ.")
        return documento


class SelectVariacao(forms.Select):
    """Lista de óculos agrupada por produto; cada opção leva preço e estoque para o resumo ao vivo."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dados: dict[str, tuple[str, int]] = {}

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        opcao = super().create_option(name, value, label, selected, index, subindex, attrs)
        info = self.dados.get(str(value))
        if info:
            opcao["attrs"].update({"data-preco": info[0], "data-estoque": info[1]})
        return opcao


def opcoes_variacoes() -> tuple[list, dict]:
    """(opções agrupadas por produto, {pk: (preço, estoque)}). Uma consulta para o formulário inteiro."""
    grupos: dict[str, list] = {}
    dados = {}
    variacoes = (
        Variacao.objects.filter(produto__isnull=False)
        .select_related("produto", "armacao", "lente")
        .order_by("produto__nome", "ordem", "id")
    )
    for v in variacoes:
        situacao = "sem estoque" if v.estoque <= 0 else f"{v.estoque} em estoque"
        inativo = "" if v.ativa and v.produto.ativo else " · fora da loja"
        rotulo = f"{v.produto.nome} · {v.descricao_cor.lower()} ({situacao}{inativo})"
        grupos.setdefault(v.produto.nome, []).append((v.pk, rotulo))
        dados[str(v.pk)] = (format(v.preco_final, "f"), v.estoque)
    return [("", "Escolha o óculos"), *grupos.items()], dados


class ItemVendaForm(forms.Form):
    variacao = forms.ModelChoiceField(
        queryset=Variacao.objects.filter(produto__isnull=False).select_related("produto", "armacao", "lente"),
        label="Óculos",
        widget=SelectVariacao(attrs={"data-item-variacao": ""}),
        error_messages={"required": "Escolha o óculos.", "invalid_choice": "Óculos não encontrado."},
    )
    quantidade = forms.IntegerField(
        label="Qtd.",
        min_value=1,
        max_value=999,
        initial=1,
        widget=forms.NumberInput(attrs={"min": "1", "data-item-quantidade": "", "inputmode": "numeric"}),
    )
    preco_unitario = forms.DecimalField(
        label="Preço unitário",
        required=False,
        min_value=0,
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"step": "0.01", "min": "0", "placeholder": "Da loja", "data-item-preco": ""}),
    )

    def __init__(self, *args, opcoes=None, **kwargs):
        super().__init__(*args, **kwargs)
        if opcoes is not None:
            escolhas, dados = opcoes
            self.fields["variacao"].choices = escolhas
            self.fields["variacao"].widget.dados = dados


ItemVendaFormSet = formset_factory(ItemVendaForm, extra=0, min_num=1, validate_min=True)


class VendaForm(EstiloPainel, forms.ModelForm):
    aplicar_pix = forms.BooleanField(label="Dar o desconto do Pix", required=False, initial=True)
    baixar_estoque = forms.BooleanField(
        label="Baixar do estoque",
        required=False,
        initial=True,
        help_text="Desligue só se o óculos já saiu do estoque antes (ex.: consignado no hotel).",
    )
    salvar_endereco = forms.BooleanField(label="Salvar este endereço no cadastro do cliente", required=False)
    # Aceita "60000-000" (9 caracteres); clean_cep deixa só os 8 dígitos que o modelo guarda.
    cep = forms.CharField(
        label="CEP",
        required=False,
        max_length=9,
        widget=forms.TextInput(attrs={"inputmode": "numeric", "placeholder": "00000-000", "maxlength": "9"}),
    )

    rotulos_vazios = {"uf": "Estado"}

    class Meta:
        model = Pedido
        fields = [
            "realizado_em",
            "situacao",
            "forma_pagamento",
            "parcelas",
            "desconto",
            "cupom",
            "frete",
            "canal",
            "parceiro",
            "entrega",
            "destinatario",
            "cep",
            "logradouro",
            "numero_endereco",
            "complemento",
            "bairro",
            "cidade",
            "uf",
            "peso_g",
            "observacoes",
        ]
        widgets = {
            "realizado_em": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "desconto": forms.NumberInput(attrs={"step": "0.01", "min": "0", "data-venda-desconto": ""}),
            "frete": forms.NumberInput(attrs={"step": "0.01", "min": "0", "data-venda-frete": ""}),
            "parcelas": forms.NumberInput(attrs={"min": "1", "max": "12"}),
            "peso_g": forms.NumberInput(attrs={"min": "1", "placeholder": "Automático"}),
            "observacoes": forms.Textarea(attrs={"rows": 3}),
            "parceiro": forms.TextInput(attrs={"placeholder": "Ex.: Hotel Praia Mar, Barbearia do Zé"}),
        }
        labels = {"desconto": "Desconto (R$)", "frete": "Frete cobrado (R$)", "numero_endereco": "Número"}
        help_texts = {
            "desconto": "Promoção ou cupom, em reais. O Pix entra depois e nunca sobre o frete.",
            "peso_g": "Vazio = soma do peso cadastrado dos produtos.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["forma_pagamento"].widget.attrs["data-venda-forma"] = ""
        self.fields["aplicar_pix"].widget.attrs["data-venda-pix"] = ""
        self.fields["entrega"].widget.attrs["data-venda-entrega"] = ""
        self.fields["situacao"].choices = [c for c in Pedido.Situacao.choices if c[0] != Pedido.Situacao.CANCELADO]
        for campo in ("desconto", "frete"):
            self.fields[campo].required = False  # vazio = zero

    def clean_desconto(self):
        return self.cleaned_data.get("desconto") or Decimal("0.00")

    def clean_frete(self):
        return self.cleaned_data.get("frete") or Decimal("0.00")

    def clean_cep(self):
        return so_digitos(self.cleaned_data.get("cep") or "")

    def clean_realizado_em(self):
        quando = self.cleaned_data["realizado_em"]
        if quando and quando > timezone.now() + timedelta(minutes=10):
            raise forms.ValidationError("A data da venda não pode estar no futuro.")
        return quando

    def clean(self):
        dados = super().clean()
        forma = dados.get("forma_pagamento")
        dados["aplicar_pix"] = bool(dados.get("aplicar_pix")) and forma == Pedido.FormaPagamento.PIX
        if forma != Pedido.FormaPagamento.CREDITO:
            dados["parcelas"] = 1
            self.instance.parcelas = 1
        if dados.get("entrega") in (Pedido.Entrega.CORREIOS, Pedido.Entrega.TRANSPORTADORA):
            for campo in ("destinatario", "cep", "logradouro", "cidade", "uf"):
                if not dados.get(campo) and campo not in self.errors:
                    self.add_error(campo, "Obrigatório para envio.")
        return dados


class SituacaoVendaForm(EstiloPainel, forms.Form):
    situacao = forms.ChoiceField(
        label="Situação", choices=[c for c in Pedido.Situacao.choices if c[0] != Pedido.Situacao.CANCELADO]
    )
    codigo_rastreio = forms.CharField(
        label="Código de rastreio",
        required=False,
        max_length=40,
        widget=forms.TextInput(attrs={"placeholder": "AA123456789BR", "autocomplete": "off"}),
    )
