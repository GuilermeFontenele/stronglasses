"""Validadores brasileiros sem dependências externas."""

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator

validar_hex = RegexValidator(r"^#[0-9A-Fa-f]{6}$", "Use uma cor no formato #RRGGBB.")
validar_whatsapp = RegexValidator(r"^\+[1-9]\d{7,14}$", "Use o formato internacional, ex.: +5585999998888.")


def so_digitos(valor: str) -> str:
    return "".join(ch for ch in valor or "" if ch.isdigit())


def _cpf_valido(cpf: str) -> bool:
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    for tamanho in (9, 10):
        soma = sum(int(cpf[i]) * (tamanho + 1 - i) for i in range(tamanho))
        digito = (soma * 10) % 11 % 10
        if digito != int(cpf[tamanho]):
            return False
    return True


def _cnpj_valido(cnpj: str) -> bool:
    if len(cnpj) != 14 or cnpj == cnpj[0] * 14:
        return False
    pesos = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    for tamanho in (12, 13):
        pesos_atuais = pesos if tamanho == 12 else [6, *pesos]
        soma = sum(int(cnpj[i]) * pesos_atuais[i] for i in range(tamanho))
        resto = soma % 11
        digito = 0 if resto < 2 else 11 - resto
        if digito != int(cnpj[tamanho]):
            return False
    return True


def cnpj_valido(valor: str) -> bool:
    return _cnpj_valido(so_digitos(valor))


def validar_cpf(valor: str) -> None:
    if not _cpf_valido(so_digitos(valor)):
        raise ValidationError("CPF inválido.")


def validar_cnpj(valor: str) -> None:
    if not _cnpj_valido(so_digitos(valor)):
        raise ValidationError("CNPJ inválido.")
