import hashlib
import hmac
import json
import time
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone

from apps.catalogo.tests.test_vitrine import VitrineBase
from apps.clientes.models import Cliente
from apps.core.models import Parametro
from apps.pagamentos import mercadopago, servicos
from apps.pagamentos.models import Pagamento
from apps.vendas.models import Pedido

SEGREDO = "segredo-de-teste-" + "x" * 16
CONFIG = {
    "MERCADOPAGO_ACCESS_TOKEN": "TEST-token",
    "MERCADOPAGO_PUBLIC_KEY": "TEST-publica",
    "MERCADOPAGO_WEBHOOK_SECRET": SEGREDO,
    "SITE_URL": "https://loja.exemplo.com.br",
}
CPF = "52998224725"


class ApiFalsa:
    """Responde como o Mercado Pago e guarda o que foi pedido."""

    def __init__(self):
        self.chamadas = []
        self.situacao = "pending"
        self.valor = None
        self.proximo = 1000

    def __call__(self, metodo, caminho, corpo=None, chave_idempotencia=None):
        self.chamadas.append((metodo, caminho, corpo, chave_idempotencia))
        if metodo == "POST":
            self.proximo += 1
            self.ultimo = corpo
            dados = {
                "id": self.proximo,
                "status": "approved" if corpo.get("token") == "aprovar" else self.situacao,
                "status_detail": "cc_rejected_high_risk" if corpo.get("token") == "recusar" else "pending_waiting",
                "transaction_amount": corpo["transaction_amount"],
                "installments": corpo.get("installments", 1),
                "payment_method_id": corpo["payment_method_id"],
                "external_reference": corpo["external_reference"],
            }
            if corpo.get("token") == "recusar":
                dados["status"] = "rejected"
            if corpo["payment_method_id"] == "pix":
                dados["point_of_interaction"] = {
                    "transaction_data": {"qr_code": "00020126PIXCOPIAECOLA", "qr_code_base64": "iVBORw0KGgo="}
                }
                dados["date_of_expiration"] = (timezone.now() + timedelta(minutes=30)).isoformat()
            self.criado = dados
            return dados
        dados = dict(self.criado)
        dados["status"] = self.situacao
        if self.valor is not None:
            dados["transaction_amount"] = self.valor
        return dados


def assinar(data_id: str, request_id: str = "req-1") -> dict:
    ts = str(int(time.time()))
    manifesto = f"id:{data_id};request-id:{request_id};ts:{ts};"
    v1 = hmac.new(SEGREDO.encode(), manifesto.encode(), hashlib.sha256).hexdigest()
    return {"HTTP_X_SIGNATURE": f"ts={ts},v1={v1}", "HTTP_X_REQUEST_ID": request_id}


