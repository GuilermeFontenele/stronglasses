from urllib.parse import quote

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from apps.catalogo.models import Variacao
from apps.catalogo.templatetags.vitrine import brl
from apps.core.parametros import get_parametro

from .carrinho import MAXIMO_POR_ITEM, Carrinho


def _variacao(request):
    variacao_id = request.POST.get("variacao", "")
    if not variacao_id.isdigit():
        return None
    return get_object_or_404(
        Variacao.objects.select_related("produto", "armacao", "lente"),
        pk=int(variacao_id),
        ativa=True,
        produto__ativo=True,
    )


def _quantidade(request, padrao=1) -> int:
    valor = request.POST.get("quantidade", "")
    return min(int(valor), MAXIMO_POR_ITEM) if valor.isdigit() else padrao


def _mensagem_whatsapp(linhas, resumo) -> str:
    partes = ["Olá! Quero finalizar este pedido:"]
    for linha in linhas:
        partes.append(
            f"- {linha.quantidade}x {linha.variacao.produto.nome} ({linha.variacao.descricao_cor.lower()}) "
            f"{brl(linha.subtotal)}"
        )
    partes.append(f"Total: {brl(resumo['subtotal'])} ({brl(resumo['total_pix'])} no Pix)")
    return "\n".join(partes)


@require_GET
def ver(request):
    carrinho = Carrinho(request)
    linhas = carrinho.linhas()
    resumo = Carrinho.resumo(linhas)
    whatsapp = "".join(c for c in str(get_parametro("WHATSAPP_LOJA", "") or "") if c.isdigit())
    link_whatsapp = ""
    if linhas and whatsapp:
        link_whatsapp = f"https://wa.me/{whatsapp}?text={quote(_mensagem_whatsapp(linhas, resumo), safe='')}"
    return render(
        request,
        "carrinho/carrinho.html",
        {
            "linhas": linhas,
            "resumo": resumo,
            "link_whatsapp": link_whatsapp,
            "quantidades": range(1, MAXIMO_POR_ITEM + 1),
        },
    )


@require_POST
def adicionar(request):
    variacao = _variacao(request)
    if variacao is None:
        return redirect("carrinho:ver")
    entrou = Carrinho(request).adicionar(variacao, _quantidade(request))
    if entrou:
        messages.success(request, f"{variacao.produto.nome} foi para o carrinho.")
    elif variacao.estoque <= 0:
        messages.error(request, "Essa cor acabou de esgotar.")
    else:
        messages.info(request, "Você já tem a quantidade máxima disponível dessa cor no carrinho.")
    return redirect("carrinho:ver")


@require_POST
def atualizar(request):
    variacao = _variacao(request)
    if variacao is not None:
        Carrinho(request).definir(variacao, _quantidade(request, padrao=0))
    return redirect("carrinho:ver")


@require_POST
def remover(request):
    variacao_id = request.POST.get("variacao", "")
    if variacao_id.isdigit():
        Carrinho(request).remover(variacao_id)
    return redirect("carrinho:ver")
