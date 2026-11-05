# Imagem da loja para homologação e produção (Railway, Render, Fly.io ou VPS).
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_SETTINGS_MODULE=config.settings.prod \
    PORT=8000

WORKDIR /app

RUN useradd --create-home --uid 1000 loja

COPY requirements/ requirements/
RUN pip install -r requirements/base.txt

COPY --chown=loja:loja . .

# Arquivos estáticos entram na imagem. Os valores abaixo só existem durante o build
# (prod.py exige configuração completa até para o collectstatic) e não ficam na imagem final.
RUN DJANGO_ALLOWED_HOSTS=build DB_NAME=build \
    DJANGO_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(64))')" \
    FIELD_ENCRYPTION_KEYS="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')" \
    FIELD_HASH_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')" \
    python manage.py collectstatic --noinput \
    && mkdir -p /app/media && chown -R loja:loja /app/media /app/staticfiles

USER loja
EXPOSE 8000
CMD ["sh", "scripts/iniciar.sh"]
