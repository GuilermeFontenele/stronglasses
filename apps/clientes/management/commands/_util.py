from django.core.management.base import CommandError

from apps.clientes.models import Cliente


def busca_cliente(uuid: str | None, email: str | None) -> Cliente:
    if not uuid and not email:
        raise CommandError("Informe --uuid ou --email.")
    try:
        if uuid:
            return Cliente.objects.get(uuid=uuid)
        return Cliente.objects.get(email=email.strip().lower())
    except (Cliente.DoesNotExist, ValueError) as exc:
        raise CommandError("Cliente não encontrado.") from exc
