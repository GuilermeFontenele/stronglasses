from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.core.cache import cache
from django.db import connection
from django.test import override_settings
from django.utils import timezone

from apps.core.models import Parametro, RegistroAuditoria
from apps.envios import melhorenvio, servicos
from apps.envios.melhorenvio import ErroMelhorEnvio
from apps.envios.models import ConexaoMelhorEnvio, Envio
from apps.gestao.tests.test_gestao import BaseGestao
from apps.vendas.models import Pedido
from apps.vendas.servicos import ItemNovo, registrar_venda

ME_ID = "9a1b2c3d-0000-4000-8000-000000000001"

COTACAO = [
    {
        "id": 2,
        "name": "SEDEX",
        "custom_price": "31.20",
        "custom_delivery_time": 3,
        "custom_delivery_range": {"min": 2, "max": 3},
        "company": {"id": 1, "name": "Correios"},
    },
    {
        "id": 1,
        "name": "PAC",
        "custom_price": "22.50",
        "custom_delivery_time": 8,
        "custom_delivery_range": {"min": 7, "max": 8},
        "company": {"id": 1, "name": "Correios"},
    },
    {"id": 3, "name": ".Package", "error": "Transportadora não atende este trecho.", "company": {"name": "Jadlog"}},
]


class ApiFalsa:
    """Responde como o Melhor Envio e guarda o que foi chamado."""

    def __init__(self, **respostas):
        self.chamadas = []
        self.respostas = {
            "/oauth/token": {"access_token": "novo-acesso", "refresh_token": "novo-refresh", "expires_in": 2592000},
            "/api/v2/me": {"firstname": "Strong", "lastname": "Glasses"},
            "/api/v2/me/balance": {"balance": 150.75},
            "/api/v2/me/shipment/calculate": COTACAO,
            "/api/v2/me/cart": {"id": ME_ID, "protocol": "ORD-1", "price": 22.5, "status": "pending"},
            "/api/v2/me/shipment/checkout": {"purchase": {"status": "paid"}},
            "/api/v2/me/shipment/generate": {ME_ID: {"status": True, "message": "Envio gerado com sucesso"}},
            "/api/v2/me/shipment/tracking": {ME_ID: {"status": "released", "tracking": "aa123456789br"}},
            "/api/v2/me/shipment/print": {"url": "https://sandbox.melhorenvio.com.br/imprimir/abc"},
            f"/api/v2/me/imprimir/dace/pdf/{ME_ID}": {"pdf": "https://arquivos.melhorenvio.com.br/dace.pdf"},
            "/api/v2/me/shipment/cancel": {ME_ID: {"canceled": True}},
            f"/api/v2/me/cart/{ME_ID}": {},
        }
        self.respostas.update(respostas)

    def __call__(self, metodo, url, corpo=None, token=None, formulario=False):
        caminho = url.split(".com.br", 1)[1]
        self.chamadas.append((metodo, caminho, corpo, token))
        resposta = self.respostas[caminho]
        if isinstance(resposta, Exception):
            raise resposta
        return resposta

    def caminhos(self):
        return [c[1] for c in self.chamadas]


class BaseEnvios(BaseGestao):
    def setUp(self):
        super().setUp()
        valores = {
            "REMETENTE_ENDERECO": "Rua da Loja",
            "REMETENTE_NUMERO": "100",
            "REMETENTE_BAIRRO": "Centro",
            "REMETENTE_CIDADE": "Fortaleza",
            "REMETENTE_UF": "CE",
            "REMETENTE_CEP": "60000-000",
        }
        for chave, valor in valores.items():
            Parametro.objects.update_or_create(chave=chave, defaults={"valor": valor, "tipo": "texto"})
        cache.clear()
        self.conexao = ConexaoMelhorEnvio.objects.create(
            ambiente="sandbox",
            access_token="token-atual",
            refresh_token="refresh-atual",
            expira_em=timezone.now() + timedelta(days=20),
        )
        self.variacao.estoque = 5
        self.variacao.save()
        self.venda = registrar_venda(
            Pedido(
                cliente=self.cliente,
                forma_pagamento="pix",
                canal="whatsapp",
                entrega="correios",
                destinatario="Maria Souza",
                cep="01310100",
                logradouro="Avenida Paulista",
                numero_endereco="1000",
                bairro="Bela Vista",
                cidade="São Paulo",
                uf="SP",
            ),
            [ItemNovo(self.variacao, 1)],
            baixar_estoque=True,
            aplicar_pix=False,
        )

    def api(self, **respostas):
        falsa = ApiFalsa(**respostas)
        patch = mock.patch("apps.envios.melhorenvio._requisicao", falsa)
        patch.start()
        self.addCleanup(patch.stop)
        return falsa


