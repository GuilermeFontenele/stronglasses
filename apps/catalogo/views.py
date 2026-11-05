from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET

from .models import Categoria, Produto
from .vitrine import produtos_visiveis

POR_PAGINA = 24


@require_GET
def home(request):
    produtos = produtos_visiveis()
    destaques = list(produtos.filter(destaque=True)[:8]) or list(produtos.order_by("-criado_em")[:8])
    novidades = list(produtos.order_by("-criado_em")[:8])
    acessorios = list(produtos.filter(tipo=Produto.Tipo.ACESSORIO)[:8])
    return render(
        request,
        "core/home.html",
        {"destaques": destaques, "novidades": novidades, "acessorios": acessorios},
    )


@require_GET
def produto(request, slug):
    item = get_object_or_404(produtos_visiveis(), slug=slug)
    variacoes = item.variacoes_ativas
    selecionada = None
    escolha = request.GET.get("cor", "")
    if escolha.isdigit():
        selecionada = next((v for v in variacoes if v.pk == int(escolha)), None)
    if selecionada is None:
        selecionada = next((v for v in variacoes if v.disponivel), variacoes[0] if variacoes else None)

    fotos = item.fotos
    if selecionada:
        da_cor = [f for f in fotos if f.variacao_id == selecionada.pk]
        fotos = da_cor + [f for f in fotos if f.variacao_id != selecionada.pk]
    preco = selecionada.preco_final if selecionada else item.preco
    return render(
        request,
        "catalogo/produto.html",
        {
            "produto": item,
            "variacoes": variacoes,
            "selecionada": selecionada,
            "fotos": fotos,
            "preco": preco,
            "comparativo": item.preco_comparativo
            if item.preco_comparativo and item.preco_comparativo > preco
            else None,
        },
    )


@require_GET
def categoria(request, slug):
    cat = Categoria.objects.filter(slug=slug, ativa=True).first()
    if cat is None:
        raise Http404  # o middleware de redirecionamentos ainda pode tratar esta URL
    produtos = produtos_visiveis().filter(categorias=cat)
    publico = request.GET.get("publico", "")
    if publico in Produto.Publico.values:
        produtos = produtos.filter(publico=publico)
    ordem = {"menor-preco": "preco", "maior-preco": "-preco", "novidades": "-criado_em"}.get(
        request.GET.get("ordem", ""), "nome"
    )
    pagina = Paginator(produtos.order_by(ordem), POR_PAGINA).get_page(request.GET.get("pagina"))
    return render(
        request,
        "catalogo/categoria.html",
        {
            "categoria": cat,
            "pagina": pagina,
            "publicos": Produto.Publico.choices,
            "publico": publico,
            "ordem": request.GET.get("ordem", ""),
        },
    )
