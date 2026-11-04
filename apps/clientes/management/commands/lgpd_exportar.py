import json

from django.core.management.base import BaseCommand

from apps.clientes.lgpd import exportar_dados

from ._util import busca_cliente


class Command(BaseCommand):
    help = "Exporta em JSON todos os dados de um titular (pedido de acesso/portabilidade da LGPD)."

    def add_arguments(self, parser):
        parser.add_argument("--uuid")
        parser.add_argument("--email")

    def handle(self, *args, uuid=None, email=None, **options):
        cliente = busca_cliente(uuid, email)
        self.stdout.write(json.dumps(exportar_dados(cliente), ensure_ascii=False, indent=2))
