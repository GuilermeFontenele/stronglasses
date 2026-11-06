"""Números do dashboard: pedidos pagos da Nuvemshop (histórico) somados às vendas lançadas na loja nova."""

from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Max, Q, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from apps.catalogo.models import Produto, Variacao
from apps.historico.models import STATUS_PAGOS, ItemPedidoHistorico, MetricaMensal, PedidoHistorico
from apps.vendas.models import UFS, ItemPedido, Pedido

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


def vendas_pagas():
    """Vendas da loja nova que contam como faturamento (pagas, enviadas ou entregues)."""
    return Pedido.objects.filter(situacao__in=Pedido.PAGOS)


def intervalo(chave: str, agora=None):
    """(início, início do período anterior) do período escolhido; None = sem limite."""
    agora = agora or timezone.now()
    dias = PERIODOS.get(chave, PERIODOS["12m"])[1]
    if dias is None:
        return None, None
    inicio = agora - timedelta(days=dias)
    return inicio, inicio - timedelta(days=dias)


def resumo(qs, vendas=None) -> dict:
    dados = qs.aggregate(faturamento=Sum("total"), pedidos=Count("id"))
    faturamento = dados["faturamento"] or ZERO
    pedidos = dados["pedidos"] or 0
    itens = ItemPedidoHistorico.objects.filter(pedido__in=qs).aggregate(n=Sum("quantidade"))["n"] or 0
    if vendas is not None:
        novas = vendas.aggregate(faturamento=Sum("total"), pedidos=Count("id"))
        faturamento += novas["faturamento"] or ZERO
        pedidos += novas["pedidos"] or 0
        itens += ItemPedido.objects.filter(pedido__in=vendas).aggregate(n=Sum("quantidade"))["n"] or 0
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
    qs, vendas = pedidos_pagos(), vendas_pagas()
    atual = qs.filter(realizado_em__gte=inicio) if inicio else qs
    vendas_atual = vendas.filter(realizado_em__gte=inicio) if inicio else vendas
    numeros = resumo(atual, vendas_atual)
    if inicio:
        anterior = resumo(
            qs.filter(realizado_em__gte=inicio_anterior, realizado_em__lt=inicio),
            vendas.filter(realizado_em__gte=inicio_anterior, realizado_em__lt=inicio),
        )
        for campo in ("faturamento", "pedidos", "ticket", "itens"):
            numeros[f"{campo}_variacao"] = variacao(numeros[campo], anterior[campo])
    return {
        "qs": atual,
        "vendas": vendas_atual,
        "numeros": numeros,
        "rotulo": PERIODOS.get(chave, PERIODOS["12m"])[0],
    }


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


def _por_mes(qs, inicio: date) -> dict:
    return {
        linha["mes"].date() if hasattr(linha["mes"], "date") else linha["mes"]: linha
        for linha in qs.filter(realizado_em__date__gte=inicio)
        .annotate(mes=TruncMonth("realizado_em"))
        .values("mes")
        .annotate(valor=Sum("total"), pedidos=Count("id"))
        .order_by()
    }


def faturamento_mensal(meses: int = 12) -> list[dict]:
    hoje = timezone.localdate()
    lista = _meses(meses, hoje)
    fontes = [_por_mes(pedidos_pagos(), lista[0]), _por_mes(vendas_pagas(), lista[0])]
    return [
        {
            "mes": dia,
            "rotulo": rotulo_mes(dia),
            "valor": sum(((f.get(dia) or {}).get("valor") or ZERO for f in fontes), ZERO),
            "pedidos": sum((f.get(dia) or {}).get("pedidos") or 0 for f in fontes),
        }
        for dia in lista
    ]


def visitas_mensais(meses: int = 12) -> list[dict]:
    linhas = list(MetricaMensal.objects.order_by("-mes")[:meses])
    return [
        {"rotulo": rotulo_mes(m.mes), "visitas": m.visitas, "vendas": m.vendas, "conversao": m.conversao}
        for m in reversed(linhas)
    ]


def _com_percentual(linhas: list[dict], campo: str) -> list[dict]:
    maximo = max((linha[campo] for linha in linhas), default=0) or 1
    for linha in linhas:
        linha["percentual"] = round(linha[campo] / maximo * 100)
    return linhas


def mais_vendidos(qs, limite: int = 8, vendas=None) -> list[dict]:
    receita = ExpressionWrapper(F("quantidade") * F("preco_unitario"), output_field=DecimalField())
    consultas = [ItemPedidoHistorico.objects.filter(pedido__in=qs)]
    if vendas is not None:
        consultas.append(ItemPedido.objects.filter(pedido__in=vendas))
    somados: dict[str, dict] = {}
    for consulta in consultas:
        for linha in (
            consulta.values("nome")
            .annotate(quantidade_total=Sum("quantidade"), receita=Sum(receita), produto_ref=Max("produto_id"))
            .order_by()
        ):
            atual = somados.setdefault(
                linha["nome"], {"nome": linha["nome"], "quantidade_total": 0, "receita": ZERO, "produto_ref": None}
            )
            atual["quantidade_total"] += linha["quantidade_total"] or 0
            atual["receita"] += linha["receita"] or ZERO
            atual["produto_ref"] = atual["produto_ref"] or linha["produto_ref"]
    linhas = sorted(somados.values(), key=lambda linha: (-linha["quantidade_total"], -linha["receita"]))[:limite]
    return _com_percentual(linhas, "quantidade_total")


def nome_do_estado(uf: str) -> str:
    """O histórico guarda o estado por extenso; a loja nova, a sigla. Tudo vira nome por extenso."""
    texto = " ".join((uf or "").split())
    return UFS.get(texto.upper(), texto)


def vendas_por_estado(qs, limite: int | None = None, vendas=None) -> list[dict]:
    consultas = [qs.exclude(uf="")]
    if vendas is not None:
        consultas.append(vendas.exclude(uf=""))
    somados: dict[str, dict] = {}
    for consulta in consultas:
        for linha in consulta.values("uf").annotate(pedidos=Count("id"), valor=Sum("total")).order_by():
            nome = nome_do_estado(linha["uf"])
            atual = somados.setdefault(nome, {"uf": nome, "pedidos": 0, "valor": ZERO})
            atual["pedidos"] += linha["pedidos"]
            atual["valor"] += linha["valor"] or ZERO
    linhas = sorted(somados.values(), key=lambda linha: (-linha["pedidos"], linha["uf"]))[:limite]
    return _com_percentual(linhas, "pedidos")


def vendas_por_canal(qs, vendas) -> list[dict]:
    """De onde vêm as vendas: site antigo (Nuvemshop) e cada canal das vendas lançadas no painel."""
    linhas = []
    antigo = qs.aggregate(pedidos=Count("id"), valor=Sum("total"))
    if antigo["pedidos"]:
        linhas.append({"canal": "Site (Nuvemshop)", "pedidos": antigo["pedidos"], "valor": antigo["valor"] or ZERO})
    rotulos = dict(Pedido.Canal.choices)
    for linha in vendas.values("canal").annotate(pedidos=Count("id"), valor=Sum("total")).order_by():
        linhas.append(
            {"canal": rotulos.get(linha["canal"], linha["canal"]), "pedidos": linha["pedidos"], "valor": linha["valor"]}
        )
    linhas.sort(key=lambda linha: (-linha["valor"], linha["canal"]))
    return _com_percentual(linhas, "valor") if linhas else []


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
