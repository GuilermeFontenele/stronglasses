import io
import json
import tempfile
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from PIL import Image

from apps.catalogo.models import AcabamentoArmacao, Banner, Categoria, CorLente, ImagemProduto, Produto, Variacao
from apps.clientes.models import Cliente, Endereco
from apps.core.models import Pagina, Parametro, RegistroAuditoria
from apps.gestao import graficos
from apps.historico.models import ItemPedidoHistorico, PedidoHistorico

Usuario = get_user_model()


def png(nome="foto.png"):
    saida = io.BytesIO()
    Image.new("RGB", (20, 20), "white").save(saida, "PNG")
    return SimpleUploadedFile(nome, saida.getvalue(), content_type="image/png")


class BaseGestao(TestCase):
    def setUp(self):
        cache.clear()
        self.dono = Usuario.objects.create_superuser("dono", "dono@exemplo.com", "Senha-forte-123")
        self.categoria = Categoria.objects.create(nome="Feminino", slug="feminino")
        self.preta = AcabamentoArmacao.objects.create(nome="Preta", cor_hex="#111111")
        self.verde = CorLente.objects.create(nome="Verde", cor_hex="#55704A")
        self.produto = Produto.objects.create(nome="Zaik", slug="zaik", preco=Decimal("85.90"), ativo=True)
        self.produto.categorias.add(self.categoria)
        self.variacao = Variacao.objects.create(
            produto=self.produto, armacao=self.preta, lente=self.verde, sku="ZK-PT", estoque=1
        )
        self.rascunho = Produto.objects.create(nome="Rascunho", slug="rascunho", preco=Decimal("50"))
        self.cliente = Cliente.objects.create(
            nome="Maria Souza", email="maria@exemplo.com", whatsapp="5585999998888", documento="52998224725"
        )
        Endereco.objects.create(
            cliente=self.cliente, cep="60000000", logradouro="Rua A", cidade="Fortaleza", uf="CE", padrao=True
        )
        agora = timezone.now()
        self.pedido = PedidoHistorico.objects.create(
            nuvemshop_id=1,
            numero=101,
            cliente=self.cliente,
            realizado_em=agora - timedelta(days=3),
            status="open",
            status_pagamento="paid",
            subtotal=Decimal("171.80"),
            total=Decimal("171.80"),
            uf="CE",
            cidade="Fortaleza",
        )
        ItemPedidoHistorico.objects.create(
            pedido=self.pedido, produto=self.produto, nome="Zaik", quantidade=2, preco_unitario=Decimal("85.90")
        )
        PedidoHistorico.objects.create(
            nuvemshop_id=2, numero=102, realizado_em=agora, status="cancelled", status_pagamento="voided", total=10
        )

    def entrar(self, usuario=None):
        self.client.force_login(usuario or self.dono)


class AcessoTests(BaseGestao):
    def test_anonimo_vai_para_o_login(self):
        resposta = self.client.get("/gestao/")
        self.assertRedirects(resposta, "/gestao/entrar/?next=/gestao/")

    def test_quem_nao_e_da_equipe_nao_entra(self):
        comum = Usuario.objects.create_user("comum", password="Senha-forte-123")
        resposta = self.client.post("/gestao/entrar/", {"username": "comum", "password": "Senha-forte-123"})
        self.assertContains(resposta, "não tem acesso ao painel")
        self.client.force_login(comum)
        self.assertEqual(self.client.get("/gestao/").status_code, 403)

    def test_equipe_sem_permissao_nao_ve_clientes(self):
        equipe = Usuario.objects.create_user("ajudante", password="Senha-forte-123", is_staff=True)
        self.client.force_login(equipe)
        self.assertEqual(self.client.get("/gestao/").status_code, 200)
        self.assertEqual(self.client.get("/gestao/clientes/").status_code, 403)

    def test_login_e_bloqueio_por_tentativas(self):
        for _ in range(5):
            self.client.post("/gestao/entrar/", {"username": "dono", "password": "errada"})
        resposta = self.client.post("/gestao/entrar/", {"username": "dono", "password": "Senha-forte-123"})
        self.assertEqual(resposta.status_code, 429)
        cache.clear()
        resposta = self.client.post(
            "/gestao/entrar/", {"username": "dono", "password": "Senha-forte-123", "next": "/gestao/produtos/"}
        )
        self.assertRedirects(resposta, "/gestao/produtos/")

    def test_next_externo_e_ignorado(self):
        resposta = self.client.post(
            "/gestao/entrar/", {"username": "dono", "password": "Senha-forte-123", "next": "https://golpe.exemplo.com/"}
        )
        self.assertRedirects(resposta, "/gestao/")

    def test_login_do_admin_usa_o_do_painel(self):
        resposta = self.client.get("/painel/login/?next=/painel/")
        self.assertRedirects(resposta, "/gestao/entrar/?next=%2Fpainel%2F", fetch_redirect_response=False)

    def test_sair_so_por_post(self):
        self.entrar()
        self.assertEqual(self.client.get("/gestao/sair/").status_code, 405)
        self.assertRedirects(self.client.post("/gestao/sair/"), "/gestao/entrar/")


