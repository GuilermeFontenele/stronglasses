#!/usr/bin/env bash
# Atualiza o código e sobe o site local: bash scripts/rodar.sh
set -e
cd "$(dirname "$0")/.."
git pull --ff-only
source .venv/Scripts/activate 2>/dev/null || source .venv/bin/activate
pip install -q -r requirements/dev.txt
python manage.py migrate
python manage.py runserver
