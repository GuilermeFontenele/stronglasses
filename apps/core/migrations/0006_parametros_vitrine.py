from django.db import migrations

PARAMETROS = [
    ("OCULOS_ENTREGUES", "10000", "inteiro", "Número do contador da home (óculos entregues). Atualize quando quiser."),
    ("WHATSAPP_LOJA", "5585981809988", "texto", "WhatsApp da loja com DDI e DDD, só números."),
    ("INSTAGRAM_LOJA", "stronglasses", "texto", "Usuário do Instagram, sem @."),
    ("CNPJ_LOJA", "", "texto", "CNPJ do MEI. Exigido no rodapé da loja virtual (Decreto 7.962/2013)."),
    ("ENDERECO_LOJA", "Fortaleza/CE", "texto", "Endereço exibido no rodapé (o decreto pede endereço físico)."),
]


def cria(apps, schema_editor):
    Parametro = apps.get_model("core", "Parametro")
    for chave, valor, tipo, descricao in PARAMETROS:
        Parametro.objects.get_or_create(chave=chave, defaults={"valor": valor, "tipo": tipo, "descricao": descricao})


def remove(apps, schema_editor):
    apps.get_model("core", "Parametro").objects.filter(chave__in=[p[0] for p in PARAMETROS]).delete()


class Migration(migrations.Migration):
    dependencies = [("core", "0005_embalagem_padrao")]

    operations = [migrations.RunPython(cria, remove)]
