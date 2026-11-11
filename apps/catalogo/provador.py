"""Imagem do provador virtual: a foto de frente do óculos sem o fundo e sem as hastes.

As fotos da loja têm fundo claro e liso. O fundo é removido por preenchimento a partir das bordas
(o que é claro mas fica "dentro" da armação, como plaquetas e reflexos, continua). Depois corta as
hastes, que na foto de frente aparecem como linhas finas saindo das laterais.
"""

from io import BytesIO

from PIL import Image, ImageChops, ImageDraw, ImageFilter

LARGURA_MAXIMA = 640
SENTINELA = (1, 254, 3)  # cor que não existe nas fotos: marca o que é fundo
TOLERANCIA_FUNDO = 48
DENSIDADE_ARMACAO = 0.22  # coluna com menos que isso (relativo à mais cheia) é haste, não frente


def _sem_fundo(foto: Image.Image) -> Image.Image:
    """Alfa: 0 no fundo (ligado às bordas), 255 no óculos."""
    if foto.mode in ("RGBA", "LA") and foto.getchannel("A").getextrema()[0] < 250:
        return foto.getchannel("A")  # já veio com fundo transparente
    rgb = foto.convert("RGB")
    marcada = rgb.copy()
    largura, altura = marcada.size
    passo = max(4, min(largura, altura) // 40)
    bordas = [(x, 0) for x in range(0, largura, passo)] + [(x, altura - 1) for x in range(0, largura, passo)]
    bordas += [(0, y) for y in range(0, altura, passo)] + [(largura - 1, y) for y in range(0, altura, passo)]
    for ponto in bordas:
        cor = marcada.getpixel(ponto)
        if cor != SENTINELA and min(cor) >= 200:  # só semeia em fundo claro
            ImageDraw.floodfill(marcada, ponto, SENTINELA, thresh=TOLERANCIA_FUNDO)
    diferenca = ImageChops.difference(marcada, Image.new("RGB", marcada.size, SENTINELA)).convert("L")
    alfa = diferenca.point(lambda v: 255 if v > 0 else 0)
    # Tira o halo claro da borda e suaviza o recorte.
    return alfa.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.8))


def _colunas_da_frente(alfa: Image.Image) -> tuple[int, int] | None:
    perfil = list(alfa.resize((alfa.width, 1), Image.Resampling.BOX).getdata())
    maximo = max(perfil, default=0)
    if maximo == 0:
        return None
    cheias = [x for x, v in enumerate(perfil) if v >= maximo * DENSIDADE_ARMACAO]
    return cheias[0], cheias[-1] + 1


def gerar(arquivo) -> bytes | None:
    """PNG com fundo transparente, recortado na frente da armação. None se não achar o óculos."""
    with Image.open(arquivo) as original:
        foto = original.copy()
    foto.thumbnail((1024, 1024))
    alfa = _sem_fundo(foto)
    colunas = _colunas_da_frente(alfa)
    if not colunas:
        return None
    x0, x1 = colunas
    faixa = alfa.crop((x0, 0, x1, alfa.height))
    caixa = faixa.getbbox()
    if not caixa:
        return None
    y0, y1 = caixa[1], caixa[3]
    if (x1 - x0) < foto.width * 0.25 or (y1 - y0) < 8:
        return None  # não parece um óculos de frente
    recorte = foto.convert("RGBA").crop((x0, y0, x1, y1))
    recorte.putalpha(alfa.crop((x0, y0, x1, y1)))
    if recorte.width > LARGURA_MAXIMA:
        recorte = recorte.resize(
            (LARGURA_MAXIMA, round(recorte.height * LARGURA_MAXIMA / recorte.width)), Image.Resampling.LANCZOS
        )
    saida = BytesIO()
    recorte.save(saida, "PNG", optimize=True)
    return saida.getvalue()


def foto_de_origem(variacao):
    """Primeira foto da cor; se o produto só tem uma cor, a primeira foto do produto."""
    fotos = variacao.produto.imagens.order_by("ordem", "id")
    foto = fotos.filter(variacao=variacao).first()
    if foto is None and variacao.produto.variacoes.count() == 1:
        foto = fotos.first()
    return foto


def atualizar(variacao, *, forcar: bool = False) -> bool:
    """Gera e salva a imagem do provador da cor. True se gerou."""
    from django.core.files.base import ContentFile

    if variacao.imagem_provador and not forcar:
        return False
    foto = foto_de_origem(variacao)
    if foto is None or not foto.imagem:
        return False
    try:
        with foto.imagem.open("rb") as arquivo:
            png = gerar(arquivo)
    except (OSError, ValueError):
        return False
    if not png:
        return False
    if variacao.imagem_provador:
        variacao.imagem_provador.delete(save=False)
    variacao.imagem_provador.save(f"{variacao.sku or variacao.pk}.png", ContentFile(png), save=False)
    variacao.save(update_fields=["imagem_provador"])
    return True


def preencher(produto) -> int:
    """Gera para as cores do produto que ainda não têm imagem do provador."""
    return sum(atualizar(v) for v in produto.variacoes.all())
