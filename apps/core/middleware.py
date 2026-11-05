"""Disponibiliza o usuário e o IP da requisição atual para a auditoria.

Usa contextvars (seguro com threads e async), em vez de variáveis globais.
"""

from contextvars import ContextVar

from django.conf import settings

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


class RedirecionamentoMiddleware:
    """Quando uma página não existe (404), procura um redirecionamento cadastrado."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        resposta = self.get_response(request)
        if resposta.status_code != 404:
            return resposta

        from django.db.models import F
        from django.http import HttpResponsePermanentRedirect, HttpResponseRedirect

        from .models import Redirecionamento

        caminho = Redirecionamento.normalizar(request.path)
        candidatos = {caminho, caminho.rstrip("/") or "/", caminho.rstrip("/") + "/"}
        regra = Redirecionamento.objects.filter(origem__in=candidatos, ativo=True).first()
        if regra is None:
            return resposta
        Redirecionamento.objects.filter(pk=regra.pk).update(acessos=F("acessos") + 1)
        destino = regra.destino
        if request.META.get("QUERY_STRING") and "?" not in destino:
            destino = f"{destino}?{request.META['QUERY_STRING']}"
        classe = HttpResponsePermanentRedirect if regra.permanente else HttpResponseRedirect
        return classe(destino)


class AmbienteTestesMiddleware:
    """Ambiente de testes nunca aparece no Google (evita conteúdo duplicado com a loja real)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if settings.AMBIENTE != "producao":
            response["X-Robots-Tag"] = "noindex, nofollow"
        return response
