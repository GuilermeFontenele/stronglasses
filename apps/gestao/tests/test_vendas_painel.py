from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.utils import timezone

from apps.clientes import lgpd
from apps.clientes.models import Cliente
from apps.core.models import Parametro, RegistroAuditoria
from apps.gestao import metricas
from apps.vendas.models import Pedido
from apps.vendas.servicos import ItemNovo, registrar_venda

from .test_gestao import SENHA, BaseGestao, Usuario

CRIACAO = RegistroAuditoria.Acao.CRIACAO


class BaseVendasPainel(BaseGestao):
    def setUp(self):
        super().setUp()
        Parametro.objects.update_or_create(
            chave="PIX_DESCONTO_PERCENTUAL", defaults={"valor": "5", "tipo": Parametro.Tipo.DECIMAL}
        )
        cache.clear()

    def dados(self, **extra):
        dados = {
            "cliente": self.cliente.pk,
            "realizado_em": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
            "situacao": "pago",
            "forma_pagamento": "pix",
            "parcelas": "1",
            "desconto": "0",
            "cupom": "",
            "frete": "0",
            "canal": "hotel",
            "parceiro": "Hotel Praia Mar",
            "entrega": "maos",
            "destinatario": "",
            "cep": "",
            "logradouro": "",
            "numero_endereco": "",
            "complemento": "",
            "bairro": "",
            "cidade": "",
            "uf": "CE",
            "peso_g": "",
            "observacoes": "",
            "aplicar_pix": "on",
            "baixar_estoque": "on",
            "itens-TOTAL_FORMS": "2",
            "itens-INITIAL_FORMS": "0",
            "itens-MIN_NUM_FORMS": "1",
            "itens-MAX_NUM_FORMS": "1000",
            "itens-0-variacao": str(self.variacao.pk),
            "itens-0-quantidade": "1",
            "itens-0-preco_unitario": "",
            # segunda linha deixada em branco (botão "Adicionar" sem uso): é ignorada
            "itens-1-variacao": "",
            "itens-1-quantidade": "1",
            "itens-1-preco_unitario": "",
        }
        dados.update(extra)
        return dados

    def venda_correios(self):
        pedido = Pedido(
            cliente=self.cliente,
            forma_pagamento="pix",
            canal="whatsapp",
            entrega="correios",
            destinatario="Maria Souza",
            cep="60000000",
            logradouro="Rua A",
            numero_endereco="10",
            bairro="Centro",
            cidade="Fortaleza",
            uf="CE",
        )
        return registrar_venda(pedido, [ItemNovo(self.variacao, 1)], baixar_estoque=True, aplicar_pix=True)


class TelasVendasTests(BaseVendasPainel):
    def test_telas_abrem_sem_style_inline(self):
        self.entrar()
        venda = self.venda_correios()
        urls = [
            "/gestao/vendas/",
            "/gestao/vendas/?situacao=a-enviar&canal=hotel&periodo=30d&q=SG00001",
            "/gestao/vendas/nova/",
            "/gestao/vendas/nova/?busca_cliente=maria",
            f"/gestao/vendas/nova/?cliente={self.cliente.pk}",
            "/gestao/clientes/novo/?para=venda&nome=Jo",
            f"/gestao/vendas/{venda.pk}/",
            f"/gestao/vendas/{venda.pk}/etiqueta/",
            f"/gestao/vendas/{venda.pk}/etiqueta/?folha=declaracao",
        ]
        for url in urls:
            with self.subTest(url=url):
                resposta = self.client.get(url)
                self.assertEqual(resposta.status_code, 200)
                html = resposta.content.decode()
                self.assertNotIn("style=", html)
                self.assertIn('content="noindex, nofollow"', html)

    def test_busca_de_cliente_e_formulario_preenchido(self):
        self.entrar()
        resposta = self.client.get("/gestao/vendas/nova/", {"busca_cliente": "maria"})
        self.assertEqual(resposta.context["resultados"], [self.cliente])
        resposta = self.client.get("/gestao/vendas/nova/", {"cliente": self.cliente.pk})
        self.assertEqual(resposta.context["form"].initial["cep"], "60000000")
        self.assertEqual(resposta.context["form"].initial["uf"], "CE")
        self.assertContains(resposta, 'data-preco="85.90"')

    def test_sem_permissao(self):
        equipe = Usuario.objects.create_user("ajudante", password=SENHA, is_staff=True)
        self.client.force_login(equipe)
        self.assertEqual(self.client.get("/gestao/vendas/").status_code, 403)
        equipe.user_permissions.add(Permission.objects.get(codename="view_pedido"))
        self.assertEqual(self.client.get("/gestao/vendas/").status_code, 200)
        self.assertEqual(self.client.get("/gestao/vendas/nova/").status_code, 403)
        venda = self.venda_correios()
        self.assertEqual(self.client.get(f"/gestao/vendas/{venda.pk}/etiqueta/").status_code, 403)


