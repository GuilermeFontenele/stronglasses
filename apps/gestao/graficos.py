"""Gráficos em SVG gerados no servidor: leves, sem JavaScript e compatíveis com a CSP estrita."""

from decimal import Decimal

LARGURA, ALTURA = 640, 240
MARGEM_ESQ, MARGEM_DIR, MARGEM_TOPO, MARGEM_BASE = 56, 12, 16, 28


def _teto(valor: float) -> float:
    """Arredonda o máximo para cima num número "redondo" (1, 2, 2,5, 5 x 10^n)."""
    if valor <= 0:
        return 1
    potencia = 10 ** (len(str(int(valor))) - 1)
    for fator in (1, 2, 2.5, 5, 10):
        if valor <= fator * potencia:
            return fator * potencia
    return 10 * potencia


def _rotulo_eixo(valor: float, moeda: bool) -> str:
    if valor >= 1000:
        texto = f"{valor / 1000:.1f}".replace(".", ",").removesuffix(",0") + " mil"
    else:
        texto = f"{valor:.0f}"
    return f"R$ {texto}" if moeda else texto


def barras(pontos: list[tuple[str, Decimal | int]], moeda: bool = True, destaque_ultimo: bool = True) -> dict:
    """pontos: [(rótulo, valor)]. Devolve coordenadas prontas para o template."""
    maximo = _teto(float(max((v for _, v in pontos), default=0) or 0))
    area_l = LARGURA - MARGEM_ESQ - MARGEM_DIR
    area_a = ALTURA - MARGEM_TOPO - MARGEM_BASE
    passo = area_l / max(len(pontos), 1)
    largura_barra = passo * 0.62
    grade = []
    for i in range(5):
        valor = maximo * i / 4
        y = MARGEM_TOPO + area_a - area_a * i / 4
        grade.append({"y": round(y, 1), "rotulo": _rotulo_eixo(valor, moeda)})
    itens = []
    for i, (rotulo, valor) in enumerate(pontos):
        altura = area_a * float(valor or 0) / maximo
        x = MARGEM_ESQ + passo * i + (passo - largura_barra) / 2
        itens.append(
            {
                "x": round(x, 1),
                "y": round(MARGEM_TOPO + area_a - altura, 1),
                "y_valor": round(max(MARGEM_TOPO + area_a - altura - 6, 11), 1),
                "largura": round(largura_barra, 1),
                "altura": round(max(altura, 0), 1),
                "centro": round(x + largura_barra / 2, 1),
                "rotulo": rotulo,
                "valor": valor,
                "destaque": destaque_ultimo and i == len(pontos) - 1,
            }
        )
    return {
        "topo": MARGEM_TOPO,
        "area_altura": area_a,
        "largura": LARGURA,
        "altura": ALTURA,
        "base": MARGEM_TOPO + area_a,
        "esquerda": MARGEM_ESQ,
        "direita": LARGURA - MARGEM_DIR,
        "rotulo_y": ALTURA - 8,
        "grade": grade,
        "itens": itens,
        "moeda": moeda,
        "vazio": not any(v for _, v in pontos),
    }


def linha(pontos: list[tuple[str, int | Decimal]], moeda: bool = False) -> dict:
    """Mesma escala do gráfico de barras, desenhado como linha com área preenchida."""
    grafico = barras(pontos, moeda=moeda, destaque_ultimo=False)
    coordenadas = [(item["centro"], item["y"]) for item in grafico["itens"]]
    grafico["linha"] = " ".join(f"{x},{y}" for x, y in coordenadas)
    if coordenadas:
        grafico["area"] = (
            f"{coordenadas[0][0]},{grafico['base']} " + grafico["linha"] + f" {coordenadas[-1][0]},{grafico['base']}"
        )
    return grafico
