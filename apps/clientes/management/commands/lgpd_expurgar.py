from django.core.management.base import BaseCommand

from apps.clientes.lgpd import expurgar_dados_tecnicos


class Command(BaseCommand):
    help = "Remove IP e navegador de consentimentos antigos (rodar diariamente via agendador)."

    def add_arguments(self, parser):
        parser.add_argument("--dias", type=int, default=None, help="Padrão: LGPD_RETENCAO_IP_DIAS.")

    def handle(self, *args, dias=None, **options):
        total = expurgar_dados_tecnicos(dias)
        self.stdout.write(self.style.SUCCESS(f"{total} registro(s) expurgado(s)."))
