from django.db import migrations

# A API das transportadoras pede número e complemento separados da rua.
PARAMETROS = [
    ("REMETENTE_NUMERO", "", "texto", "Número do endereço do remetente."),
    ("REMETENTE_COMPLEMENTO", "", "texto", "Complemento do remetente (sala, loja, bloco). Opcional."),
]


def cria(apps, schema_editor):
    Parametro = apps.get_model("core", "Parametro")
    for chave, valor, tipo, descricao in PARAMETROS:
        Parametro.objects.get_or_create(chave=chave, defaults={"valor": valor, "tipo": tipo, "descricao": descricao})
    Parametro.objects.filter(chave="REMETENTE_ENDERECO").update(
        descricao="Rua de onde os pacotes saem, sem o número (ex.: Rua Tal)."
    )


def remove(apps, schema_editor):
    apps.get_model("core", "Parametro").objects.filter(chave__in=[p[0] for p in PARAMETROS]).delete()


class Migration(migrations.Migration):
    dependencies = [("core", "0008_parametros_remetente")]

    operations = [migrations.RunPython(cria, remove)]
