"""Contadores de tentativas (login, cotações, pedidos). Em produção ficam no banco: valem para todos os processos."""

from django.core.cache import caches


def _cache():
    return caches["limites"]


def contar(chave: str, janela_segundos: int) -> int:
    """Soma 1 ao contador da chave (que zera sozinho depois da janela) e devolve o total."""
    cache = _cache()
    cache.add(chave, 0, janela_segundos)
    try:
        return cache.incr(chave)
    except ValueError:  # expirou entre o add e o incr
        cache.set(chave, 1, janela_segundos)
        return 1


def excedeu(chave: str, maximo: int, janela_segundos: int) -> bool:
    """Conta esta tentativa e diz se passou do máximo dentro da janela."""
    return contar(chave, janela_segundos) > maximo


def total(chave: str) -> int:
    return _cache().get(chave) or 0


def zerar(*chaves: str) -> None:
    _cache().delete_many(chaves)
