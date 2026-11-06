"""Cotar, comprar, gerar, imprimir, rastrear e cancelar etiquetas pelo Melhor Envio.

Regras:
- O preço vem sempre de uma cotação feita no servidor na hora da compra (nunca do navegador).
- A etiqueta é paga com o saldo da conta do Melhor Envio; se a compra falhar, o item sai do carrinho.
- O corpo enviado tem dados pessoais do cliente (nome, endereço, CPF): nada disso vai para log.
"""

from decimal import Decimal

from django.utils import timezone

from apps.core.auditoria import foto, registrar
from apps.core.models import RegistroAuditoria
from apps.core.parametros import get_parametros
from apps.core.validators import so_digitos
from apps.vendas.models import Pedido
from apps.vendas.servicos import mudar_situacao, peso_do_pacote

from . import melhorenvio
from .melhorenvio import ErroMelhorEnvio, MelhorEnvio
from .models import Envio

PESO_PADRAO_G = 50


def remetente() -> dict:
    p = get_parametros(
        "REMETENTE_NOME",
        "REMETENTE_ENDERECO",
        "REMETENTE_NUMERO",
        "REMETENTE_COMPLEMENTO",
        "REMETENTE_BAIRRO",
        "REMETENTE_CIDADE",
        "REMETENTE_UF",
        "REMETENTE_CEP",
        "CNPJ_LOJA",
        "WHATSAPP_LOJA",
        "EMAIL_LOJA",
    )
    dados = {
        "nome": p["REMETENTE_NOME"] or "Strong Glasses",
        "endereco": (p["REMETENTE_ENDERECO"] or "").strip(),
        "numero": (p["REMETENTE_NUMERO"] or "").strip(),
        "complemento": (p["REMETENTE_COMPLEMENTO"] or "").strip(),
        "bairro": (p["REMETENTE_BAIRRO"] or "").strip(),
        "cidade": (p["REMETENTE_CIDADE"] or "").strip(),
        "uf": (p["REMETENTE_UF"] or "").strip().upper(),
        "cep": so_digitos(p["REMETENTE_CEP"] or ""),
        "documento": so_digitos(p["CNPJ_LOJA"] or ""),
        "telefone": so_digitos(p["WHATSAPP_LOJA"] or ""),
        "email": (p["EMAIL_LOJA"] or "").strip(),
    }
    dados["completo"] = all(dados[c] for c in ("endereco", "cidade", "uf")) and len(dados["cep"]) == 8
    return dados


def volume(pedido: Pedido, itens) -> dict:
    """Um pacote: medidas do produto (se for um só e tiver medidas) ou da embalagem padrão; peso somado."""
    p = get_parametros(
        "EMBALAGEM_ALTURA_CM",
        "EMBALAGEM_LARGURA_CM",
        "EMBALAGEM_COMPRIMENTO_CM",
        "PESO_PADRAO_G",
        padroes={
            "EMBALAGEM_ALTURA_CM": 5,
            "EMBALAGEM_LARGURA_CM": 10,
            "EMBALAGEM_COMPRIMENTO_CM": 18,
            "PESO_PADRAO_G": PESO_PADRAO_G,
        },
    )
    medidas = (p["EMBALAGEM_ALTURA_CM"], p["EMBALAGEM_LARGURA_CM"], p["EMBALAGEM_COMPRIMENTO_CM"])
    produtos = {item.produto_id: item.produto for item in itens if item.produto_id}
    if len(produtos) == 1 and sum(item.quantidade for item in itens) == 1:
        produto = next(iter(produtos.values()))
        if produto.pronto_para_envio:
            medidas = (produto.altura_cm, produto.largura_cm, produto.comprimento_cm)
    gramas = peso_do_pacote(pedido, itens, int(p["PESO_PADRAO_G"] or PESO_PADRAO_G))
    altura, largura, comprimento = (max(1, int(Decimal(str(m or 1)))) for m in medidas)
    return {"height": altura, "width": largura, "length": comprimento, "weight": round(max(gramas, 1) / 1000, 3)}


def _itens(pedido: Pedido):
    return list(pedido.itens.select_related("produto"))


def valor_dos_itens(itens) -> Decimal:
    return sum((item.subtotal for item in itens), Decimal("0.00"))


def pode_enviar(pedido: Pedido) -> str:
    """Motivo para não cotar/comprar (texto para a tela) ou vazio se está tudo certo."""
    if pedido.situacao == Pedido.Situacao.CANCELADO:
        return "Venda cancelada."
    if not pedido.tem_endereco or len(pedido.cep) != 8 or not pedido.uf:
        return "A venda está sem endereço completo (CEP, rua, cidade e estado)."
    if not remetente()["completo"]:
        return "Preencha o endereço do remetente em Configurações → Remetente."
    return ""


