"""Leitura de parâmetros da loja com cache simples."""

from django.core.cache import cache
from django.db import connection, transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Parametro

_PREFIXO = "parametro:"
_AUSENTE = object()


def get_parametro(chave: str, padrao=None):
    em_cache = cache.get(_PREFIXO + chave, _AUSENTE)
    if em_cache is not _AUSENTE:
        return em_cache
    try:
        valor = Parametro.objects.get(pk=chave).valor_tipado()
    except Parametro.DoesNotExist:
        return padrao
    # Dentro de uma transação o valor pode ainda ser desfeito: não guarda no cache.
    if not connection.in_atomic_block:
        cache.set(_PREFIXO + chave, valor, timeout=300)
    return valor


@receiver([post_save, post_delete], sender=Parametro)
def _limpa_cache(sender, instance, **kwargs):
    chave = _PREFIXO + instance.pk
    cache.delete(chave)
    transaction.on_commit(lambda: cache.delete(chave))