class TelasTests(BaseGestao):
    def test_todas_as_telas_abrem_sem_style_inline(self):
        self.entrar()
        banner = Banner.objects.create(titulo="Mapa", imagem="banners/a.webp")
        pagina = Pagina.objects.get(slug="trocas-e-devolucoes")
        urls = [
            "/gestao/",
            "/gestao/?periodo=30d",
            "/gestao/?periodo=tudo",
            "/gestao/produtos/",
            "/gestao/produtos/?status=publicados&estoque=baixo&ordem=-preco&q=zaik",
            "/gestao/produtos/novo/",
            f"/gestao/produtos/{self.produto.pk}/",
            "/gestao/estoque/?filtro=baixo",
            "/gestao/clientes/?ordem=gasto",
            f"/gestao/clientes/{self.cliente.pk}/",
            "/gestao/pedidos/?situacao=pagos&periodo=30d&cupom=",
            f"/gestao/pedidos/{self.pedido.pk}/",
            "/gestao/banners/",
            "/gestao/banners/novo/",
            f"/gestao/banners/{banner.pk}/",
            "/gestao/paginas/",
            f"/gestao/paginas/{pagina.pk}/",
            "/gestao/configuracoes/",
        ]
        for url in urls:
            with self.subTest(url=url):
                resposta = self.client.get(url)
                self.assertEqual(resposta.status_code, 200)
                html = resposta.content.decode()
                self.assertNotIn("style=", html)
                self.assertIn('content="noindex, nofollow"', html)

    def test_dashboard_soma_so_pedidos_pagos(self):
        self.entrar()
        resposta = self.client.get("/gestao/?periodo=30d")
        numeros = resposta.context["numeros"]
        self.assertEqual(numeros["faturamento"], Decimal("171.80"))
        self.assertEqual(numeros["pedidos"], 1)
        self.assertEqual(numeros["itens"], 2)
        self.assertContains(resposta, '<svg class="grafico"')
        self.assertEqual(resposta.context["mais_vendidos"][0]["nome"], "Zaik")
        self.assertEqual(resposta.context["alertas"]["estoque_baixo_total"], 1)

    def test_busca_de_cliente_pelo_cpf(self):
        self.entrar()
        resposta = self.client.get("/gestao/clientes/", {"q": "529.982.247-25"})
        self.assertEqual([c.pk for c in resposta.context["pagina"]], [self.cliente.pk])
        self.assertEqual(resposta.context["pagina"][0].total_gasto, Decimal("171.80"))

    def test_pedidos_filtra_pagos(self):
        self.entrar()
        resposta = self.client.get("/gestao/pedidos/", {"situacao": "pagos"})
        self.assertEqual([p.numero for p in resposta.context["pagina"]], [101])


