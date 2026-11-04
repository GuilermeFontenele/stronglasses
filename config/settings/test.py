"""Configurações para a suíte de testes (local e CI)."""

import os

from config.env import chave_derivada

os.environ.setdefault("DJANGO_SECRET_KEY", "teste-" + "y" * 50)
os.environ.setdefault("FIELD_ENCRYPTION_KEYS", chave_derivada("fernet", os.environ["DJANGO_SECRET_KEY"]))
os.environ.setdefault("FIELD_HASH_KEY", chave_derivada("hmac", os.environ["DJANGO_SECRET_KEY"]))

from .base import *

DEBUG = False
ALLOWED_HOSTS = ["testserver", "localhost"]

# Hash rápido só nos testes.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