class LancarVendaTests(BaseVendasPainel):
    def test_lanca_venda_baixa_estoque_e_entra_no_dashboard(self):
        self.entrar()
        resposta = self.client.post("/gestao/vendas/nova/", self.dados())
        venda = Pedido.objects.get()
        self.assertRedirects(resposta, f"/gestao/vendas/{venda.pk}/")
        self.assertEqual(venda.cliente, self.cliente)
        self.assertEqual(venda.total, Decimal("81.60"))  # 85,90 - 5% Pix (4,30)
        self.assertEqual(venda.parceiro, "Hotel Praia Mar")
        self.assertEqual(venda.itens.count(), 1)
        self.variacao.refresh_from_db()
        self.assertEqual(self.variacao.estoque, 0)
        self.assertEqual(venda.criado_por, self.dono)

        numeros = self.client.get("/gestao/?periodo=30d").context["numeros"]
        self.assertEqual(numeros["faturamento"], Decimal("253.40"))  # 171,80 da Nuvemshop + 81,60
        self.assertEqual(numeros["pedidos"], 2)
        self.assertEqual(numeros["itens"], 3)
        dashboard = self.client.get("/gestao/")
        self.assertEqual(dashboard.context["mais_vendidos"][0]["quantidade_total"], 3)
        estado = dashboard.context["estados"][0]
        self.assertEqual((estado["uf"], estado["pedidos"], estado["valor"]), ("Ceará", 2, Decimal("253.40")))
        self.assertEqual([c["canal"] for c in dashboard.context["canais"]], ["Site (Nuvemshop)", "Hotel"])
        self.assertIn("SG00001", [linha["codigo"] for linha in dashboard.context["ultimos"]])

        lista = self.client.get("/gestao/clientes/", {"ordem": "gasto"})
        maria = lista.context["pagina"][0]
        self.assertEqual((maria.n_pedidos, maria.total_gasto), (2, Decimal("253.40")))
        ficha = self.client.get(f"/gestao/clientes/{self.cliente.pk}/")
        self.assertEqual([p["codigo"] for p in ficha.context["pedidos"]], ["SG00001", "#101"])
        self.assertEqual(ficha.context["total_gasto"], Decimal("253.40"))

    def test_pix_so_quando_paga_no_pix_e_parcelas_so_no_credito(self):
        self.entrar()
        self.client.post("/gestao/vendas/nova/", self.dados(forma_pagamento="dinheiro", parcelas="3"))
        venda = Pedido.objects.get()
        self.assertEqual((venda.total, venda.desconto_pix, venda.parcelas), (Decimal("85.90"), Decimal("0.00"), 1))

    def test_estoque_insuficiente(self):
        self.entrar()
        resposta = self.client.post("/gestao/vendas/nova/", self.dados(**{"itens-0-quantidade": "2"}), follow=True)
        self.assertFalse(Pedido.objects.exists())
        self.assertContains(resposta, "Estoque insuficiente")
        self.assertContains(resposta, "em estoque 1")

    def test_sem_item(self):
        self.entrar()
        resposta = self.client.post("/gestao/vendas/nova/", self.dados(**{"itens-0-variacao": ""}))
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(Pedido.objects.exists())

    def test_correios_exige_endereco_e_pode_salvar_no_cadastro(self):
        self.entrar()
        resposta = self.client.post("/gestao/vendas/nova/", self.dados(entrega="correios"))
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("cep", resposta.context["form"].errors)
        endereco = {
            "entrega": "correios",
            "destinatario": "Maria Souza",
            "cep": "60110-000",
            "logradouro": "Av. Beira Mar",
            "numero_endereco": "100",
            "bairro": "Meireles",
            "cidade": "Fortaleza",
            "uf": "CE",
            "frete": "20.00",
            "salvar_endereco": "on",
        }
        self.client.post("/gestao/vendas/nova/", self.dados(**endereco))
        venda = Pedido.objects.get()
        self.assertEqual(venda.cep, "60110000")
        self.assertEqual(venda.total, Decimal("101.60"))  # o Pix não incide sobre os 20 de frete
        self.assertTrue(self.cliente.enderecos.filter(cep="60110000", logradouro="Av. Beira Mar").exists())

    def test_data_no_futuro(self):
        self.entrar()
        futuro = (timezone.localtime() + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M")
        resposta = self.client.post("/gestao/vendas/nova/", self.dados(realizado_em=futuro))
        self.assertIn("realizado_em", resposta.context["form"].errors)

    def test_cadastrar_cliente_e_voltar_para_a_venda(self):
        self.entrar()
        resposta = self.client.post(
            "/gestao/clientes/novo/",
            {
                "para": "venda",
                "tipo": "PJ",
                "nome": "Hotel Praia",
                "razao_social": "Praia Ltda",
                "whatsapp": "+5585988887777",
            },
        )
        novo = Cliente.objects.get(nome="Hotel Praia")
        self.assertRedirects(resposta, f"/gestao/vendas/nova/?cliente={novo.pk}")
        auditoria = RegistroAuditoria.objects.filter(modelo="clientes.Cliente", objeto_id=str(novo.pk), acao=CRIACAO)
        self.assertTrue(auditoria.exists())

    def test_cpf_repetido(self):
        self.entrar()
        resposta = self.client.post(
            "/gestao/clientes/novo/",
            {"tipo": "PF", "nome": "Outra", "email": "outra@exemplo.com", "documento": "529.982.247-25"},
        )
        self.assertContains(resposta, "Já existe um cliente com este CPF/CNPJ")


class VendaDetalheTests(BaseVendasPainel):
    def test_andamento_e_cancelamento(self):
        self.entrar()
        venda = self.venda_correios()
        self.client.post(
            f"/gestao/vendas/{venda.pk}/", {"acao": "situacao", "situacao": "enviado", "codigo_rastreio": "aa1br"}
        )
        venda.refresh_from_db()
        self.assertEqual((venda.situacao, venda.codigo_rastreio), ("enviado", "AA1BR"))
        self.client.post(f"/gestao/vendas/{venda.pk}/", {"acao": "cancelar"})
        venda.refresh_from_db()
        self.variacao.refresh_from_db()
        self.assertEqual(venda.situacao, "cancelado")
        self.assertEqual(self.variacao.estoque, 1)  # voltou
        self.assertEqual(metricas.resumo(metricas.pedidos_pagos(), metricas.vendas_pagas())["pedidos"], 1)
        url = f"/gestao/vendas/{venda.pk}/"
        resposta = self.client.post(url, {"acao": "situacao", "situacao": "pago"}, follow=True)
        self.assertContains(resposta, "Venda cancelada não pode ser alterada")

    def test_etiqueta_mostra_cpf_e_registra_acesso(self):
        self.entrar()
        venda = self.venda_correios()
        resposta = self.client.get(f"/gestao/vendas/{venda.pk}/etiqueta/")
        self.assertContains(resposta, "529.982.247-25")
        self.assertContains(resposta, "60000-000")
        self.assertContains(resposta, "Declaração de conteúdo")
        self.assertContains(resposta, "Endereço do remetente incompleto")
        self.assertEqual(resposta.context["peso_kg"], Decimal("0.05"))  # PESO_PADRAO_G (50 g)
        self.assertTrue(
            RegistroAuditoria.objects.filter(
                acao=RegistroAuditoria.Acao.ACESSO, objeto_id=str(self.cliente.pk), depois__campo="documento"
            ).exists()
        )


class LgpdVendasTests(BaseVendasPainel):
    def test_exportar_e_anonimizar(self):
        venda = self.venda_correios()
        dados = lgpd.exportar_dados(self.cliente)
        self.assertEqual(dados["compras"][0]["codigo"], venda.codigo)
        self.assertIn("Rua A", dados["compras"][0]["endereco"])
        lgpd.anonimizar(self.cliente)
        venda.refresh_from_db()
        self.assertEqual((venda.logradouro, venda.cep, venda.destinatario), ("", "", ""))
        self.assertEqual((venda.cidade, venda.uf, venda.total), ("Fortaleza", "CE", Decimal("81.60")))
