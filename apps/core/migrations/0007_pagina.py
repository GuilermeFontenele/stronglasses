import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

TROCAS = """## Direito de arrependimento

Comprou pelo site e mudou de ideia? Você pode desistir da compra em até 7 dias corridos a partir do recebimento, sem precisar explicar o motivo (Código de Defesa do Consumidor, art. 49). O óculos precisa voltar sem sinais de uso, com estojo, flanela e embalagem originais. Devolvemos o valor pago, inclusive o frete de envio, pelo mesmo meio de pagamento.

## Garantia

Nossos óculos têm garantia de 3 meses contra defeitos de fabricação. Se notar qualquer problema, fale com a gente mandando fotos do produto e o número do pedido: analisamos e trocamos a peça ou devolvemos o valor.

## Troca de modelo ou cor

Quer outro modelo ou cor? Fale com a gente em até 7 dias após o recebimento. A peça precisa estar sem uso e na embalagem original. O frete da troca é combinado no atendimento.

## Como pedir troca ou devolução

Chame a gente no WhatsApp ou mande um e-mail com o número do pedido e o que aconteceu. Respondemos o mais rápido possível e passamos as instruções de envio."""


def cria(apps, schema_editor):
    Parametro = apps.get_model("core", "Parametro")
    Parametro.objects.get_or_create(
        chave="EMAIL_LOJA",
        defaults={"valor": "stronglasses@outlook.com", "tipo": "texto", "descricao": "E-mail de contato exibido no site."},
    )
    Pagina = apps.get_model("core", "Pagina")
    Pagina.objects.get_or_create(
        slug="trocas-e-devolucoes",
        defaults={
            "titulo": "Trocas e devoluções",
            "conteudo": TROCAS,
            "seo_descricao": "Como funcionam trocas, devoluções e garantia dos óculos Strong Glasses.",
        },
    )


def remove(apps, schema_editor):
    apps.get_model("core", "Parametro").objects.filter(chave="EMAIL_LOJA").delete()


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core", "0006_parametros_vitrine"),
    ]

    operations = [
        migrations.CreateModel(
            name="Pagina",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("criado_em", models.DateTimeField(auto_now_add=True, verbose_name="criado em")),
                ("atualizado_em", models.DateTimeField(auto_now=True, verbose_name="atualizado em")),
                ("titulo", models.CharField(max_length=120, verbose_name="título")),
                (
                    "slug",
                    models.SlugField(
                        help_text="Fica em /<slug>/. Não use o mesmo endereço de uma categoria (a categoria tem prioridade).",
                        max_length=120,
                        unique=True,
                        verbose_name="endereço (slug)",
                    ),
                ),
                (
                    "conteudo",
                    models.TextField(
                        help_text="Texto simples. Deixe uma linha em branco entre parágrafos e comece um subtítulo com ## .",
                        verbose_name="conteúdo",
                    ),
                ),
                (
                    "seo_descricao",
                    models.CharField(blank=True, max_length=160, verbose_name="descrição para o Google"),
                ),
                ("publicada", models.BooleanField(default=True, verbose_name="publicada")),
                (
                    "atualizado_por",
                    models.ForeignKey(
                        blank=True,
                        editable=False,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="atualizado por",
                    ),
                ),
                (
                    "criado_por",
                    models.ForeignKey(
                        blank=True,
                        editable=False,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="criado por",
                    ),
                ),
            ],
            options={"verbose_name": "página", "verbose_name_plural": "páginas", "ordering": ["titulo"]},
        ),
        migrations.RunPython(cria, remove),
    ]
