"""Download seguro das fotos dos produtos da Nuvemshop."""

import io
import urllib.parse
import urllib.request

from PIL import Image, UnidentifiedImageError

from apps.catalogo.models import TAMANHO_MAXIMO_IMAGEM

FORMATOS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}


class ImagemInvalida(Exception):
    pass


def baixar_imagem(url: str) -> tuple[bytes, str]:
    """Baixa a imagem e devolve (conteúdo, extensão). Recusa o que não for imagem real."""
    endereco = urllib.parse.urlsplit(url if not url.startswith("//") else "https:" + url)
    if endereco.scheme != "https" or not endereco.netloc:
        raise ImagemInvalida("URL de imagem precisa ser https.")
    requisicao = urllib.request.Request(  # noqa: S310 (https validado acima)
        endereco.geturl(), headers={"User-Agent": "StrongGlasses-Importador"}
    )
    with urllib.request.urlopen(requisicao, timeout=60) as resposta:  # noqa: S310 (https validado acima)
        conteudo = resposta.read(TAMANHO_MAXIMO_IMAGEM + 1)
    if len(conteudo) > TAMANHO_MAXIMO_IMAGEM:
        raise ImagemInvalida("Imagem maior que 5 MB.")
    return conteudo, validar_imagem(conteudo)


def validar_imagem(conteudo: bytes) -> str:
    try:
        with Image.open(io.BytesIO(conteudo)) as imagem:
            formato = imagem.format
            imagem.verify()
    except (UnidentifiedImageError, OSError, SyntaxError) as exc:
        raise ImagemInvalida("Arquivo não é uma imagem válida.") from exc
    if formato not in FORMATOS:
        raise ImagemInvalida(f"Formato {formato} não aceito.")
    return FORMATOS[formato]
