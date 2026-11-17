"""Checkout do site: frete, criação do pedido e pagamento (Pix e cartão) no Mercado Pago.

Regras (CLAUDE.md):
- Valores sempre calculados no servidor: preço → desconto → Pix → frete (o Pix nunca incide no frete).
- O estoque sai na criação do pedido e volta se ele não for pago no prazo (expirar_pendentes).
- Pedido só vira "pago" com a situação confirmada na API do Mercado Pago e com o valor batendo.
"""

import hashlib
import logging
import secrets
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.clientes.models import Cliente, Endereco
from apps.core.auditoria import foto, registrar
from apps.core.crypto import hash_busca
from apps.core.models import RegistroAuditoria
from apps.core.parametros import get_parametros
from apps.core.validators import so_digitos
from apps.envios import melhorenvio
from apps.envios import servicos as envios
from apps.envios.melhorenvio import ErroMelhorEnvio
from apps.vendas import avisos
from apps.vendas.models import Pedido, sigla_uf
from apps.vendas.servicos import ItemNovo, calcular, mudar_situacao, reativar, registrar_venda

from . import mercadopago
from .mercadopago import ErroMercadoPago
from .models import Pagamento

logger = logging.getLogger(__name__)
ZERO = Decimal("0.00")
MAXIMO_TENTATIVAS_CARTAO = 5
PARAMETROS_FRETE = {
    "FRETE_LOCAL_CEPS": "60000000-60999999",
    "FRETE_MOTOBOY_PRECO": Decimal("10.00"),
    "FRETE_GRATIS_LOCAL_ACIMA": Decimal("300.00"),
    "FRETE_GRATIS_ACIMA": Decimal("0"),
    "PIX_EXPIRACAO_MINUTOS": 30,
    "PARCELAS_SEM_JUROS": 3,
}


def _parametros() -> dict:
    return get_parametros(*PARAMETROS_FRETE, padroes=PARAMETROS_FRETE)


# ---------------------------------------------------------------- frete


def cep_local(cep: str, faixas: str | None = None) -> bool:
    """CEP dentro das faixas de entrega local (motoboy). Ex.: "60000000-60999999, 61600000-61619999"."""
    cep = so_digitos(cep)
    if len(cep) != 8:
        return False
    faixas = faixas if faixas is not None else str(_parametros()["FRETE_LOCAL_CEPS"] or "")
    for faixa in faixas.replace(";", ",").split(","):
        inicio, _, fim = faixa.strip().partition("-")
        inicio, fim = so_digitos(inicio), so_digitos(fim or inicio)
        if len(inicio) == 8 and len(fim) == 8 and int(inicio) <= int(cep) <= int(fim):
            return True
    return False


def _prazo(minimo, maximo, dias) -> str:
    if minimo and maximo and minimo != maximo:
        return f"{minimo} a {maximo} dias úteis"
    dias = int(maximo or dias or 0)
    if not dias:
        return ""
    return "1 dia útil" if dias == 1 else f"{dias} dias úteis"


def opcoes_de_frete(cep: str, linhas) -> list[dict]:
    """Opções para o CEP: motoboy (só faixas locais) e as transportadoras do Melhor Envio."""
    cep = so_digitos(cep)
    p = _parametros()
    subtotal = sum((linha.subtotal for linha in linhas), ZERO)
    opcoes = []
    if cep_local(cep, str(p["FRETE_LOCAL_CEPS"] or "")):
        gratis = subtotal >= Decimal(str(p["FRETE_GRATIS_LOCAL_ACIMA"] or 0)) > 0
        preco = ZERO if gratis else Decimal(str(p["FRETE_MOTOBOY_PRECO"] or 0)).quantize(Decimal("0.01"))
        opcoes.append(
            {
                "id": "motoboy",
                "nome": "Motoboy (Fortaleza)" + (" · frete grátis" if gratis else ""),
                "preco": str(preco),
                "prazo": "1 a 2 dias úteis",
                "entrega": Pedido.Entrega.MOTOBOY,
                "servico_id": None,
            }
        )
    conexao = melhorenvio.conexao_atual()
    if conexao and conexao.conectada:
        itens = [
            SimpleNamespace(
                produto=linha.variacao.produto, produto_id=linha.variacao.produto_id, quantidade=linha.quantidade
            )
            for linha in linhas
        ]
        try:
            for o in envios.simular(cep, itens, subtotal):
                if o["erro"] or not o["preco"]:
                    continue
                opcoes.append(
                    {
                        "id": f"me:{o['id']}",
                        "nome": f"{o['transportadora']} {o['servico']}",
                        "preco": str(Decimal(o["preco"]).quantize(Decimal("0.01"))),
                        "prazo": _prazo(o["prazo_min"], o["prazo_max"], o["prazo"]),
                        "entrega": Pedido.Entrega.CORREIOS
                        if o["transportadora"].lower() == "correios"
                        else Pedido.Entrega.TRANSPORTADORA,
                        "servico_id": o["id"],
                    }
                )
        except ErroMelhorEnvio as erro:
            logger.warning("Cotação de frete do checkout falhou: %s", type(erro).__name__)
    # Frete grátis geral (Configurações → Vendas): a loja paga a transportadora mais barata.
    acima = Decimal(str(p["FRETE_GRATIS_ACIMA"] or 0))
    transportadoras = [o for o in opcoes if o["id"].startswith("me:")]
    if acima > 0 and subtotal >= acima and transportadoras:
        mais_barata = min(transportadoras, key=lambda o: Decimal(o["preco"]))
        mais_barata["preco"] = "0.00"
        mais_barata["nome"] += " · frete grátis"
    return sorted(opcoes, key=lambda o: Decimal(o["preco"]))


