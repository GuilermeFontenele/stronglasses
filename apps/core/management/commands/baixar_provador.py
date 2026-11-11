"""Baixa (uma vez) os arquivos do MediaPipe usados pelo provador virtual para static/vendor/mediapipe/.

Ficam fora do git (são grandes) e são servidos pelo próprio site: nada de script de terceiros na página.
Cada arquivo é conferido pelo SHA-256 fixado abaixo; se não bater, nada é gravado.
Para atualizar a versão, rode o workflow "Provador (conferir arquivos do MediaPipe)" e troque os hashes.
"""

import hashlib
import urllib.request
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

VERSAO = "1.2.2"
CDN = f"https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@{VERSAO}"
MODELO = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"
)
ARQUIVOS = {
    "vision_bundle.mjs": (
        f"{CDN}/vision_bundle.mjs",
        "b65acb59b370cd6561afd9d04c29ed7a87e7ed6386922ac1b263af1f1ad06b7d",
    ),
    "wasm/vision_wasm_internal.js": (
        f"{CDN}/wasm/vision_wasm_internal.js",
        "f2b9c17131ea79716ec6bf07b117a087b2749a6f8a1e2f1f2e77a9382092db5b",
    ),
    "wasm/vision_wasm_internal.wasm": (
        f"{CDN}/wasm/vision_wasm_internal.wasm",
        "f5bd25147ac89d506074293ce2675969b10e827180db95a0d9689c2ed80764ab",
    ),
    "face_landmarker.task": (MODELO, "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff"),
}


def pasta_destino() -> Path:
    return Path(settings.BASE_DIR) / "static" / "vendor" / "mediapipe"


class Command(BaseCommand):
    help = "Baixa os arquivos do provador virtual (MediaPipe), conferindo o SHA-256."

    def handle(self, *args, **opcoes):
        destino = pasta_destino()
        for nome, (url, esperado) in ARQUIVOS.items():
            caminho = destino / nome
            if caminho.is_file() and hashlib.sha256(caminho.read_bytes()).hexdigest() == esperado:
                self.stdout.write(f"ok (já existe): {nome}")
                continue
            pedido = urllib.request.Request(url, headers={"User-Agent": "Strong Glasses"})  # noqa: S310 (URL fixa)
            with urllib.request.urlopen(pedido, timeout=120) as resposta:  # noqa: S310
                conteudo = resposta.read()
            obtido = hashlib.sha256(conteudo).hexdigest()
            if obtido != esperado:
                raise CommandError(f"{nome}: SHA-256 não confere (esperado {esperado}, veio {obtido}). Nada gravado.")
            caminho.parent.mkdir(parents=True, exist_ok=True)
            caminho.write_bytes(conteudo)
            self.stdout.write(f"baixado: {nome} ({len(conteudo) // 1024} KB)")
        self.stdout.write(self.style.SUCCESS("Provador pronto. Rode collectstatic em produção."))
