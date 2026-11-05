"""Conversões puras dos dados da Nuvemshop para o formato do sistema."""

import html
import re
import unicodedata
from datetime import UTC
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.core.validators import cnpj_valido, cpf_valido, so_digitos

# Tom aproximado de cada cor (pode ser ajustado depois no painel).
CORES = {
    "preto": "#111111",
    "branco": "#F5F5F5",
    "off white": "#F2EFE6",
    "azul": "#2B4C9B",
    "azul claro": "#7FB3E6",
    "azul marinho": "#1B2A4A",
    "amarelo": "#E8C33A",
    "amarelo escuro": "#B8860B",
    "champanhe": "#D9C7A0",
    "tartaruga": "#6B3E1F",
    "tartaruga claro": "#A0703F",
    "bege": "#D8C3A5",
    "transparente": "#E6E9EC",
    "cristal": "#E6E9EC",
    "marrom": "#5C3A21",
    "roxo": "#5B2C83",
    "lilas": "#B39DDB",
    "verde": "#4F6F46",
    "verde agua": "#7FC8B8",
    "verde militar": "#4B5320",
    "laranja": "#E3762B",
    "rosa": "#E8A0B4",
    "cinza": "#8A8F96",
    "grafite": "#3D4148",
    "fume": "#5A5A5A",
    "dourado": "#C9A13B",
    "prata": "#C0C0C0",
    "vermelho": "#B22222",
    "vinho": "#6D1A2A",
    "bordo": "#6D1A2A",
    "nude": "#E3C1A8",
    "caramelo": "#A8642A",
    "mel": "#C68E3F",
    "chocolate": "#4E2E1E",
    "degrade": "#8A8F96",
    "espelhado": "#B8C4CC",
}
# Cores que costumam ser de armação: se aparecerem como "lente", vale revisar.
TIPICAS_DE_ARMACAO = {"tartaruga", "tartaruga claro", "transparente", "cristal", "champanhe", "dourado", "prata"}
COR_PADRAO_HEX = "#999999"


