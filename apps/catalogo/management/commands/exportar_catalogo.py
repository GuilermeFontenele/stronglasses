from django.core.management.base import BaseCommand

from apps.catalogo.transferencia import exportar


class Command(BaseCommand):
    help = "Gera um .zip só com o catálogo (sem clientes, pedidos ou usuários) para o ambiente de testes."

    def handle(self, *args, **opcoes):
        destino = exportar()
        relativo = destino.relative_to(destino.parents[1])
        self.stdout.write(self.style.SUCCESS(f"Catálogo exportado: {destino}"))
        self.stdout.write(
            "Com o runserver e o cloudflared ligados, o servidor de testes baixa por:\n"
            f"  https://<seu-tunnel>.trycloudflare.com/media/{relativo.as_posix()}\n"
            "Apague o arquivo depois da importação."
        )
