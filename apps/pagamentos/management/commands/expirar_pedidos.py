"""Cancela pedidos do site não pagos no prazo e devolve o estoque. Agende a cada 10 minutos."""

from django.core.management.base import BaseCommand

from apps.pagamentos.servicos import expirar_pendentes


class Command(BaseCommand):
    help = "Cancela pedidos do site que passaram do prazo de pagamento (confere o Mercado Pago antes)."

    def handle(self, *args, **opcoes):
        self.stdout.write(f"{expirar_pendentes()} pedido(s) cancelado(s) por falta de pagamento.")
