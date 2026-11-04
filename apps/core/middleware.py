"""Disponibiliza o usuário e o IP da requisição atual para a auditoria.

Usa contextvars (seguro com threads e async), em vez de variáveis globais.
"""

from contextvars import ContextVar

_usuario_atual: ContextVar = ContextVar("usuario_atual", default=None)
_ip_atual: ContextVar = ContextVar("ip_atual", default=None)


def get_usuario_atual():
    usuario = _usuario_atual.get()
    if usuario is not None and getattr(usuario, "is_authenticated", False):
        return usuario
    return None


def get_ip_atual():
    return _ip_atual.get()


def ip_da_requisicao(request) -> str | None:
    """IP do cliente. Só confia em X-Forwarded-For se o proxy estiver configurado."""
    from django.conf import settings

    if getattr(settings, "SECURE_PROXY_SSL_HEADER", None):
        encaminhado = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if encaminhado:
            # O último IP é o adicionado pelo nosso proxy (o primeiro pode ser forjado).
            return encaminhado.split(",")[-1].strip() or None
    return request.META.get("REMOTE_ADDR")


class UsuarioAtualMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token_usuario = _usuario_atual.set(getattr(request, "user", None))
        token_ip = _ip_atual.set(ip_da_requisicao(request))
        try:
            return self.get_response(request)
        finally:
            _usuario_atual.reset(token_usuario)
            _ip_atual.reset(token_ip)