class ClienteApiTests(BaseEnvios):
    def test_url_de_autorizacao(self):
        with override_settings(MELHOR_ENVIO_CLIENT_ID="123"):
            url = melhorenvio.url_autorizacao("http://localhost:8080/retorno/", "estado1")
        self.assertTrue(url.startswith("https://sandbox.melhorenvio.com.br/oauth/authorize?"))
        self.assertIn("state=estado1", url)
        self.assertIn("shipping-generate", url)
        self.assertNotIn("users-write", url)

    def test_tokens_ficam_cifrados_no_banco(self):
        self.api()
        melhorenvio.trocar_codigo("codigo", "http://localhost/retorno/")
        conexao = ConexaoMelhorEnvio.objects.get(ambiente="sandbox")
        self.assertEqual(conexao.access_token, "novo-acesso")
        with connection.cursor() as cursor:
            cursor.execute("SELECT access_token FROM envios_conexaomelhorenvio WHERE id = %s", [conexao.pk])
            self.assertNotIn("novo-acesso", cursor.fetchone()[0])

    def test_renova_token_perto_de_vencer(self):
        falsa = self.api()
        ConexaoMelhorEnvio.objects.filter(pk=self.conexao.pk).update(expira_em=timezone.now() + timedelta(days=1))
        self.assertEqual(melhorenvio.token_valido(), "novo-acesso")
        self.assertEqual(falsa.chamadas[0][2]["grant_type"], "refresh_token")

    def test_sem_conexao(self):
        self.conexao.delete()
        with self.assertRaises(melhorenvio.NaoConectado):
            melhorenvio.token_valido()

    def test_mensagem_de_erro(self):
        corpo = b'{"message":"The given data was invalid.","errors":{"to.document":["CPF invalido."]}}'
        self.assertEqual(melhorenvio._mensagem_de_erro(corpo, 422), "CPF invalido.")
        self.assertIn("Reconecte", melhorenvio._mensagem_de_erro(b"{}", 401))


