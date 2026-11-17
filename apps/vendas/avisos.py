"""Avisos por e-mail ao comprador de pedidos do site: recebido, pagamento aprovado e enviado.

Texto simples de propósito (chega em qualquer caixa de entrada e não cai em spam por causa de HTML).
Falha no envio nunca derruba a compra: fica só um aviso no log, sem dados pessoais.
"""

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse

from apps.core.parametros import get_parametros

from .models import Pedido

logger = logging.getLogger(__name__)

ASSUNTOS = {
    "recebido": "Recebemos seu pedido {codigo}",
    "pago": "Pagamento aprovado: pedido {codigo}",
    "enviado": "Seu pedido {codigo} foi enviado",
}


def _pode_enviar() -> bool:
    # Sem servidor de e-mail configurado em produção, o Django "enviaria" para o log: seria dado pessoal em log.
    return settings.DEBUG or not settings.EMAIL_BACKEND.endswith("console.EmailBackend")


def link_do_pedido(pedido: Pedido, base_url: str = "") -> str:
    base = (settings.SITE_URL or base_url or "").rstrip("/")
    if not base or not pedido.token_acesso:
        return ""
    return base + reverse("pagamentos:pedido", args=[pedido.token_acesso])


def avisar(pedido: Pedido, evento: str, base_url: str = "") -> bool:
    """Envia o e-mail do evento. True se enviou."""
    if evento not in ASSUNTOS or pedido.canal != Pedido.Canal.SITE or not pedido.email or not _pode_enviar():
        return False
    loja = get_parametros("WHATSAPP_LOJA", "EMAIL_LOJA")
    contexto = {
        "pedido": pedido,
        "itens": list(pedido.itens.all()),
        "primeiro_nome": (pedido.destinatario.split() or [""])[0],
        "link": link_do_pedido(pedido, base_url),
        "whatsapp": "".join(c for c in str(loja["WHATSAPP_LOJA"] or "") if c.isdigit()),
    }
    try:
        send_mail(
            ASSUNTOS[evento].format(codigo=pedido.codigo),
            render_to_string(f"emails/pedido_{evento}.txt", contexto),
            None,
            [pedido.email],
        )
    except Exception:  # noqa: BLE001 (qualquer falha de envio: a compra segue)
        logger.warning('Não foi possível enviar o e-mail "%s" do pedido %s', evento, pedido.pk)
        return False
    return True
