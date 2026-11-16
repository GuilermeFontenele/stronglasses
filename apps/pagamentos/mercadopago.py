"""Cliente mínimo da API de pagamentos do Mercado Pago (Checkout Transparente), sem dependências externas.

- Pix e cartão por POST /v1/payments, sempre com X-Idempotency-Key (clique duplo não cobra duas vezes).
- O cartão nunca passa pelo servidor: o navegador (Brick do Mercado Pago) gera um token de uso único.
- Webhook: assinatura HMAC-SHA256 em `x-signature` e confirmação da situação na própria API.
- Nada de dados pessoais em log.
"""

import hashlib
import hmac
import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)

API = "https://api.mercadopago.com"
TEMPO_LIMITE = 25
TOLERANCIA_WEBHOOK_S = 15 * 60


class ErroMercadoPago(Exception):
    """Mensagem que pode ir para a tela (sem dado pessoal)."""

    def __init__(self, mensagem: str, status: int | None = None):
        self.status = status
        super().__init__(mensagem)


def configurado() -> bool:
    return bool(settings.MERCADOPAGO_ACCESS_TOKEN and settings.MERCADOPAGO_PUBLIC_KEY)


def _requisicao(metodo: str, caminho: str, corpo: dict | None = None, chave_idempotencia: str | None = None) -> dict:
    if not settings.MERCADOPAGO_ACCESS_TOKEN:
        raise ErroMercadoPago("Pagamento online indisponível no momento.")
    cabecalhos = {
        "Accept": "application/json",
        "Authorization": f"Bearer {settings.MERCADOPAGO_ACCESS_TOKEN}",
        "User-Agent": "Strong Glasses",
    }
    dados = None
    if corpo is not None:
        dados = json.dumps(corpo).encode("utf-8")
        cabecalhos["Content-Type"] = "application/json"
    if chave_idempotencia:
        cabecalhos["X-Idempotency-Key"] = chave_idempotencia
    pedido = urllib.request.Request(f"{API}{caminho}", data=dados, headers=cabecalhos, method=metodo)  # noqa: S310
    try:
        with urllib.request.urlopen(pedido, timeout=TEMPO_LIMITE) as resposta:  # noqa: S310 (URL fixa https)
            return json.loads(resposta.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as erro:
        logger.warning("Mercado Pago respondeu %s em %s %s", erro.code, metodo, urllib.parse.urlsplit(caminho).path)
        try:
            detalhe = json.loads(erro.read().decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            detalhe = {}
        mensagem = "O Mercado Pago não aceitou o pagamento. Confira os dados e tente de novo."
        if erro.code in (401, 403):
            mensagem = "Pagamento online indisponível no momento (credenciais da loja)."
        elif isinstance(detalhe, dict) and detalhe.get("message") and erro.code == 400:
            mensagem = f"O Mercado Pago recusou: {str(detalhe['message'])[:200]}"
        raise ErroMercadoPago(mensagem, erro.code) from erro
    except (urllib.error.URLError, TimeoutError) as erro:
        logger.warning("Mercado Pago fora do ar ou sem rede: %s", type(erro).__name__)
        raise ErroMercadoPago("Não conseguimos falar com o Mercado Pago agora. Tente de novo em instantes.") from erro


def criar_pagamento(corpo: dict, chave_idempotencia: str) -> dict:
    return _requisicao("POST", "/v1/payments", corpo, chave_idempotencia)


def consultar(pagamento_id: str) -> dict:
    return _requisicao("GET", f"/v1/payments/{urllib.parse.quote(str(pagamento_id))}")


def assinatura_valida(cabecalho: str, request_id: str, data_id: str, agora: float | None = None) -> bool:
    """Confere o `x-signature` (ts=...,v1=...) do webhook com a assinatura secreta do aplicativo."""
    segredo = settings.MERCADOPAGO_WEBHOOK_SECRET
    if not segredo or not cabecalho:
        return False
    partes = dict(p.strip().split("=", 1) for p in cabecalho.split(",") if "=" in p)
    ts, v1 = partes.get("ts", ""), partes.get("v1", "")
    if not ts.isdigit() or not v1:
        return False
    if agora is not None:
        segundos = int(ts) / 1000 if len(ts) > 11 else int(ts)
        if abs(agora - segundos) > TOLERANCIA_WEBHOOK_S:
            return False
    manifesto = ""
    if data_id:
        manifesto += f"id:{data_id.lower() if data_id.isalnum() else data_id};"
    if request_id:
        manifesto += f"request-id:{request_id};"
    manifesto += f"ts:{ts};"
    esperado = hmac.new(segredo.encode(), manifesto.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperado, v1)
