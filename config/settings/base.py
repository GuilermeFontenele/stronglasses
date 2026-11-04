"""Configurações comuns a todos os ambientes.

Os arquivos dev.py, prod.py e test.py herdam daqui. Segredos e valores que
mudam por ambiente vêm SEMPRE de variáveis de ambiente (ver .env.example).
"""

from pathlib import Path

from django.utils.csp import CSP

from config.env import env_bool, env_int, env_list, env_str, load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")

# ---------------------------------------------------------------------------
# Núcleo
# ---------------------------------------------------------------------------
SECRET_KEY = env_str("DJANGO_SECRET_KEY", required=True)
DEBUG = False
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    # Apps da loja
    "apps.core",
    "apps.clientes",
    "apps.catalogo",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.core.middleware.UsuarioAtualMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django.middleware.csp.ContentSecurityPolicyMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "django.template.context_processors.csp",
            ],
        },
    },
]

# ---------------------------------------------------------------------------
# Banco de dados
# Postgres quando DB_NAME estiver definido; SQLite só como conveniência local.
# prod.py exige Postgres.
# ---------------------------------------------------------------------------
if env_str("DB_NAME"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env_str("DB_NAME"),
            "USER": env_str("DB_USER"),
            "PASSWORD": env_str("DB_PASSWORD"),
            "HOST": env_str("DB_HOST", "localhost"),
            "PORT": env_str("DB_PORT", "5432"),
            "CONN_MAX_AGE": env_int("DB_CONN_MAX_AGE", 60),
            "CONN_HEALTH_CHECKS": True,
            "OPTIONS": {"sslmode": env_str("DB_SSLMODE", "prefer")},
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# ---------------------------------------------------------------------------
# Autenticação e senhas
# ---------------------------------------------------------------------------
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# URL do painel administrativo vem do ambiente, para não ficar no padrão /admin/.
ADMIN_URL = env_str("DJANGO_ADMIN_URL", "painel/").strip("/") + "/"

# ---------------------------------------------------------------------------
# Sessão, cookies e cabeçalhos de segurança
# ---------------------------------------------------------------------------
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = env_int("DJANGO_SESSION_AGE", 60 * 60 * 8)  # 8 horas
CSRF_COOKIE_HTTPONLY = True  # o front envia o token via cabeçalho lido do template
CSRF_COOKIE_SAMESITE = "Lax"

X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

# Content Security Policy (nativa do Django 6). Scripts e estilos inline só com
# nonce ({{ csp_nonce }}). Integrações externas (ex.: SDK do Mercado Pago) entram
# por override na view do checkout, nunca liberando o site inteiro.
SECURE_CSP = {
    "default-src": [CSP.SELF],
    "script-src": [CSP.SELF, CSP.NONCE],
    "style-src": [CSP.SELF, CSP.NONCE],
    # Atributos style="" (usados pelo admin do Django) são de baixo risco; tags
    # <style> e <script> continuam exigindo nonce.
    "style-src-attr": [CSP.UNSAFE_INLINE],
    "img-src": [CSP.SELF, "data:"],
    "font-src": [CSP.SELF],
    "connect-src": [CSP.SELF],
    "media-src": [CSP.SELF],
    "frame-src": [CSP.NONE],
    "frame-ancestors": [CSP.NONE],
    "object-src": [CSP.NONE],
    "base-uri": [CSP.SELF],
    "form-action": [CSP.SELF],
}

# Limites de upload (protege contra requisições gigantes)
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 2000
FILE_UPLOAD_PERMISSIONS = 0o640

# ---------------------------------------------------------------------------
# Criptografia de campos sensíveis (LGPD)
# FIELD_ENCRYPTION_KEYS: chaves Fernet separadas por vírgula; a primeira cifra,
# as demais só decifram (permite rotação). FIELD_HASH_KEY: chave do HMAC usado
# para buscar documentos sem guardá-los em claro.
# ---------------------------------------------------------------------------
FIELD_ENCRYPTION_KEYS = env_list("FIELD_ENCRYPTION_KEYS")
FIELD_HASH_KEY = env_str("FIELD_HASH_KEY")

# ---------------------------------------------------------------------------
# LGPD
# ---------------------------------------------------------------------------
LGPD_VERSAO_POLITICA = env_str("LGPD_VERSAO_POLITICA", "2026-11")
# Dias que IP/user-agent de consentimentos são guardados (Marco Civil: mín. 6 meses)
LGPD_RETENCAO_IP_DIAS = env_int("LGPD_RETENCAO_IP_DIAS", 180)
LGPD_CONTATO_ENCARREGADO = env_str("LGPD_CONTATO_ENCARREGADO", "privacidade@stronglasses.com.br")
SECURITY_CONTATO = env_str("SECURITY_CONTATO", "seguranca@stronglasses.com.br")

# ---------------------------------------------------------------------------
# Internacionalização
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Fortaleza"
USE_I18N = True
USE_TZ = True  # datas gravadas em UTC; webhooks de pagamento chegam com fuso

# ---------------------------------------------------------------------------
# Arquivos estáticos e mídia
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "media/"
MEDIA_ROOT = Path(env_str("DJANGO_MEDIA_ROOT", str(BASE_DIR / "media")))

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# E-mail (credenciais só por ambiente)
# ---------------------------------------------------------------------------
EMAIL_BACKEND = env_str("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env_str("EMAIL_HOST")
EMAIL_PORT = env_int("EMAIL_PORT", 587)
EMAIL_HOST_USER = env_str("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = env_str("EMAIL_HOST_PASSWORD")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
DEFAULT_FROM_EMAIL = env_str("DEFAULT_FROM_EMAIL", "Strong Glasses <nao-responda@stronglasses.com.br>")
SERVER_EMAIL = DEFAULT_FROM_EMAIL
ADMINS = env_list("DJANGO_ADMINS")

# ---------------------------------------------------------------------------
# Logs: nada de dados pessoais, corpos de requisição ou segredos.
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "mascara_dados_pessoais": {"()": "apps.core.logging.MascaraDadosPessoaisFilter"},
    },
    "formatters": {
        "padrao": {"format": "{asctime} {levelname} {name} {message}", "style": "{"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "padrao",
            "filters": ["mascara_dados_pessoais"],
        },
    },
    "root": {"handlers": ["console"], "level": env_str("DJANGO_LOG_LEVEL", "INFO")},
    "loggers": {
        "django.security": {"handlers": ["console"], "level": "WARNING", "propagate": False},
    },
}
