"""Quem entra no painel: só a equipe (is_staff), com limite de tentativas de login."""

import hashlib
from functools import wraps
from urllib.parse import urlencode

from django.contrib.auth.views import redirect_to_login
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.cache import never_cache

from apps.core.middleware import ip_da_requisicao

MAXIMO_TENTATIVAS = 5
BLOQUEIO_SEGUNDOS = 15 * 60


def _chaves(request, usuario: str) -> list[str]:
    ip = ip_da_requisicao(request) or "?"
    nome = hashlib.sha256((usuario or "").strip().lower().encode()).hexdigest()[:16]  # sem usuário em claro no cache
    return [f"gestao:login:ip:{ip}", f"gestao:login:usuario:{nome}"]


def bloqueado(request, usuario: str) -> bool:
    return any((cache.get(chave) or 0) >= MAXIMO_TENTATIVAS for chave in _chaves(request, usuario))


def registrar_falha(request, usuario: str) -> None:
    for chave in _chaves(request, usuario):
        cache.add(chave, 0, BLOQUEIO_SEGUNDOS)
        try:
            cache.incr(chave)
        except ValueError:
            cache.set(chave, 1, BLOQUEIO_SEGUNDOS)


def limpar_falhas(request, usuario: str) -> None:
    cache.delete_many(_chaves(request, usuario))


def equipe(view=None, *, permissao: str | None = None):
    """Exige login de alguém da equipe; com `permissao`, também a permissão do Django."""

    def decorador(funcao):
        @wraps(funcao)
        def interna(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path(), reverse("gestao:entrar"))
            if not request.user.is_staff or (permissao and not request.user.has_perm(permissao)):
                raise PermissionDenied
            return funcao(request, *args, **kwargs)

        return never_cache(interna)

    return decorador(view) if view else decorador


def login_do_admin(request, extra_context=None):
    destino = request.GET.get("next") or reverse("admin:index")
    return redirect(f"{reverse('gestao:entrar')}?{urlencode({'next': destino})}")
