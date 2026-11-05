from django.db import migrations


def cria(apps, schema_editor):
    Parametro = apps.get_model("core", "Parametro")
    Parametro.objects.get_or_create(
        chave="PESO_PADRAO_G",
        defaults={
            "valor": "50",
            "tipo": "inteiro",
            "descricao": "Peso com embalagem (g) usado quando o produto não tem peso cadastrado.",
        },
    )


def remove(apps, schema_editor):
    apps.get_model("core", "Parametro").objects.filter(chave="PESO_PADRAO_G").delete()


class Migration(migrations.Migration):
    dependencies = [("core", "0002_parametros_iniciais")]

    operations = [migrations.RunPython(cria, remove)]
