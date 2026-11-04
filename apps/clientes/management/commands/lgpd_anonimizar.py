from django.core.management.base import BaseCommand, CommandError

from apps.clientes.lgpd import anonimizar

from ._util import busca_cliente


class Command(BaseCommand):
    help = "Anonimiza um titular (pedido de eliminação da LGPD). Irreversível."

    def add_arguments(self, parser):
        parser.add_argument("--uuid")
        parser.add_argument("--email")
        parser.add_argument("--confirmar", action="store_true", help="Obrigatório: confirma a ação irreversível.")

    def handle(self, *args, uuid=None, email=None, confirmar=False, **options):
        cliente = busca_cliente(uuid, email)
        if cliente.anonimizado_em:
            raise CommandError("Este cliente já foi anonimizado.")
        if not confirmar:
            raise CommandError(f"Isso apagará os dados de {cliente.uuid}. Repita com --confirmar.")
        anonimizar(cliente)
        self.stdout.write(self.style.SUCCESS(f"Cliente {cliente.uuid} anonimizado."))
