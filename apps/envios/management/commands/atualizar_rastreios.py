"""Atualiza rastreio e situação das etiquetas em andamento. Agende a cada poucas horas na hospedagem."""

from django.core.management.base import BaseCommand

from apps.envios import melhorenvio
from apps.envios.melhorenvio import ErroMelhorEnvio, MelhorEnvio, NaoConectado
from apps.envios.models import Envio
from apps.envios.servicos import atualizar_rastreio


class Command(BaseCommand):
    help = "Busca no Melhor Envio o rastreio das etiquetas geradas/postadas e atualiza as vendas."

    def handle(self, *args, **opcoes):
        try:
            api = MelhorEnvio()
        except NaoConectado as erro:
            self.stderr.write(str(erro))
            return
        pendentes = Envio.objects.filter(
            ambiente=melhorenvio.ambiente(), status__in=[Envio.Status.GERADO, Envio.Status.POSTADO]
        )
        atualizados = falhas = 0
        for envio in pendentes:
            try:
                atualizar_rastreio(envio, api=api)
                atualizados += 1
            except ErroMelhorEnvio:
                falhas += 1
        self.stdout.write(f"{atualizados} etiqueta(s) conferida(s), {falhas} com erro.")
