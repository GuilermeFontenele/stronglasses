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
        if metodo == "PUT":  # cancelar cobrança pendente
            return {**self.criado, "status": corpo["status"]}
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

    def test_email_de_outra_pessoa_nao_expoe_nem_altera_o_cadastro(self):
        existente = Cliente.objects.create(nome="Maria Secreta", email="maria@exemplo.com")
        pedido = self.comprar(nome="Outra Pessoa")
        self.assertEqual(pedido.cliente, existente)
        existente.refresh_from_db()
        self.assertEqual((existente.nome, existente.whatsapp, existente.documento), ("Maria Secreta", "", ""))
        self.assertFalse(existente.enderecos.exists())
        # A cobrança e a tela usam só o que foi digitado nesta compra.
        self.assertEqual(
            (pedido.destinatario, pedido.email, pedido.documento), ("Outra Pessoa", "maria@exemplo.com", CPF)
        )
        self.assertEqual(self.api.chamadas[0][2]["payer"]["first_name"], "Outra")
        self.api.situacao = "approved"
        self.assertNotContains(self.client.get(f"/pedido/{pedido.token_acesso}/"), "Secreta")

    def test_mesmo_cpf_reaproveita_o_cadastro(self):
        existente = Cliente.objects.create(nome="Maria Souza", email="antigo@exemplo.com", documento=CPF)
        pedido = self.comprar()
        self.assertEqual(pedido.cliente, existente)
        self.assertEqual(Cliente.objects.count(), 1)
        self.assertTrue(existente.enderecos.filter(cep="60110000").exists())
        self.assertEqual(pedido.email, "maria@exemplo.com")

    def test_cpf_e_link_do_pedido_ficam_fora_da_auditoria(self):
        from apps.core.models import RegistroAuditoria

        pedido = self.comprar()
        registro = RegistroAuditoria.objects.filter(modelo="vendas.Pedido", objeto_id=str(pedido.pk)).first()
        texto = str(registro.depois)
        self.assertNotIn(CPF, texto)
        self.assertNotIn(pedido.token_acesso, texto)

    def test_emails_do_pedido(self):
        from django.core import mail

        pedido = self.comprar()
        self.assertEqual(len(mail.outbox), 1)
        recebido = mail.outbox[0]
        self.assertEqual(recebido.to, ["maria@exemplo.com"])
        self.assertIn(pedido.codigo, recebido.subject)
        self.assertIn(f"https://loja.exemplo.com.br/pedido/{pedido.token_acesso}/", recebido.body)
        self.assertIn("R$ 100,15", recebido.body)
        self.api.situacao = "approved"
        with self.captureOnCommitCallbacks(execute=True):
            servicos.sincronizar(Pagamento.objects.get().provedor_id)
        self.assertEqual(len(mail.outbox), 2)
        self.assertIn("Pagamento aprovado", mail.outbox[1].subject)

    def test_limite_de_pedidos_por_hora(self):
        from apps.pagamentos import views

        with mock.patch.object(views, "MAXIMO_PEDIDOS_POR_HORA", 1):
            self.comprar()
            self.client.post("/carrinho/adicionar/", {"variacao": self.v1.pk, "quantidade": 1})
            self.client.post("/finalizar/frete/", {"cep": "60110000"})
            resposta = self.client.post("/finalizar/", self.dados())
        self.assertContains(resposta, "Muitos pedidos seguidos")
        self.assertEqual(Pedido.objects.count(), 1)

    def test_carrinho_lembra_do_pedido_em_aberto(self):
        pedido = self.comprar()
        resposta = self.client.get("/carrinho/")
        self.assertContains(resposta, "Você tem um pedido aguardando pagamento")
        self.assertContains(resposta, f"/pedido/{pedido.token_acesso}/")


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
        self.assertContains(pagina, 'data-valor="104.90"')  # sem o desconto do Pix
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
        self.assertEqual(pedido.total, Decimal("104.90"))

    def test_limite_de_tentativas_de_cartao(self):
        pedido = self.comprar(forma="credito")
        url = f"/pedido/{pedido.token_acesso}/cartao/"
        dados = {"token": "recusar", "payment_method_id": "visa", "installments": 1}
        for _ in range(servicos.MAXIMO_TENTATIVAS_CARTAO):
            self.assertEqual(self.client.post(url, dados, content_type="application/json").status_code, 402)
        bloqueado = self.client.post(url, {**dados, "token": "aprovar"}, content_type="application/json")
        self.assertEqual(bloqueado.status_code, 400)
        self.assertIn("Muitas tentativas", bloqueado.json()["mensagem"])

    def test_pix_gerado_antes_ainda_vale_depois_de_abrir_o_cartao(self):
        pedido = self.comprar()  # Pix de 100,15 gerado
        pix = Pagamento.objects.get()
        self.client.get(f"/pedido/{pedido.token_acesso}/pagar/")  # só olhar o cartão não muda o pedido
        pedido.refresh_from_db()
        self.assertEqual((pedido.forma_pagamento, pedido.total), ("pix", Decimal("100.15")))
        # Tentou o cartão (recusado): o pedido passou para 104,90. Aí pagou o Pix antigo.
        url = f"/pedido/{pedido.token_acesso}/cartao/"
        self.client.post(
            url, {"token": "recusar", "payment_method_id": "visa", "installments": 1}, content_type="application/json"
        )
        pedido.refresh_from_db()
        self.assertEqual(pedido.total, Decimal("104.90"))
        self.api.criado = {"id": int(pix.provedor_id), "transaction_amount": 100.15, "payment_method_id": "pix"}
        self.api.situacao = "approved"
        servicos.sincronizar(pix.provedor_id)
        pedido.refresh_from_db()
        self.assertEqual((pedido.situacao, pedido.forma_pagamento, pedido.total), ("pago", "pix", Decimal("100.15")))

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

    def test_cancelar_fecha_a_cobranca_no_mercado_pago(self):
        pedido = self.comprar()
        servicos.cancelar_pedido(pedido)
        self.assertIn("PUT", [c[0] for c in self.api.chamadas])
        self.assertEqual(Pagamento.objects.get().status, "cancelled")
        pedido.refresh_from_db()
        self.assertEqual(pedido.situacao, "cancelado")

    def test_pago_depois_de_cancelado_reativa_se_tem_estoque(self):
        pedido = self.comprar()
        pagamento = Pagamento.objects.get()
        Pedido.objects.filter(pk=pedido.pk).update(expira_em=timezone.now() - timedelta(minutes=10))
        self.api.situacao = "cancelled"
        servicos.expirar_pendentes()
        self.v1.refresh_from_db()
        self.assertEqual(self.v1.estoque, 2)
        self.api.situacao = "approved"  # o banco confirmou o Pix com atraso
        servicos.sincronizar(pagamento.provedor_id)
        pedido.refresh_from_db()
        self.v1.refresh_from_db()
        self.assertEqual((pedido.situacao, self.v1.estoque), ("pago", 1))
        self.assertIn("Reativado", pedido.observacoes)
        self.assertEqual(servicos.para_conferir().count(), 0)

    def test_pago_depois_de_cancelado_sem_estoque_vira_alerta(self):
        pedido = self.comprar()
        pagamento = Pagamento.objects.get()
        servicos.cancelar_pedido(pedido)
        self.v1.estoque = 0
        self.v1.save()
        self.api.situacao = "approved"
        servicos.sincronizar(pagamento.provedor_id)
        pedido.refresh_from_db()
        self.assertEqual(pedido.situacao, "cancelado")
        self.assertEqual(servicos.para_conferir().count(), 1)

    def test_link_errado(self):
        self.assertEqual(self.client.get("/pedido/nao-existe/").status_code, 404)
