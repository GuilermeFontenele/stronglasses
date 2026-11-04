"""Desenvolvimento local. Nunca use em produção."""

import os

# Valores apenas para rodar localmente sem configurar nada. Produção exige os reais.
os.environ.setdefault("DJANGO_SECRET_KEY", "dev-inseguro-troque-em-producao-" + "x" * 32)
os.environ.setdefault("FIELD_ENCRYPTION_KEYS", "ZGV2LWluc2VndXJvLW5hby11c2FyLWVtLXByb2QtMTI=")
os.environ.setdefault("FIELD_HASH_KEY", "dev-inseguro-hmac")

from .base import *

DEBUG = True
ALLOWED_HOSTS = ALLOWED_HOSTS or ["localhost", "127.0.0.1"]

# Em dev a CSP só reporta (facilita testar componentes); em prod ela bloqueia.
SECURE_CSP_REPORT_ONLY = SECURE_CSP
SECURE_CSP = {}