def assinatura_do_carrinho(cep: str, linhas) -> str:
    base = so_digitos(cep) + "|" + ",".join(f"{linha.variacao.pk}x{linha.quantidade}" for linha in linhas)
    return hashlib.sha256(base.encode()).hexdigest()[:24]


# ---------------------------------------------------------------- cliente e pedido


def cliente_do_checkout(*, nome: str, email: str, whatsapp: str, cpf: str) -> tuple[Cliente, bool]:
    """Liga o pedido a um cadastro, sem nunca alterar um cadastro que já existe.

    Ordem: mesmo CPF (identifica a pessoa) → mesmo e-mail → cadastro novo. Devolve (cliente, confiavel):
    "confiavel" é falso quando só o e-mail bateu, porque qualquer um pode digitar o e-mail de outra pessoa.
    Nesse caso o pedido usa só os dados digitados nesta compra e nada do cadastro antigo aparece para quem compra.
    """
    email = email.strip().lower()
    ativos = Cliente.objects.filter(anonimizado_em__isnull=True)
    por_cpf = ativos.filter(documento_hash=hash_busca(cpf)).first()
    if por_cpf:
        return por_cpf, True
    por_email = ativos.filter(email__iexact=email).first()
    if por_email:
        return por_email, False
    cliente = Cliente(nome=nome, email=email, whatsapp=whatsapp, documento=cpf)
    cliente.full_clean()
    try:
        with transaction.atomic():
            cliente.save()
    except IntegrityError:  # dois envios ao mesmo tempo (clique duplo): o outro já criou
        existente = ativos.filter(documento_hash=hash_busca(cpf)).first() or ativos.filter(email__iexact=email).first()
        if existente is None:
            raise
        return existente, False
    registrar(RegistroAuditoria.Acao.CRIACAO, cliente, None, foto(cliente), None)
    return cliente, True


def _salvar_endereco(cliente: Cliente, dados: dict):
    if cliente.enderecos.filter(cep=dados["cep"], logradouro=dados["logradouro"], numero=dados["numero"]).exists():
        return
    Endereco.objects.create(
        cliente=cliente,
        destinatario=dados["nome"],
        cep=dados["cep"],
        logradouro=dados["logradouro"],
        numero=dados["numero"],
        complemento=dados["complemento"],
        bairro=dados["bairro"],
        cidade=dados["cidade"],
        uf=dados["uf"],
        padrao=not cliente.enderecos.exists(),
    )


