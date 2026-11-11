from io import BytesIO, StringIO
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from PIL import Image, ImageDraw

from apps.catalogo import provador
from apps.catalogo.models import ImagemProduto, Variacao

from .test_vitrine import VitrineBase


def foto_de_frente(fundo=(255, 255, 255)) -> bytes:
    """Óculos simulado: duas lentes escuras, ponte e hastes finas saindo para as laterais."""
    imagem = Image.new("RGB", (400, 200), fundo)
    desenho = ImageDraw.Draw(imagem)
    desenho.rounded_rectangle((60, 60, 180, 140), radius=18, fill=(30, 30, 30))
    desenho.rounded_rectangle((220, 60, 340, 140), radius=18, fill=(30, 30, 30))
    desenho.rectangle((180, 70, 220, 76), fill=(30, 30, 30))  # ponte
    desenho.rectangle((0, 64, 60, 66), fill=(30, 30, 30))  # haste esquerda
    desenho.rectangle((340, 64, 400, 66), fill=(30, 30, 30))  # haste direita
    saida = BytesIO()
    imagem.save(saida, "PNG")
    return saida.getvalue()


class GerarTests(VitrineBase):
    def test_tira_fundo_e_hastes(self):
        png = provador.gerar(BytesIO(foto_de_frente()))
        resultado = Image.open(BytesIO(png))
        self.assertEqual(resultado.mode, "RGBA")
        # Sem as hastes: a largura é a da frente (≈ 280 px), não a da foto inteira (400 px).
        self.assertLess(abs(resultado.width - 280), 12)
        self.assertLess(abs(resultado.height - 80), 12)
        meio_da_lente = resultado.getpixel((60, resultado.height // 2))
        self.assertEqual(meio_da_lente[3], 255)
        fora = resultado.getpixel((resultado.width // 2, resultado.height - 2))  # abaixo da ponte, entre as lentes
        self.assertEqual(fora[3], 0)

    def test_foto_sem_oculos(self):
        vazia = BytesIO()
        Image.new("RGB", (300, 300), "white").save(vazia, "PNG")
        self.assertIsNone(provador.gerar(BytesIO(vazia.getvalue())))

    def test_atualizar_usa_a_foto_da_cor_e_o_comando_refaz(self):
        ImagemProduto.objects.create(
            produto=self.produto,
            variacao=self.v1,
            imagem=SimpleUploadedFile("frente.png", foto_de_frente(), content_type="image/png"),
        )
        self.assertTrue(provador.atualizar(self.v1))
        self.v1.refresh_from_db()
        self.assertTrue(self.v1.imagem_provador.name.startswith("provador/"))
        self.assertFalse(provador.atualizar(self.v1))  # já tem: não refaz sem forçar
        self.assertFalse(provador.atualizar(self.v2))  # cor sem foto e o produto tem 2 cores
        saida = StringIO()
        call_command("gerar_provador", "--todas", stdout=saida)
        self.assertIn("1 imagem(ns) do provador gerada(s). 1 cor(es) sem foto de frente.", saida.getvalue())


class PaginaProdutoTests(VitrineBase):
    def setUp(self):
        super().setUp()
        from apps.catalogo import views

        views.provador_instalado.cache_clear()
        self.addCleanup(views.provador_instalado.cache_clear)

    def test_sem_arquivos_do_mediapipe_nao_mostra(self):
        Variacao.objects.filter(pk=self.v1.pk).update(imagem_provador="provador/x.png")
        with mock.patch("apps.catalogo.views.finders.find", return_value=None):
            html = self.client.get("/produtos/oculos-de-sol-roshi/").content.decode()
        self.assertNotIn("Provar no rosto", html)

    def test_botao_dialogo_e_csp_com_wasm(self):
        Variacao.objects.filter(pk=self.v1.pk).update(imagem_provador="provador/x.png")
        with mock.patch("apps.catalogo.views.finders.find", return_value="face_landmarker.task"):
            resposta = self.client.get("/produtos/oculos-de-sol-roshi/")
        html = resposta.content.decode()
        self.assertIn("Provar no rosto", html)
        self.assertIn('data-src="/media/provador/x.png"', html)
        self.assertIn('src="/static/js/provador.js"', html)
        self.assertIn("nenhuma imagem é enviada nem guardada", html)
        self.assertNotIn("style=", html)
        self.assertIn("'wasm-unsafe-eval'", resposta["Content-Security-Policy"])
        home = self.client.get("/")
        self.assertNotIn("wasm-unsafe-eval", home.get("Content-Security-Policy", ""))
