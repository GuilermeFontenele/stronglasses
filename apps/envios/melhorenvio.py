"""Cliente mínimo da API do Melhor Envio (Correios, Jadlog, J&T...), sem dependências externas.

Documentação: https://docs.melhorenvio.com.br/
- OAuth2: token de acesso vale 30 dias, o de renovação 45. Renovamos sozinhos antes de vencer.
- User-Agent obrigatório: nome da aplicação + e-mail técnico.
- Nunca registre em log o corpo das requisições: tem nome, endereço e CPF do cliente.
"""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

BASES = {"sandbox": "https://sandbox.melhorenvio.com.br", "producao": "https://melhorenvio.com.br"}
# Só o necessário (princípio do menor privilégio).
ESCOPOS = (
    "cart-read cart-write shipping-calculate shipping-checkout shipping-generate "
    "shipping-print shipping-tracking shipping-cancel users-read"
)
TEMPO_LIMITE = 25


class ErroMelhorEnvio(Exception):
    """Erro com mensagem que pode ir para a tela (sem dado pessoal)."""

    def __init__(self, mensagem: str, status: int | None = None):
        self.status = status
        super().__init__(mensagem)


class NaoConectado(ErroMelhorEnvio):
    pass


def ambiente() -> str:
    valor = (settings.MELHOR_ENVIO_AMBIENTE or "sandbox").strip().lower()
    return valor if valor in BASES else "sandbox"


def base() -> str:
    return BASES[ambiente()]


def user_agent() -> str:
    return f"Strong Glasses ({settings.MELHOR_ENVIO_CONTATO})"


def configurado() -> bool:
    return bool(settings.MELHOR_ENVIO_CLIENT_ID and settings.MELHOR_ENVIO_CLIENT_SECRET)