def criar_pedido(linhas, dados: dict, frete: dict, origem: dict | None = None, base_url: str = "") -> Pedido:
    """Pedido do site, pendente, com o estoque reservado. `frete` é uma opção de opcoes_de_frete()."""
    cliente, confiavel = cliente_do_checkout(
        nome=dados["nome"], email=dados["email"], whatsapp=dados["whatsapp"], cpf=dados["cpf"]
    )
    if confiavel:
        _salvar_endereco(cliente, dados)
    origem = origem or {}
    prazo = int(_parametros()["PIX_EXPIRACAO_MINUTOS"] or 30)
    pedido = Pedido(
        cliente=cliente,
        canal=Pedido.Canal.SITE,
        situacao=Pedido.Situacao.PENDENTE,
        forma_pagamento=dados["forma"],
        entrega=frete["entrega"],
        frete=Decimal(frete["preco"]),
        frete_servico_id=frete["servico_id"],
        frete_servico=frete["nome"][:80],
        destinatario=dados["nome"][:150],
        email=dados["email"],
        whatsapp=dados["whatsapp"],
        documento=dados["cpf"],
        cep=dados["cep"],
        logradouro=dados["logradouro"],
        numero_endereco=dados["numero"],
        complemento=dados["complemento"],
        bairro=dados["bairro"],
        cidade=dados["cidade"],
        uf=sigla_uf(dados["uf"]) or dados["uf"][:2].upper(),
        ref=str(origem.get("ref", ""))[:60],
        utm_source=str(origem.get("utm_source", ""))[:100],
        utm_medium=str(origem.get("utm_medium", ""))[:100],
        utm_campaign=str(origem.get("utm_campaign", ""))[:100],
        token_acesso=secrets.token_urlsafe(32),
        expira_em=timezone.now() + timedelta(minutes=prazo),
    )
    itens = [ItemNovo(linha.variacao, linha.quantidade) for linha in linhas]
    pedido = registrar_venda(
        pedido, itens, baixar_estoque=True, aplicar_pix=dados["forma"] == Pedido.FormaPagamento.PIX
    )
    avisos.avisar(pedido, "recebido", base_url)
    return pedido


@transaction.atomic
def mudar_forma(pedido: Pedido, forma: str) -> Pedido:
    """Troca Pix ↔ cartão num pedido pendente e recalcula o total (o desconto do Pix entra ou sai)."""
    pedido = Pedido.objects.select_for_update().get(pk=pedido.pk)
    if pedido.situacao != Pedido.Situacao.PENDENTE or pedido.forma_pagamento == forma:
        return pedido
    antes = foto(pedido)
    valores = calcular(pedido.subtotal, pedido.desconto, pedido.frete, aplicar_pix=forma == Pedido.FormaPagamento.PIX)
    pedido.forma_pagamento = forma
    pedido.desconto_pix = valores["desconto_pix"]
    pedido.total = valores["total"]
    pedido.save()
    registrar(RegistroAuditoria.Acao.ALTERACAO, pedido, antes, foto(pedido), None)
    return pedido


# ---------------------------------------------------------------- pagamento


def _url_aviso() -> str | None:
    base = settings.SITE_URL
    if base.startswith("https://"):
        from django.urls import reverse

        return base + reverse("pagamentos:webhook")
    return None


def _pagador(pedido: Pedido) -> dict:
    """Quem paga: os dados digitados nesta compra (nunca os de um cadastro antigo)."""
    nome = pedido.destinatario.split()
    pagador = {"email": pedido.email, "first_name": nome[0] if nome else ""}
    if len(nome) > 1:
        pagador["last_name"] = " ".join(nome[1:])
    if pedido.documento:
        tipo = "CNPJ" if len(pedido.documento) == 14 else "CPF"
        pagador["identification"] = {"type": tipo, "number": pedido.documento}
    return pagador


def _info_adicional(pedido: Pedido) -> dict:
    return {
        "items": [
            {
                "id": item.sku or str(item.variacao_id or item.pk),
                "title": f"{item.nome} ({item.cor})"[:250] if item.cor else item.nome[:250],
                "quantity": item.quantidade,
                "unit_price": float(item.preco_unitario),
                "category_id": "fashion",
            }
            for item in pedido.itens.all()
        ],
        "shipments": {
            "receiver_address": {
                "zip_code": pedido.cep,
                "street_name": pedido.logradouro,
                "street_number": pedido.numero_endereco or "S/N",
                "city_name": pedido.cidade,
                "state_name": pedido.uf,
            }
        },
    }


def _corpo_base(pedido: Pedido) -> dict:
    corpo = {
        "transaction_amount": float(pedido.total),
        "description": f"Pedido {pedido.codigo} · Strong Glasses",
        "external_reference": pedido.codigo,
        "additional_info": _info_adicional(pedido),
    }
    aviso = _url_aviso()
    if aviso:
        corpo["notification_url"] = aviso
    return corpo


