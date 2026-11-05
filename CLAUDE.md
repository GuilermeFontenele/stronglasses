# Strong Glasses: instruções para o Claude

Loja virtual da Strong Glasses (óculos de sol e armações), em Django 6.

## Economia de contexto (Graphify)

- Se existir `graphify-out/GRAPH_REPORT.md`, leia-o **antes** de explorar o código.
- Para entender relações entre módulos, prefira `/graphify query "..."`,
  `/graphify path "A" "B"` e `/graphify explain "X"` a abrir arquivos um por um.
- Se o grafo não existir ou estiver desatualizado: `/graphify .` (primeira vez)
  ou `/graphify . --update`.
- Configuração inicial: `scripts/setup-graphify.ps1` (Windows) ou `scripts/setup-graphify.sh`.

## Stack e estrutura

- Django 6 + Postgres, templates do Django + HTMX/Alpine (sem SPA).
- `config/settings/{base,dev,test,prod}.py`: tudo sensível vem do ambiente (`.env.example`).
- `apps/core`: `AuditModel` (auditoria automática), `Parametro` (configurações da loja),
  `RegistroAuditoria` (trilha imutável), `Redirecionamento` (301 em 404; troca de slug de produto cria um
  automaticamente), criptografia de campos, validadores BR.
- `apps/clientes`: `Cliente`, `Endereco`, `Consentimento` e os direitos do titular (`lgpd.py`).
- `apps/catalogo`: `Produto` → `Variacao` (armação + lente, SKU, estoque), imagens, seletor de cor.
- `apps/historico`: pedidos e métricas da Nuvemshop (somente leitura; faturamento por ano para o MEI).
- `apps/nuvemshop`: importação via API (`importar_nuvemshop`, `nuvemshop_token`). Ver `docs/IMPORTACAO.md`.

## Regras do projeto (não negociáveis)

1. **Segredos e dados de clientes nunca no git.** Use `config.env`; nada de senha, token ou chave em arquivo
   versionado. O repositório é público: `importacao/`, relatórios, métricas e dumps ficam fora do git.
2. **LGPD.** Colete o mínimo. Documento (CPF/CNPJ) só com `EncryptedTextField` + hash para busca.
   Dado pessoal novo? Atualize `docs/LGPD.md` (finalidade, base legal, retenção) e `lgpd.exportar_dados`.
3. **Nada de dado pessoal em logs.** O filtro mascara o óbvio, mas não conte com ele.
4. **CSP estrita.** Sem `<script>`/`<style>` inline sem `nonce="{{ csp_nonce }}"`; sem `style=""` no front
   da loja. Domínio externo só via `csp_override` na view que precisa (ex.: checkout).
5. **Dinheiro** em `DecimalField`; valores de pedido calculados **sempre no servidor**.
6. **Webhooks** de pagamento: validar assinatura, ser idempotente e confirmar o status na API do provedor.
7. Models novos herdam de `AuditModel`; admins usam `AuditoriaAdminMixin`.
8. Toda mudança vem com teste. CI: ruff, testes em Postgres, `check --deploy`, pip-audit e gitleaks.

## Comandos

```bash
python manage.py test                      # usa config.settings.dev por padrão; CI usa test
DJANGO_SETTINGS_MODULE=config.settings.test python manage.py test
ruff check . && ruff format .
python manage.py lgpd_exportar --email fulano@exemplo.com
python manage.py lgpd_anonimizar --uuid <uuid> --confirmar
python manage.py lgpd_expurgar             # agendar diariamente
```

## Decisões de negócio já tomadas

- MEI: nota fiscal só para PJ (hotéis), emitida fora do sistema e anexada ao pedido.
- Pagamento: Mercado Pago (checkout transparente + Pix via API). Pix sempre com desconto
  (`PIX_DESCONTO_PERCENTUAL`), aplicado por último, sem incidir sobre o frete.
- Ordem do cálculo: preço → promoção → cupom (se acumulativo) → Pix → frete.
- Todo pedido guarda a origem (canal, ref, cupom, UTMs) para afiliação futura.
- URLs de produto iguais às da Nuvemshop (`/produtos/<slug>/`) para preservar SEO.
