from django.core.management.base import BaseCommand, CommandError

from apps.nuvemshop.api import ErroNuvemshop, trocar_codigo_por_token


class Command(BaseCommand):
    help = "Troca o código recebido ao instalar o app da Nuvemshop pelo token de acesso."

    def add_arguments(self, parser):
        parser.add_argument("--codigo", required=True, help="Valor do parâmetro ?code= da URL (vale 5 minutos).")

    def handle(self, *args, codigo, **options):
        try:
            dados = trocar_codigo_por_token(codigo)
        except ErroNuvemshop as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS("Token gerado. Cole estas duas linhas no seu .env (nunca no git):\n"))
        self.stdout.write(f"NUVEMSHOP_STORE_ID={dados.get('user_id') or dados.get('store_id')}")
        self.stdout.write(f"NUVEMSHOP_ACCESS_TOKEN={dados['access_token']}")
        self.stdout.write(f"\nPermissões concedidas: {dados.get('scope', '?')}")