def cotar(pedido: Pedido, api: MelhorEnvio | None = None) -> list[dict]:
    motivo = pode_enviar(pedido)
    if motivo:
        raise ErroMelhorEnvio(motivo)
    api = api or MelhorEnvio()
    itens = _itens(pedido)
    opcoes = api.calcular(remetente()["cep"], pedido.cep, volume(pedido, itens), valor_dos_itens(itens))
    disponiveis = sorted((o for o in opcoes if not o["erro"] and o["preco"]), key=lambda o: Decimal(o["preco"]))
    return disponiveis + [o for o in opcoes if o["erro"] or not o["preco"]]


def montar_carrinho(pedido: Pedido, servico_id: int, documento: str, chave_nfe: str) -> dict:
    r = remetente()
    itens = _itens(pedido)
    cliente = pedido.cliente
    origem = {
        "name": r["nome"],
        "phone": r["telefone"][-11:],
        "email": r["email"],
        "company_document": r["documento"],
        "address": r["endereco"],
        "number": r["numero"] or "S/N",
        "complement": r["complemento"],
        "district": r["bairro"],
        "city": r["cidade"],
        "state_abbr": r["uf"],
        "country_id": "BR",
        "postal_code": r["cep"],
    }
    destino = {
        "name": pedido.destinatario or (cliente.nome if cliente else ""),
        "phone": so_digitos(cliente.whatsapp)[-11:] if cliente and cliente.whatsapp else "",
        "email": cliente.email if cliente else "",
        "address": pedido.logradouro,
        "number": pedido.numero_endereco or "S/N",
        "complement": pedido.complemento,
        "district": pedido.bairro,
        "city": pedido.cidade,
        "state_abbr": pedido.uf,
        "country_id": "BR",
        "postal_code": pedido.cep,
    }
    documento = so_digitos(documento)
    if len(documento) == 14:
        destino["company_document"] = documento
    elif documento:
        destino["document"] = documento
    opcoes = {
        "insurance_value": float(valor_dos_itens(itens)),
        "receipt": False,
        "own_hand": False,
        "reverse": False,
        "non_commercial": not chave_nfe,
        "platform": "Strong Glasses",
        "tags": [{"tag": pedido.codigo, "url": None}],
    }
    if chave_nfe:
        opcoes["invoice"] = {"key": chave_nfe}
    return {
        "service": servico_id,
        "from": origem,
        "to": destino,
        "products": [
            {
                "name": f"{item.nome} ({item.cor})"[:150] if item.cor else item.nome[:150],
                "quantity": item.quantidade,
                "unitary_value": float(item.preco_unitario),
            }
            for item in itens
        ],
        "volumes": [volume(pedido, itens)],
        "options": opcoes,
    }


def envio_ativo(pedido: Pedido) -> Envio | None:
    return pedido.envios.filter(status__in=Envio.ATIVOS).order_by("-criado_em").first()


def comprar_etiqueta(
    pedido: Pedido, servico_id: int, *, documento: str = "", chave_nfe: str = "", usuario=None, api=None
) -> Envio:
    if envio_ativo(pedido):
        raise ErroMelhorEnvio("Esta venda já tem uma etiqueta. Cancele a atual antes de comprar outra.")
    api = api or MelhorEnvio()
    escolhida = next((o for o in cotar(pedido, api) if o["id"] == servico_id and not o["erro"]), None)
    if not escolhida:
        raise ErroMelhorEnvio("Esse serviço não está mais disponível para este CEP. Cote de novo.")
    carrinho = api.inserir_no_carrinho(montar_carrinho(pedido, servico_id, documento, chave_nfe))
    if not carrinho.get("id"):
        raise ErroMelhorEnvio("O Melhor Envio não devolveu o número da etiqueta.")
    envio = Envio.objects.create(
        pedido=pedido,
        ambiente=melhorenvio.ambiente(),
        me_id=str(carrinho["id"])[:64],
        protocolo=str(carrinho.get("protocol") or "")[:40],
        transportadora=escolhida["transportadora"],
        servico=escolhida["servico"],
        servico_id=servico_id,
        preco=Decimal(str(carrinho.get("price") or escolhida["preco"])),
        prazo_dias=escolhida["prazo"],
        com_nota_fiscal=bool(chave_nfe),
    )
    registrar(RegistroAuditoria.Acao.CRIACAO, envio, None, foto(envio), usuario)
    try:
        api.comprar(envio.me_id)
    except ErroMelhorEnvio as erro:
        try:
            api.remover_do_carrinho(envio.me_id)
        except ErroMelhorEnvio:
            pass  # expira sozinho em 7 dias
        _atualizar(envio, usuario, status=Envio.Status.CANCELADO, cancelado_em=timezone.now(), erro=str(erro)[:255])
        raise ErroMelhorEnvio(f"Compra não concluída: {erro}") from erro
    _atualizar(envio, usuario, status=Envio.Status.PAGO, pago_em=timezone.now(), erro="")
    try:
        gerar(envio, api=api, usuario=usuario)
    except ErroMelhorEnvio:
        pass  # já ficou anotado no envio; a tela oferece "Gerar de novo"
    return envio


