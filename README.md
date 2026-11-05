# Strong Glasses

Loja virtual da Strong Glasses, em Django 6 + Postgres.

## Rodando localmente

Requisitos: Python 3.12+ (Postgres é opcional no desenvolvimento: sem `DB_NAME`, usa SQLite).

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate   |   Linux/Mac: source .venv/bin/activate
pip install -r requirements/dev.txt
copy .env.example .env               # Linux/Mac: cp .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

O painel fica em `http://localhost:8000/painel/` (configurável por `DJANGO_ADMIN_URL`).

Para o Claude gastar menos tokens no projeto, rode uma vez `scripts/setup-graphify.ps1`
(ou `.sh`) e depois `/graphify .` no Claude Code. Detalhes em `CLAUDE.md`.

## Testes e qualidade

```bash
DJANGO_SETTINGS_MODULE=config.settings.test python manage.py test
ruff check . && ruff format --check .
```

O CI (GitHub Actions) roda em todo push: lint, testes em Postgres, verificação de
migrations, `check --deploy` com as configurações de produção, `pip-audit` e `gitleaks`.

## Estrutura

| Pasta | Conteúdo |
|---|---|
| `config/` | settings por ambiente, URLs, WSGI/ASGI |
| `apps/core/` | auditoria, parâmetros da loja, criptografia, validadores, health check |
| `apps/clientes/` | clientes, consentimentos e direitos do titular (LGPD) |
| `apps/catalogo/` | categorias, produtos, variações (armação + lente), imagens |
| `apps/historico/` | pedidos e métricas importados da Nuvemshop |
| `apps/nuvemshop/` | importação da Nuvemshop (`docs/IMPORTACAO.md`) |
| `docs/` | `LGPD.md` (inventário de dados), `IMPORTACAO.md` |

Segurança: veja `SECURITY.md`. Privacidade: veja `docs/LGPD.md`.
