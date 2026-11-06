"""Números do dashboard. Fonte atual: pedidos importados da Nuvemshop (pagos e não cancelados)."""

from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Max, Q, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from apps.catalogo.models import Produto, Variacao
from apps.historico.models import STATUS_PAGOS, ItemPedidoHistorico, MetricaMensal, PedidoHistorico

PERIODOS = {
    "30d": ("Últimos 30 dias", 30),
    "90d": ("Últimos 90 dias", 90),
    "12m": ("Últimos 12 meses", 365),
    "tudo": ("Desde o início", None),
}
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
ZERO = Decimal("0.00")
ESTOQUE_BAIXO = 1


def pedidos_pagos():
    return PedidoHistorico.objects.filter(status_pagamento__in=STATUS_PAGOS).exclude(status="cancelled")


def intervalo(chave: str, agora=None):
    """(início, início do período anterior) do período escolhido; None = sem limite."""
    agora = agora or timezone.now()
    dias = PERIODOS.get(chave, PERIODOS["12m"])[1]
    if dias is None:
        return None, None
    inicio = agora - timedelta(days=dias)
    return inicio, inicio - timedelta(days=dias)


def resumo(qs) -> dict:
    dados = qs.aggregate(faturamento=Sum("total"), pedidos=Count("id"))
    faturamento = dados["faturamento"] or ZERO
    pedidos = dados["pedidos"] or 0
    itens = ItemPedidoHistorico.objects.filter(pedido__in=qs).aggregate(n=Sum("quantidade"))["n"] or 0
    return {
        "faturamento": faturamento,
        "pedidos": pedidos,
        "ticket": (faturamento / pedidos).quantize(Decimal("0.01")) if pedidos else ZERO,
        "itens": itens,
    }


def variacao(atual, anterior) -> float | None:
    if not anterior:
        return None
    return round((float(atual) - float(anterior)) / float(anterior) * 100, 1)


def periodo(chave: str) -> dict:
    inicio, inicio_anterior = intervalo(chave)
    qs = pedidos_pagos()
    atual = qs.filter(realizado_em__gte=inicio) if inicio else qs
    numeros = resumo(atual)
    if inicio:
        anterior = resumo(qs.filter(realizado_em__gte=inicio_anterior, realizado_em__lt=inicio))
        for campo in ("faturamento", "pedidos", "ticket", "itens"):
            numeros[f"{campo}_variacao"] = variacao(numeros[campo], anterior[campo])
    return {"qs": atual, "numeros": numeros, "rotulo": PERIODOS.get(chave, PERIODOS["12m"])[0]}


def _meses(quantidade: int, hoje: date) -> list[date]:
    ano, mes = hoje.year, hoje.month
    resultado = []
    for _ in range(quantidade):
        resultado.append(date(ano, mes, 1))
        mes -= 1
        if mes == 0:
            ano, mes = ano - 1, 12
    return list(reversed(resultado))


def rotulo_mes(dia: date) -> str:
    return f"{MESES[dia.month - 1]}/{str(dia.year)[2:]}"


def faturamento_mensal(meses: int = 12) -> list[dict]:
    hoje = timezone.localdate()
    lista = _meses(meses, hoje)
    dados = {
        linha["mes"].date() if hasattr(linha["mes"], "date") else linha["mes"]: linha
        for linha in pedidos_pagos()
        .filter(realizado_em__date__gte=lista[0])
        .annotate(mes=TruncMonth("realizado_em"))
        .values("mes")
        .annotate(valor=Sum("total"), pedidos=Count("id"))
    }
    return [
        {
            "mes": dia,
            "rotulo": rotulo_mes(dia),
            "valor": (dados.get(dia) or {}).get("valor") or ZERO,
            "pedidos": (dados.get(dia) or {}).get("pedidos") or 0,
        }
        for dia in lista
    ]


def visitas_mensais(meses: int = 12) -> list[dict]:
    linhas = list(MetricaMensal.objects.order_by("-mes")[:meses])
    return [
        {"rotulo": rotulo_mes(m.mes), "visitas": m.visitas, "vendas": m.vendas, "conversao": m.conversao}
        for m in reversed(linhas)
    ]


def mais_vendidos(qs, limite: int = 8) -> list[dict]:
    receita = ExpressionWrapper(F("quantidade") * F("preco_unitario"), output_field=DecimalField())
    linhas = list(
        ItemPedidoHistorico.objects.filter(pedido__in=qs)
        .values("nome")
        .annotate(quantidade_total=Sum("quantidade"), receita=Sum(receita), produto_ref=Max("produto_id"))
        .order_by("-quantidade_total", "-receita")[:limite]
    )
    maximo = max((linha["quantidade_total"] for linha in linhas), default=0) or 1
    for linha in linhas:
        linha["percentual"] = round(linha["quantidade_total"] / maximo * 100)
    return linhas


def vendas_por_estado(qs, limite: int | None = None) -> list[dict]:
    linhas = list(
        qs.exclude(uf="")
        .values("uf")
        .annotate(pedidos=Count("id"), valor=Sum("total"))
        .order_by("-pedidos", "uf")[:limite]
    )
    maximo = max((linha["pedidos"] for linha in linhas), default=0) or 1
    for linha in linhas:
        linha["percentual"] = round(linha["pedidos"] / maximo * 100)
    return linhas


def alertas() -> dict:
    publicados = Produto.objects.filter(ativo=True)
    estoque_baixo = (
        Variacao.objects.filter(ativa=True, produto__ativo=True, estoque__lte=ESTOQUE_BAIXO)
        .select_related("produto", "armacao", "lente")
        .order_by("estoque", "produto__nome")
    )
    sem_estoque = publicados.annotate(total=Sum("variacoes__estoque", filter=Q(variacoes__ativa=True))).filter(
        Q(total__lte=0) | Q(total__isnull=True)
    )
    return {
        "estoque_baixo": estoque_baixo[:8],
        "estoque_baixo_total": estoque_baixo.count(),
        "sem_estoque": sem_estoque.count(),
        "sem_foto": publicados.filter(imagens__isnull=True).count(),
        "sem_categoria": publicados.filter(categorias__isnull=True).count(),
        "rascunhos": Produto.objects.filter(ativo=False).count(),
    }
