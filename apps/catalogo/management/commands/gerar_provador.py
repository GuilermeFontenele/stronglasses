"""Gera as imagens do provador virtual (óculos de frente, sem fundo) a partir das fotos de cada cor."""

from django.core.management.base import BaseCommand

from apps.catalogo import provador
from apps.catalogo.models import Variacao


class Command(BaseCommand):
    help = "Gera a imagem do provador das cores que ainda não têm (use --todas para refazer todas)."

    def add_arguments(self, parser):
        parser.add_argument("--todas", action="store_true", help="Refaz também as que já existem.")

    def handle(self, *args, **opcoes):
        geradas = sem_foto = 0
        for variacao in Variacao.objects.select_related("produto").order_by("produto__nome", "ordem"):
            if provador.atualizar(variacao, forcar=opcoes["todas"]):
                geradas += 1
            elif not variacao.imagem_provador:
                sem_foto += 1
        self.stdout.write(f"{geradas} imagem(ns) do provador gerada(s). {sem_foto} cor(es) sem foto de frente.")