def chave_cor(nome: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", nome or "").encode("ascii", "ignore").decode("ascii")
    return " ".join(sem_acento.lower().split())


def hex_da_cor(nome: str) -> str | None:
    return CORES.get(chave_cor(nome))


def nome_cor(valor: str) -> str:
    """'verde ÁGUA' -> 'Verde Água'."""
    return " ".join(parte[:1].upper() + parte[1:].lower() for parte in (valor or "").split())


def separar_cor(valor: str) -> tuple[str, str | None]:
    """'Preto/Azul' -> ('Preto', 'Azul'); 'Tartaruga' -> ('Tartaruga', None)."""
    partes = [nome_cor(p) for p in (valor or "").split("/") if p.strip()]
    if not partes:
        return "", None
    return partes[0], (partes[1] if len(partes) > 1 else None)


def cor_no_nome(nome_produto: str) -> str | None:
    """Produtos antigos sem variação trazem a cor no nome: 'Óculos de Sol Nice Dourado'."""
    chave = chave_cor(nome_produto)
    for cor in sorted(CORES, key=len, reverse=True):
        if chave == cor or chave.endswith(" " + cor):
            palavras = (nome_produto or "").split()
            return nome_cor(" ".join(palavras[-len(cor.split()) :]))
    return None


def texto(valor, idiomas=("pt", "pt_BR", "es", "es_AR", "en", "en_US")) -> str:
    """Campos multilíngues da API vêm como {'pt': '...'}."""
    if valor is None:
        return ""
    if isinstance(valor, str):
        return valor
    if isinstance(valor, dict):
        for idioma in idiomas:
            if valor.get(idioma):
                return str(valor[idioma])
        return next((str(v) for v in valor.values() if v), "")
    if isinstance(valor, list):
        return next((texto(v) for v in valor if texto(v)), "")
    return str(valor)


def decimal(valor) -> Decimal | None:
    if valor in (None, ""):
        return None
    try:
        return Decimal(str(valor)).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def precos(preco, promocional) -> tuple[Decimal, Decimal | None]:
    """(preço de venda, preço riscado). Promoção só vale se for menor que o preço cheio."""
    cheio = decimal(preco) or Decimal("0.01")
    promo = decimal(promocional)
    if promo and Decimal("0") < promo < cheio:
        return promo, cheio
    return cheio, None


def peso_gramas(peso_kg) -> int | None:
    valor = decimal(peso_kg)
    return int(valor * 1000) if valor else None


def medida_cm(valor) -> Decimal | None:
    numero = decimal(valor)
    return numero.quantize(Decimal("0.1")) if numero else None


def whatsapp(telefone: str) -> str:
    digitos = so_digitos(telefone)
    if len(digitos) in (12, 13) and digitos.startswith("55"):
        return "+" + digitos
    if len(digitos) in (10, 11):
        return "+55" + digitos
    return ""


def documento(identificacao: str) -> tuple[str, str]:
    """('PF', cpf) ou ('PJ', cnpj) só com dígitos; ('', '') se vazio ou inválido."""
    digitos = so_digitos(identificacao)
    if len(digitos) == 11 and cpf_valido(digitos):
        return "PF", digitos
    if len(digitos) == 14 and cnpj_valido(digitos):
        return "PJ", digitos
    return "", ""


def endereco(dados: dict) -> dict | None:
    """Endereço da Nuvemshop -> campos do model Endereco. None se faltar o essencial."""
    if not dados:
        return None
    cep = so_digitos(dados.get("zipcode") or "")
    logradouro = " ".join((dados.get("address") or "").split())
    cidade = " ".join((dados.get("city") or "").split())
    if not (cep and logradouro and cidade):
        return None
    return {
        "destinatario": " ".join((dados.get("name") or "").split())[:150],
        "cep": cep[:8],
        "logradouro": logradouro[:200],
        "numero": (dados.get("number") or "").strip()[:20],
        "complemento": " ".join((dados.get("floor") or "").split())[:120],
        "bairro": " ".join((dados.get("locality") or "").split())[:100],
        "cidade": cidade[:100],
        "uf": " ".join((dados.get("province") or "").split())[:40],
        "pais": ((dados.get("country") or "BR").strip().upper() or "BR")[:2],
    }


def data_hora(valor):
    if not valor or not isinstance(valor, str):
        return None
    momento = parse_datetime(valor.replace(" ", "T", 1))
    if momento and timezone.is_naive(momento):
        momento = timezone.make_aware(momento, UTC)
    return momento


class _ExtratorTexto(HTMLParser):
    QUEBRAS = {"br", "p", "div", "li", "h1", "h2", "h3", "h4", "tr"}

    IGNORADAS = {"script", "style", "iframe", "noscript"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.partes: list[str] = []
        self._ignorando = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.IGNORADAS:
            self._ignorando += 1
        elif tag == "li":
            self.partes.append("\n• ")
        elif tag in self.QUEBRAS:
            self.partes.append("\n")

    def handle_endtag(self, tag):
        if tag in self.IGNORADAS:
            self._ignorando = max(self._ignorando - 1, 0)
        elif tag in self.QUEBRAS and tag != "li":
            self.partes.append("\n")

    def handle_data(self, data):
        if not self._ignorando:
            self.partes.append(data)


def html_para_texto(conteudo: str) -> str:
    """Descrição da Nuvemshop vem em HTML; guardamos texto puro (nada de HTML não confiável)."""
    if not conteudo:
        return ""
    extrator = _ExtratorTexto()
    extrator.feed(conteudo)
    bruto = html.unescape("".join(extrator.partes)).replace("\xa0", " ")
    linhas = [" ".join(linha.split()) for linha in bruto.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(linhas)).strip()
