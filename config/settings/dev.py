"""Desenvolvimento local. Nunca use em produção."""

import os

from config.env import chave_derivada

# Valores apenas para rodar localmente sem configurar nada. Produção exige os reais.
os.environ.setdefault("DJANGO_SECRET_KEY", "dev-inseguro-troque-em-producao-" + "x" * 32)
os.environ.setdefault("FIELD_ENCRYPTION_KEYS", chave_derivada("fernet", os.environ["DJANGO_SECRET_KEY"]))
os.environ.setdefault("FIELD_HASH_KEY", chave_derivada("hmac", os.environ["DJANGO_SECRET_KEY"]))

from .base import *

DEBUG = True
ALLOWED_HOSTS = ALLOWED_HOSTS or ["localhost", "127.0.0.1"]

# Em dev a CSP só reporta (facilita testar componentes); em prod ela bloqueia.
SECURE_CSP_REPORT_ONLY = SECURE_CSP
SECURE_CSP = {}
