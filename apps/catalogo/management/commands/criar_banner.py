"""Cria um banner da home a partir de uma imagem na internet (ex.: o banner atual da Nuvemshop).

python manage.py criar_banner
python manage.py criar_banner --url https://.../imagem.webp --titulo "Promoção" --link /masculino/
"""

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError

from apps.catalogo.models import Banner
from apps.nuvemshop.imagens import ImagemInvalida, baixar_imagem

# Banner atual da loja na Nuvemshop (mapa do Brasil). Tenta a versão maior primeiro.
_BASE = (
    "https://dcdn-us.mitiendanube.com/stores/002/103/611/themes/new_linkedman/"
    "1-slide-1660698398522-8980499355-40a9ea63bd3edffd40f95b83d6c637051660698405"
)
URLS_PADRAO = [f"{_BASE}-2048-2048.webp", f"{_BASE}-1024-1024.webp", f"{_BASE}-480-0.webp"]
TITULO_PADRAO = "Strong Glasses: óculos entregues em todos os estados do Brasil"


class Command(BaseCommand):
    help = "Baixa uma imagem e cria um banner na home."

    def add_arguments(self, parser):
        parser.add_argument("--url", action="append", help="Endereço https da imagem (pode repetir).")
        parser.add_argument("--titulo", default=TITULO_PADRAO, help="Descrição da imagem.")
        parser.add_argument("--link", default="", help="Para onde o banner leva (ex.: /masculino/).")

    def handle(self, *args, **opcoes):
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

        banner = Banner(titulo=opcoes["titulo"], link=opcoes["link"])
        banner.imagem.save(f"banner.{extensao}", ContentFile(conteudo), save=False)
        try:
            banner.full_clean()
        except ValidationError as exc:
            banner.imagem.delete(save=False)
            raise CommandError(f"Banner inválido: {exc}") from exc
        banner.save()
        self.stdout.write(self.style.SUCCESS(f"Banner criado (#{banner.pk}). Edite em Catálogo > Banners."))
