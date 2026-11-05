"""Cliente mínimo da API da Nuvemshop (somente leitura), sem dependências externas.

Documentação: https://tiendanube.github.io/api-documentation/intro
- Autenticação: cabeçalho `Authorization: Bearer <token>`.
- User-Agent obrigatório (nome do app + contato).
- Paginação por `page`/`per_page` (máx. 200).
- Limite: balde de 40 requisições, esvazia 2 por segundo (HTTP 429 quando estoura).
"""

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)

POR_PAGINA = 200
MAX_TENTATIVAS = 6
ENDERECO_AUTORIZACAO = "https://www.tiendanube.com/apps/authorize/token"


class ErroNuvemshop(Exception):
    pass


class NuvemshopAPI:
    def __init__(self, store_id: str, token: str, user_agent: str, base_url: str, pausa: float = 0.5):
        if not store_id or not token:
            raise ImproperlyConfigured(
                "Defina NUVEMSHOP_STORE_ID e NUVEMSHOP_ACCESS_TOKEN no .env (veja docs/IMPORTACAO.md)."
            )
        self.base = f"{base_url.rstrip('/')}/{store_id}"
        self.cabecalhos = {
            "Authorization": f"Bearer {token}",
            "User-Agent": user_agent,
            "Content-Type": "application/json",
        }
        self.pausa = pausa

    @classmethod
    def das_configuracoes(cls) -> "NuvemshopAPI":
        return cls(
            settings.NUVEMSHOP_STORE_ID,
            settings.NUVEMSHOP_ACCESS_TOKEN,
            settings.NUVEMSHOP_USER_AGENT,
            settings.NUVEMSHOP_API_URL,
        )

    def _abrir(self, url: str):
        requisicao = urllib.request.Request(url, headers=self.cabecalhos, method="GET")  # noqa: S310
        return urllib.request.urlopen(requisicao, timeout=60)  # noqa: S310 (URL fixa https da API)

    def get(self, caminho: str, params: dict | None = None):
        """GET com novas tentativas em 429/5xx. Retorna (dados, cabeçalhos) ou None em 404."""
        url = f"{self.base}/{caminho.lstrip('/')}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        for tentativa in range(1, MAX_TENTATIVAS + 1):
            try:
                with self._abrir(url) as resposta:
                    return json.loads(resposta.read().decode("utf-8")), dict(resposta.headers)
            except urllib.error.HTTPError as erro:
                if erro.code == 404:
                    return None  # a API responde 404 depois da última página
                if erro.code == 429 or erro.code >= 500:
                    espera = self._espera(erro, tentativa)
                    logger.warning("Nuvemshop respondeu %s; aguardando %.1fs", erro.code, espera)
                    time.sleep(espera)
                    continue
                if erro.code in (401, 403):
                    raise ErroNuvemshop(
                        "Acesso negado pela Nuvemshop: confira o token e as permissões (escopos) do aplicativo."
                    ) from erro
                raise ErroNuvemshop(f"Erro {erro.code} ao acessar {caminho}.") from erro
            except urllib.error.URLError as erro:
                if tentativa == MAX_TENTATIVAS:
                    raise ErroNuvemshop(f"Sem conexão com a Nuvemshop: {erro.reason}") from erro
                time.sleep(2 * tentativa)
        raise ErroNuvemshop(f"A Nuvemshop não respondeu após {MAX_TENTATIVAS} tentativas ({caminho}).")

    @staticmethod
    def _espera(erro, tentativa: int) -> float:
        reset = erro.headers.get("x-rate-limit-reset") if erro.headers else None
        try:
            # O cabeçalho vem em milissegundos.
            return max(float(reset) / 1000, 1.0)
        except (TypeError, ValueError):
            return float(min(2**tentativa, 30))

    def paginar(self, caminho: str, params: dict | None = None) -> Iterator[dict]:
        pagina = 1
        while True:
            resultado = self.get(caminho, {**(params or {}), "page": pagina, "per_page": POR_PAGINA})
            if not resultado:
                return
            itens, _ = resultado
            if not itens:
                return
            yield from itens
            if len(itens) < POR_PAGINA:
                return
            pagina += 1
            time.sleep(self.pausa)


def trocar_codigo_por_token(codigo: str) -> dict:
    """Passo final do OAuth: troca o `code` recebido na instalação do app pelo token."""
    if not settings.NUVEMSHOP_CLIENT_ID or not settings.NUVEMSHOP_CLIENT_SECRET:
        raise ImproperlyConfigured("Defina NUVEMSHOP_CLIENT_ID e NUVEMSHOP_CLIENT_SECRET no .env.")
    corpo = json.dumps(
        {
            "client_id": settings.NUVEMSHOP_CLIENT_ID,
            "client_secret": settings.NUVEMSHOP_CLIENT_SECRET,
            "grant_type": "authorization_code",
            "code": codigo.strip(),
        }
    ).encode()
    requisicao = urllib.request.Request(
        ENDERECO_AUTORIZACAO,
        data=corpo,
        headers={"Content-Type": "application/json", "User-Agent": settings.NUVEMSHOP_USER_AGENT},
        method="POST",
    )
    try:
        with urllib.request.urlopen(requisicao, timeout=30) as resposta:  # noqa: S310
            dados = json.loads(resposta.read().decode("utf-8"))
    except urllib.error.HTTPError as erro:
        raise ErroNuvemshop(f"A Nuvemshop recusou o código (HTTP {erro.code}). Códigos valem só 5 minutos.") from erro
    if "access_token" not in dados:
        raise ErroNuvemshop(f"Resposta inesperada da Nuvemshop: {dados.get('error_description') or dados}")
    return dados
