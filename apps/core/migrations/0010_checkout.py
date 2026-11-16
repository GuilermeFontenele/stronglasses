from django.db import migrations

PARAMETROS = [
    (
        "FRETE_LOCAL_CEPS",
        "60000000-60999999",
        "texto",
        "Faixas de CEP com entrega por motoboy (ex.: 60000000-60999999, 61600000-61619999).",
    ),
    ("FRETE_MOTOBOY_PRECO", "10", "decimal", "Preço do motoboy dentro das faixas de CEP locais."),
    ("FRETE_GRATIS_LOCAL_ACIMA", "300", "decimal", "Motoboy grátis a partir deste valor em produtos (0 = nunca)."),
]

PRIVACIDADE = """*Rascunho: revise antes de publicar o site.*

A Strong Glasses leva a sério a proteção dos seus dados. Aqui explicamos, de forma simples, o que coletamos, por que e quais são os seus direitos, conforme a Lei Geral de Proteção de Dados (Lei 13.709/2018).

## Quem cuida dos seus dados

Strong Glasses, Fortaleza/CE. Para qualquer assunto sobre seus dados, fale com a gente pelo e-mail ou WhatsApp que aparecem no rodapé do site.

## O que coletamos e para quê

- **Nome, e-mail e WhatsApp:** para registrar o pedido, avisar sobre o pagamento e a entrega e atender você.
- **CPF:** exigido para emitir o pagamento e para a declaração de conteúdo ou nota fiscal do envio.
- **Endereço de entrega:** para enviar o seu pedido. Guardamos para facilitar as próximas compras.
- **Itens e valores dos pedidos:** para entrega, trocas, garantia e obrigações fiscais.
- **Ofertas por e-mail ou WhatsApp:** só se você marcar que quer receber. Pode cancelar quando quiser.

Não pedimos mais do que isso. Os dados do cartão são digitados direto no ambiente seguro do Mercado Pago: não passam pelo nosso site e não ficam guardados com a gente.

## Provador virtual

O provador da página do produto usa a câmera só no seu aparelho. Nenhuma imagem do seu rosto é enviada, gravada ou guardada.

## Com quem compartilhamos

Só com quem precisa para o pedido acontecer: Mercado Pago (pagamento), Melhor Envio e a transportadora escolhida (entrega) e nossos fornecedores de hospedagem e e-mail. Não vendemos nem alugamos dados.

## Por quanto tempo guardamos

Enquanto você for nosso cliente e, depois, pelo tempo exigido por lei (em geral, 5 anos para dados de vendas). Depois disso, os dados são apagados ou anonimizados.

## Seus direitos

Você pode pedir a qualquer momento: confirmação e cópia dos seus dados, correção, exclusão ou anonimização (respeitando o que a lei manda guardar), e cancelar o recebimento de ofertas. Basta falar com a gente pelos contatos do rodapé.

## Segurança

O site usa conexão segura (https), dados sensíveis como o CPF ficam cifrados no banco, e o acesso ao painel da loja é restrito e registrado.

## Cookies

Usamos apenas os cookies necessários para o carrinho e a segurança do site."""


def cria(apps, schema_editor):
    Parametro = apps.get_model("core", "Parametro")
    for chave, valor, tipo, descricao in PARAMETROS:
        Parametro.objects.get_or_create(chave=chave, defaults={"valor": valor, "tipo": tipo, "descricao": descricao})
    apps.get_model("core", "Pagina").objects.get_or_create(
        slug="politica-de-privacidade",
        defaults={
            "titulo": "Política de privacidade",
            "conteudo": PRIVACIDADE,
            "seo_descricao": "Como a Strong Glasses usa e protege os seus dados pessoais (LGPD).",
        },
    )


def remove(apps, schema_editor):
    apps.get_model("core", "Parametro").objects.filter(chave__in=[p[0] for p in PARAMETROS]).delete()


class Migration(migrations.Migration):
    dependencies = [("core", "0009_remetente_numero")]

    operations = [migrations.RunPython(cria, remove)]
