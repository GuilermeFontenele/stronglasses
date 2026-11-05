# Importação da Nuvemshop

Traz para o sistema: **categorias, produtos (com fotos e variações armação/lente), clientes,
pedidos e cupons**. Pode rodar quantas vezes quiser: o que já existe é atualizado, nada é duplicado.

Tudo roda **no seu computador**, direto na API da Nuvemshop. Os dados de clientes não passam por
nenhum outro lugar.

## 1. Criar o acesso à API (uma vez só)

A Nuvemshop só libera a API por meio de um "aplicativo". É gratuito e só a sua loja vai usá-lo.
Os nomes dos menus podem mudar um pouco no portal.

1. Entre em <https://partners.nuvemshop.com.br> e crie uma conta de parceiro (pode usar o mesmo e-mail).
2. Vá em **Aplicativos → Criar aplicativo**. Se perguntar o tipo, escolha uso próprio/privado.
3. Preencha:
   - **Nome:** `Strong Importador`
   - **URL de redirecionamento:** `https://www.stronglasses.com.br/` (o código vai aparecer na barra de endereço)
   - **Permissões (só leitura):** Produtos, Clientes, Pedidos e Cupons/Descontos
4. Copie o **ID do aplicativo** e o **Client Secret** para o seu `.env`:
   ```
   NUVEMSHOP_CLIENT_ID=12345
   NUVEMSHOP_CLIENT_SECRET=...
   ```
5. Logado na sua loja, abra `https://www.nuvemshop.com.br/apps/<ID_DO_APLICATIVO>/authorize` e aceite.
6. Você cai em `https://www.stronglasses.com.br/?code=XXXXXXXX`. Copie o valor do `code`
   e, **em até 5 minutos**, rode:
   ```bash
   python manage.py nuvemshop_token --codigo XXXXXXXX
   ```
7. Cole as duas linhas que aparecerem (`NUVEMSHOP_STORE_ID` e `NUVEMSHOP_ACCESS_TOKEN`) no `.env`.

## 2. Importar

```bash
# Ensaio: lê tudo da Nuvemshop e mostra o relatório, sem gravar nada
python manage.py importar_nuvemshop --simular

# Para valer (as ~1.000 fotos levam alguns minutos)
python manage.py importar_nuvemshop

# Só uma parte, se precisar repetir
python manage.py importar_nuvemshop --etapas produtos --sem-imagens
```

Etapas: `categorias, produtos, clientes, pedidos, cupons` (nessa ordem).

O relatório fica em `importacao/relatorio-AAAAMMDD-HHMM.md` com o que precisa de revisão no painel
(cores sem tom, armação/lente que parecem invertidas, produtos sem peso para o frete etc.).
Os cupons ficam em `importacao/cupons.json` até existir o cadastro de cupons no sistema.

## 3. Métricas (visitas, funil, origem do tráfego)

As visitas não existem na API; foram exportadas das estatísticas da loja para o arquivo
`metricas-nuvemshop.json` (enviado à parte, **não** vai para o git):

```bash
python manage.py importar_metricas caminho/para/metricas-nuvemshop.json
```

## 4. Depois de importar

- Revise o relatório no painel.
- Quando a loja nova estiver no ar, **desinstale o aplicativo na Nuvemshop** (isso revoga o token)
  e apague as linhas `NUVEMSHOP_*` do `.env`.

## O que é e o que não é importado (LGPD)

| Dado | Importado? | Por quê |
|---|---|---|
| Nome, e-mail, telefone (como WhatsApp) | Sim | Atender e falar sobre pedidos |
| CPF / CNPJ | Sim (criptografado) | Etiqueta/declaração de conteúdo do envio; nota fiscal para PJ |
| Endereços de entrega (cadastro e pedidos) | Sim, completos | Continuar enviando pedidos ao cliente |
| Peso e medidas | Da Nuvemshop; se não houver, a embalagem padrão (50 g, 5 × 10 × 18 cm, editável em Parâmetros) | Cálculo do frete |
| Aceite de e-mail marketing | Sim, como consentimento "Importado da Nuvemshop" | Prova da base legal |
| Cliente que pediu exclusão (anonimizado) | Nunca é reimportado | Direito do titular |
