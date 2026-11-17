"""Checkout do site e acompanhamento do pedido (link secreto, sem login) + webhook do Mercado Pago."""

import json
import logging
import time
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csp import csp_override, csp_report_only_override
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.carrinho.carrinho import Carrinho
from apps.clientes import lgpd
from apps.clientes.models import Consentimento
from apps.core import limites
from apps.core.middleware import ip_da_requisicao
from apps.core.parametros import get_parametro
from apps.vendas.models import Pedido
from apps.vendas.servicos import EstoqueInsuficiente, calcular

from . import mercadopago, servicos
from .forms import CheckoutForm
from .mercadopago import ErroMercadoPago
from .models import Pagamento

logger = logging.getLogger(__name__)
CHAVE_FRETE = "checkout_frete"
CHAVE_ORIGEM = "origem"
CHAVE_PEDIDO = "ultimo_pedido"
# Cada pedido reserva estoque por alguns minutos: o limite impede esvaziar a loja com pedidos falsos.
MAXIMO_PEDIDOS_POR_HORA = 20

# Mercado Pago (Brick de cartão): SDK, campos seguros em iframe, antifraude e desafio 3DS do banco.
MP = ["https://*.mercadopago.com", "https://*.mercadolibre.com", "https://*.mlstatic.com", "https://*.mercadolivre.com"]


def _csp_mercadopago(politica: dict) -> dict:
    if not politica:
        return politica
    nova = {chave: list(valores) for chave, valores in politica.items()}
    nova["script-src"] = [*nova["script-src"], "https://sdk.mercadopago.com", *MP]
    # O Brick injeta <style> sem nonce; com nonce na lista, 'unsafe-inline' seria ignorado.
    nova["style-src"] = ["'self'", "'unsafe-inline'", *MP]
    nova["connect-src"] = [*nova["connect-src"], *MP]
    nova["img-src"] = [*nova["img-src"], *MP]
    nova["font-src"] = [*nova["font-src"], *MP]
    nova["frame-src"] = ["https:"]  # campos do cartão e desafio 3DS (domínio do banco)
    return nova


com_mercadopago = csp_override(_csp_mercadopago(settings.SECURE_CSP))
com_mercadopago_ro = csp_report_only_override(_csp_mercadopago(getattr(settings, "SECURE_CSP_REPORT_ONLY", {})))


def _pedido(token: str) -> Pedido:
    return get_object_or_404(Pedido.objects.select_related("cliente"), token_acesso=token, canal=Pedido.Canal.SITE)


def _totais(linhas) -> dict:
    subtotal = sum((linha.subtotal for linha in linhas), Decimal("0.00"))
    return {
        "subtotal": subtotal,
        "pix": calcular(subtotal, Decimal("0.00"), Decimal("0.00"), aplicar_pix=True),
    }


# ---------------------------------------------------------------- finalizar compra


@never_cache
def finalizar(request):
    carrinho = Carrinho(request)
    linhas = carrinho.linhas()
    if not linhas:
        messages.info(request, "Seu carrinho está vazio.")
        return redirect("carrinho:ver")
    if not mercadopago.configurado():
        messages.info(request, "O pagamento online ainda não está disponível. Finalize pelo WhatsApp.")
        return redirect("carrinho:ver")
    form = CheckoutForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        dados = form.cleaned_data
        frete = _opcao_escolhida(request, dados["cep"], linhas, dados["frete"])
        if frete is None:
            form.add_error(None, "Calcule o frete de novo e escolha uma opção.")
        else:
            base = f"{request.scheme}://{request.get_host()}"
            try:
                if limites.excedeu(f"pedidos:{ip_da_requisicao(request) or '?'}", MAXIMO_PEDIDOS_POR_HORA, 3600):
                    raise ValidationError("Muitos pedidos seguidos. Espere um pouco ou finalize pelo WhatsApp.")
                pedido = servicos.criar_pedido(linhas, dados, frete, request.session.get(CHAVE_ORIGEM), base)
            except EstoqueInsuficiente:
                messages.error(request, "Um dos óculos acabou de esgotar. Confira o carrinho.")
                return redirect("carrinho:ver")
            except ValidationError as erro:
                form.add_error(None, " ".join(erro.messages))
            else:
                carrinho.limpar()
                request.session.pop(CHAVE_FRETE, None)
                request.session[CHAVE_PEDIDO] = pedido.token_acesso  # para achar o pedido se a aba fechar
                if dados["novidades"] and pedido.cliente:
                    lgpd.registrar_consentimento(
                        pedido.cliente, Consentimento.Finalidade.MARKETING_EMAIL, Consentimento.Origem.CHECKOUT, request
                    )
                if dados["forma"] == Pedido.FormaPagamento.PIX:
                    try:
                        servicos.pagar_pix(pedido)
                    except ErroMercadoPago as erro:
                        messages.error(request, str(erro))
                    return redirect("pagamentos:pedido", token=pedido.token_acesso)
                return redirect("pagamentos:pagar", token=pedido.token_acesso)
    return render(
        request,
        "pagamentos/finalizar.html",
        {
            "form": form,
            "linhas": linhas,
            "totais": _totais(linhas),
            "parcelas": max(int(get_parametro("PARCELAS_SEM_JUROS", 1) or 1), 1),
            "pix_percentual": get_parametro("PIX_DESCONTO_PERCENTUAL", 0),
        },
    )


