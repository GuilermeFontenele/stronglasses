import json
import tempfile
from datetime import date
from decimal import Decimal
from io import StringIO
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.historico.models import MetricaMensal, PedidoHistorico, VisitasPorDimensao

METRICAS = {
    "periodo": {"inicio": "2024-12-01", "fim": "2026-11-05"},
    "mensal": [
        {
            "mes": "2025-08-01",
            "visitas": 222,
            "visualizacoes_produto": 110,
            "carrinhos": 18,
            "checkouts": 10,
            "vendas": 7,
            "receita": "1093.63",
            "ticket_medio": "156.23",
            "conversao": "3.15",
        },
        {"mes": "2025-04-01", "visitas": 231, "vendas": 0, "receita": "0", "ticket_medio": None, "conversao": "0"},
    ],
    "origens": [{"valor": "instagram", "tipo": "organic", "visitas": 168}],
    "dispositivos": [{"valor": "Celular", "tipo": "", "visitas": 3520}],
}


class MetricasTests(TestCase):
    def test_importar_metricas_idempotente(self):
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / "metricas.json"
            arquivo.write_text(json.dumps(METRICAS), encoding="utf-8")
            call_command("importar_metricas", str(arquivo), stdout=StringIO())
            call_command("importar_metricas", str(arquivo), stdout=StringIO())
        agosto = MetricaMensal.objects.get(mes=date(2025, 8, 1))
        self.assertEqual((agosto.vendas, agosto.receita, agosto.conversao), (7, Decimal("1093.63"), Decimal("3.15")))
        self.assertIsNone(MetricaMensal.objects.get(mes=date(2025, 4, 1)).ticket_medio)
        self.assertEqual(MetricaMensal.objects.count(), 2)
        self.assertEqual(VisitasPorDimensao.objects.count(), 2)


class PainelTests(TestCase):
    def setUp(self):
        dono = get_user_model().objects.create_superuser("dono", "dono@exemplo.com", "s" * 16)
        self.client.force_login(dono)
        momento = timezone.now()
        PedidoHistorico.objects.create(
            nuvemshop_id=1,
            numero=101,
            realizado_em=momento,
            status="closed",
            status_pagamento="paid",
            total=Decimal("100.00"),
        )
        PedidoHistorico.objects.create(
            nuvemshop_id=2,
            numero=102,
            realizado_em=momento,
            status="cancelled",
            status_pagamento="paid",
            total=Decimal("999.00"),
        )

    def test_lista_mostra_faturamento_pago_por_ano(self):
        resposta = self.client.get("/painel/historico/pedidohistorico/")
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Faturamento pago por ano")
        linhas = resposta.context["faturamento_por_ano"]
        self.assertEqual(linhas[0]["total"], Decimal("100.00"))  # cancelado não conta

    def test_paginas_carregam_e_sao_somente_leitura(self):
        for url in (
            "/painel/historico/metricamensal/",
            "/painel/historico/visitaspordimensao/",
            f"/painel/historico/pedidohistorico/{PedidoHistorico.objects.first().pk}/change/",
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.get("/painel/historico/pedidohistorico/add/").status_code, 403)
