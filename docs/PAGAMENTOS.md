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

## Regras que evitam dor de cabeça

- O pedido guarda o que o comprador digitou (nome, e-mail, WhatsApp, CPF cifrado). Cobrança, e-mails e etiqueta
  usam esses dados, nunca os de um cadastro antigo com o mesmo e-mail.
- Quem gerou o Pix e depois tentou o cartão ainda pode pagar aquele Pix: o valor é conferido contra o total da
  forma usada. Cancelar um pedido fecha a cobrança aberta no Mercado Pago.
- Pagamento aprovado depois do cancelamento reativa o pedido se ainda houver estoque. O que não fechar aparece no
  dashboard em **Pagamentos para conferir** (inclui estorno e contestação de pedido já pago).
- Cancelar no painel **não devolve dinheiro**: o estorno é feito no painel do Mercado Pago.
- E-mails ao comprador: pedido recebido (com o link), pagamento aprovado e enviado (com rastreio). Só saem com
  servidor de e-mail configurado (`EMAIL_HOST` etc.); defina `SITE_URL` para os links.
- Limites: 5 tentativas de cartão por pedido, 20 pedidos por hora e 40 cotações por minuto por IP
  (exige `DJANGO_BEHIND_PROXY=1` na hospedagem para enxergar o IP real).

## Agendar na hospedagem

| Comando | Frequência |
|---|---|
| `python manage.py expirar_pedidos` | a cada 10 minutos |
| `python manage.py atualizar_rastreios` | a cada 3 ou 4 horas |
| `python manage.py lgpd_expurgar` | diário |
| `python manage.py clearsessions` | diário (limpa carrinhos abandonados) |

## Segurança

- Dados do cartão nunca passam pelo servidor. CSP liberada para o Mercado Pago só na página do cartão.
- Chave de idempotência em toda criação de pagamento (clique duplo não cobra duas vezes).
- Link do pedido com token aleatório de 43 caracteres, sem dados pessoais na URL; `noindex`.
- Nada do corpo das requisições vai para log.
