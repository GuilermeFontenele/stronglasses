"""Filtro de log que mascara e-mails, CPFs/CNPJs e telefones antes de escrever."""

import logging
import re

_PADROES = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[email]"),
    (re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b"), "[cpf]"),
    (re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b"), "[cnpj]"),
    (re.compile(r"\+?55?\s?\(?\d{2}\)?\s?9?\d{4}-?\d{4}\b"), "[telefone]"),
]


def mascarar(texto: str) -> str:
    for padrao, substituto in _PADROES:
        texto = padrao.sub(substituto, texto)
    return texto


class MascaraDadosPessoaisFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            mensagem = record.getMessage()
        except Exception:  # noqa: BLE001 - nunca derrubar o log
            return True
        mascarada = mascarar(mensagem)
        if mascarada != mensagem:
            record.msg = mascarada
            record.args = None
        return True
