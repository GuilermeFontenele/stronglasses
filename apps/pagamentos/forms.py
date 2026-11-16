from django import forms
from django.core.exceptions import ValidationError

from apps.core.validators import so_digitos, validar_cpf
from apps.vendas.models import UFS, Pedido

TELEFONE = {"data-mascara": "telefone", "inputmode": "tel", "autocomplete": "tel", "maxlength": "19"}


class CheckoutForm(forms.Form):
    nome = forms.CharField(
        label="Nome completo", max_length=150, widget=forms.TextInput(attrs={"autocomplete": "name"})
    )
    email = forms.EmailField(label="E-mail", widget=forms.EmailInput(attrs={"autocomplete": "email"}))
    whatsapp = forms.CharField(label="WhatsApp", max_length=19, widget=forms.TextInput(attrs=TELEFONE))
    cpf = forms.CharField(
        label="CPF",
        max_length=14,
        help_text="Exigido pelo Mercado Pago e pela transportadora.",
        widget=forms.TextInput(attrs={"data-mascara": "documento", "inputmode": "numeric", "maxlength": "14"}),
    )
    cep = forms.CharField(
        label="CEP",
        max_length=9,
        widget=forms.TextInput(
            attrs={"data-mascara": "cep", "inputmode": "numeric", "autocomplete": "postal-code", "data-cep": ""}
        ),
    )
    logradouro = forms.CharField(
        label="Rua", max_length=200, widget=forms.TextInput(attrs={"autocomplete": "address-line1"})
    )
    numero = forms.CharField(label="Número", max_length=20)
    complemento = forms.CharField(
        label="Complemento",
        max_length=120,
        required=False,
        widget=forms.TextInput(attrs={"autocomplete": "address-line2"}),
    )
    bairro = forms.CharField(label="Bairro", max_length=100)
    cidade = forms.CharField(
        label="Cidade", max_length=100, widget=forms.TextInput(attrs={"autocomplete": "address-level2"})
    )
    uf = forms.ChoiceField(
        label="Estado",
        choices=[("", "Estado"), *sorted(UFS.items())],
        widget=forms.Select(attrs={"autocomplete": "address-level1"}),
    )
    frete = forms.CharField(
        max_length=20, error_messages={"required": "Calcule o frete e escolha uma opção."}, widget=forms.HiddenInput
    )
    forma = forms.ChoiceField(
        label="Pagamento",
        choices=[(Pedido.FormaPagamento.PIX, "Pix"), (Pedido.FormaPagamento.CREDITO, "Cartão de crédito")],
        initial=Pedido.FormaPagamento.PIX,
        widget=forms.RadioSelect,
    )
    aceite = forms.BooleanField(
        label="Li e concordo com a política de privacidade e a de trocas e devoluções.",
        error_messages={"required": "Para continuar, confirme que leu as políticas."},
    )
    novidades = forms.BooleanField(label="Quero receber novidades e ofertas por e-mail.", required=False)

    def clean_nome(self):
        nome = " ".join(self.cleaned_data["nome"].split())
        if len(nome.split()) < 2:
            raise ValidationError("Informe nome e sobrenome.")
        return nome

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()

    def clean_whatsapp(self):
        digitos = so_digitos(self.cleaned_data["whatsapp"])
        if len(digitos) in (10, 11):
            digitos = "55" + digitos
        if not (12 <= len(digitos) <= 13 and digitos.startswith("55")):
            raise ValidationError("Informe o WhatsApp com DDD.")
        return "+" + digitos

    def clean_cpf(self):
        cpf = so_digitos(self.cleaned_data["cpf"])
        validar_cpf(cpf)
        return cpf

    def clean_cep(self):
        cep = so_digitos(self.cleaned_data["cep"])
        if len(cep) != 8:
            raise ValidationError("CEP com 8 números.")
        return cep