def _pagavel(pedido: Pedido):
    if pedido.situacao != Pedido.Situacao.PENDENTE:
        raise ErroMercadoPago("Este pedido não está aguardando pagamento.")
    if pedido.expira_em and pedido.expira_em < timezone.now():
        raise ErroMercadoPago("O prazo para pagar este pedido acabou. Monte o carrinho de novo.")


def pagar_pix(pedido: Pedido) -> Pagamento:
    """QR Code do Pix do pedido. Reaproveita o que ainda vale (mesmo valor e no prazo)."""
    _pagavel(pedido)
    atual = pedido.pagamentos.filter(
        metodo=Pagamento.Metodo.PIX, status=Pagamento.Status.PENDENTE, valor=pedido.total, expira_em__gt=timezone.now()
    ).first()
    if atual:
        return atual
    tentativas = pedido.pagamentos.filter(metodo=Pagamento.Metodo.PIX).count()
    corpo = {
        **_corpo_base(pedido),
        "payment_method_id": "pix",
        "payer": _pagador(pedido),
        "date_of_expiration": timezone.localtime(pedido.expira_em).isoformat(timespec="milliseconds"),
    }
    chave = f"pix-{pedido.token_acesso[:20]}-{pedido.total}-{tentativas}"
    dados = mercadopago.criar_pagamento(corpo, chave)
    return _registrar(pedido, dados, Pagamento.Metodo.PIX)


def pagar_cartao(pedido: Pedido, formulario: dict) -> Pagamento:
    """Cartão com o token gerado pelo Brick no navegador. O valor e o limite de parcelas são da loja."""
    _pagavel(pedido)
    token = str(formulario.get("token") or "")
    metodo = str(formulario.get("payment_method_id") or "")
    parcelas = formulario.get("installments")
    maximo = max(int(_parametros()["PARCELAS_SEM_JUROS"] or 1), 1)
    if not token or not metodo or len(token) > 100 or len(metodo) > 30:
        raise ErroMercadoPago("Dados do cartão incompletos. Confira e tente de novo.")
    try:
        parcelas = int(parcelas)
    except (TypeError, ValueError):
        parcelas = 1
    if not 1 <= parcelas <= maximo:
        raise ErroMercadoPago(f"Parcelamos em até {maximo}x.")
    # Freia quem usa o checkout para testar cartões roubados.
    if pedido.pagamentos.filter(metodo=Pagamento.Metodo.CARTAO).count() >= MAXIMO_TENTATIVAS_CARTAO:
        raise ErroMercadoPago("Muitas tentativas com cartão neste pedido. Pague com Pix ou fale com a gente.")
    pedido = mudar_forma(pedido, Pedido.FormaPagamento.CREDITO)
    pagador = _pagador(pedido)
    identificacao = ((formulario.get("payer") or {}).get("identification")) or {}
    numero = so_digitos(str(identificacao.get("number") or ""))
    if numero:
        pagador["identification"] = {"type": str(identificacao.get("type") or "CPF")[:10], "number": numero[:14]}
    email = str(((formulario.get("payer") or {}).get("email")) or "")
    if email and "@" in email and len(email) <= 254:
        pagador["email"] = email
    corpo = {
        **_corpo_base(pedido),
        "token": token,
        "installments": parcelas,
        "payment_method_id": metodo,
        "payer": pagador,
        "statement_descriptor": "STRONGGLASSES",
    }
    emissor = str(formulario.get("issuer_id") or "")
    if emissor.isdigit():
        corpo["issuer_id"] = int(emissor)
    chave = "cartao-" + hashlib.sha256(token.encode()).hexdigest()[:40]
    dados = mercadopago.criar_pagamento(corpo, chave)
    return _registrar(pedido, dados, Pagamento.Metodo.CARTAO)


def _registrar(pedido: Pedido, dados: dict, metodo: str) -> Pagamento:
    if not dados.get("id"):
        raise ErroMercadoPago("O Mercado Pago não devolveu o pagamento. Tente de novo.")
    pagamento, criado = Pagamento.objects.get_or_create(
        provedor_id=str(dados["id"]),
        defaults={"pedido": pedido, "metodo": metodo, "valor": pedido.total},
    )
    if criado:
        registrar(RegistroAuditoria.Acao.CRIACAO, pagamento, None, foto(pagamento), None)
    return aplicar(pagamento, dados)


