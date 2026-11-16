# Pagamentos: Pix e cartão pelo Mercado Pago

Checkout no próprio site (`/finalizar/`): dados, entrega (motoboy em Fortaleza + transportadoras do Melhor Envio)
e pagamento. Código em `apps/pagamentos/`.

## Configurar

1. Em <https://www.mercadopago.com.br/developers/panel/app>, crie um aplicativo (Checkout Transparente / pagamentos online).
2. Copie as **credenciais de teste** (Public Key e Access Token) para o `.env`:
   ```
   MERCADOPAGO_ACCESS_TOKEN=...
   MERCADOPAGO_PUBLIC_KEY=...
   ```
3. Em **Webhooks**, cadastre `https://SEU-DOMINIO/pagamentos/mercadopago/webhook/`, evento **Pagamentos**, e copie a
   **assinatura secreta** para `MERCADOPAGO_WEBHOOK_SECRET`. Preencha `SITE_URL` com o endereço público (https).
   Sem webhook (no computador), a página do pedido consulta o Mercado Pago sozinha a cada poucos segundos.
4. Na conta do Mercado Pago, configure o **parcelamento sem juros** (até 3x) para a loja absorver os juros.
5. Para produção, troque pelas credenciais de produção.

## Fluxo

1. `/finalizar/`: dados, CEP (cotação no servidor), forma de pagamento. Cria o pedido **pendente** (canal "site") e
   reserva o estoque. Prazo para pagar: `PIX_EXPIRACAO_MINUTOS` (Configurações → Vendas).
2. **Pix**: o servidor cria o pagamento e mostra QR Code + copia e cola em `/pedido/<link secreto>/`.
3. **Cartão**: o Brick do Mercado Pago gera um token no navegador; o servidor cria o pagamento com o valor e o limite
   de parcelas da loja (nunca os do navegador).
4. **Confirmação**: webhook com assinatura HMAC conferida → consulta na API → aplica. Idempotente; só marca como
   pago se o valor bater com o pedido.
5. **Não pagou no prazo**: `python manage.py expirar_pedidos` (agendar a cada 10 min) cancela e devolve o estoque,
   conferindo a API antes. A página do pedido também cancela quando o cliente volta depois do prazo.

## Segurança

- Dados do cartão nunca passam pelo servidor. CSP liberada para o Mercado Pago só na página do cartão.
- Chave de idempotência em toda criação de pagamento (clique duplo não cobra duas vezes).
- Link do pedido com token aleatório de 43 caracteres, sem dados pessoais na URL; `noindex`.
- Nada do corpo das requisições vai para log.