def _opcao_escolhida(request, cep: str, linhas, escolha: str) -> dict | None:
    """A opção vem da cotação guardada na sessão (feita no servidor) para o mesmo CEP e carrinho."""
    guardado = request.session.get(CHAVE_FRETE) or {}
    mesmo_carrinho = guardado.get("assinatura") == servicos.assinatura_do_carrinho(cep, linhas)
    opcoes = guardado.get("opcoes") if mesmo_carrinho else None
    if not opcoes or time.time() - guardado.get("quando", 0) > 30 * 60:
        opcoes = servicos.opcoes_de_frete(cep, linhas)
    return next((o for o in opcoes if o["id"] == escolha), None)


@require_POST
def frete(request):
    linhas = Carrinho(request).linhas()
    cep = request.POST.get("cep", "")
    if not linhas:
        return JsonResponse({"erro": "Seu carrinho está vazio."}, status=400)
    if len("".join(c for c in cep if c.isdigit())) != 8:
        return JsonResponse({"erro": "Informe o CEP com 8 números."}, status=400)
    if limites.excedeu(f"frete:{ip_da_requisicao(request) or '?'}", 40, 60):  # evita cotação em massa
        return JsonResponse({"erro": "Muitas cotações seguidas. Espere um minuto."}, status=429)
    opcoes = servicos.opcoes_de_frete(cep, linhas)
    request.session[CHAVE_FRETE] = {
        "assinatura": servicos.assinatura_do_carrinho(cep, linhas),
        "opcoes": opcoes,
        "quando": time.time(),
    }
    if not opcoes:
        erro = "Não encontramos entrega para esse CEP. Fale com a gente no WhatsApp."
        return JsonResponse({"erro": erro}, status=400)
    return JsonResponse(
        {
            "opcoes": [{k: o[k] for k in ("id", "nome", "preco", "prazo")} for o in opcoes],
            "endereco": servicos.endereco_do_cep(cep),
        }
    )


# ---------------------------------------------------------------- acompanhamento e pagamento


def _expirar_se_venceu(pedido: Pedido) -> Pedido:
    if pedido.situacao == Pedido.Situacao.PENDENTE and pedido.expira_em and pedido.expira_em < timezone.now():
        servicos.expirar(pedido)
        pedido.refresh_from_db()
    return pedido


def _conferir(pedido: Pedido) -> Pedido:
    """Consulta o Mercado Pago no máximo a cada 4 s por pedido (a tela consulta sozinha enquanto espera)."""
    if pedido.situacao == Pedido.Situacao.PENDENTE and cache.add(f"pedido-conferido:{pedido.pk}", 1, 4):
        pedido = servicos.atualizar_pedido(pedido)
    return _expirar_se_venceu(pedido)


@require_GET
@never_cache
def pedido(request, token):
    obj = _conferir(_pedido(token))
    pix = None
    if obj.situacao == Pedido.Situacao.PENDENTE and obj.forma_pagamento == Pedido.FormaPagamento.PIX:
        pix = obj.pagamentos.filter(metodo=Pagamento.Metodo.PIX, status=Pagamento.Status.PENDENTE).first()
    return render(
        request,
        "pagamentos/pedido.html",
        {
            "pedido": obj,
            "itens": list(obj.itens.all()),
            "pix": pix,
            "ultimo": obj.pagamentos.first(),
            "primeiro_nome": (obj.destinatario.split() or [""])[0],
            "pix_total": servicos.total_para(obj, Pedido.FormaPagamento.PIX)["total"],
        },
    )


