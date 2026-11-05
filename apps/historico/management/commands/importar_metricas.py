import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.historico.models import MetricaMensal, VisitasPorDimensao


def _decimal(valor):
    return None if valor in (None, "") else Decimal(str(valor)).quantize(Decimal("0.01"))


class Command(BaseCommand):
    help = "Carrega o arquivo de métricas (visitas, funil, vendas) exportado da Nuvemshop."

    def add_arguments(self, parser):
        parser.add_argument("arquivo", help="Caminho do metricas-nuvemshop.json")

    @transaction.atomic
    def handle(self, *args, arquivo, **options):
        caminho = Path(arquivo)
        if not caminho.is_file():
            raise CommandError(f"Arquivo não encontrado: {caminho}")
        dados = json.loads(caminho.read_text(encoding="utf-8"))

        for linha in dados.get("mensal", []):
            MetricaMensal.objects.update_or_create(
                mes=date.fromisoformat(linha["mes"]),
                defaults={
                    "visitas": int(linha.get("visitas") or 0),
                    "visualizacoes_produto": int(linha.get("visualizacoes_produto") or 0),
                    "carrinhos": int(linha.get("carrinhos") or 0),
                    "checkouts": int(linha.get("checkouts") or 0),
                    "vendas": int(linha.get("vendas") or 0),
                    "receita": _decimal(linha.get("receita")) or Decimal("0"),
                    "ticket_medio": _decimal(linha.get("ticket_medio")),
                    "conversao": _decimal(linha.get("conversao")),
                },
            )

        inicio = date.fromisoformat(dados["periodo"]["inicio"])
        fim = date.fromisoformat(dados["periodo"]["fim"])
        for dimensao, chave in (
            (VisitasPorDimensao.Dimensao.ORIGEM, "origens"),
            (VisitasPorDimensao.Dimensao.DISPOSITIVO, "dispositivos"),
        ):
            for linha in dados.get(chave, []):
                VisitasPorDimensao.objects.update_or_create(
                    dimensao=dimensao,
                    valor=linha["valor"][:80],
                    tipo=(linha.get("tipo") or "")[:20],
                    periodo_inicio=inicio,
                    periodo_fim=fim,
                    defaults={"visitas": int(linha.get("visitas") or 0)},
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"{len(dados.get('mensal', []))} meses, {len(dados.get('origens', []))} origens e "
                f"{len(dados.get('dispositivos', []))} dispositivos carregados."
            )
        )
