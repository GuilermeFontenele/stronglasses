"""Se o endereço (slug) de um produto mudar, a URL antiga redireciona para a nova (SEO)."""

from django.db.models.signals import pre_save
from django.dispatch import receiver

from apps.core.models import Redirecionamento

from .models import Produto


def url_produto(slug: str) -> str:
    return f"/produtos/{slug}/"


@receiver(pre_save, sender=Produto)
def redireciona_slug_antigo(sender, instance, raw=False, **kwargs):
    if raw or instance._state.adding or not instance.pk:
        return
    anterior = Produto.objects.filter(pk=instance.pk).values_list("slug", flat=True).first()
    if not anterior or anterior == instance.slug:
        return
    antigo, novo = url_produto(anterior), url_produto(instance.slug)
    # Evita cadeias: quem apontava para a URL antiga passa a apontar direto para a nova.
    Redirecionamento.objects.filter(destino=antigo).update(destino=novo)
    Redirecionamento.objects.filter(origem=novo).delete()
    Redirecionamento.objects.update_or_create(origem=antigo, defaults={"destino": novo, "ativo": True})
