from django.contrib.staticfiles.management.commands.runserver import Command as RunserverDjango


class Command(RunserverDjango):
    """runserver na porta 8080 por padrão (a 8000 já é usada por outro sistema na máquina)."""

    default_port = "8080"
