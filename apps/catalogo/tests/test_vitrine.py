from decimal import Decimal

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from apps.catalogo.models import AcabamentoArmacao, Categoria, CorLente, Produto, Variacao
from apps.catalogo.templatetags.vitrine import brl
from apps.core.models import Parametro, Redirecionamento


class VitrineBase(TestCase):
    def setUp(self):
        Parametro.objects.update_or_create(chave="PIX_DESCONTO_PERCENTUAL", defaults={"valor": "5"})
        Parametro.objects.update_or_create(chave="PARCELAS_SEM_JUROS", defaults={"valor": "3"})
        self.preta = AcabamentoArmacao.objects.create(nome="Preta", cor_hex="#111111")
        self.tartaruga = AcabamentoArmacao.objects.create(nome="Tartaruga", cor_hex="#6B3E1F")
        self.verde = CorLente.objects.create(nome="Verde", cor_hex="#55704A")
        self.categoria = Categoria.objects.create(nome="Óculos de sol", slug="oculos-de-sol")
        self.produto = Produto.objects.create(
            nome="Roshi", slug="oculos-de-sol-roshi", preco=Decimal("94.90"), ativo=True, destaque=True
        )
        self.produto.categorias.add(self.categoria)
        self.v1 = Variacao.objects.create(
            produto=self.produto, armacao=self.preta, lente=self.verde, sku="RSH-PT", estoque=2
        )
        self.v2 = Variacao.objects.create(
            produto=self.produto, armacao=self.tartaruga, lente=self.verde, sku="RSH-TT", estoque=0
        )
        self.oculto = Produto.objects.create(nome="Rascunho", slug="rascunho", preco=Decimal("50.00"))
        self.oculto.categorias.add(self.categoria)


class VitrineTests(VitrineBase):
    def test_brl(self):
        self.assertEqual(brl(Decimal("1234.5")), "R$ 1.234,50")
        self.assertEqual(brl(None), "")

    def test_home_lista_so_publicados(self):
        resposta = self.client.get("/")
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Roshi")
        self.assertNotContains(resposta, "Rascunho")
        self.assertContains(resposta, 'href="/oculos-de-sol/"')

    def test_pagina_do_produto(self):
        resposta = self.client.get("/produtos/oculos-de-sol-roshi/")
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "R$ 94,90")
        self.assertContains(resposta, "R$ 90,16")  # 5% no Pix
        self.assertContains(resposta, "3x de R$ 31,63")
        self.assertEqual(resposta.context["selecionada"], self.v1)  # primeira com estoque
        self.assertContains(resposta, "Em estoque")

    def test_escolher_cor(self):
        resposta = self.client.get(f"/produtos/oculos-de-sol-roshi/?cor={self.v2.pk}")
        self.assertEqual(resposta.context["selecionada"], self.v2)
        self.assertContains(resposta, "Esgotado nesta cor")
        # cor inválida volta para a padrão em vez de quebrar
        resposta = self.client.get("/produtos/oculos-de-sol-roshi/?cor=abc")
        self.assertEqual(resposta.context["selecionada"], self.v1)

    def test_produto_nao_publicado_404(self):
        self.assertEqual(self.client.get("/produtos/rascunho/").status_code, 404)

    def test_categoria_com_filtro_e_ordem(self):
        resposta = self.client.get("/oculos-de-sol/?publico=unissex&ordem=menor-preco")
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Roshi")
        self.assertNotContains(resposta, "Rascunho")
        resposta = self.client.get("/oculos-de-sol/?publico=feminino")
        self.assertNotContains(resposta, "Roshi")

    def test_categoria_paginada(self):
        for i in range(30):
            p = Produto.objects.create(nome=f"Modelo {i:02}", slug=f"modelo-{i}", preco=Decimal("80"), ativo=True)
            p.categorias.add(self.categoria)
        resposta = self.client.get("/oculos-de-sol/?pagina=2")
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.context["pagina"].number, 2)
        self.assertContains(resposta, "2 de 2")

    def test_categoria_inexistente_404_e_redirecionamento(self):
        self.assertEqual(self.client.get("/nao-existe/").status_code, 404)
        Redirecionamento.objects.create(origem="/antiga/", destino="/oculos-de-sol/")
        resposta = self.client.get("/antiga/")
        self.assertEqual(resposta.status_code, 301)

    def test_sem_style_inline(self):
        for url in ("/", "/produtos/oculos-de-sol-roshi/", "/oculos-de-sol/"):
            html = self.client.get(url).content.decode()
            self.assertNotIn("style=", html, url)
            self.assertNotIn("<style", html, url)

    def test_consultas_limitadas(self):
        with CaptureQueriesContext(connection) as consultas:
            self.client.get("/produtos/oculos-de-sol-roshi/")
        self.assertLess(len(consultas), 12)  # sem N+1 nas variações e fotos
