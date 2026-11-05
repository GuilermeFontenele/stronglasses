from decimal import Decimal

from django.test import TestCase

from apps.catalogo.models import AcabamentoArmacao, CorLente, Produto, Variacao
from apps.core.models import Parametro


class CarrinhoTests(TestCase):
    def setUp(self):
        Parametro.objects.update_or_create(chave="PIX_DESCONTO_PERCENTUAL", defaults={"valor": "5"})
        preta = AcabamentoArmacao.objects.create(nome="Preta", cor_hex="#111111")
        verde = CorLente.objects.create(nome="Verde", cor_hex="#55704A")
        tartaruga = AcabamentoArmacao.objects.create(nome="Tartaruga", cor_hex="#6B3E1F")
        self.produto = Produto.objects.create(nome="Roshi", slug="roshi", preco=Decimal("94.90"), ativo=True)
        self.v1 = Variacao.objects.create(produto=self.produto, armacao=preta, lente=verde, sku="A", estoque=3)
        self.v2 = Variacao.objects.create(
            produto=self.produto, armacao=tartaruga, lente=verde, sku="B", estoque=5, preco=Decimal("99.90")
        )

    def adicionar(self, variacao, quantidade=1):
        return self.client.post("/carrinho/adicionar/", {"variacao": variacao.pk, "quantidade": quantidade})

    def test_adicionar_e_calcular_no_servidor(self):
        resposta = self.adicionar(self.v1, 2)
        self.assertRedirects(resposta, "/carrinho/")
        self.adicionar(self.v2)
        pagina = self.client.get("/carrinho/")
        self.assertEqual(pagina.context["resumo"]["subtotal"], Decimal("289.70"))  # 2 x 94,90 + 99,90
        self.assertEqual(pagina.context["resumo"]["total_pix"], Decimal("275.22"))
        self.assertContains(pagina, "R$ 289,70")
        self.assertContains(pagina, "Finalizar pelo WhatsApp")
        self.assertIn("2x%20Roshi", pagina.context["link_whatsapp"])
        self.assertContains(pagina, 'class="contagem-carrinho"')  # ícone do topo mostra 3

    def test_respeita_estoque_e_limite(self):
        self.adicionar(self.v1, 2)
        self.adicionar(self.v1, 5)
        self.assertEqual(self.client.session["carrinho"], {str(self.v1.pk): 3})
        self.adicionar(self.v1, 1)  # já está no máximo
        self.assertEqual(self.client.session["carrinho"][str(self.v1.pk)], 3)

    def test_esgotado_inativo_ou_invalido_nao_entra(self):
        self.v1.estoque = 0
        self.v1.save()
        self.adicionar(self.v1)
        self.assertNotIn("carrinho", self.client.session)
        self.produto.ativo = False
        self.produto.save()
        self.assertEqual(self.adicionar(self.v2).status_code, 404)
        self.assertEqual(self.client.post("/carrinho/adicionar/", {"variacao": "abc"}).status_code, 302)

    def test_atualizar_e_remover(self):
        self.adicionar(self.v1, 1)
        self.adicionar(self.v2, 1)
        self.client.post("/carrinho/atualizar/", {"variacao": self.v2.pk, "quantidade": 4})
        self.assertEqual(self.client.session["carrinho"][str(self.v2.pk)], 4)
        self.client.post("/carrinho/atualizar/", {"variacao": self.v2.pk, "quantidade": 0})
        self.assertNotIn(str(self.v2.pk), self.client.session["carrinho"])
        self.client.post("/carrinho/remover/", {"variacao": self.v1.pk})
        self.assertContains(self.client.get("/carrinho/"), "Seu carrinho está vazio")

    def test_item_que_saiu_de_estoque_some_do_carrinho(self):
        self.adicionar(self.v1, 2)
        Variacao.objects.filter(pk=self.v1.pk).update(estoque=0)
        pagina = self.client.get("/carrinho/")
        self.assertEqual(pagina.context["linhas"], [])
        self.assertEqual(self.client.session["carrinho"], {})

    def test_sessao_adulterada_e_ignorada(self):
        sessao = self.client.session
        sessao["carrinho"] = {"x": 1, str(self.v1.pk): 999, str(self.v2.pk): "2", "99999": 1}
        sessao.save()
        self.assertEqual(self.client.get("/carrinho/").context["linhas"], [])

    def test_so_post_altera(self):
        self.assertEqual(self.client.get("/carrinho/adicionar/").status_code, 405)
