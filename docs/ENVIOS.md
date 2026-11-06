# Envios: etiquetas pelo Melhor Envio

Cotação e etiquetas de Correios, Jadlog e J&T direto da ficha da venda (`/gestao/vendas/<id>/`),
pagas com o saldo da conta do Melhor Envio. Código em `apps/envios/`.

## Configurar (uma vez)

1. Crie a conta: testes em <https://sandbox.melhorenvio.com.br>, produção em <https://melhorenvio.com.br>.
2. Em **Integrações → Área Dev. → Cadastrar aplicativo**, use como URL de redirecionamento o endereço
   mostrado em **Painel → Integrações** (no computador: `http://localhost:8080/gestao/integracoes/melhor-envio/retorno/`).
3. No `.env` (nunca no git):
   ```
   MELHOR_ENVIO_AMBIENTE=sandbox
   MELHOR_ENVIO_CLIENT_ID=...
   MELHOR_ENVIO_CLIENT_SECRET=...
   ```
4. Reinicie o servidor, abra **Painel → Integrações → Conectar conta** e autorize.
5. Preencha **Configurações → Remetente** (rua, número, bairro, cidade, UF, CEP) e o CNPJ.

Para produção: crie o aplicativo também na conta de produção, troque as três linhas e conecte de novo.
Testes e produção guardam conexões separadas.

## Como funciona

1. **Cotar frete**: um pacote com a embalagem padrão (ou as medidas do produto, se for um só) e a soma dos pesos.
2. **Comprar etiqueta**: o servidor cota de novo (o preço nunca vem do navegador), põe no carrinho, paga com o
   saldo e gera a etiqueta. Se o pagamento falhar, o item sai do carrinho. Se a geração falhar, a etiqueta fica
   paga e aparece "Gerar de novo".
3. **Sem nota fiscal** vai com declaração de conteúdo eletrônica (botão "Declaração de conteúdo"), que exige o
   CPF/CNPJ do destinatário. **Com nota** (vendas para empresa), informe a chave de 44 números.
4. **Rastreio**: o código entra na venda; "Postado" leva a venda para Enviado e "Entregue" para Entregue.
   Agende `python manage.py atualizar_rastreios` a cada 3 ou 4 horas na hospedagem (ou use o botão).
5. **Cancelar**: só antes de postar; o valor volta ao saldo em até 12 horas.

## Segurança e LGPD

- Tokens OAuth cifrados no banco (`ConexaoMelhorEnvio`), renovados sozinhos antes de vencer; o Secret só no `.env`.
- Escopos mínimos (cotar, carrinho, comprar, gerar, imprimir, rastrear, cancelar, ler usuário).
- Nada do corpo das requisições vai para log (tem nome, endereço e CPF).
- Usar o CPF do cadastro e imprimir a etiqueta registram acesso na auditoria.
- A página de impressão fica para quem só posta no balcão, sem a integração.