def _atualizar(envio: Envio, usuario, **campos):
    antes = foto(envio)
    for campo, valor in campos.items():
        setattr(envio, campo, valor)
    envio.save()
    registrar(RegistroAuditoria.Acao.ALTERACAO, envio, antes, foto(envio), usuario)


def gerar(envio: Envio, *, api=None, usuario=None) -> Envio:
    api = api or MelhorEnvio()
    try:
        resposta = api.gerar(envio.me_id)
    except ErroMelhorEnvio as erro:
        _atualizar(envio, usuario, erro=str(erro)[:255])
        raise
    item = resposta.get(envio.me_id) or {}
    if item.get("status") is False:
        mensagem = str(item.get("message") or "A transportadora recusou a geração da etiqueta.")
        _atualizar(envio, usuario, erro=mensagem[:255])
        raise ErroMelhorEnvio(mensagem)
    _atualizar(envio, usuario, status=Envio.Status.GERADO, gerado_em=timezone.now(), erro="")
    try:
        atualizar_rastreio(envio, api=api, usuario=usuario)
    except ErroMelhorEnvio:
        pass  # o código de rastreio às vezes demora alguns minutos para sair
    return envio


ESTADOS = {
    "posted": Envio.Status.POSTADO,
    "delivered": Envio.Status.ENTREGUE,
    "canceled": Envio.Status.CANCELADO,
    "cancelled": Envio.Status.CANCELADO,
}


def atualizar_rastreio(envio: Envio, *, api=None, usuario=None) -> Envio:
    """Busca o rastreio e a situação; leva para a venda (Enviado/Entregue) quando mudar."""
    api = api or MelhorEnvio()
    dados = api.rastrear(envio.me_id)
    rastreio = str(dados.get("tracking") or "").strip().upper()[:40]
    novo = ESTADOS.get(str(dados.get("status") or "").lower())
    campos = {}
    if rastreio and rastreio != envio.rastreio:
        campos["rastreio"] = rastreio
    if novo and novo != envio.status:
        campos["status"] = novo
        agora = timezone.now()
        campos[{"postado": "postado_em", "entregue": "entregue_em", "cancelado": "cancelado_em"}[novo]] = agora
    if campos:
        _atualizar(envio, usuario, **campos)
    pedido = Pedido.objects.get(pk=envio.pedido_id)
    if pedido.situacao == Pedido.Situacao.CANCELADO or envio.status == Envio.Status.CANCELADO:
        return envio
    situacao = pedido.situacao
    if envio.status == Envio.Status.POSTADO and pedido.situacao == Pedido.Situacao.PAGO:
        situacao = Pedido.Situacao.ENVIADO
    elif envio.status == Envio.Status.ENTREGUE:
        situacao = Pedido.Situacao.ENTREGUE
    if situacao != pedido.situacao or (envio.rastreio and envio.rastreio != pedido.codigo_rastreio):
        mudar_situacao(pedido, situacao, usuario=usuario, codigo_rastreio=envio.rastreio or None)
    return envio


def cancelar(envio: Envio, *, api=None, usuario=None) -> Envio:
    if not envio.pode_cancelar:
        raise ErroMelhorEnvio("Esta etiqueta não pode mais ser cancelada (já foi postada ou cancelada).")
    api = api or MelhorEnvio()
    if envio.status == Envio.Status.CARRINHO:
        api.remover_do_carrinho(envio.me_id)
    elif not api.cancelar(envio.me_id):
        raise ErroMelhorEnvio("O Melhor Envio não aceitou o cancelamento. Veja a etiqueta no painel deles.")
    _atualizar(envio, usuario, status=Envio.Status.CANCELADO, cancelado_em=timezone.now())
    pedido = Pedido.objects.get(pk=envio.pedido_id)
    if envio.rastreio and pedido.codigo_rastreio == envio.rastreio:
        mudar_situacao(pedido, pedido.situacao, usuario=usuario, codigo_rastreio="")
    return envio