@override_settings(**CONFIG)
class BaseCheckout(VitrineBase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.api = ApiFalsa()
        patch = mock.patch("apps.pagamentos.mercadopago._requisicao", self.api)
        patch.start()
        self.addCleanup(patch.stop)

    def dados(self, **extra):
        dados = {
            "nome": "Maria Souza",
            "email": "Maria@Exemplo.com",
            "whatsapp": "(85) 98888-7777",
            "cpf": "529.982.247-25",
            "cep": "60110-000",
            "logradouro": "Av. Beira Mar",
            "numero": "100",
            "complemento": "Ap 2",
            "bairro": "Meireles",
            "cidade": "Fortaleza",
            "uf": "CE",
            "frete": "motoboy",
            "forma": "pix",
            "aceite": "on",
        }
        dados.update(extra)
        return dados

    def comprar(self, **extra) -> Pedido:
        self.client.post("/carrinho/adicionar/", {"variacao": self.v1.pk, "quantidade": 1})
        self.client.post("/finalizar/frete/", {"cep": "60110000"})
        resposta = self.client.post("/finalizar/", self.dados(**extra))
        pedido = Pedido.objects.get()
        self.assertEqual(resposta.status_code, 302)
        return pedido


class CheckoutTests(BaseCheckout):
    def test_sem_credenciais_volta_para_o_carrinho(self):
        self.client.post("/carrinho/adicionar/", {"variacao": self.v1.pk, "quantidade": 1})
        with override_settings(MERCADOPAGO_ACCESS_TOKEN=""):
            self.assertRedirects(self.client.get("/finalizar/"), "/carrinho/")
            self.assertNotContains(self.client.get("/carrinho/"), "Finalizar compra")
        self.assertContains(self.client.get("/carrinho/"), "Finalizar compra")

    def test_pagina_de_finalizar(self):
        self.client.post("/carrinho/adicionar/", {"variacao": self.v1.pk, "quantidade": 1})
        html = self.client.get("/finalizar/").content.decode()
        self.assertIn("Calcular frete", html)
        self.assertIn("/politica-de-privacidade/", html)
        self.assertNotIn("style=", html)

    def test_frete_local_e_fora(self):
        self.client.post("/carrinho/adicionar/", {"variacao": self.v1.pk, "quantidade": 1})
        local = self.client.post("/finalizar/frete/", {"cep": "60110-000"}).json()
        esperado = {"id": "motoboy", "nome": "Motoboy (Fortaleza)", "preco": "10.00", "prazo": "1 a 2 dias úteis"}
        self.assertEqual(local["opcoes"][0], esperado)
        fora = self.client.post("/finalizar/frete/", {"cep": "01310100"})
        self.assertEqual(fora.status_code, 400)  # Melhor Envio não conectado nos testes

    def test_frete_gratis_local(self):
        Parametro.objects.filter(chave="FRETE_GRATIS_LOCAL_ACIMA").update(valor="50")
        cache.clear()
        self.client.post("/carrinho/adicionar/", {"variacao": self.v1.pk, "quantidade": 1})
        opcao = self.client.post("/finalizar/frete/", {"cep": "60110000"}).json()["opcoes"][0]
        self.assertEqual((opcao["preco"], opcao["nome"]), ("0.00", "Motoboy (Fortaleza) · frete grátis"))

    def test_faixas_de_cep(self):
        self.assertTrue(servicos.cep_local("60110-000", "60000000-60999999"))
        self.assertTrue(servicos.cep_local("61600123", "60000000-60999999, 61600000-61619999"))
        self.assertFalse(servicos.cep_local("01310100", "60000000-60999999"))
        self.assertFalse(servicos.cep_local("123", "60000000-60999999"))

    def test_compra_com_pix(self):
        self.client.get("/?utm_source=instagram&ref=ana10")
        pedido = self.comprar()
        self.assertEqual((pedido.canal, pedido.situacao, pedido.forma_pagamento), ("site", "pendente", "pix"))
        # 94,90 - 5% Pix (4,75) + 10 do motoboy (o Pix não incide sobre o frete)
        valores = (pedido.desconto_pix, pedido.frete, pedido.total)
        self.assertEqual(valores, (Decimal("4.75"), Decimal("10.00"), Decimal("100.15")))
        self.assertEqual((pedido.utm_source, pedido.ref), ("instagram", "ana10"))
        self.v1.refresh_from_db()
        self.assertEqual(self.v1.estoque, 1)  # reservado
        cliente = Cliente.objects.get()
        contato = (cliente.email, cliente.whatsapp, cliente.documento)
        self.assertEqual(contato, ("maria@exemplo.com", "+5585988887777", CPF))
        self.assertTrue(cliente.enderecos.filter(cep="60110000").exists())
        _, caminho, corpo, chave = self.api.chamadas[0]
        self.assertEqual(caminho, "/v1/payments")
        self.assertEqual((corpo["payment_method_id"], corpo["transaction_amount"]), ("pix", 100.15))
        self.assertEqual(corpo["payer"]["identification"], {"type": "CPF", "number": CPF})
        self.assertEqual(corpo["notification_url"], "https://loja.exemplo.com.br/pagamentos/mercadopago/webhook/")
        self.assertTrue(chave)
        html = self.client.get(f"/pedido/{pedido.token_acesso}/").content.decode()
        self.assertIn("00020126PIXCOPIAECOLA", html)
        self.assertIn('src="data:image/png;base64,iVBORw0KGgo="', html)
        self.assertNotIn("style=", html)
        self.assertEqual(len(self.client.session.get("carrinho", {})), 0)

    def test_dados_invalidos(self):
        self.client.post("/carrinho/adicionar/", {"variacao": self.v1.pk, "quantidade": 1})
        self.client.post("/finalizar/frete/", {"cep": "60110000"})
        resposta = self.client.post("/finalizar/", self.dados(cpf="111.111.111-11", nome="Maria", aceite=""))
        self.assertEqual(resposta.status_code, 200)
        erros = resposta.context["form"].errors
        self.assertIn("cpf", erros)
        self.assertIn("nome", erros)
        self.assertIn("aceite", erros)
        self.assertFalse(Pedido.objects.exists())

    def test_frete_que_nao_foi_cotado(self):
        self.client.post("/carrinho/adicionar/", {"variacao": self.v1.pk, "quantidade": 1})
        resposta = self.client.post("/finalizar/", self.dados(frete="me:999"))
        self.assertContains(resposta, "Calcule o frete de novo")
        self.assertFalse(Pedido.objects.exists())

    def test_cliente_existente_nao_e_sobrescrito(self):
        existente = Cliente.objects.create(nome="Maria S.", email="maria@exemplo.com")
        pedido = self.comprar(nome="Outra Pessoa")
        self.assertEqual(pedido.cliente, existente)
        existente.refresh_from_db()
        self.assertEqual((existente.nome, existente.whatsapp), ("Maria S.", "+5585988887777"))


class WebhookTests(BaseCheckout):
    def test_assinatura(self):
        with override_settings(MERCADOPAGO_WEBHOOK_SECRET=SEGREDO):
            cab = assinar("123")
            self.assertTrue(mercadopago.assinatura_valida(cab["HTTP_X_SIGNATURE"], "req-1", "123", time.time()))
            self.assertFalse(mercadopago.assinatura_valida(cab["HTTP_X_SIGNATURE"], "req-2", "123", time.time()))
            self.assertFalse(mercadopago.assinatura_valida(cab["HTTP_X_SIGNATURE"], "req-1", "123", time.time() + 3600))
            self.assertFalse(mercadopago.assinatura_valida("", "req-1", "123"))

    def test_aprovado_pelo_webhook_e_idempotente(self):
        pedido = self.comprar()
        pagamento = Pagamento.objects.get()
        url = f"/pagamentos/mercadopago/webhook/?data.id={pagamento.provedor_id}&type=payment"
        corpo = json.dumps({"type": "payment", "data": {"id": pagamento.provedor_id}})
        falso = self.client.post(url, corpo, content_type="application/json", HTTP_X_SIGNATURE="ts=1,v1=abc")
        self.assertEqual(falso.status_code, 401)
        pedido.refresh_from_db()
        self.assertEqual(pedido.situacao, "pendente")
        self.api.situacao = "approved"
        for _ in range(2):
            resposta = self.client.post(url, corpo, content_type="application/json", **assinar(pagamento.provedor_id))
            self.assertEqual(resposta.status_code, 200)
        pedido.refresh_from_db()
        pagamento.refresh_from_db()
        self.assertEqual((pedido.situacao, pagamento.status), ("pago", "approved"))
        self.assertIsNotNone(pedido.pago_em)
        self.assertContains(self.client.get(f"/pedido/{pedido.token_acesso}/"), "Pagamento aprovado!")

    def test_valor_divergente_nao_marca_como_pago(self):
        pedido = self.comprar()
        pagamento = Pagamento.objects.get()
        self.api.situacao, self.api.valor = "approved", 1.00
        servicos.sincronizar(pagamento.provedor_id)
        pedido.refresh_from_db()
        self.assertEqual(pedido.situacao, "pendente")

    def test_tela_do_pedido_consulta_sozinha(self):
        pedido = self.comprar()
        self.api.situacao = "approved"
        resposta = self.client.get(f"/pedido/{pedido.token_acesso}/situacao/")
        self.assertEqual(resposta.json(), {"situacao": "pago", "pago": True})


class CartaoTests(BaseCheckout):
    def test_cartao_aprovado(self):
        pedido = self.comprar(forma="credito")
        self.assertFalse(Pagamento.objects.exists())
        pagina = self.client.get(f"/pedido/{pedido.token_acesso}/pagar/")
        self.assertContains(pagina, "https://sdk.mercadopago.com/js/v2")
        politica = pagina["Content-Security-Policy"]
        self.assertIn("https://sdk.mercadopago.com", politica)
        self.assertNotIn("sdk.mercadopago.com", self.client.get("/").get("Content-Security-Policy", ""))
        pedido.refresh_from_db()
        self.assertEqual(pedido.total, Decimal("104.90"))  # sem desconto do Pix
        url = f"/pedido/{pedido.token_acesso}/cartao/"
        muitas = {"token": "aprovar", "payment_method_id": "visa", "installments": 6, "issuer_id": "25"}
        self.assertEqual(self.client.post(url, muitas, content_type="application/json").status_code, 400)
        dados = {**muitas, "token": "recusar", "installments": 1}
        recusado = self.client.post(url, dados, content_type="application/json")
        self.assertEqual(recusado.status_code, 402)
        self.assertIn("Tente outro cartão", recusado.json()["mensagem"])
        aprovado = self.client.post(url, {**muitas, "installments": 3}, content_type="application/json")
        self.assertEqual(aprovado.status_code, 200)
        corpo = self.api.ultimo
        self.assertEqual((corpo["transaction_amount"], corpo["installments"], corpo["issuer_id"]), (104.9, 3, 25))
        self.assertEqual(corpo["statement_descriptor"], "STRONGGLASSES")
        pedido.refresh_from_db()
        self.assertEqual((pedido.situacao, pedido.forma_pagamento, pedido.parcelas), ("pago", "credito", 3))

    def test_trocar_para_pix(self):
        pedido = self.comprar(forma="credito")
        self.client.post(f"/pedido/{pedido.token_acesso}/pix/")
        pedido.refresh_from_db()
        self.assertEqual((pedido.forma_pagamento, pedido.total), ("pix", Decimal("100.15")))
        self.assertEqual(Pagamento.objects.get().metodo, "pix")


class ExpiracaoTests(BaseCheckout):
    def test_expira_devolve_estoque_e_refaz_carrinho(self):
        pedido = self.comprar()
        Pedido.objects.filter(pk=pedido.pk).update(expira_em=timezone.now() - timedelta(minutes=10))
        self.api.situacao = "cancelled"
        self.assertEqual(servicos.expirar_pendentes(), 1)
        pedido.refresh_from_db()
        self.v1.refresh_from_db()
        self.assertEqual((pedido.situacao, self.v1.estoque), ("cancelado", 2))
        self.assertContains(self.client.get(f"/pedido/{pedido.token_acesso}/"), "Pedido cancelado")
        self.client.post(f"/pedido/{pedido.token_acesso}/refazer/")
        self.assertEqual(self.client.session["carrinho"], {str(self.v1.pk): 1})

    def test_pago_no_ultimo_minuto_nao_cancela(self):
        pedido = self.comprar()
        Pedido.objects.filter(pk=pedido.pk).update(expira_em=timezone.now() - timedelta(minutes=10))
        self.api.situacao = "approved"
        self.assertEqual(servicos.expirar_pendentes(), 0)
        pedido.refresh_from_db()
        self.assertEqual(pedido.situacao, "pago")

    def test_link_errado(self):
        self.assertEqual(self.client.get("/pedido/nao-existe/").status_code, 404)
