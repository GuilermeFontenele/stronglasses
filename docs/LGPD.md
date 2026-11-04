# LGPD: inventário de dados pessoais

Documento vivo. Todo dado pessoal novo no sistema entra aqui antes de ir para produção.
Revise com um contador ou advogado: isto é um ponto de partida técnico, não parecer jurídico.

- **Controlador:** Strong Glasses (MEI).
- **Encarregado (DPO):** contato em `LGPD_CONTATO_ENCARREGADO`. MEIs podem ser dispensados de nomear
  encarregado (Resolução CD/ANPD nº 2/2022), mas é obrigatório ter um canal de atendimento ao titular.

## O que coletamos e por quê

| Dado | Onde | Finalidade | Base legal (art. 7º) | Retenção |
|---|---|---|---|---|
| Nome, e-mail, WhatsApp | `Cliente` | Atender, entregar e falar sobre o pedido | Execução de contrato (V) | Enquanto houver relação + 5 anos (CDC/fiscal); depois, anonimizar |
| CPF/CNPJ | `Cliente.documento` (cifrado) | Nota fiscal para PJ; exigência de pagamento ou envio | Obrigação legal (II) / contrato (V) | 5 anos após a venda |
| Contato para ofertas | `Consentimento` | Marketing por e-mail ou WhatsApp | Consentimento (I) | Até revogação |
| IP e navegador do aceite | `Consentimento.ip/user_agent` | Provar o consentimento; segurança | Legítimo interesse (IX) / Marco Civil | 180 dias (`lgpd_expurgar`) |
| Usuário do painel | `RegistroAuditoria` | Rastrear alterações e acessos | Legítimo interesse (IX) | Indefinida (não contém dados de clientes em claro) |

**Não coletamos:** data de nascimento, gênero, foto ou endereço fora do pedido. Dados de cartão nunca
passam pelo nosso servidor (tokenização do Mercado Pago).

## Compartilhamento (operadores)

| Com quem | O quê | Para quê |
|---|---|---|
| Mercado Pago | Nome, e-mail, documento, valor | Processar o pagamento |
| Melhor Envio / transportadora | Nome, endereço, telefone | Entregar o pedido |
| Provedor de e-mail transacional | E-mail, nome | Confirmação e rastreio |
| Hospedagem e banco de dados | Todos (cifrados onde aplicável) | Operar a loja |

Cada operador precisa ter termos compatíveis com a LGPD. Revise antes de contratar.

## Direitos do titular (art. 18) e como atender

Prazo de resposta recomendado: até 15 dias.

| Pedido | Como atender |
|---|---|
| Confirmação e acesso | Painel → Clientes → ação "Exportar dados do titular" ou `lgpd_exportar` |
| Portabilidade | Mesmo arquivo JSON |
| Correção | Editar no painel (fica registrado na auditoria) |
| Revogar consentimento | `lgpd.revogar_consentimento` (o histórico do aceite é mantido) |
| Eliminação | `lgpd_anonimizar --confirmar` (mantém valores de vendas por obrigação legal, sem identificar a pessoa) |

Toda exportação e anonimização fica registrada em `RegistroAuditoria`.

## Medidas de segurança (art. 46)

Ver `SECURITY.md`: criptografia de documento, CSP, HTTPS/HSTS, Argon2, auditoria imutável,
logs mascarados e varredura de segredos no CI.

## Incidentes (art. 48)

Em caso de vazamento: conter, registrar o que aconteceu, avaliar o risco aos titulares e comunicar a
ANPD e os titulares afetados quando houver risco relevante, no prazo previsto em regulamento da ANPD.

## Pendências

- [ ] Publicar a política de privacidade e os termos no site (versão = `LGPD_VERSAO_POLITICA`).
- [ ] Banner de cookies, só se forem usados cookies não essenciais (analytics/pixels).
- [ ] Agendar `lgpd_expurgar` diariamente na hospedagem.
- [ ] Rotina de anonimização automática de clientes inativos após o prazo de retenção.