class FluxoEtiquetaTests(BaseEnvios):
    def test_cotacao_ordena_e_separa_indisponiveis(self):
        falsa = self.api()
        opcoes = servicos.cotar(self.venda)
        self.assertEqual([o["servico"] for o in opcoes], ["PAC", "SEDEX", ".Package"])
        self.assertTrue(opcoes[-1]["erro"])
        corpo = falsa.chamadas[0][2]
        self.assertEqual((corpo["from"]["postal_code"], corpo["to"]["postal_code"]), ("60000000", "01310100"))
        self.assertEqual(corpo["volumes"][0]["weight"], 0.05)

    def test_cotacao_exige_remetente(self):
        Parametro.objects.filter(chave="REMETENTE_CEP").update(valor="")
        cache.clear()
        with self.assertRaisesMessage(ErroMelhorEnvio, "remetente"):
            servicos.cotar(self.venda)

    def test_compra_completa(self):
        falsa = self.api()
        envio = servicos.comprar_etiqueta(self.venda, 1, documento="529.982.247-25")
        self.assertEqual(
            falsa.caminhos(),
            [
                "/api/v2/me/shipment/calculate",
                "/api/v2/me/cart",
                "/api/v2/me/shipment/checkout",
                "/api/v2/me/shipment/generate",
                "/api/v2/me/shipment/tracking",
            ],
        )
        carrinho = falsa.chamadas[1][2]
        self.assertEqual(carrinho["service"], 1)
        self.assertEqual(carrinho["to"]["document"], "52998224725")
        self.assertTrue(carrinho["options"]["non_commercial"])
        self.assertEqual(carrinho["options"]["tags"][0]["tag"], "SG00001")
        self.assertEqual(carrinho["from"]["number"], "100")
        envio.refresh_from_db()
        self.assertEqual((envio.status, envio.preco, envio.rastreio), ("gerado", Decimal("22.50"), "AA123456789BR"))
        self.venda.refresh_from_db()
        self.assertEqual(self.venda.codigo_rastreio, "AA123456789BR")
        self.assertTrue(RegistroAuditoria.objects.filter(modelo="envios.Envio", acao="I").exists())
        with self.assertRaisesMessage(ErroMelhorEnvio, "já tem uma etiqueta"):
            servicos.comprar_etiqueta(self.venda, 1, documento="52998224725")

    def test_com_nota_fiscal(self):
        falsa = self.api()
        servicos.comprar_etiqueta(self.venda, 1, chave_nfe="1" * 44)
        opcoes = falsa.chamadas[1][2]["options"]
        self.assertFalse(opcoes["non_commercial"])
        self.assertEqual(opcoes["invoice"], {"key": "1" * 44})

    def test_saldo_insuficiente_tira_do_carrinho(self):
        falsa = self.api(**{"/api/v2/me/shipment/checkout": ErroMelhorEnvio("Saldo insuficiente.", 422)})
        with self.assertRaisesMessage(ErroMelhorEnvio, "Saldo insuficiente"):
            servicos.comprar_etiqueta(self.venda, 1, documento="52998224725")
        self.assertIn(f"/api/v2/me/cart/{ME_ID}", falsa.caminhos())
        envio = Envio.objects.get()
        self.assertEqual(envio.status, "cancelado")
        self.assertIsNone(servicos.envio_ativo(self.venda))

    def test_servico_que_sumiu_da_cotacao(self):
        self.api()
        with self.assertRaisesMessage(ErroMelhorEnvio, "não está mais disponível"):
            servicos.comprar_etiqueta(self.venda, 3, documento="52998224725")
        self.assertFalse(Envio.objects.exists())

    def test_geracao_recusada_fica_paga_para_tentar_de_novo(self):
        falsa = self.api(**{"/api/v2/me/shipment/generate": {ME_ID: {"status": False, "message": "CPF inválido"}}})
        envio = servicos.comprar_etiqueta(self.venda, 1, documento="52998224725")
        self.assertEqual((envio.status, envio.erro), ("pago", "CPF inválido"))
        falsa.respostas["/api/v2/me/shipment/generate"] = {ME_ID: {"status": True}}
        servicos.gerar(envio)
        self.assertEqual(envio.status, "gerado")

    def test_rastreio_leva_a_venda_para_enviado_e_entregue(self):
        falsa = self.api()
        envio = servicos.comprar_etiqueta(self.venda, 1, documento="52998224725")
        falsa.respostas["/api/v2/me/shipment/tracking"] = {ME_ID: {"status": "posted", "tracking": "AA123456789BR"}}
        servicos.atualizar_rastreio(envio)
        self.venda.refresh_from_db()
        self.assertEqual((envio.status, self.venda.situacao), ("postado", "enviado"))
        falsa.respostas["/api/v2/me/shipment/tracking"] = {ME_ID: {"status": "delivered", "tracking": "AA123456789BR"}}
        servicos.atualizar_rastreio(envio)
        self.venda.refresh_from_db()
        self.assertEqual((envio.status, self.venda.situacao), ("entregue", "entregue"))
        self.assertIsNotNone(envio.entregue_em)

    def test_cancelar(self):
        self.api()
        envio = servicos.comprar_etiqueta(self.venda, 1, documento="52998224725")
        servicos.cancelar(envio)
        self.venda.refresh_from_db()
        self.assertEqual((envio.status, self.venda.codigo_rastreio), ("cancelado", ""))
        with self.assertRaises(ErroMelhorEnvio):
            servicos.cancelar(envio)


