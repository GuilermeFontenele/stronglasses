from django.db import migrations

PARAMETROS = [
    ("EMBALAGEM_ALTURA_CM", "5", "Altura da embalagem padrão (cm), usada quando o produto não tem medidas."),
    ("EMBALAGEM_LARGURA_CM", "10", "Largura da embalagem padrão (cm), usada quando o produto não tem medidas."),
    ("EMBALAGEM_COMPRIMENTO_CM", "18", "Comprimento da embalagem padrão (cm), usado quando o produto não tem medidas."),
]


def cria(apps, schema_editor):
    Parametro = apps.get_model("core", "Parametro")
    for chave, valor, descricao in PARAMETROS:
        Parametro.objects.get_or_create(chave=chave, defaults={"valor": valor, "tipo": "decimal", "descricao": descricao})


def remove(apps, schema_editor):
    apps.get_model("core", "Parametro").objects.filter(chave__in=[p[0] for p in PARAMETROS]).delete()


class Migration(migrations.Migration):
    dependencies = [("core", "0004_redirecionamento")]

    operations = [migrations.RunPython(cria, remove)]
