from django.db import models

from .crypto import cifrar, decifrar


class EncryptedTextField(models.TextField):
    """Texto cifrado com Fernet no banco e decifrado ao ler.

    Não serve para filtros/buscas (cada gravação gera um token diferente).
    Para localizar registros, guarde também um hash com `crypto.hash_busca`.
    """

    description = "Texto cifrado (Fernet)"

    def from_db_value(self, value, expression, connection):
        if value is None or value == "":
            return value
        return decifrar(value)

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value is None or value == "":
            return value
        return cifrar(str(value))
