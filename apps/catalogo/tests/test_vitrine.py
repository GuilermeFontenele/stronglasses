import io
import tempfile
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.core.exceptions import ValidationError
from django.core.management import CommandError, call_command
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from PIL import Image

from apps.catalogo.models import AcabamentoArmacao, Banner, Categoria, CorLente, Produto, Variacao
from apps.catalogo.templatetags.vitrine import brl, milhar
from apps.catalogo.views import _json_seguro
from apps.core.models import Parametro, Redirecionamento
from apps.nuvemshop.imagens import ImagemInvalida


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


class HomeTests(VitrineBase):
    def test_contador_de_oculos_entregues(self):
        Parametro.objects.filter(chave="OCULOS_ENTREGUES").update(valor="12345")
        from django.core.cache import cache

        cache.clear()
        resposta = self.client.get("/")
        self.assertContains(resposta, 'data-contador="12345"')
        self.assertContains(resposta, "+12.345")  # sem JS o número final já aparece
        self.assertContains(resposta, "óculos entregues em todo o Brasil")
        self.assertContains(resposta, "js/vitrine.js")
        self.assertEqual(milhar(10000), "10.000")

    def test_banner_respeita_ativo_e_periodo(self):
        agora = timezone.now()
        Banner.objects.create(titulo="Mapa do Brasil", imagem="banners/mapa.webp")
        Banner.objects.create(titulo="Desligado", imagem="banners/a.webp", ativo=False)
        Banner.objects.create(titulo="Futuro", imagem="banners/b.webp", inicio=agora + timedelta(days=1))
        Banner.objects.create(titulo="Vencido", imagem="banners/c.webp", fim=agora - timedelta(days=1))
        resposta = self.client.get("/")
        self.assertContains(resposta, 'alt="Mapa do Brasil"')
        for titulo in ("Desligado", "Futuro", "Vencido"):
            self.assertNotContains(resposta, titulo)

    def test_sem_banner_mostra_titulo_em_texto(self):
        self.assertContains(self.client.get("/"), "<h1>")

    def test_link_do_banner_validado(self):
        for link in ("javascript:alert(1)", "http://x.com", "//x.com"):
            with self.subTest(link=link), self.assertRaises(ValidationError):
                Banner(titulo="X", link=link).full_clean(exclude=["imagem"])
        Banner(titulo="X", link="/masculino/").full_clean(exclude=["imagem"])

    def test_rodape_e_whatsapp(self):
        resposta = self.client.get("/")
        self.assertContains(resposta, "https://wa.me/5585981809988")
        self.assertContains(resposta, "instagram.com/stronglasses")


class ProdutoSeoTests(VitrineBase):
    def test_comprar_pelo_whatsapp_com_cor(self):
        resposta = self.client.get("/produtos/oculos-de-sol-roshi/")
        self.assertContains(resposta, "Comprar pelo WhatsApp")
        self.assertIn("lente%20verde", resposta.content.decode())
        self.assertIn("Roshi", resposta.context["mensagem_whatsapp"])

    def test_dados_estruturados_com_nonce(self):
        resposta = self.client.get("/produtos/oculos-de-sol-roshi/")
        html = resposta.content.decode()
        self.assertIn('<script type="application/ld+json" nonce="', html)
        self.assertIn('"price": "94.90"', html)
        self.assertIn("InStock", html)
        self.assertIn('rel="canonical" href="http://testserver/produtos/oculos-de-sol-roshi/"', html)

    def test_galeria_com_miniaturas(self):
        from apps.catalogo.models import ImagemProduto

        for i in range(3):
            ImagemProduto.objects.create(
                produto=self.produto, imagem=f"produtos/{i}.jpg", texto_alternativo=f"Foto {i}"
            )
        html = self.client.get("/produtos/oculos-de-sol-roshi/").content.decode()
        self.assertIn('id="foto-3"', html)
        self.assertIn('href="#foto-3"', html)  # sem JS a miniatura ainda leva à foto
        self.assertEqual(html.count('aria-current="true"'), 1)

    def test_json_seguro_nao_fecha_script(self):
        self.assertNotIn("</script>", _json_seguro({"nome": "</script><script>alert(1)"}))

    def test_sitemap_e_robots(self):
        sitemap = self.client.get("/sitemap.xml").content.decode()
        self.assertIn("/produtos/oculos-de-sol-roshi/", sitemap)
        self.assertIn("/oculos-de-sol/", sitemap)
        self.assertNotIn("rascunho", sitemap)
        robots = self.client.get("/robots.txt")
        self.assertContains(robots, "Sitemap: http://testserver/sitemap.xml")
        self.assertNotContains(robots, "painel")  # não entrega o endereço do admin


class CriarBannerTests(TestCase):
    def _png(self):
        saida = io.BytesIO()
        Image.new("RGB", (20, 10), "white").save(saida, "PNG")
        return saida.getvalue()

    def test_cria_banner_com_a_primeira_url_que_funciona(self):
        alvo = "apps.catalogo.management.commands.criar_banner.baixar_imagem"
        with (
            tempfile.TemporaryDirectory() as pasta,
            override_settings(MEDIA_ROOT=pasta),
            mock.patch(alvo, side_effect=[ImagemInvalida("404"), (self._png(), "png")]) as baixar,
        ):
            call_command("criar_banner", stdout=io.StringIO())
            banner = Banner.objects.get()
            self.assertTrue(banner.imagem.name.startswith("banners/"))
            self.assertEqual(baixar.call_count, 2)

    def test_erro_quando_nenhuma_url_funciona(self):
        alvo = "apps.catalogo.management.commands.criar_banner.baixar_imagem"
        with mock.patch(alvo, side_effect=ImagemInvalida("404")), self.assertRaises(CommandError):
            call_command("criar_banner", "--url", "https://exemplo.com/a.png", stdout=io.StringIO())
        self.assertFalse(Banner.objects.exists())
