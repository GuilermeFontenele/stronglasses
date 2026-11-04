from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.template import Context, Template
from django.test import TestCase

from apps.catalogo.models import (
    AcabamentoArmacao,
    CorLente,
    Produto,
    Variacao,
    caminho_imagem_produto,
    validar_tamanho_imagem,
)
from apps.core.models import RegistroAuditoria


class CatalogoBase(TestCase):
    def setUp(self):
        self.tartaruga = AcabamentoArmacao.objects.create(nome="Tartaruga", cor_hex="#6B3E1F")
        self.preta = AcabamentoArmacao.objects.create(nome="Preta", cor_hex="#111111")
        self.verde = CorLente.objects.create(nome="Verde", cor_hex="#55704A")
        self.produto = Produto.objects.create(nome="Roshi", slug="oculos-de-sol-roshi", preco=Decimal("94.90"))


class ProdutoTests(CatalogoBase):
    def test_preco_final_e_disponibilidade(self):
        v = Variacao.objects.create(produto=self.produto, armacao=self.tartaruga, lente=self.verde, sku="RSH-TT-VD")
        self.assertEqual(v.preco_final, Decimal("94.90"))
        self.assertFalse(v.disponivel)
        v.preco, v.estoque = Decimal("99.90"), 3
        self.assertEqual(v.preco_final, Decimal("99.90"))
        self.assertTrue(v.disponivel)
        self.assertEqual(v.descricao_cor, "Armação tartaruga, lente verde")

    def test_preco_riscado_precisa_ser_maior(self):
        self.produto.preco_comparativo = Decimal("50.00")
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.produto.save()

    def test_combinacao_unica(self):
        Variacao.objects.create(produto=self.produto, armacao=self.tartaruga, lente=self.verde, sku="A")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Variacao.objects.create(produto=self.produto, armacao=self.tartaruga, lente=self.verde, sku="B")
        Variacao.objects.create(produto=self.produto, armacao=self.preta, sku="C")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Variacao.objects.create(produto=self.produto, armacao=self.preta, sku="D")

    def test_pronto_para_envio(self):
        self.assertFalse(self.produto.pronto_para_envio)
        self.produto.peso_g, self.produto.altura_cm = 180, Decimal("6")
        self.produto.largura_cm, self.produto.comprimento_cm = Decimal("16"), Decimal("8")
        self.assertTrue(self.produto.pronto_para_envio)

    def test_cor_hex_validada(self):
        with self.assertRaises(ValidationError):
            AcabamentoArmacao(nome="X", cor_hex="red; background:url(x)").full_clean()


class UploadTests(CatalogoBase):
    def test_nome_de_arquivo_aleatorio(self):
        caminho = caminho_imagem_produto(None, "../../etc/passwd.PNG")
        self.assertTrue(caminho.startswith("produtos/"))
        self.assertTrue(caminho.endswith(".png"))
        self.assertNotIn("..", caminho)

    def test_tamanho_maximo(self):
        class Arquivo:
            size = 6 * 1024 * 1024

        with self.assertRaises(ValidationError):
            validar_tamanho_imagem(Arquivo())


class SwatchTests(CatalogoBase):
    def test_renderiza_duas_metades_e_rotulo(self):
        v = Variacao.objects.create(produto=self.produto, armacao=self.tartaruga, lente=self.verde, sku="A")
        html = Template("{% load catalogo %}{% swatch v %}").render(Context({"v": v}))
        self.assertIn('fill="#6B3E1F"', html)
        self.assertIn('fill="#55704A"', html)
        self.assertIn('aria-label="Armação tartaruga, lente verde"', html)
        self.assertNotIn("style=", html)


class AdminTests(CatalogoBase):
    def setUp(self):
        super().setUp()
        self.admin = get_user_model().objects.create_superuser("dono", "dono@exemplo.com", "s" * 16)
        self.client.force_login(self.admin)

    def test_paginas_do_painel_carregam(self):
        for url in (
            "/painel/catalogo/produto/",
            f"/painel/catalogo/produto/{self.produto.pk}/change/",
            "/painel/catalogo/acabamentoarmacao/",
            "/painel/clientes/cliente/",
            "/painel/core/parametro/",
            "/painel/core/registroauditoria/",
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_alteracao_pelo_painel_gera_auditoria(self):
        url = f"/painel/catalogo/corlente/{self.verde.pk}/change/"
        resposta = self.client.post(url, {"nome": "Verde G15", "cor_hex": "#55704A", "ativo": "on"})
        self.assertEqual(resposta.status_code, 302)
        registro = RegistroAuditoria.objects.get(modelo="catalogo.CorLente", acao="U")
        self.assertEqual(registro.antes, {"nome": "Verde"})
        self.assertEqual(registro.depois, {"nome": "Verde G15"})
        self.assertEqual(registro.usuario, self.admin)
