from django.test import SimpleTestCase, TestCase

from apps.catalogo.models import Categoria
from apps.core.models import Pagina
from apps.core.templatetags.paginas import telefone, texto_pagina


class PaginaTests(TestCase):
    def test_trocas_e_devolucoes_no_mesmo_endereco_da_nuvemshop(self):
        resposta = self.client.get("/trocas-e-devolucoes/")  # criada pela migração
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "<h2>Direito de arrependimento</h2>", html=True)
        self.assertContains(resposta, "7 dias")

    def test_despublicada_da_404_e_categoria_tem_prioridade(self):
        Pagina.objects.create(titulo="Rascunho", slug="rascunho", conteudo="x", publicada=False)
        self.assertEqual(self.client.get("/rascunho/").status_code, 404)
        Pagina.objects.create(titulo="Página", slug="masculino", conteudo="texto da página")
        Categoria.objects.create(nome="Masculino", slug="masculino")
        self.assertNotContains(self.client.get("/masculino/"), "texto da página")

    def test_contato(self):
        resposta = self.client.get("/contato/")
        self.assertContains(resposta, "(85) 98180-9988")
        self.assertContains(resposta, "mailto:stronglasses@outlook.com")

    def test_rodape(self):
        html = self.client.get("/contato/").content.decode()
        for trecho in (
            "Siga-nos no Instagram",
            "Meios de pagamento",
            "Formas de envio",
            "Todos os direitos reservados",
        ):
            self.assertIn(trecho, html)
        self.assertIn('href="/trocas-e-devolucoes/"', html)


class FiltrosPaginaTests(SimpleTestCase):
    def test_texto_pagina_escapa_html(self):
        html = texto_pagina("## Título <b>\n\nLinha 1\nLinha <script>2</script>")
        self.assertEqual(html, "<h2>Título &lt;b&gt;</h2><p>Linha 1<br>Linha &lt;script&gt;2&lt;/script&gt;</p>")

    def test_telefone(self):
        self.assertEqual(telefone("5585981809988"), "(85) 98180-9988")
        self.assertEqual(telefone("8532221234"), "(85) 3222-1234")
