from django.db import migrations

# Remetente impresso na etiqueta e na declaração de conteúdo. O documento vem de CNPJ_LOJA.
PARAMETROS = [
    ("REMETENTE_NOME", "Strong Glasses", "texto", "Nome do remetente na etiqueta e na declaração de conteúdo."),
    ("REMETENTE_ENDERECO", "", "texto", "Rua e número de onde os pacotes saem (ex.: Rua Tal, 123, sala 4)."),
    ("REMETENTE_BAIRRO", "", "texto", "Bairro do remetente."),
    ("REMETENTE_CIDADE", "Fortaleza", "texto", "Cidade do remetente."),
    ("REMETENTE_UF", "CE", "texto", "Sigla do estado do remetente (ex.: CE)."),
    ("REMETENTE_CEP", "", "texto", "CEP do remetente, só números."),
]


def cria(apps, schema_editor):
    Parametro = apps.get_model("core", "Parametro")
    for chave, valor, tipo, descricao in PARAMETROS:
        Parametro.objects.get_or_create(chave=chave, defaults={"valor": valor, "tipo": tipo, "descricao": descricao})


def remove(apps, schema_editor):
    apps.get_model("core", "Parametro").objects.filter(chave__in=[p[0] for p in PARAMETROS]).delete()


class Migration(migrations.Migration):
    dependencies = [("core", "0007_pagina")]

    operations = [migrations.RunPython(cria, remove)]
