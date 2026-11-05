import json
import tempfile
from decimal import Decimal
from io import StringIO
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.catalogo.models import AcabamentoArmacao, Categoria, CorLente, ImagemProduto, Produto, Variacao
from apps.clientes import lgpd
from apps.clientes.models import Cliente, Consentimento
from apps.historico.models import PedidoHistorico
from apps.nuvemshop.imagens import ImagemInvalida
from apps.nuvemshop.importador import Importador

from .test_mapeamento import png


def variante(id_, cor, preco="159.90", promo="94.90", estoque=3, **extra):
    return {
        "id": id_,
        "values": [{"pt": cor}] if cor else [],
        "price": preco,
        "promotional_price": promo,
        "stock": estoque,
        "sku": None,
        **extra,
    }


DADOS = {
    "categories": [
        {"id": 1, "name": {"pt": "Masculino"}, "handle": {"pt": "masculino"}, "parent": None},
        {"id": 2, "name": {"pt": "Feminino"}, "handle": {"pt": "feminino"}, "parent": None},
        {"id": 3, "name": {"pt": "Armações de Grau"}, "handle": {"pt": "armacoes-de-grau"}, "parent": None},
        {"id": 4, "name": {"pt": "Novidades Fem"}, "handle": {"pt": "novidades-fem"}, "parent": 2},
    ],
    "products": [
        {
            "id": 100,
            "name": {"pt": "Óculos de Sol Roshi"},
            "handle": {"pt": "oculos-de-sol-roshi-preto-azul"},
            "description": {"pt": "<p>Proteção <b>UV400</b></p>"},
            "attributes": [{"pt": "Cor"}],
            "categories": [{"id": 1}, {"id": 2}],
            "published": True,
            "seo_title": {"pt": "Roshi"},
            "variants": [
                variante(1001, "Preto/Azul", weight="0.180", width="16", height="6", depth="8", image_id=5001),
                variante(1002, "Tartaruga", estoque=None, sku="RSH-TT"),
                variante(1003, "Amarelo/Tartaruga"),
            ],
            "images": [
                {"id": 5001, "src": "https://cdn.exemplo/a.png", "position": 1, "alt": []},
                {"id": 5002, "src": "https://cdn.exemplo/erro.png", "position": 2, "alt": []},
            ],
        },
        {
            "id": 200,
            "name": {"pt": "Óculos de Sol Nice Dourado"},
            "handle": {"pt": "oculos-de-sol-nice-dourado"},
            "categories": [{"id": 2}],
            "published": True,
            "variants": [variante(2001, "", preco="149.90", promo="74.90", estoque=1)],
        },
        {
            "id": 300,
            "name": {"pt": "Armação Lisboa"},
            "handle": {"pt": "armacao-lisboa"},
            "attributes": [{"pt": "Cor"}],
            "categories": [{"id": 3}],
            "published": False,
            "variants": [variante(3001, "Roxo Neon", preco="100", promo=None)],
        },
        {
            "id": 400,
            "name": {"pt": "Roshi duplicado"},
            "handle": {"pt": "oculos-de-sol-roshi-preto-azul"},
            "variants": [variante(4001, "Preto")],
        },
    ],
    "customers": [
        {
            "id": 10,
            "name": "Maria",
            "email": "Maria@Ex.com",
            "phone": "85999990000",
            "identification": "529.982.247-25",
            "accepts_marketing": True,
            "default_address": {
                "id": 70,
                "address": "Rua Tomás Pompeu",
                "number": "111",
                "floor": "apto 1000",
                "locality": "Meireles",
                "city": "Fortaleza",
                "province": "Ceará",
                "zipcode": "60160080",
                "country": "BR",
            },
            "addresses": [
                {
                    "id": 70,
                    "address": "Rua Tomás Pompeu",
                    "number": "111",
                    "floor": "apto 1000",
                    "locality": "Meireles",
                    "city": "Fortaleza",
                    "province": "Ceará",
                    "zipcode": "60160080",
                    "country": "BR",
                },
                {
                    "id": 71,
                    "address": "Av. Beira Mar",
                    "number": "500",
                    "city": "Fortaleza",
                    "province": "Ceará",
                    "zipcode": "60165121",
                },
            ],
        },
        {"id": 11, "name": "Hotel Mar", "email": "hotel@ex.com", "identification": "11.222.333/0001-81"},
        {"id": 12, "name": "Maria (2ª conta)", "email": "maria@ex.com"},
    ],
    "orders": [
        {
            "id": 9001,
            "number": 101,
            "customer": {"id": 10, "email": "maria@ex.com"},
            "created_at": "2025-08-29T05:33:53+0000",
            "paid_at": "2025-08-29T05:40:00+0000",
            "status": "closed",
            "payment_status": "paid",
            "subtotal": "174.70",
            "discount": "0.00",
            "discount_coupon": "17.47",
            "shipping_cost_customer": "17.43",
            "total": "174.66",
            "coupon": [{"code": "PRIMEIRA10"}],
            "storefront": "store",
            "gateway_name": "Nuvem Pago",
            "shipping_address": {
                "name": "Maria",
                "address": "Rua Nova",
                "number": "1",
                "city": "Fortaleza",
                "province": "Ceará",
                "zipcode": "60000000",
            },
            "products": [
                {
                    "product_id": 100,
                    "variant_id": 1001,
                    "name": "Óculos de Sol Roshi",
                    "price": "94.90",
                    "quantity": 2,
                    "variant_values": ["Preto/Azul"],
                }
            ],
        },
        {
            "id": 9002,
            "number": 102,
            "customer": {"id": 77, "name": "Visitante", "email": "novo@ex.com"},
            "created_at": "2025-09-01T10:00:00+0000",
            "status": "cancelled",
            "payment_status": "voided",
            "total": "79.90",
            "products": [],
        },
    ],
    "coupons": [{"code": "PRIMEIRA10", "type": "percentage", "value": 10}],
}


