from django.core.management.base import BaseCommand, CommandError

from apps.catalogo.transferencia import TransferenciaInvalida, importar


class Command(BaseCommand):
    help = "Importa o .zip gerado por exportar_catalogo (caminho local ou endereço https)."

    def add_arguments(self, parser):
        parser.add_argument("origem", help="Caminho do .zip ou https://.../catalogo-xxxx.zip")

    def handle(self, *args, **opcoes):
        try:
            resultado = importar(opcoes["origem"])
        except (TransferenciaInvalida, OSError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            self.style.SUCCESS(f"Importados {resultado['registros']} registros e {resultado['arquivos']} arquivos.")
        )