class ProdutoTests(BaseGestao):
    def dados(self, **extra):
        dados = {
            "nome": "Zaik",
            "slug": "zaik",
            "tipo": "sol",
            "publico": "unissex",
            "formato": "",
            "descricao": "Nova descrição",
            "preco": "89.90",
            "preco_comparativo": "",
            "categorias": [self.categoria.pk],
            "ativo": "on",
            "peso_g": "50",
            "altura_cm": "",
            "largura_cm": "",
            "comprimento_cm": "",
            "seo_titulo": "",
            "seo_descricao": "",
            "variacoes-TOTAL_FORMS": "2",
            "variacoes-INITIAL_FORMS": "1",
            "variacoes-MIN_NUM_FORMS": "0",
            "variacoes-MAX_NUM_FORMS": "1000",
            "variacoes-0-id": self.variacao.pk,
            "variacoes-0-armacao": self.preta.pk,
            "variacoes-0-lente": self.verde.pk,
            "variacoes-0-sku": "ZK-PT",
            "variacoes-0-estoque": "7",
            "variacoes-0-ativa": "on",
            "variacoes-0-ordem": "0",
            "variacoes-1-armacao": "",
            "variacoes-1-lente": "",
            "variacoes-1-sku": "",
            "variacoes-1-estoque": "0",
            "variacoes-1-ordem": "0",
            "variacoes-1-ativa": "on",
            "imagens-TOTAL_FORMS": "0",
            "imagens-INITIAL_FORMS": "0",
            "imagens-MIN_NUM_FORMS": "0",
            "imagens-MAX_NUM_FORMS": "1000",
        }
        dados.update(extra)
        return dados

    def test_editar_produto_variacao_e_fotos_com_auditoria(self):
        self.entrar()
        with tempfile.TemporaryDirectory() as pasta, override_settings(MEDIA_ROOT=pasta):
            dados = self.dados()
            dados["novas_fotos"] = [png("a.png"), png("b.png")]
            resposta = self.client.post(f"/gestao/produtos/{self.produto.pk}/", dados)
            self.assertRedirects(resposta, "/gestao/produtos/")
            self.produto.refresh_from_db()
            self.assertEqual(self.produto.preco, Decimal("89.90"))
            self.variacao.refresh_from_db()
            self.assertEqual(self.variacao.estoque, 7)
            self.assertEqual(ImagemProduto.objects.filter(produto=self.produto).count(), 2)
        registro = RegistroAuditoria.objects.filter(modelo="catalogo.Produto", acao="U").latest("pk")
        self.assertEqual(registro.depois["preco"], "89.90")
        self.assertEqual(registro.usuario, self.dono)

    def test_preco_riscado_menor_que_preco_e_recusado(self):
        self.entrar()
        resposta = self.client.post(f"/gestao/produtos/{self.produto.pk}/", self.dados(preco_comparativo="10"))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "preço riscado precisa ser maior")

    def test_arquivo_que_nao_e_imagem_e_recusado(self):
        self.entrar()
        dados = self.dados()
        dados["novas_fotos"] = [SimpleUploadedFile("x.png", b"<?php echo 1; ?>", content_type="image/png")]
        resposta = self.client.post(f"/gestao/produtos/{self.produto.pk}/", dados)
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(ImagemProduto.objects.exists())

    def test_publicar_em_massa(self):
        self.entrar()
        self.client.post("/gestao/produtos/", {"selecionados": [self.rascunho.pk], "acao": "publicar"})
        self.rascunho.refresh_from_db()
        self.assertTrue(self.rascunho.ativo)
        self.assertTrue(RegistroAuditoria.objects.filter(objeto_id=str(self.rascunho.pk), acao="U").exists())

    def test_estoque_em_lote(self):
        self.entrar()
        dados = {
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "1",
            "form-MIN_NUM_FORMS": "0",
            "form-MAX_NUM_FORMS": "1000",
            "form-0-id": self.variacao.pk,
            "form-0-estoque": "12",
            "form-0-preco": "",
        }
        resposta = self.client.post("/gestao/estoque/", dados)
        self.assertEqual(resposta.status_code, 302)
        self.variacao.refresh_from_db()
        self.assertEqual(self.variacao.estoque, 12)


