# Ambiente de testes (homologação)

Servidor sempre ligado para testar a loja sem depender do seu PC. Usa a mesma imagem
Docker da produção, com **banco só de catálogo** (nenhum cliente, pedido ou usuário).

## O que tem de diferente da loja real

- Faixa amarela "Ambiente de testes" no topo.
- `robots.txt` bloqueia tudo e toda resposta leva `X-Robots-Tag: noindex` (o Google não indexa).
- O botão de WhatsApp continua falando com o número real da loja.

## 1. Criar o serviço (Railway como exemplo)

A imagem roda em qualquer lugar que aceite Dockerfile (Railway, Render, Fly.io, VPS).
No Railway:

1. **New Project → Deploy from GitHub repo →** `GuilermeFontenele/stronglasses`.
2. No mesmo projeto: **New → Database → PostgreSQL**.
3. No serviço da loja, **Settings → Volumes → Add volume** montado em `/dados`.
4. **Settings → Networking → Generate domain** (algo como `stronglasses-teste.up.railway.app`).
5. **Settings → Healthcheck path:** `/saude/`.

## 2. Variáveis do serviço da loja

Gere as três chaves **no seu PC** (são diferentes das da produção e nunca vão para o git):

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"                                  # DJANGO_SECRET_KEY
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"      # FIELD_ENCRYPTION_KEYS
python -c "import secrets; print(secrets.token_urlsafe(48))"                                  # FIELD_HASH_KEY
```

| Variável | Valor |
|---|---|
| `DJANGO_SECRET_KEY` | (gerada acima) |
| `FIELD_ENCRYPTION_KEYS` | (gerada acima) |
| `FIELD_HASH_KEY` | (gerada acima) |
| `DJANGO_ALLOWED_HOSTS` | `stronglasses-teste.up.railway.app,healthcheck.railway.app` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `https://stronglasses-teste.up.railway.app` |
| `DJANGO_AMBIENTE` | `testes` |
| `DJANGO_BEHIND_PROXY` | `1` |
| `DJANGO_SERVIR_MEDIA` | `1` |
| `DJANGO_MEDIA_ROOT` | `/dados/media` |
| `DB_NAME` / `DB_USER` / `DB_PASSWORD` / `DB_HOST` / `DB_PORT` | referências do Postgres: `${{Postgres.PGDATABASE}}`, `${{Postgres.PGUSER}}`, `${{Postgres.PGPASSWORD}}`, `${{Postgres.PGHOST}}`, `${{Postgres.PGPORT}}` |
| `RAILWAY_RUN_UID` | `0` (só se aparecer erro de permissão ao gravar fotos no volume) |

Se o deploy falhar com erro de SSL no banco, adicione `DB_SSLMODE=disable` (a conexão é pela
rede privada do Railway).

## 3. Levar o catálogo do seu PC para o servidor

No seu PC (servidor local ligado):

```bash
python manage.py exportar_catalogo
cloudflared tunnel --url http://localhost:8080
```

O primeiro comando mostra o caminho do arquivo, algo como `/media/exportacao/catalogo-<código>.zip`.
O nome é aleatório e o arquivo só tem catálogo, fotos, banners, páginas e parâmetros.

No servidor (Railway: botão **⋯ → SSH** no serviço, ou `railway ssh`):

```bash
python manage.py importar_catalogo https://<seu-tunnel>.trycloudflare.com/media/exportacao/catalogo-<código>.zip
python manage.py createsuperuser
```

Depois **feche o tunnel** e apague o `.zip` da pasta `media/exportacao/` do seu PC.
Para o sócio, crie um usuário próprio no painel (nunca compartilhe o seu).

## 4. Atualizações

Cada `git push` no `main` faz o Railway montar e publicar de novo. As migrações rodam
sozinhas na subida (`scripts/iniciar.sh`). Para atualizar o catálogo, repita o passo 3.
