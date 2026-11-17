import json
import unicodedata
from functools import cache

from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.paginator import Paginator
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils.safestring import mark_safe
from django.views.decorators.csp import csp_override, csp_report_only_override
from django.views.decorators.http import require_GET

from apps.core.models import Pagina
from apps.core.parametros import get_parametro

from .models import Banner, Categoria, Produto
from .vitrine import categorias_menu, produtos_visiveis

POR_PAGINA = 24
WASM = "'wasm-unsafe-eval'"


def _com_wasm(politica: dict) -> dict:
    """A política da loja + WebAssembly (só na página do produto, para o provador virtual)."""
    if not politica:
        return politica
    nova = {chave: list(valores) for chave, valores in politica.items()}
    nova["script-src"] = [*nova.get("script-src", []), WASM]
    return nova


@cache
def provador_instalado() -> bool:
    """Os arquivos do MediaPipe existem? (manage.py baixar_provador)"""
    return bool(finders.find("vendor/mediapipe/face_landmarker.task"))


@require_GET
def home(request):
    produtos = produtos_visiveis()
    destaques = list(produtos.filter(destaque=True)[:12]) or list(produtos.order_by("-criado_em")[:12])
    # Uma fileira por categoria do menu (estilo New Era), com "Ver mais" para a página da categoria.
    fileiras = []
    for categoria_menu in categorias_menu()[:8]:
        itens = list(produtos.filter(categorias=categoria_menu).order_by("-destaque", "-criado_em")[:12])
        if itens:
            fileiras.append({"categoria": categoria_menu, "produtos": itens})
    return render(
        request,
        "core/home.html",
        {
            "banners": list(Banner.no_ar()[:6]),
            "oculos_entregues": int(get_parametro("OCULOS_ENTREGUES", 0) or 0),
            "destaques": destaques,
            "fileiras": fileiras,
        },
    )


@require_GET
@csp_override(_com_wasm(settings.SECURE_CSP))
@csp_report_only_override(_com_wasm(getattr(settings, "SECURE_CSP_REPORT_ONLY", {})))
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
    provador = []
    if provador_instalado():
        provador = [
            {"id": v.pk, "cor": v.descricao_cor, "src": v.imagem_provador.url} for v in variacoes if v.imagem_provador
        ]
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
            "quantidades": range(1, min(selecionada.estoque, 10) + 1) if selecionada else range(0),
            "url_canonica": url,
            "mensagem_whatsapp": mensagem,
            "dados_estruturados": _dados_estruturados(request, item, variacoes, fotos, preco, url),
            "provador": provador,
            "relacionados": _relacionados(item),
        },
    )


def _relacionados(item, quantidade: int = 8) -> list:
    """Outros produtos das mesmas categorias (primeiro os destaques), para quem ainda está escolhendo."""
    categorias = list(item.categorias.values_list("pk", flat=True))
    if not categorias:
        return []
    candidatos = produtos_visiveis().filter(categorias__in=categorias).exclude(pk=item.pk)
    return [p for p in candidatos.order_by("-destaque", "nome")[: quantidade * 2] if p.variacoes_ativas][:quantidade]


def _sem_acento(texto: str) -> str:
    decomposto = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in decomposto if not unicodedata.combining(c)).lower()


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
    if settings.AMBIENTE != "producao":
        return HttpResponse("User-agent: *\nDisallow: /\n", content_type="text/plain; charset=utf-8")
    linhas = ["User-agent: *", "Disallow: /saude/", f"Sitemap: {request.build_absolute_uri('/sitemap.xml')}", ""]
    return HttpResponse("\n".join(linhas), content_type="text/plain; charset=utf-8")


@require_GET
def categoria(request, slug):
    cat = Categoria.objects.filter(slug=slug, ativa=True).first()
    if cat is None:
        # Mesmo formato de URL das páginas da Nuvemshop (/trocas-e-devolucoes/).
        pagina = Pagina.objects.filter(slug=slug, publicada=True).first()
        if pagina is None:
            raise Http404  # o middleware de redirecionamentos ainda pode tratar esta URL
        return render(request, "core/pagina.html", {"pagina": pagina})
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


@require_GET
def busca(request):
    termo = " ".join(request.GET.get("q", "").split())[:80]
    resultados = []
    if len(termo) >= 2:
        # A loja tem poucas centenas de produtos: comparar em Python deixa a busca igual em qualquer banco,
        # ignora acentos ("oculos" acha "Óculos") e não repete produto.
        palavras = [_sem_acento(p) for p in termo.split()[:5]]
        for produto in produtos_visiveis().prefetch_related("categorias").order_by("-destaque", "nome"):
            texto = _sem_acento(
                " ".join(
                    [
                        produto.nome,
                        produto.descricao,
                        *(c.nome for c in produto.categorias.all()),
                        *(v.descricao_cor for v in produto.variacoes_ativas),
                        *(v.sku for v in produto.variacoes_ativas),
                    ]
                )
            )
            if all(palavra in texto for palavra in palavras):
                resultados.append(produto)
        resultados = resultados[:48]
    return render(request, "catalogo/busca.html", {"termo": termo, "resultados": resultados})
