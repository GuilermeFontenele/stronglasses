from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase

from apps.catalogo.models import AcabamentoArmacao, CorLente, Produto, Variacao
from apps.core.models import Parametro, RegistroAuditoria
from apps.vendas.models import Pedido, sigla_uf
from apps.vendas.servicos import EstoqueInsuficiente, ItemNovo, calcular, mudar_situacao, registrar_venda

CRIACAO = RegistroAuditoria.Acao.CRIACAO


class BaseVendas(TestCase):
    def setUp(self):
        cache.clear()
        Parametro.objects.update_or_create(
            chave="PIX_DESCONTO_PERCENTUAL", defaults={"valor": "5", "tipo": Parametro.Tipo.DECIMAL}
        )
        preta = AcabamentoArmacao.objects.create(nome="Preta", cor_hex="#111111")
        verde = CorLente.objects.create(nome="Verde", cor_hex="#55704A")
        self.produto = Produto.objects.create(nome="Zaik", slug="zaik", preco=Decimal("100.00"), ativo=True)
        self.variacao = Variacao.objects.create(produto=self.produto, armacao=preta, lente=verde, sku="ZK-1", estoque=3)

    def venda(self, **campos):
        dados = {"forma_pagamento": Pedido.FormaPagamento.PIX, "canal": Pedido.Canal.HOTEL} | campos
        return Pedido(**dados)


class CalculoTests(BaseVendas):
    def test_ordem_preco_desconto_pix_frete(self):
        valores = calcular(Decimal("200.00"), Decimal("20.00"), Decimal("15.00"), aplicar_pix=True)
        # (200 - 20) = 180; Pix 5% = 9,00 (nunca sobre o frete); + 15 de frete
        self.assertEqual(valores["desconto_pix"], Decimal("9.00"))
        self.assertEqual(valores["total"], Decimal("186.00"))

    def test_sem_pix(self):
        valores = calcular(Decimal("200.00"), Decimal("0"), Decimal("0"), aplicar_pix=False)
        self.assertEqual(valores, {"desconto_pix": Decimal("0.00"), "total": Decimal("200.00")})

    def test_desconto_maior_que_subtotal_nao_fica_negativo(self):
        valores = calcular(Decimal("50.00"), Decimal("80.00"), Decimal("10.00"), aplicar_pix=True)
        self.assertEqual(valores["total"], Decimal("10.00"))


class RegistrarVendaTests(BaseVendas):
    def test_registra_baixa_estoque_e_numera(self):
        pedido = registrar_venda(self.venda(), [ItemNovo(self.variacao, 2)], baixar_estoque=True, aplicar_pix=True)
        self.variacao.refresh_from_db()
        self.assertEqual(self.variacao.estoque, 1)
        self.assertEqual(pedido.numero, 1)
        self.assertEqual(pedido.codigo, "SG00001")
        self.assertEqual(pedido.subtotal, Decimal("200.00"))
        self.assertEqual(pedido.total, Decimal("190.00"))
        self.assertTrue(pedido.estoque_baixado)
        self.assertIsNotNone(pedido.pago_em)
        item = pedido.itens.get()
        self.assertEqual((item.nome, item.sku, item.quantidade), ("Zaik", "ZK-1", 2))
        self.assertTrue(RegistroAuditoria.objects.filter(modelo="vendas.Pedido", acao=CRIACAO).exists())
        segunda = registrar_venda(self.venda(), [ItemNovo(self.variacao, 1)], baixar_estoque=False, aplicar_pix=False)
        self.assertEqual(segunda.numero, 2)

    def test_preco_combinado_substitui_o_da_loja(self):
        pedido = registrar_venda(
            self.venda(), [ItemNovo(self.variacao, 1, Decimal("80.00"))], baixar_estoque=True, aplicar_pix=False
        )
        self.assertEqual(pedido.total, Decimal("80.00"))

    def test_estoque_insuficiente_nao_grava_nada(self):
        with self.assertRaises(EstoqueInsuficiente) as erro:
            registrar_venda(self.venda(), [ItemNovo(self.variacao, 4)], baixar_estoque=True, aplicar_pix=True)
        self.assertIn("em estoque 3", erro.exception.faltas[0])
        self.assertFalse(Pedido.objects.exists())
        self.variacao.refresh_from_db()
        self.assertEqual(self.variacao.estoque, 3)

    def test_mesma_cor_em_duas_linhas_soma_para_conferir_estoque(self):
        with self.assertRaises(EstoqueInsuficiente):
            registrar_venda(
                self.venda(),
                [ItemNovo(self.variacao, 2), ItemNovo(self.variacao, 2)],
                baixar_estoque=True,
                aplicar_pix=True,
            )

    def test_sem_baixar_estoque_permite_vender_sem_saldo(self):
        pedido = registrar_venda(self.venda(), [ItemNovo(self.variacao, 10)], baixar_estoque=False, aplicar_pix=False)
        self.variacao.refresh_from_db()
        self.assertEqual(self.variacao.estoque, 3)
        self.assertFalse(pedido.estoque_baixado)

    def test_venda_sem_itens(self):
        with self.assertRaises(ValueError):
            registrar_venda(self.venda(), [], baixar_estoque=True, aplicar_pix=True)


class SituacaoTests(BaseVendas):
    def test_cancelar_devolve_estoque_uma_vez(self):
        pedido = registrar_venda(self.venda(), [ItemNovo(self.variacao, 2)], baixar_estoque=True, aplicar_pix=True)
        mudar_situacao(pedido, Pedido.Situacao.CANCELADO)
        mudar_situacao(pedido, Pedido.Situacao.CANCELADO)
        self.variacao.refresh_from_db()
        self.assertEqual(self.variacao.estoque, 3)
        pedido.refresh_from_db()
        self.assertFalse(pedido.estoque_baixado)
        self.assertIsNotNone(pedido.cancelado_em)
        self.assertFalse(pedido.pago)

    def test_enviar_com_rastreio(self):
        venda = self.venda(entrega=Pedido.Entrega.CORREIOS)
        pedido = registrar_venda(venda, [ItemNovo(self.variacao, 1)], baixar_estoque=True, aplicar_pix=False)
        pedido = mudar_situacao(pedido, Pedido.Situacao.ENVIADO, codigo_rastreio=" aa123456789br ")
        self.assertEqual(pedido.codigo_rastreio, "AA123456789BR")
        self.assertIsNotNone(pedido.enviado_em)
        self.assertTrue(pedido.pago)

    def test_pendente_so_conta_pago_depois(self):
        venda = self.venda(situacao=Pedido.Situacao.PENDENTE)
        pedido = registrar_venda(venda, [ItemNovo(self.variacao, 1)], baixar_estoque=True, aplicar_pix=True)
        self.assertIsNone(pedido.pago_em)
        pedido = mudar_situacao(pedido, Pedido.Situacao.PAGO)
        self.assertIsNotNone(pedido.pago_em)


class UfTests(TestCase):
    def test_sigla_uf(self):
        self.assertEqual(sigla_uf("ce"), "CE")
        self.assertEqual(sigla_uf(" Rio  Grande do Norte "), "RN")
        self.assertEqual(sigla_uf("Ceará"), "CE")
        self.assertEqual(sigla_uf("Atlântida"), "")
