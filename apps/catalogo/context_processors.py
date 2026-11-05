from .vitrine import categorias_menu


def navegacao(request):
    return {"categorias_menu": categorias_menu()}
