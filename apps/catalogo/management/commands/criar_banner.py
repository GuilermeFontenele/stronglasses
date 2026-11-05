"""Cria um banner da home a partir de imagens no computador ou na internet.

python manage.py criar_banner --arquivo pc.webp --arquivo-celular celular.webp --substituir
python manage.py criar_banner --url https://.../imagem.webp --titulo "Promoção" --link /masculino/

--substituir desativa os banners que estavam no ar (não apaga nada).
"""

from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.catalogo.models import Banner
from apps.nuvemshop.imagens import ImagemInvalida, baixar_imagem, validar_imagem

# Banner atual da loja na Nuvemshop (mapa do Brasil). Tenta a versão maior primeiro.
_BASE = (
    "https://dcdn-us.mitiendanube.com/stores/002/103/611/themes/new_linkedman/"
    "1-slide-1660698398522-8980499355-40a9ea63bd3edffd40f95b83d6c637051660698405"
)
URLS_PADRAO = [f"{_BASE}-2048-2048.webp", f"{_BASE}-1024-1024.webp", f"{_BASE}-480-0.webp"]
TITULO_PADRAO = "Strong Glasses: óculos entregues em todos os estados do Brasil"


class Command(BaseCommand):
    help = "Cria um banner na home a partir de arquivos locais ou de uma URL."

    def add_arguments(self, parser):
        parser.add_argument("--arquivo", help="Imagem do computador (1920 x 800) salva na sua máquina.")
        parser.add_argument("--arquivo-celular", help="Imagem do celular (1080 x 1350) salva na sua máquina.")
        parser.add_argument("--substituir", action="store_true", help="Desativa os banners que estavam no ar.")
        parser.add_argument("--url", action="append", help="Endereço https da imagem (pode repetir).")
        parser.add_argument("--titulo", default=TITULO_PADRAO, help="Descrição da imagem.")
        parser.add_argument("--link", default="", help="Para onde o banner leva (ex.: /masculino/).")

    @staticmethod
    def _ler(caminho: str) -> tuple[bytes, str]:
        arquivo = Path(caminho)
        if not arquivo.is_file():
            raise CommandError(f"Arquivo não encontrado: {caminho}")
        conteudo = arquivo.read_bytes()
        try:
            return conteudo, validar_imagem(conteudo)
        except ImagemInvalida as exc:
            raise CommandError(f"{caminho}: {exc}") from exc

    def handle(self, *args, **opcoes):
        if opcoes["arquivo"]:
            conteudo, extensao = self._ler(opcoes["arquivo"])
            celular = self._ler(opcoes["arquivo_celular"]) if opcoes["arquivo_celular"] else None
            return self._criar(opcoes, conteudo, extensao, celular)
        urls = opcoes["url"] or URLS_PADRAO
        conteudo, extensao, erros = None, None, []
        for url in urls:
            try:
                conteudo, extensao = baixar_imagem(url)
                self.stdout.write(f"Imagem baixada: {url}")
                break
            except (ImagemInvalida, OSError) as exc:
                erros.append(f"{url}: {exc}")
        if conteudo is None:
            raise CommandError("Não consegui baixar a imagem.\n" + "\n".join(erros))
        return self._criar(opcoes, conteudo, extensao, None)

    def _criar(self, opcoes, conteudo, extensao, celular):
        banner = Banner(titulo=opcoes["titulo"], link=opcoes["link"])
        banner.imagem.save(f"banner.{extensao}", ContentFile(conteudo), save=False)
        if celular:
            banner.imagem_mobile.save(f"banner-celular.{celular[1]}", ContentFile(celular[0]), save=False)
        try:
            if celular:
                banner.full_clean()  # confere também as proporções
            else:
                # Sem versão de celular (ex.: importado da Nuvemshop); ela entra depois pelo painel.
                banner.clean_fields(exclude=["imagem_mobile"])
        except ValidationError as exc:
            banner.imagem.delete(save=False)
            if celular:
                banner.imagem_mobile.delete(save=False)
            raise CommandError(f"Banner inválido: {exc}") from exc
        with transaction.atomic():
            if opcoes["substituir"]:
                desativados = Banner.objects.filter(ativo=True).update(ativo=False)
                self.stdout.write(f"{desativados} banner(s) antigo(s) desativado(s).")
            banner.save()
        self.stdout.write(self.style.SUCCESS(f"Banner criado (#{banner.pk}). Edite em Catálogo > Banners."))