def _mensagem_de_erro(corpo: bytes, status: int) -> str:
    try:
        dados = json.loads(corpo.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        dados = {}
    partes = []
    if isinstance(dados, dict):
        if dados.get("message") and dados.get("message") != "The given data was invalid.":
            partes.append(str(dados["message"]))
        if isinstance(dados.get("error"), str):
            partes.append(dados["error"])
        erros = dados.get("errors")
        if isinstance(erros, dict):
            for lista in erros.values():
                partes.extend(str(e) for e in (lista if isinstance(lista, list) else [lista]))
    if status == 401:
        return "O Melhor Envio recusou o acesso. Reconecte a conta em Integrações."
    texto = " ".join(dict.fromkeys(partes))[:400]
    return texto or f"O Melhor Envio respondeu com erro {status}."


def _requisicao(metodo: str, url: str, corpo=None, token: str | None = None, formulario: bool = False):
    cabecalhos = {"Accept": "application/json", "User-Agent": user_agent()}
    dados = None
    if corpo is not None:
        if formulario:
            dados = urllib.parse.urlencode(corpo).encode("utf-8")
            cabecalhos["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            dados = json.dumps(corpo).encode("utf-8")
            cabecalhos["Content-Type"] = "application/json"
    if token:
        cabecalhos["Authorization"] = f"Bearer {token}"
    pedido = urllib.request.Request(url, data=dados, headers=cabecalhos, method=metodo)  # noqa: S310
    try:
        with urllib.request.urlopen(pedido, timeout=TEMPO_LIMITE) as resposta:  # noqa: S310 (URL fixa https)
            conteudo = resposta.read()
            return json.loads(conteudo.decode("utf-8")) if conteudo else {}
    except urllib.error.HTTPError as erro:
        caminho = urllib.parse.urlsplit(url).path
        logger.warning("Melhor Envio respondeu %s em %s %s", erro.code, metodo, caminho)
        raise ErroMelhorEnvio(_mensagem_de_erro(erro.read(), erro.code), erro.code) from erro
    except (urllib.error.URLError, TimeoutError) as erro:
        logger.warning("Melhor Envio fora do ar ou sem rede: %s", type(erro).__name__)
        raise ErroMelhorEnvio("Não foi possível falar com o Melhor Envio agora. Tente de novo em instantes.") from erro


# ---------------------------------------------------------------- OAuth


def url_autorizacao(redirect_uri: str, state: str) -> str:
    parametros = {
        "client_id": settings.MELHOR_ENVIO_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "state": state,
        "scope": ESCOPOS,
    }
    return f"{base()}/oauth/authorize?{urllib.parse.urlencode(parametros, quote_via=urllib.parse.quote)}"


def _salvar_tokens(dados: dict):
    from .models import ConexaoMelhorEnvio

    if not dados.get("access_token"):
        raise ErroMelhorEnvio("O Melhor Envio não devolveu o token de acesso.")
    conexao, _ = ConexaoMelhorEnvio.objects.get_or_create(ambiente=ambiente())
    conexao.access_token = dados["access_token"]
    conexao.refresh_token = dados.get("refresh_token") or conexao.refresh_token
    segundos = int(dados.get("expires_in") or 30 * 24 * 3600)
    conexao.expira_em = timezone.now() + timedelta(seconds=segundos)
    conexao.save()
    return conexao


def trocar_codigo(codigo: str, redirect_uri: str):
    dados = _requisicao(
        "POST",
        f"{base()}/oauth/token",
        {
            "grant_type": "authorization_code",
            "client_id": settings.MELHOR_ENVIO_CLIENT_ID,
            "client_secret": settings.MELHOR_ENVIO_CLIENT_SECRET,
            "redirect_uri": redirect_uri,
            "code": codigo,
        },
        formulario=True,
    )
    return _salvar_tokens(dados)


def renovar(conexao):
    if not conexao.refresh_token:
        raise NaoConectado("A conexão com o Melhor Envio venceu. Reconecte em Integrações.")
    dados = _requisicao(
        "POST",
        f"{base()}/oauth/token",
        {
            "grant_type": "refresh_token",
            "refresh_token": conexao.refresh_token,
            "client_id": settings.MELHOR_ENVIO_CLIENT_ID,
            "client_secret": settings.MELHOR_ENVIO_CLIENT_SECRET,
        },
        formulario=True,
    )
    return _salvar_tokens(dados)


def conexao_atual():
    from .models import ConexaoMelhorEnvio

    return ConexaoMelhorEnvio.objects.filter(ambiente=ambiente()).first()


def token_valido() -> str:
    conexao = conexao_atual()
    if not conexao or not conexao.conectada:
        raise NaoConectado("Conecte a conta do Melhor Envio em Integrações para gerar etiquetas.")
    if conexao.perto_de_expirar:
        conexao = renovar(conexao)
    return conexao.access_token


# ---------------------------------------------------------------- API


class MelhorEnvio:
    def __init__(self, token: str | None = None):
        self.token = token or token_valido()

    def _chamar(self, metodo: str, caminho: str, corpo=None):
        return _requisicao(metodo, f"{base()}/api/v2/me/{caminho.lstrip('/')}", corpo, token=self.token)

    def calcular(self, cep_origem: str, cep_destino: str, volume: dict, seguro) -> list[dict]:
        """Cotação de um pacote. Devolve todas as opções, inclusive as indisponíveis (com 'erro')."""
        corpo = {
            "from": {"postal_code": cep_origem},
            "to": {"postal_code": cep_destino},
            "volumes": [{**volume, "insurance": float(seguro)}],
            "options": {"receipt": False, "own_hand": False},
        }
        resposta = self._chamar("POST", "shipment/calculate", corpo)
        return [_opcao(item) for item in (resposta if isinstance(resposta, list) else [])]

    def inserir_no_carrinho(self, corpo: dict) -> dict:
        return self._chamar("POST", "cart", corpo)

    def remover_do_carrinho(self, me_id: str):
        return self._chamar("DELETE", f"cart/{urllib.parse.quote(me_id)}")

    def comprar(self, me_id: str) -> dict:
        return self._chamar("POST", "shipment/checkout", {"orders": [me_id]})

    def gerar(self, me_id: str) -> dict:
        return self._chamar("POST", "shipment/generate", {"orders": [me_id]})

    def imprimir(self, me_id: str) -> str:
        resposta = self._chamar("POST", "shipment/print", {"mode": "public", "orders": [me_id]})
        return resposta.get("url", "")

    def dace(self, me_id: str) -> str:
        resposta = self._chamar("GET", f"imprimir/dace/pdf/{urllib.parse.quote(me_id)}")
        return resposta.get("pdf") or resposta.get("url", "")

    def rastrear(self, me_id: str) -> dict:
        resposta = self._chamar("POST", "shipment/tracking", {"orders": [me_id]})
        return resposta.get(me_id) or {}

    def cancelar(self, me_id: str) -> bool:
        corpo = {"order": {"id": me_id, "reason_id": "2", "description": "Cancelada pela loja"}}
        resposta = self._chamar("POST", "shipment/cancel", corpo)
        return bool((resposta.get(me_id) or {}).get("canceled"))

    def saldo(self):
        return self._chamar("GET", "balance").get("balance")

    def usuario(self) -> dict:
        return _requisicao("GET", f"{base()}/api/v2/me", token=self.token)


def _opcao(item: dict) -> dict:
    """Formato enxuto e seguro para guardar na sessão (só números e nomes de serviço)."""
    empresa = item.get("company") or {}
    faixa = item.get("custom_delivery_range") or item.get("delivery_range") or {}
    return {
        "id": int(item.get("id") or 0),
        "servico": str(item.get("name") or "")[:60],
        "transportadora": str(empresa.get("name") or "")[:60],
        "preco": str(item.get("custom_price") or item.get("price") or ""),
        "prazo": item.get("custom_delivery_time") or item.get("delivery_time"),
        "prazo_min": faixa.get("min"),
        "prazo_max": faixa.get("max"),
        "erro": str(item.get("error") or "")[:200],
    }
