"""Criptografia de campos e hash para busca (LGPD: proteção de dados em repouso)."""

import hashlib
import hmac
import unicodedata
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


@lru_cache(maxsize=1)
def _cifrador(chaves: tuple[str, ...]) -> MultiFernet:
    if not chaves:
        raise ImproperlyConfigured("FIELD_ENCRYPTION_KEYS não configurada.")
    return MultiFernet([Fernet(chave.encode()) for chave in chaves])


def cifrador() -> MultiFernet:
    return _cifrador(tuple(settings.FIELD_ENCRYPTION_KEYS))


def cifrar(texto: str) -> str:
    return cifrador().encrypt(texto.encode("utf-8")).decode("ascii")


def decifrar(token: str) -> str:
    try:
        return cifrador().decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Não foi possível decifrar o campo (chave incorreta ou dado corrompido).") from exc


def normalizar(valor: str) -> str:
    """Remove pontuação/espaços e acentos para comparar documentos e contatos."""
    sem_acento = unicodedata.normalize("NFKD", valor).encode("ascii", "ignore").decode("ascii")
    return "".join(ch for ch in sem_acento.lower() if ch.isalnum() or ch in "@.+_-")


def hash_busca(valor: str) -> str:
    """HMAC-SHA256 determinístico: permite achar um registro sem guardar o dado em claro."""
    chave = settings.FIELD_HASH_KEY
    if not chave:
        raise ImproperlyConfigured("FIELD_HASH_KEY não configurada.")
    return hmac.new(chave.encode(), normalizar(valor).encode(), hashlib.sha256).hexdigest()