class TelasEnvioTests(BaseEnvios):
    def test_telas_sem_style_inline(self):
        self.entrar()
        self.api()
        urls = [
            "/gestao/integracoes/",
            f"/gestao/vendas/{self.venda.pk}/",
        ]
        self.client.post(f"/gestao/vendas/{self.venda.pk}/frete/cotar/")
        for url in urls:
            with self.subTest(url=url):
                resposta = self.client.get(url)
                self.assertEqual(resposta.status_code, 200)
                self.assertNotIn("style=", resposta.content.decode())
        resposta = self.client.get(f"/gestao/vendas/{self.venda.pk}/")
        self.assertContains(resposta, "Correios · PAC")
        self.assertContains(resposta, "Transportadora não atende este trecho.")
        self.assertContains(self.client.get("/gestao/integracoes/"), "R$ 150,75")

    def test_conectar_e_retorno(self):
        self.entrar()
        self.conexao.delete()
        with override_settings(MELHOR_ENVIO_CLIENT_ID="123", MELHOR_ENVIO_CLIENT_SECRET="x" * 10):
            resposta = self.client.get("/gestao/integracoes/melhor-envio/conectar/")
            self.assertTrue(resposta["Location"].startswith("https://sandbox.melhorenvio.com.br/oauth/authorize"))
            ruim = self.client.get("/gestao/integracoes/melhor-envio/retorno/", {"code": "c", "state": "outro"})
            self.assertRedirects(ruim, "/gestao/integracoes/")
            self.assertFalse(ConexaoMelhorEnvio.objects.exists())
            self.client.get("/gestao/integracoes/melhor-envio/conectar/")
            estado = self.client.session["melhorenvio_estado"]
            self.api()
            self.client.get("/gestao/integracoes/melhor-envio/retorno/", {"code": "c", "state": estado})
        conexao = ConexaoMelhorEnvio.objects.get()
        self.assertEqual((conexao.access_token, conexao.conta), ("novo-acesso", "Strong Glasses"))

    def test_comprar_pelo_painel(self):
        self.entrar()
        Pedido.objects.filter(pk=self.venda.pk).update(cliente=None)
        self.api()
        url = f"/gestao/vendas/{self.venda.pk}/frete/comprar/"
        resposta = self.client.post(url, {"servico": "1"}, follow=True)
        self.assertContains(resposta, "declaração de conteúdo exige")
        resposta = self.client.post(url, {"servico": "1", "documento": "111.111.111-11"}, follow=True)
        self.assertFalse(Envio.objects.exists())
        resposta = self.client.post(url, {"servico": "1", "documento": "529.982.247-25"}, follow=True)
        self.assertContains(resposta, "Etiqueta Correios PAC comprada")
        envio = Envio.objects.get()
        impressao = self.client.get(f"/gestao/envios/{envio.pk}/imprimir/")
        self.assertEqual(impressao["Location"], "https://sandbox.melhorenvio.com.br/imprimir/abc")
        dace = self.client.get(f"/gestao/envios/{envio.pk}/declaracao/")
        self.assertEqual(dace["Location"], "https://arquivos.melhorenvio.com.br/dace.pdf")
        self.client.post(f"/gestao/envios/{envio.pk}/cancelar/")
        envio.refresh_from_db()
        self.assertEqual(envio.status, "cancelado")

    def test_usa_cpf_do_cadastro_com_registro_de_acesso(self):
        self.entrar()
        falsa = self.api()
        self.client.post(f"/gestao/vendas/{self.venda.pk}/frete/comprar/", {"servico": "1"})
        carrinho = next(c[2] for c in falsa.chamadas if c[1] == "/api/v2/me/cart")
        self.assertEqual(carrinho["to"]["document"], "52998224725")
        acessos = RegistroAuditoria.objects.filter(acao="A", objeto_id=str(self.cliente.pk))
        self.assertTrue(acessos.filter(depois__motivo="etiqueta de envio").exists())

    def test_comando_atualiza_rastreios(self):
        from io import StringIO

        from django.core.management import call_command

        falsa = self.api()
        servicos.comprar_etiqueta(self.venda, 1, documento="52998224725")
        falsa.respostas["/api/v2/me/shipment/tracking"] = {ME_ID: {"status": "posted", "tracking": "AA123456789BR"}}
        saida = StringIO()
        call_command("atualizar_rastreios", stdout=saida)
        self.assertIn("1 etiqueta(s) conferida(s)", saida.getvalue())
        self.assertEqual(Envio.objects.get().status, "postado")


class SimularFreteTests(BaseEnvios):
    def test_simula_no_lancamento(self):
        self.entrar()
        falsa = self.api()
        resposta = self.client.post(
            "/gestao/vendas/frete/simular/",
            {"cep": "01310-100", "variacao": [self.variacao.pk], "quantidade": ["2"]},
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual([o["servico"] for o in resposta.json()["opcoes"]], ["PAC", "SEDEX", ".Package"])
        corpo = falsa.chamadas[0][2]
        self.assertEqual(corpo["to"]["postal_code"], "01310100")
        self.assertEqual(corpo["volumes"][0]["weight"], 0.1)  # 2 x 50 g

    def test_simular_sem_cep_ou_sem_itens(self):
        self.entrar()
        self.api()
        url = "/gestao/vendas/frete/simular/"
        sem_cep = self.client.post(url, {"variacao": [self.variacao.pk], "quantidade": ["1"]})
        self.assertEqual(sem_cep.status_code, 400)
        self.assertIn("CEP", sem_cep.json()["erro"])
        sem_itens = self.client.post(url, {"cep": "01310100"})
        self.assertIn("óculos", sem_itens.json()["erro"])

    def test_servico_escolhido_vem_marcado_na_compra(self):
        self.entrar()
        self.api()
        Pedido.objects.filter(pk=self.venda.pk).update(frete_servico_id=2, frete_servico="Correios · SEDEX")
        self.client.post(f"/gestao/vendas/{self.venda.pk}/frete/cotar/")
        html = self.client.get(f"/gestao/vendas/{self.venda.pk}/").content.decode()
        self.assertIn('value="2" required checked', html)
        self.assertNotIn('value="1" required checked', html)