@require_GET
@never_cache
def situacao(request, token):
    obj = _conferir(_pedido(token))
    return JsonResponse({"situacao": obj.situacao, "pago": obj.pago})


@require_POST
def gerar_pix(request, token):
    obj = _expirar_se_venceu(_pedido(token))
    try:
        obj = servicos.mudar_forma(obj, Pedido.FormaPagamento.PIX)
        servicos.pagar_pix(obj)
    except ErroMercadoPago as erro:
        messages.error(request, str(erro))
    return redirect("pagamentos:pedido", token=token)


@never_cache
@com_mercadopago
@com_mercadopago_ro
def pagar(request, token):
    obj = _expirar_se_venceu(_pedido(token))
    if obj.situacao != Pedido.Situacao.PENDENTE:
        return redirect("pagamentos:pedido", token=token)
    # Só mostra o valor no cartão; o pedido muda de forma quando o pagamento é enviado de fato.
    return render(
        request,
        "pagamentos/pagar.html",
        {
            "pedido": obj,
            "total_cartao": servicos.total_para(obj, Pedido.FormaPagamento.CREDITO)["total"],
            "chave_publica": settings.MERCADOPAGO_PUBLIC_KEY,
            "parcelas": max(int(get_parametro("PARCELAS_SEM_JUROS", 1) or 1), 1),
            "pix_total": servicos.total_para(obj, Pedido.FormaPagamento.PIX)["total"],
        },
    )


@require_POST
def cartao(request, token):
    obj = _pedido(token)
    try:
        formulario = json.loads(request.body.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"mensagem": "Dados inválidos."}, status=400)
    if not isinstance(formulario, dict):
        return JsonResponse({"mensagem": "Dados inválidos."}, status=400)
    try:
        pagamento = servicos.pagar_cartao(obj, formulario)
    except ErroMercadoPago as erro:
        return JsonResponse({"mensagem": str(erro)}, status=400)
    resposta = {"situacao": pagamento.status, "url": reverse("pagamentos:pedido", args=[token])}
    if pagamento.status == Pagamento.Status.RECUSADO:
        resposta["mensagem"] = servicos.mensagem_recusa(pagamento)
        return JsonResponse(resposta, status=402)
    return JsonResponse(resposta)


@require_POST
def refazer(request, token):
    """Pedido não pago: devolve os itens ao carrinho (e o estoque, cancelando o pendente)."""
    obj = _pedido(token)
    if (
        obj.situacao == Pedido.Situacao.PENDENTE
        and not obj.pagamentos.filter(status__in=[Pagamento.Status.APROVADO, Pagamento.Status.EM_ANALISE]).exists()
    ):
        obj = servicos.cancelar_pedido(obj)
    if obj.situacao != Pedido.Situacao.CANCELADO:
        return redirect("pagamentos:pedido", token=token)
    carrinho = Carrinho(request)
    for item in obj.itens.select_related("variacao", "variacao__produto"):
        if item.variacao and item.variacao.ativa and item.variacao.produto.ativo:
            carrinho.adicionar(item.variacao, item.quantidade)
    messages.info(request, "Os itens voltaram para o seu carrinho.")
    return redirect("carrinho:ver")


# ---------------------------------------------------------------- webhook


@csrf_exempt
@require_POST
def webhook(request):
    """Aviso do Mercado Pago. Confere a assinatura, busca a situação na API (fonte da verdade) e aplica."""
    if len(request.body) > 64 * 1024:
        return HttpResponse(status=413)
    try:
        corpo = json.loads(request.body.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        corpo = {}
    corpo = corpo if isinstance(corpo, dict) else {}
    data_id = request.GET.get("data.id") or str((corpo.get("data") or {}).get("id") or "")
    tipo = request.GET.get("type") or str(corpo.get("type") or "")
    if not mercadopago.assinatura_valida(
        request.headers.get("x-signature", ""), request.headers.get("x-request-id", ""), data_id, agora=time.time()
    ):
        logger.warning("Webhook do Mercado Pago com assinatura inválida")
        return HttpResponse(status=401)
    if tipo == "payment" and data_id:
        try:
            servicos.sincronizar(data_id)
        except ErroMercadoPago:
            return HttpResponse(status=503)  # o Mercado Pago tenta de novo
    return HttpResponse("ok")
