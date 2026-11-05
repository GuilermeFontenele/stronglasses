"""Exporta e importa só o catálogo (produtos, fotos, banners, páginas e parâmetros).

Nunca inclui clientes, endereços, pedidos, usuários ou auditoria: serve para montar o
ambiente de testes sem dado pessoal (LGPD).
"""

import io
import json
import secrets
import tempfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

from django.apps import apps
from django.conf import settings
from django.core import serializers
from django.core.management import call_command
from django.db import transaction

MODELOS = [
    "catalogo.Categoria",
    "catalogo.AcabamentoArmacao",
    "catalogo.CorLente",
    "catalogo.Produto",
    "catalogo.Variacao",
    "catalogo.ImagemProduto",
    "catalogo.Banner",
    "core.Pagina",
    "core.Parametro",
    "core.Redirecionamento",
]
CAMPOS_DE_ARQUIVO = {
    "catalogo.acabamentoarmacao": ["textura"],
    "catalogo.imagemproduto": ["imagem"],
    "catalogo.banner": ["imagem", "imagem_mobile", "video", "video_mobile"],
}
CAMPOS_DE_USUARIO = ("criado_por", "atualizado_por")
PASTAS_PERMITIDAS = {"produtos", "texturas", "banners"}
TAMANHO_MAXIMO_ZIP = 1024 * 1024 * 1024  # 1 GB
TAMANHO_MAXIMO_ARQUIVO = 40 * 1024 * 1024


class TransferenciaInvalida(Exception):
    pass


def exportar(destino: Path | None = None) -> Path:
    objetos = []
    for rotulo in MODELOS:
        modelo = apps.get_model(rotulo)
        objetos.extend(json.loads(serializers.serialize("json", modelo.objects.all().order_by("pk"))))
    arquivos = set()
    for obj in objetos:
        for campo in CAMPOS_DE_USUARIO:  # usuários do painel ficam de fora
            if campo in obj["fields"]:
                obj["fields"][campo] = None
        for campo in CAMPOS_DE_ARQUIVO.get(obj["model"], []):
            if obj["fields"].get(campo):
                arquivos.add(obj["fields"][campo])

    if destino is None:
        pasta = Path(settings.MEDIA_ROOT) / "exportacao"
        pasta.mkdir(parents=True, exist_ok=True)
        destino = pasta / f"catalogo-{secrets.token_hex(16)}.zip"  # nome impossível de adivinhar
    raiz = Path(settings.MEDIA_ROOT)
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as zip_:
        zip_.writestr("catalogo.json", json.dumps(objetos, ensure_ascii=False))
        for nome in sorted(arquivos):
            caminho = raiz / nome
            if caminho.is_file():
                zip_.write(caminho, f"media/{nome}", compress_type=zipfile.ZIP_STORED)
    return destino


def _baixar(url: str) -> Path:
    endereco = urllib.parse.urlsplit(url)
    if endereco.scheme != "https" or not endereco.netloc:
        raise TransferenciaInvalida("O endereço precisa começar com https://")
    temporario = Path(tempfile.mkstemp(suffix=".zip")[1])
    requisicao = urllib.request.Request(url, headers={"User-Agent": "StrongGlasses-Importador"})  # noqa: S310
    with urllib.request.urlopen(requisicao, timeout=120) as resposta, temporario.open("wb") as saida:  # noqa: S310
        total = 0
        while bloco := resposta.read(1024 * 1024):
            total += len(bloco)
            if total > TAMANHO_MAXIMO_ZIP:
                raise TransferenciaInvalida("Arquivo maior que 1 GB.")
            saida.write(bloco)
    return temporario


def _destino_seguro(nome: str) -> Path:
    """Só aceita media/<pasta permitida>/<arquivo>, sem '..' nem caminhos absolutos."""
    caminho = PurePosixPath(nome)
    partes = caminho.parts
    if (
        caminho.is_absolute()
        or len(partes) != 3
        or partes[0] != "media"
        or partes[1] not in PASTAS_PERMITIDAS
        or any(p in ("", ".", "..") or "\\" in p for p in partes)
    ):
        raise TransferenciaInvalida(f"Caminho não permitido no arquivo: {nome}")
    raiz = Path(settings.MEDIA_ROOT).resolve()
    destino = (raiz / partes[1] / partes[2]).resolve()
    if raiz not in destino.parents:
        raise TransferenciaInvalida(f"Caminho não permitido no arquivo: {nome}")
    return destino


def importar(origem: str) -> dict:
    caminho = _baixar(origem) if origem.startswith(("https://", "http://")) else Path(origem)
    if not caminho.is_file():
        raise TransferenciaInvalida(f"Arquivo não encontrado: {origem}")
    with zipfile.ZipFile(caminho) as zip_:
        membros = zip_.infolist()
        if sum(m.file_size for m in membros) > TAMANHO_MAXIMO_ZIP:
            raise TransferenciaInvalida("Conteúdo descompactado maior que 1 GB.")
        dados = json.loads(zip_.read("catalogo.json"))
        modelos_permitidos = {rotulo.lower() for rotulo in MODELOS}
        for obj in dados:
            if obj.get("model") not in modelos_permitidos:
                raise TransferenciaInvalida(f"Tipo de dado não permitido: {obj.get('model')}")
            for campo in CAMPOS_DE_USUARIO:
                if campo in obj.get("fields", {}):
                    obj["fields"][campo] = None
        arquivos = [m for m in membros if not m.is_dir() and m.filename != "catalogo.json"]
        destinos = [(m, _destino_seguro(m.filename)) for m in arquivos]  # valida tudo antes de gravar
        for membro, destino in destinos:
            if membro.file_size > TAMANHO_MAXIMO_ARQUIVO:
                raise TransferenciaInvalida(f"Arquivo grande demais: {membro.filename}")
            destino.parent.mkdir(parents=True, exist_ok=True)
            with zip_.open(membro) as entrada, destino.open("wb") as saida:
                saida.write(entrada.read(TAMANHO_MAXIMO_ARQUIVO + 1))

    with tempfile.TemporaryDirectory() as pasta:
        fixture = Path(pasta) / "catalogo.json"
        fixture.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
        with transaction.atomic():
            call_command("loaddata", str(fixture), verbosity=0, stdout=io.StringIO())
    if caminho != Path(origem):
        caminho.unlink(missing_ok=True)
    return {"registros": len(dados), "arquivos": len(destinos)}
