import unicodedata

from django.db import migrations

PALAVRAS = ("limpa lente", "estojo", "box organizador", "porta oculos", "cordao", "flanela", "necessaire", "case ")


def _normaliza(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return f"{sem_acento.lower()} "


def cria(apps, schema_editor):
    Categoria = apps.get_model("catalogo", "Categoria")
    Produto = apps.get_model("catalogo", "Produto")
    categoria, _ = Categoria.objects.get_or_create(
        slug="acessorios", defaults={"nome": "Acessórios", "ordem": 90, "ativa": True}
    )
    for produto in Produto.objects.all():
        if produto.tipo == "acessorio" or any(p in _normaliza(produto.nome) for p in PALAVRAS):
            if produto.tipo != "acessorio":
                produto.tipo = "acessorio"
                produto.save(update_fields=["tipo"])
            produto.categorias.add(categoria)


class Migration(migrations.Migration):
    dependencies = [("catalogo", "0005_banner_video")]

    operations = [migrations.RunPython(cria, migrations.RunPython.noop)]
