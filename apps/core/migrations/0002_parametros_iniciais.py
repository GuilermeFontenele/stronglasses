from django.db import migrations

PARAMETROS = [
    ("PIX_DESCONTO_PERCENTUAL", "5", "decimal", "Desconto aplicado em todo pagamento via Pix (%)."),
    ("FRETE_GRATIS_ACIMA", "0", "decimal", "Valor mínimo do carrinho para frete grátis (0 = desativado)."),
    ("PARCELAS_SEM_JUROS", "3", "inteiro", "Número máximo de parcelas sem juros no cartão."),
    ("LIMITE_FATURAMENTO_MEI", "81000", "decimal", "Teto anual de faturamento do MEI (R$)."),
    ("ALERTA_MEI_PERCENTUAL", "80", "inteiro", "Avisar quando o faturamento do ano atingir este % do teto."),
    ("PIX_EXPIRACAO_MINUTOS", "30", "inteiro", "Validade do QR Code Pix; ao expirar, o estoque é liberado."),
]


def cria_parametros(apps, schema_editor):
    Parametro = apps.get_model("core", "Parametro")
    for chave, valor, tipo, descricao in PARAMETROS:
        Parametro.objects.get_or_create(
            chave=chave, defaults={"valor": valor, "tipo": tipo, "descricao": descricao}
        )


def remove_parametros(apps, schema_editor):
    Parametro = apps.get_model("core", "Parametro")
    Parametro.objects.filter(chave__in=[p[0] for p in PARAMETROS]).delete()


class Migration(migrations.Migration):
    dependencies = [("core", "0001_initial")]

    operations = [migrations.RunPython(cria_parametros, remove_parametros)]
