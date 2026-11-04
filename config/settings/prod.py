"""Produção. Tudo sensível vem do ambiente; o boot falha se faltar algo crítico."""

from django.core.exceptions import ImproperlyConfigured

from config.env import env_bool, env_int, env_str

from .base import *

DEBUG = False

if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("Defina DJANGO_ALLOWED_HOSTS em produção.")
if DATABASES["default"]["ENGINE"] != "django.db.backends.postgresql":
    raise ImproperlyConfigured("Produção exige Postgres (defina DB_NAME e demais DB_*).")
if not FIELD_ENCRYPTION_KEYS or not FIELD_HASH_KEY:
    raise ImproperlyConfigured("Defina FIELD_ENCRYPTION_KEYS e FIELD_HASH_KEY em produção.")

DATABASES["default"]["OPTIONS"]["sslmode"] = env_str("DB_SSLMODE", "require")

# HTTPS em tudo
SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_NAME = "__Host-sessionid"
CSRF_COOKIE_NAME = "__Host-csrftoken"

# HSTS: comece com valor baixo e aumente para 1 ano depois de validar o HTTPS.
SECURE_HSTS_SECONDS = env_int("DJANGO_HSTS_SECONDS", 3600)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("DJANGO_HSTS_INCLUDE_SUBDOMAINS", True)
SECURE_HSTS_PRELOAD = env_bool("DJANGO_HSTS_PRELOAD", False)
if not SECURE_HSTS_PRELOAD:
    # Preload só depois de confirmar HTTPS em todos os subdomínios.
    SILENCED_SYSTEM_CHECKS = ["security.W021"]

# Só ative atrás de um proxy confiável que sobrescreve esse cabeçalho.
if env_bool("DJANGO_BEHIND_PROXY", False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