def aplicar(pagamento: Pagamento, dados: dict) -> Pagamento:
    """Leva a situação do Mercado Pago para o pagamento e para o pedido. Idempotente."""
    transacao = (dados.get("point_of_interaction") or {}).get("transaction_data") or {}
    expira = parse_datetime(str(dados.get("date_of_expiration") or "")) if dados.get("date_of_expiration") else None
    valor = Decimal(str(dados.get("transaction_amount") or pagamento.valor)).quantize(Decimal("0.01"))
    with transaction.atomic():
        pagamento = Pagamento.objects.select_for_update().get(pk=pagamento.pk)
        antes = foto(pagamento)
        pagamento.status = str(dados.get("status") or pagamento.status)[:20]
        pagamento.status_detalhe = str(dados.get("status_detail") or "")[:80]
        pagamento.valor = valor
        pagamento.parcelas = int(dados.get("installments") or pagamento.parcelas or 1)
        pagamento.bandeira = str(dados.get("payment_method_id") or pagamento.bandeira)[:30]
        if transacao.get("qr_code"):
            pagamento.pix_copia_e_cola = str(transacao["qr_code"])
            pagamento.pix_qr_base64 = str(transacao.get("qr_code_base64") or "")
        if expira:
            pagamento.expira_em = expira
        if pagamento.status == Pagamento.Status.APROVADO and not pagamento.aprovado_em:
            pagamento.aprovado_em = timezone.now()
        pagamento.save()
        if foto(pagamento) != antes:
            registrar(RegistroAuditoria.Acao.ALTERACAO, pagamento, antes, foto(pagamento), None)
        if pagamento.status == Pagamento.Status.APROVADO:
            _confirmar(Pedido.objects.select_for_update().get(pk=pagamento.pedido_id), pagamento)
    return pagamento


def total_para(pedido: Pedido, metodo: str) -> dict:
    """Total do pedido se for pago com `metodo` ("pix" ou "credito"): o desconto do Pix entra ou sai."""
    if pedido.forma_pagamento == metodo:
        return {"desconto_pix": pedido.desconto_pix, "total": pedido.total}
    return calcular(pedido.subtotal, pedido.desconto, pedido.frete, aplicar_pix=metodo == Pedido.FormaPagamento.PIX)


def _confirmar(pedido: Pedido, pagamento: Pagamento) -> None:
    """Dinheiro aprovado no Mercado Pago: marca o pedido como pago se o valor bater.

    O valor certo depende da forma usada: quem gerou o Pix e depois abriu a tela do cartão ainda pode
    pagar aquele Pix (com desconto). E se o pedido já tinha sido cancelado por prazo, ele é reativado
    quando ainda há estoque. O que não fechar fica como alerta no painel para alguém conferir.
    """
    if pedido.canal != Pedido.Canal.SITE or pedido.situacao not in (
        Pedido.Situacao.PENDENTE,
        Pedido.Situacao.CANCELADO,
    ):
        return
    esperado = total_para(pedido, pagamento.metodo)
    if pagamento.valor != esperado["total"]:
        logger.error("Pagamento %s aprovado com valor diferente do pedido %s", pagamento.pk, pedido.pk)
        return
    if pedido.situacao == Pedido.Situacao.CANCELADO:
        motivo = "Reativado sozinho: o pagamento foi aprovado depois do cancelamento."
        if not reativar(pedido, motivo=motivo):
            logger.error("Pagamento %s aprovado em pedido cancelado sem estoque (%s)", pagamento.pk, pedido.pk)
            return
        pedido.refresh_from_db()
    pedido.forma_pagamento = pagamento.metodo  # "pix" ou "credito", os mesmos valores do pedido
    pedido.desconto_pix, pedido.total = esperado["desconto_pix"], esperado["total"]
    pedido.parcelas = pagamento.parcelas
    pedido.save(update_fields=["forma_pagamento", "desconto_pix", "total", "parcelas", "atualizado_em"])
    mudar_situacao(pedido, Pedido.Situacao.PAGO)


def para_conferir():
    """Pagamentos que pedem olho humano: dinheiro aprovado sem pedido pago, ou estorno/contestação de pedido pago."""
    aprovado_sem_pedido = Q(status=Pagamento.Status.APROVADO) & ~Q(pedido__situacao__in=Pedido.PAGOS)
    devolvido = Q(
        status__in=[Pagamento.Status.ESTORNADO, Pagamento.Status.CONTESTADO, Pagamento.Status.EM_MEDIACAO],
        pedido__situacao__in=Pedido.PAGOS,
    )
    return Pagamento.objects.filter(aprovado_sem_pedido | devolvido).select_related("pedido")


