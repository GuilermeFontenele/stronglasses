# Segurança

## Reportar uma vulnerabilidade

Envie para o contato em `/.well-known/security.txt` (padrão: seguranca@stronglasses.com.br).
Não abra issue pública com detalhes da falha.

## Controles implementados

**Segredos e configuração**
- Nenhum segredo no repositório; tudo por variável de ambiente (`.env.example`).
- Produção não sobe sem `DJANGO_SECRET_KEY`, `ALLOWED_HOSTS`, Postgres e chaves de criptografia.
- `gitleaks` no CI barra segredos commitados (inclusive no histórico).

**Transporte e navegador**
- HTTPS obrigatório, HSTS (comece com 1 hora e suba para 1 ano após validar), cookies `Secure`,
  `HttpOnly`, `SameSite=Lax` e prefixo `__Host-`.
- Content Security Policy nativa do Django 6: scripts e estilos só do próprio domínio ou com nonce;
  `frame-ancestors 'none'`, `object-src 'none'`.
- `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy` restritiva, `Cross-Origin-Opener-Policy`.

**Autenticação**
- Senhas com Argon2, mínimo de 12 caracteres.
- Painel fora de `/admin/` (`DJANGO_ADMIN_URL`), sessão de 8 horas.

**Dados**
- CPF/CNPJ criptografados (Fernet, com rotação de chave) e buscáveis só por HMAC.
- Trilha de auditoria imutável para tudo que muda pelo painel, além de exportações e anonimizações.
- Logs com máscara de e-mail, CPF, CNPJ e telefone.
- Uploads com extensão e tamanho validados e nome de arquivo aleatório.
- Banco com TLS (`sslmode=require`) em produção.

**Cadeia de dependências**
- Poucas dependências; `pip-audit` no CI e Dependabot semanal.

## Pendências conhecidas (próximas etapas)

- [ ] 2FA para o painel (ex.: django-otp) e limite de tentativas de login.
- [ ] Rate limit em formulários públicos (popup, checkout, cupom).
- [ ] Validação de assinatura dos webhooks do Mercado Pago (quando o pagamento entrar).
- [ ] Backups automáticos do banco, criptografados, com teste de restauração.
- [ ] Monitoramento de erros sem dados pessoais (ex.: Sentry com `send_default_pii=False`).
- [ ] Lockfile com hashes (`pip-compile --generate-hashes`).

## Checklist antes de publicar

- [ ] `python manage.py check --deploy` sem avisos com as variáveis reais.
- [ ] Chaves geradas só para produção (nunca reutilizar as de dev).
- [ ] HSTS aumentado para 31536000 depois de uma semana estável.
- [ ] Superusuário com senha forte e 2FA.
