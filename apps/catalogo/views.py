import json

from django.core.paginator import Paginator
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_GET

from apps.core.parametros import get_parametro

from .models import Banner, Categoria, Produto
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
        {
            "banners": list(Banner.no_ar()[:5]),
            "oculos_entregues": int(get_parametro("OCULOS_ENTREGUES", 0) or 0),
            "destaques": destaques,
            "novidades": novidades,
            "acessorios": acessorios,
        },
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
    url = request.build_absolute_uri(item.get_absolute_url())
    mensagem = f"Olá! Tenho interesse no {item.nome}"
    if selecionada:
        mensagem += f" ({selecionada.descricao_cor.lower()})"
    mensagem += f": {url}"
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
            "url_canonica": url,
            "mensagem_whatsapp": mensagem,
            "dados_estruturados": _dados_estruturados(request, item, variacoes, fotos, preco, url),
        },
    )


def _json_seguro(dados) -> str:
    """JSON dentro de <script>: escapa <, > e & para não fechar a tag."""
    texto = json.dumps(dados, ensure_ascii=False)
    texto = texto.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return mark_safe(texto)  # noqa: S308 (escapado acima)


def _dados_estruturados(request, item, variacoes, fotos, preco, url):
    """Schema.org Product: preço e disponibilidade aparecem no resultado do Google."""
    disponivel = any(v.disponivel for v in variacoes)
    dados = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": item.nome,
        "url": url,
        "brand": {"@type": "Brand", "name": "Strong Glasses"},
        "image": [request.build_absolute_uri(f.imagem.url) for f in fotos[:5]],
        "offers": {
            "@type": "Offer",
            "priceCurrency": "BRL",
            "price": str(preco),
            "availability": "https://schema.org/" + ("InStock" if disponivel else "OutOfStock"),
            "url": url,
        },
    }
    if item.descricao:
        dados["description"] = item.descricao[:500]
    if variacoes:
        dados["sku"] = variacoes[0].sku
    return _json_seguro(dados)


@require_GET
def robots_txt(request):
    linhas = ["User-agent: *", "Disallow: /saude/", f"Sitemap: {request.build_absolute_uri('/sitemap.xml')}", ""]
    return HttpResponse("\n".join(linhas), content_type="text/plain; charset=utf-8")


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
