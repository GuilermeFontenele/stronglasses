"""Regras de venda: totais (ordem do CLAUDE.md), numeração e estoque. Tudo no servidor, em transação."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from django.db import IntegrityError, transaction
from django.db.models import F, Max
from django.utils import timezone

from apps.catalogo.models import Variacao
from apps.core.auditoria import foto, registrar
from apps.core.models import RegistroAuditoria
from apps.core.parametros import get_parametro

from .models import ZERO, ItemPedido, Pedido

CENTAVO = Decimal("0.01")


class EstoqueInsuficiente(Exception):
    def __init__(self, faltas: list[str]):
        self.faltas = faltas
        super().__init__("; ".join(faltas))


@dataclass
class ItemNovo:
    variacao: Variacao
    quantidade: int
    preco_unitario: Decimal | None = None  # vazio = preço atual da variação


def calcular(subtotal: Decimal, desconto: Decimal, frete: Decimal, aplicar_pix: bool) -> dict:
    """preço → (promoção/cupom = desconto) → Pix → frete. O Pix nunca incide sobre o frete."""
    base = max(subtotal - (desconto or ZERO), ZERO)
    percentual = Decimal(str(get_parametro("PIX_DESCONTO_PERCENTUAL", 0) or 0)) if aplicar_pix else ZERO
    desconto_pix = (base * percentual / 100).quantize(CENTAVO, ROUND_HALF_UP)
    return {"desconto_pix": desconto_pix, "total": (base - desconto_pix + (frete or ZERO)).quantize(CENTAVO)}


def _proximo_numero() -> int:
    return (Pedido.objects.aggregate(m=Max("numero"))["m"] or 0) + 1


def registrar_venda(
    pedido: Pedido, itens: list[ItemNovo], *, baixar_estoque: bool, aplicar_pix: bool, usuario=None
) -> Pedido:
    if not itens:
        raise ValueError("A venda precisa de pelo menos um item.")
    for tentativa in range(3):
        try:
            with transaction.atomic():
                return _registrar(pedido, itens, baixar_estoque, aplicar_pix, usuario)
        except IntegrityError:  # dois lançamentos ao mesmo tempo pegaram o mesmo número
            pedido.pk = None
            if tentativa == 2:
                raise
    raise RuntimeError("inalcançável")


def _registrar(pedido, itens, baixar_estoque, aplicar_pix, usuario):
    ids = [item.variacao.pk for item in itens]
    variacoes = {v.pk: v for v in Variacao.objects.select_for_update().select_related("produto").filter(pk__in=ids)}
    quantidades: dict[int, int] = {}
    for item in itens:
        quantidades[item.variacao.pk] = quantidades.get(item.variacao.pk, 0) + item.quantidade
    if baixar_estoque:
        faltas = [
            f"{variacoes[pk].produto.nome} ({variacoes[pk].descricao_cor.lower()}): pedido {qtd}, "
            f"em estoque {variacoes[pk].estoque}"
            for pk, qtd in quantidades.items()
            if variacoes[pk].estoque < qtd
        ]
        if faltas:
            raise EstoqueInsuficiente(faltas)

    linhas = []
    for item in itens:
        variacao = variacoes[item.variacao.pk]
        preco = item.preco_unitario if item.preco_unitario is not None else variacao.preco_final
        linhas.append(
            ItemPedido(
                variacao=variacao,
                produto=variacao.produto,
                nome=variacao.produto.nome[:150],
                cor=variacao.descricao_cor[:150],
                sku=variacao.sku,
                quantidade=item.quantidade,
                preco_unitario=preco,
            )
        )
    pedido.subtotal = sum((linha.subtotal for linha in linhas), ZERO).quantize(CENTAVO)
    valores = calcular(pedido.subtotal, pedido.desconto, pedido.frete, aplicar_pix)
    pedido.desconto_pix, pedido.total = valores["desconto_pix"], valores["total"]
    pedido.numero = _proximo_numero()
    pedido.realizado_em = pedido.realizado_em or timezone.now()
    if pedido.pago:
        pedido.pago_em = timezone.now()
    if pedido.situacao in (Pedido.Situacao.ENVIADO, Pedido.Situacao.ENTREGUE):
        pedido.enviado_em = timezone.now()
    pedido.estoque_baixado = baixar_estoque
    pedido.save()
    for linha in linhas:
        linha.pedido = pedido
    ItemPedido.objects.bulk_create(linhas)
    if baixar_estoque:
        for pk, qtd in quantidades.items():
            Variacao.objects.filter(pk=pk).update(estoque=F("estoque") - qtd)
    registrar(RegistroAuditoria.Acao.CRIACAO, pedido, None, foto(pedido), usuario)
    return pedido


@transaction.atomic
def mudar_situacao(pedido: Pedido, nova: str, *, usuario=None, codigo_rastreio: str | None = None) -> Pedido:
    pedido = Pedido.objects.select_for_update().get(pk=pedido.pk)
    antes = foto(pedido)
    agora = timezone.now()
    if nova == Pedido.Situacao.CANCELADO and pedido.situacao != Pedido.Situacao.CANCELADO:
        if pedido.estoque_baixado:  # devolve o que saiu do estoque
            for item in pedido.itens.exclude(variacao__isnull=True):
                Variacao.objects.filter(pk=item.variacao_id).update(estoque=F("estoque") + item.quantidade)
            pedido.estoque_baixado = False
        pedido.cancelado_em = agora
    if nova in Pedido.PAGOS and not pedido.pago_em:
        pedido.pago_em = agora
    if nova in (Pedido.Situacao.ENVIADO, Pedido.Situacao.ENTREGUE) and not pedido.enviado_em:
        pedido.enviado_em = agora
    if codigo_rastreio is not None:
        pedido.codigo_rastreio = codigo_rastreio.strip().upper()[:40]
    pedido.situacao = nova
    pedido.save()
    registrar(RegistroAuditoria.Acao.ALTERACAO, pedido, antes, foto(pedido), usuario)
    return pedido


def peso_do_pacote(pedido: Pedido, itens, padrao: int) -> int:
    """Gramas: o peso informado na venda ou a soma do peso cadastrado dos produtos (padrão para quem não tem)."""
    if pedido.peso_g:
        return pedido.peso_g
    return sum(
        (item.produto.peso_g if item.produto and item.produto.peso_g else padrao) * item.quantidade for item in itens
    )
