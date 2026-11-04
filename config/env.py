"""Leitura de configuração por variáveis de ambiente.

Nenhum segredo fica no código. Em desenvolvimento, um arquivo `.env` na raiz
(nunca versionado) é carregado sem sobrescrever variáveis já definidas.
"""

import base64
import hashlib
import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

_TRUE = {"1", "true", "yes", "on", "sim"}
_FALSE = {"0", "false", "no", "off", "nao", "não", ""}


def load_dotenv(path: Path) -> None:
    """Carrega KEY=VALUE de um arquivo .env simples, sem sobrescrever o ambiente."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if value == "":
            continue  # linha vazia do .env.example não deve "apagar" um padrão
        os.environ.setdefault(key, value)


def chave_derivada(finalidade: str, segredo: str) -> str:
    """Chave Fernet determinística derivada de outro segredo. Só para dev/teste:
    evita deixar chaves fixas no repositório. Produção usa chaves próprias."""
    digest = hashlib.sha256(f"{finalidade}:{segredo}".encode()).digest()
    return base64.urlsafe_b64encode(digest).decode()


def env_str(name: str, default: str | None = None, *, required: bool = False) -> str:
    value = os.environ.get(name)
    if value is None or value == "":
        if required:
            raise ImproperlyConfigured(f"Variável de ambiente obrigatória ausente: {name}")
        return default if default is not None else ""
    return value


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in _TRUE:
        return True
    if normalized in _FALSE:
        return False
    raise ImproperlyConfigured(f"Valor booleano inválido em {name}: {value!r}")


def env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ImproperlyConfigured(f"Valor inteiro inválido em {name}: {value!r}") from exc


def env_list(name: str, default: list[str] | None = None) -> list[str]:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return list(default or [])
    return [item.strip() for item in value.split(",") if item.strip()]