def sincronizar(provedor_id: str) -> Pagamento | None:
    """Busca a situação na API (fonte da verdade) e aplica. Usado pelo webhook e pela tela do pedido."""
    dados = mercadopago.consultar(provedor_id)
    pagamento = Pagamento.objects.filter(provedor_id=str(dados.get("id") or provedor_id)).first()
    if pagamento is None:
        codigo = str(dados.get("external_reference") or "")
        numero = codigo.upper().removeprefix("SG")
        pedido = Pedido.objects.filter(numero=int(numero)).first() if numero.isdigit() else None
        if pedido is None or pedido.canal != Pedido.Canal.SITE:
            return None
        metodo = Pagamento.Metodo.PIX if dados.get("payment_method_id") == "pix" else Pagamento.Metodo.CARTAO
        return _registrar(pedido, dados, metodo)
    return aplicar(pagamento, dados)


def atualizar_pedido(pedido: Pedido) -> Pedido:
    """Para a tela do pedido: confere na API os pagamentos ainda em aberto."""
    for pagamento in pedido.pagamentos.filter(status__in=[Pagamento.Status.PENDENTE, Pagamento.Status.EM_ANALISE]):
        try:
            sincronizar(pagamento.provedor_id)
        except ErroMercadoPago:
            break
    pedido.refresh_from_db()
    return pedido


def cancelar_pedido(pedido: Pedido, *, usuario=None, mesmo_pago: bool = False) -> Pedido:
    """Cancela o pedido (o estoque volta) e as cobranças ainda abertas no Mercado Pago, para o Pix
    antigo não poder ser pago depois. Não devolve dinheiro: estorno de pedido pago é feito no Mercado Pago."""
    abertos = pedido.pagamentos.filter(status__in=[Pagamento.Status.PENDENTE, Pagamento.Status.AUTORIZADO])
    for pagamento in abertos:
        try:
            aplicar(pagamento, mercadopago.cancelar(pagamento.provedor_id))
        except ErroMercadoPago:
            pass  # a cobrança vence sozinha no prazo do pedido
    pedido.refresh_from_db()
    if pedido.situacao == Pedido.Situacao.CANCELADO or (pedido.pago and not mesmo_pago):
        return pedido
    return mudar_situacao(pedido, Pedido.Situacao.CANCELADO, usuario=usuario)


def expirar(pedido: Pedido) -> bool:
    """Cancela o pedido não pago no prazo e devolve o estoque. Confere a API antes. True se cancelou."""
    pedido = atualizar_pedido(pedido)
    if pedido.situacao != Pedido.Situacao.PENDENTE:
        return False
    if pedido.pagamentos.filter(status=Pagamento.Status.EM_ANALISE).exists():
        return False  # cartão em análise: espera a resposta
    return cancelar_pedido(pedido).situacao == Pedido.Situacao.CANCELADO


def expirar_pendentes(margem_minutos: int = 5) -> int:
    limite = timezone.now() - timedelta(minutes=margem_minutos)
    vencidos = Pedido.objects.filter(canal=Pedido.Canal.SITE, situacao=Pedido.Situacao.PENDENTE, expira_em__lt=limite)
    return sum(expirar(pedido) for pedido in vencidos)


MENSAGENS_RECUSA = {
    "cc_rejected_bad_filled_card_number": "Confira o número do cartão.",
    "cc_rejected_bad_filled_date": "Confira a data de validade.",
    "cc_rejected_bad_filled_security_code": "Confira o código de segurança.",
    "cc_rejected_bad_filled_other": "Confira os dados do cartão.",
    "cc_rejected_insufficient_amount": "O cartão não tem limite suficiente.",
    "cc_rejected_call_for_authorize": "Autorize o pagamento com o banco do cartão e tente de novo.",
    "cc_rejected_card_disabled": "Ative o cartão com o banco e tente de novo.",
    "cc_rejected_duplicated_payment": "Você já fez um pagamento com esse valor. Para pagar de novo, use outro cartão.",
    "cc_rejected_high_risk": "O pagamento foi recusado. Tente outro cartão ou pague com Pix.",
    "cc_rejected_max_attempts": "Limite de tentativas atingido. Tente outro cartão ou pague com Pix.",
}


def mensagem_recusa(pagamento: Pagamento) -> str:
    return MENSAGENS_RECUSA.get(
        pagamento.status_detalhe, "O banco recusou o pagamento. Tente outro cartão ou pague com Pix."
    )
