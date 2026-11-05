from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.nuvemshop.api import ErroNuvemshop, NuvemshopAPI
from apps.nuvemshop.importador import ETAPAS, Importador


class _Simulacao(Exception):
    pass


class Command(BaseCommand):
    help = "Importa categorias, produtos (com fotos), clientes, pedidos e cupons da Nuvemshop."

    def add_arguments(self, parser):
        parser.add_argument(
            "--etapas",
            default=",".join(ETAPAS),
            help=f"Quais etapas rodar, separadas por vírgula. Padrão: {','.join(ETAPAS)}",
        )
        parser.add_argument("--sem-imagens", action="store_true", help="Não baixa as fotos (mais rápido).")
        parser.add_argument(
            "--simular", action="store_true", help="Lê tudo e mostra o relatório, mas não grava nada no banco."
        )
        parser.add_argument(
            "--pasta",
            default=str(Path(settings.BASE_DIR) / "importacao"),
            help="Onde salvar relatório e cupons (fora do git).",
        )

    def handle(self, *args, etapas, sem_imagens, simular, pasta, **options):
        escolhidas = [e.strip() for e in etapas.split(",") if e.strip()]
        invalidas = set(escolhidas) - set(ETAPAS)
        if invalidas:
            raise CommandError(f"Etapas desconhecidas: {', '.join(sorted(invalidas))}")

        pasta = Path(pasta)
        importador = Importador(
            NuvemshopAPI.das_configuracoes(),
            baixar_imagens=not (sem_imagens or simular),
            pasta_saida=pasta,
        )
        try:
            if simular:
                try:
                    with transaction.atomic():
                        importador.executar(escolhidas)
                        raise _Simulacao
                except _Simulacao:
                    self.stdout.write(self.style.WARNING("Simulação: nada foi gravado."))
            else:
                importador.executar(escolhidas)
        except ErroNuvemshop as exc:
            raise CommandError(str(exc)) from exc

        relatorio = importador.relatorio.em_markdown()
        pasta.mkdir(parents=True, exist_ok=True)
        arquivo = pasta / f"relatorio-{timezone.localtime():%Y%m%d-%H%M}.md"
        arquivo.write_text(relatorio, encoding="utf-8")
        self.stdout.write(relatorio)
        self.stdout.write(self.style.SUCCESS(f"\nRelatório salvo em {arquivo}"))
