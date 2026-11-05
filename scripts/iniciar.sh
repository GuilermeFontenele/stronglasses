#!/bin/sh
# Sobe a loja no servidor: aplica migrações e inicia o gunicorn.
set -e
python manage.py migrate --noinput
# Sem log de acesso: ele grava IP de cada visitante (dado pessoal, regra 3 do CLAUDE.md).
exec gunicorn config.wsgi \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers "${WEB_CONCURRENCY:-2}" \
    --timeout "${GUNICORN_TIMEOUT:-60}" \
    --forwarded-allow-ips "*"