class APIFalsa:
    def __init__(self, dados):
        self.dados = dados

    def paginar(self, caminho, params=None):
        yield from self.dados.get(caminho, [])


class BaixadorFalso:
    def __init__(self):
        self.chamadas = 0

    def __call__(self, url):
        self.chamadas += 1
        if "erro" in url:
            raise ImagemInvalida("Arquivo não é uma imagem válida.")
        return png(), "png"


class ImportadorTests(TestCase):
    def importar(self, etapas=("categorias", "produtos", "clientes", "pedidos", "cupons"), pasta=None):
        self.baixador = getattr(self, "baixador", BaixadorFalso())
        importador = Importador(APIFalsa(DADOS), pasta_saida=pasta, baixador=self.baixador)
        return importador.executar(etapas)

    def test_categorias_e_produtos(self):
        relatorio = self.importar(("categorias", "produtos"))

        self.assertEqual(Categoria.objects.count(), 4)
        self.assertEqual(Categoria.objects.get(nuvemshop_id=4).pai.nome, "Feminino")

        roshi = Produto.objects.get(nuvemshop_id=100)
        self.assertEqual(roshi.slug, "oculos-de-sol-roshi-preto-azul")
        self.assertEqual((roshi.preco, roshi.preco_comparativo), (Decimal("94.90"), Decimal("159.90")))
        self.assertEqual(roshi.publico, Produto.Publico.UNISSEX)
        self.assertEqual(roshi.descricao, "Proteção UV400")
        self.assertTrue(roshi.ativo)
        self.assertTrue(roshi.pronto_para_envio)
        self.assertEqual(roshi.peso_g, 180)

        v1 = Variacao.objects.get(nuvemshop_id=1001)
        self.assertEqual((v1.armacao.nome, v1.lente.nome, v1.sku, v1.estoque), ("Preto", "Azul", "NS-1001", 3))
        v2 = Variacao.objects.get(nuvemshop_id=1002)
        self.assertEqual((v2.armacao.nome, v2.lente, v2.sku, v2.estoque), ("Tartaruga", None, "RSH-TT", 0))
        self.assertEqual(AcabamentoArmacao.objects.get(nome="Tartaruga").cor_hex, "#6B3E1F")

        foto = ImagemProduto.objects.get(nuvemshop_id=5001)
        self.assertEqual(foto.variacao, v1)
        self.assertTrue(foto.imagem.name.startswith("produtos/"))
        self.assertFalse(ImagemProduto.objects.filter(nuvemshop_id=5002).exists())

        nice = Produto.objects.get(nuvemshop_id=200)
        self.assertEqual(nice.variacoes.get().armacao.nome, "Dourado")  # cor tirada do nome
        self.assertEqual(nice.publico, Produto.Publico.FEMININO)

        lisboa = Produto.objects.get(nuvemshop_id=300)
        self.assertEqual(lisboa.tipo, Produto.Tipo.GRAU)
        self.assertFalse(lisboa.ativo)
        self.assertEqual(AcabamentoArmacao.objects.get(nome="Roxo Neon").cor_hex, "#999999")

        self.assertEqual(Produto.objects.get(nuvemshop_id=400).slug, "oculos-de-sol-roshi-preto-azul-400")

        pendencias = relatorio.pendencias
        invertidas = pendencias["Cores 'armação/lente' que parecem invertidas"]
        self.assertIn("Óculos de Sol Roshi: Amarelo/Tartaruga", invertidas)
        self.assertTrue(pendencias["Fotos que não puderam ser baixadas"])
        self.assertTrue(pendencias["Cores sem tom definido (cinza provisório)"])
        self.assertTrue(pendencias["Endereços (slug) alterados por conflito — revise o SEO"])
        self.assertIn("Produtos sem peso/medidas (frete)", pendencias)
        self.assertEqual(Produto.objects.get(nuvemshop_id=200).peso_g, 50)  # peso padrão

    def test_reimportar_nao_duplica_nem_baixa_fotos_de_novo(self):
        self.importar(("categorias", "produtos"))
        chamadas = self.baixador.chamadas
        self.importar(("categorias", "produtos"))
        self.assertEqual(Produto.objects.count(), 4)
        self.assertEqual(Variacao.objects.count(), 6)
        self.assertEqual(ImagemProduto.objects.count(), 1)
        self.assertEqual(AcabamentoArmacao.objects.filter(nome="Preto").count(), 1)
        self.assertEqual(CorLente.objects.filter(nome="Azul").count(), 1)
        self.assertEqual(self.baixador.chamadas, chamadas + 1)  # só tenta de novo a que falhou

    def test_clientes_com_documento_e_enderecos(self):
        relatorio = self.importar(("clientes",))
        maria = Cliente.objects.get(nuvemshop_id=10)
        self.assertEqual(maria.email, "maria@ex.com")
        self.assertEqual(maria.whatsapp, "+5585999990000")
        self.assertEqual((maria.tipo, maria.documento), (Cliente.Tipo.PESSOA_FISICA, "52998224725"))
        self.assertEqual(maria.enderecos.count(), 2)  # endereço padrão não duplica
        padrao = maria.enderecos.get(padrao=True)
        self.assertEqual((padrao.cep, padrao.numero, padrao.complemento), ("60160080", "111", "apto 1000"))
        self.assertTrue(maria.tem_consentimento(Consentimento.Finalidade.MARKETING_EMAIL))
        self.assertEqual(maria.consentimentos.get().origem, Consentimento.Origem.IMPORTACAO)

        hotel = Cliente.objects.get(nuvemshop_id=11)
        self.assertEqual((hotel.tipo, hotel.documento), (Cliente.Tipo.PESSOA_JURIDICA, "11222333000181"))

        self.assertEqual(Cliente.objects.count(), 2)  # 2ª conta da Maria unificada
        self.assertEqual(relatorio.contagem["clientes com CPF"], 1)
        self.assertEqual(relatorio.contagem["clientes com CNPJ"], 1)

        self.importar(("clientes",))  # reimportar não duplica endereços
        self.assertEqual(maria.enderecos.count(), 2)

    def test_nao_reimporta_titular_anonimizado(self):
        self.importar(("clientes",))
        lgpd.anonimizar(Cliente.objects.get(nuvemshop_id=10))
        self.importar(("clientes",))
        maria = Cliente.objects.get(nuvemshop_id=10)
        self.assertIsNotNone(maria.anonimizado_em)
        self.assertEqual((maria.email, maria.documento), ("", ""))
        self.assertFalse(maria.enderecos.exists())
        self.assertFalse(maria.tem_consentimento(Consentimento.Finalidade.MARKETING_EMAIL))

    def test_pedidos(self):
        self.importar(("categorias", "produtos", "clientes", "pedidos"))
        pedido = PedidoHistorico.objects.get(numero=101)
        self.assertEqual(pedido.cliente.nuvemshop_id, 10)
        valores = (pedido.total, pedido.desconto, pedido.frete)
        self.assertEqual(valores, (Decimal("174.66"), Decimal("17.47"), Decimal("17.43")))
        self.assertEqual((pedido.cupom, pedido.cidade, pedido.uf), ("PRIMEIRA10", "Fortaleza", "Ceará"))
        self.assertTrue(pedido.pago)
        item = pedido.itens.get()
        self.assertEqual((item.quantidade, item.variacao.nuvemshop_id, item.variante), (2, 1001, "Preto/Azul"))

        cancelado = PedidoHistorico.objects.get(numero=102)
        self.assertFalse(cancelado.pago)
        self.assertEqual(cancelado.cliente.email, "novo@ex.com")  # cliente criado a partir do pedido

        # Endereço da entrega vira endereço do cliente (para os próximos envios).
        self.assertTrue(pedido.cliente.enderecos.filter(logradouro="Rua Nova", destinatario="Maria").exists())

        # Reimportar não duplica pedidos nem itens.
        self.importar(("pedidos",))
        self.assertEqual(PedidoHistorico.objects.count(), 2)
        self.assertEqual(pedido.itens.count(), 1)

        # Pedidos entram no direito de acesso do titular.
        dados = lgpd.exportar_dados(pedido.cliente)
        self.assertEqual(dados["pedidos_anteriores"][0]["numero"], 101)
        self.assertEqual(len(dados["enderecos"]), 3)

    def test_cupons_salvos_fora_do_banco(self):
        with tempfile.TemporaryDirectory() as pasta:
            self.importar(("cupons",), pasta=Path(pasta))
            salvos = json.loads((Path(pasta) / "cupons.json").read_text(encoding="utf-8"))
        self.assertEqual(salvos[0]["code"], "PRIMEIRA10")

    def test_relatorio_markdown(self):
        texto = self.importar(("categorias", "produtos")).em_markdown()
        self.assertIn("# Relatório da importação da Nuvemshop", texto)
        self.assertIn("## Para revisar no painel", texto)


@override_settings(NUVEMSHOP_STORE_ID="1", NUVEMSHOP_ACCESS_TOKEN="t")
class ComandoTests(TestCase):
    def test_simular_nao_grava(self):
        with (
            tempfile.TemporaryDirectory() as pasta,
            mock.patch(
                "apps.nuvemshop.management.commands.importar_nuvemshop.NuvemshopAPI.das_configuracoes",
                return_value=APIFalsa(DADOS),
            ),
        ):
            call_command("importar_nuvemshop", "--simular", "--pasta", pasta, stdout=StringIO())
            self.assertTrue(list(Path(pasta).glob("relatorio-*.md")))
        self.assertEqual(Produto.objects.count(), 0)
        self.assertEqual(Cliente.objects.count(), 0)

    def test_etapa_invalida(self):
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError):
            call_command("importar_nuvemshop", "--etapas", "produtos,foguete", stdout=StringIO())