class ClienteTests(BaseGestao):
    def test_ficha_registra_acesso_e_mascara_documento(self):
        self.entrar()
        resposta = self.client.get(f"/gestao/clientes/{self.cliente.pk}/")
        self.assertNotContains(resposta, "52998224725")
        self.assertContains(resposta, "•••••••••25")
        self.assertTrue(RegistroAuditoria.objects.filter(acao="A", objeto_id=str(self.cliente.pk)).exists())

    def test_mostrar_documento_uma_vez(self):
        self.entrar()
        self.client.post(f"/gestao/clientes/{self.cliente.pk}/documento/")
        self.assertContains(self.client.get(f"/gestao/clientes/{self.cliente.pk}/"), "52998224725")
        self.assertNotContains(self.client.get(f"/gestao/clientes/{self.cliente.pk}/"), "52998224725")

    def test_exportar_e_anonimizar(self):
        self.entrar()
        resposta = self.client.post(f"/gestao/clientes/{self.cliente.pk}/exportar/")
        self.assertEqual(json.loads(resposta.content)["cliente"]["email"], "maria@exemplo.com")
        self.client.post(f"/gestao/clientes/{self.cliente.pk}/anonimizar/", {"confirmacao": "talvez"})
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.nome, "Maria Souza")
        self.client.post(f"/gestao/clientes/{self.cliente.pk}/anonimizar/", {"confirmacao": "anonimizar"})
        self.cliente.refresh_from_db()
        self.assertIsNotNone(self.cliente.anonimizado_em)
        self.assertFalse(self.cliente.enderecos.exists())


class LojaTests(BaseGestao):
    def test_configuracoes_salvam_e_auditam(self):
        self.entrar()
        resposta = self.client.get("/gestao/configuracoes/")
        dados = {nome: campo.initial for nome, campo in resposta.context["form"].fields.items()}
        dados = {k: ("" if v is None else v) for k, v in dados.items()}
        dados["PIX_DESCONTO_PERCENTUAL"] = "7"
        dados["OCULOS_ENTREGUES"] = "12000"
        self.assertRedirects(self.client.post("/gestao/configuracoes/", dados), "/gestao/configuracoes/")
        self.assertEqual(Parametro.objects.get(chave="PIX_DESCONTO_PERCENTUAL").valor_tipado(), Decimal("7"))
        self.assertEqual(Parametro.objects.get(chave="OCULOS_ENTREGUES").valor, "12000")
        self.assertTrue(RegistroAuditoria.objects.filter(modelo="core.Parametro", acao="U").exists())

    def test_pagina_editar(self):
        self.entrar()
        pagina = Pagina.objects.get(slug="trocas-e-devolucoes")
        dados = {
            "titulo": "Trocas",
            "slug": pagina.slug,
            "conteudo": "Texto novo",
            "seo_descricao": "",
            "publicada": "on",
        }
        self.assertRedirects(self.client.post(f"/gestao/paginas/{pagina.pk}/", dados), "/gestao/paginas/")
        pagina.refresh_from_db()
        self.assertEqual(pagina.conteudo, "Texto novo")

    def test_banner_excluir(self):
        self.entrar()
        banner = Banner.objects.create(titulo="Velho", imagem="banners/a.webp")
        self.client.post(f"/gestao/banners/{banner.pk}/", {"excluir": "1"})
        self.assertFalse(Banner.objects.filter(pk=banner.pk).exists())
        self.assertTrue(RegistroAuditoria.objects.filter(modelo="catalogo.Banner", acao="D").exists())


class GraficosTests(SimpleTestCase):
    def test_escala_e_coordenadas(self):
        g = graficos.barras([("jan", Decimal("100")), ("fev", Decimal("380"))])
        self.assertEqual(g["grade"][-1]["rotulo"], "R$ 500")
        self.assertTrue(g["itens"][1]["destaque"])
        self.assertGreater(g["itens"][1]["altura"], g["itens"][0]["altura"])
        vazio = graficos.linha([("jan", 0), ("fev", 0)])
        self.assertTrue(vazio["vazio"])
        self.assertIn(",", vazio["linha"])
