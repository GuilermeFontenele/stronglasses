"""Gera o HTML das telas do painel com dados fictícios, para conferir o visual fora da máquina local.

Uso (CI): DJANGO_SETTINGS_MODULE=config.settings.test python scripts/previa_gestao.py saida/
Nunca rode contra o banco real: cria dados de demonstração.
"""

import random
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import django

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from django.test import Client  # noqa: E402
from django.utils import timezone  # noqa: E402

from apps.catalogo.models import (  # noqa: E402
    AcabamentoArmacao,
    Banner,
    Categoria,
    CorLente,
    ImagemProduto,
    Produto,
    Variacao,
)
from apps.clientes.models import Cliente, Endereco  # noqa: E402
from apps.core.models import Parametro  # noqa: E402
from apps.historico.models import ItemPedidoHistorico, MetricaMensal, PedidoHistorico  # noqa: E402
from apps.vendas.models import Pedido  # noqa: E402
from apps.vendas.servicos import ItemNovo, mudar_situacao, registrar_venda  # noqa: E402

saida = Path(sys.argv[1] if len(sys.argv) > 1 else "previa")
saida.mkdir(parents=True, exist_ok=True)
aleatorio = random.Random(42)  # noqa: S311 (dados fictícios, não é criptografia)

dono = get_user_model().objects.create_superuser("guilherme", "dono@exemplo.com", "x")
dono.first_name = "Guilherme"
dono.save()
categorias = [
    Categoria.objects.create(nome=n, slug=n.lower().replace(" ", "-"))
    for n in ("Feminino", "Masculino", "Infantil", "Outlet")
]
armacoes = [
    AcabamentoArmacao.objects.create(nome=n, cor_hex=c)
    for n, c in (("Preta", "#111111"), ("Tartaruga", "#6B3E1F"), ("Dourada", "#C9A54C"))
]
lentes = [
    CorLente.objects.create(nome=n, cor_hex=c)
    for n, c in (("Verde", "#55704A"), ("Marrom", "#6A4A2E"), ("Laranja", "#D9822B"))
]
produtos = []
for i, nome in enumerate(["Zaik", "Roshi", "Ohana", "Laguna", "Noruega", "Aviador Clássico", "Mauritius", "Stark"]):
    p = Produto.objects.create(
        nome=f"Óculos de Sol {nome}",
        slug=f"oculos-{i}",
        preco=Decimal("85.90") + i * 10,
        preco_comparativo=Decimal("189.90") if i % 2 == 0 else None,
        ativo=i != 7,
        destaque=i < 3,
    )
    p.categorias.add(categorias[i % 4])
    for j in range(1 + i % 3):
        Variacao.objects.create(
            produto=p, armacao=armacoes[j], lente=lentes[(i + j) % 3], sku=f"SG{i}{j}", estoque=(i * 3 + j) % 6
        )
    produtos.append(p)
nomes = ["Ana Lima", "Bruno Costa", "Carla Dias", "Diego Rocha", "Elisa Prado", "Fábio Nunes", "Gabi Melo", "Hugo Reis"]
clientes = []
for i, nome in enumerate(nomes):
    c = Cliente.objects.create(nome=nome, email=f"cliente{i}@exemplo.com", whatsapp=f"55859999900{i:02d}")
    Endereco.objects.create(
        cliente=c,
        cep="60000000",
        logradouro="Rua Exemplo",
        numero=str(10 + i),
        cidade="Fortaleza",
        uf="CE",
        padrao=True,
    )
    clientes.append(c)
agora = timezone.now()
ufs = ["CE", "CE", "CE", "SP", "RJ", "PE", "BA", "MG"]
for n in range(140):
    dias = aleatorio.randint(0, 360)
    p = aleatorio.choice(produtos)
    qtd = aleatorio.choice([1, 1, 1, 2])
    pago = aleatorio.random() > 0.12
    pedido = PedidoHistorico.objects.create(
        nuvemshop_id=1000 + n,
        numero=200 + n,
        cliente=aleatorio.choice(clientes),
        realizado_em=agora - timedelta(days=dias, hours=n),
        status="open" if pago else "cancelled",
        status_pagamento="paid" if pago else "voided",
        status_envio="shipped",
        total=p.preco * qtd,
        subtotal=p.preco * qtd,
        uf=aleatorio.choice(ufs),
        cidade="Fortaleza",
        cupom="VOLTA10" if n % 9 == 0 else "",
        forma_pagamento="Pix",
    )
    ItemPedidoHistorico.objects.create(
        pedido=pedido,
        produto=p,
        nome=p.nome,
        variante="Preta / Verde",
        sku="SG",
        quantidade=qtd,
        preco_unitario=p.preco,
    )
hoje = date.today()
for m in range(12):
    mes = date(hoje.year - (1 if hoje.month - m <= 0 else 0), (hoje.month - m - 1) % 12 + 1, 1)
    MetricaMensal.objects.create(mes=mes, visitas=900 + aleatorio.randint(0, 900), vendas=aleatorio.randint(5, 20))
for k in range(3):
    ImagemProduto.objects.create(
        produto=produtos[2], imagem=f"produtos/demo{k}.webp", texto_alternativo=f"Foto {k}", ordem=k
    )
Banner.objects.create(titulo="Mapa do Brasil", imagem="banners/demo.webp", imagem_mobile="banners/demo-cel.webp")

# Vendas lançadas no painel (hotel, barbearia, WhatsApp)
Parametro.objects.filter(chave="REMETENTE_ENDERECO").update(valor="Rua Exemplo, 100, sala 2")
Parametro.objects.filter(chave="REMETENTE_CEP").update(valor="60000000")
canais = ["hotel", "barbearia", "whatsapp", "whatsapp", "presencial"]
for n in range(14):
    cliente = clientes[n % len(clientes)]
    entrega = "correios" if n % 3 == 0 else "maos"
    venda = Pedido(
        cliente=cliente,
        realizado_em=agora - timedelta(days=n * 2, hours=n),
        canal=canais[n % len(canais)],
        parceiro="Hotel Praia Mar" if canais[n % len(canais)] == "hotel" else "",
        forma_pagamento="pix" if n % 2 == 0 else "credito",
        parcelas=1 if n % 2 == 0 else 3,
        entrega=entrega,
        frete=Decimal("22.50") if entrega == "correios" else Decimal("0"),
        destinatario=cliente.nome if entrega == "correios" else "",
        cep="01310100" if entrega == "correios" else "",
        logradouro="Avenida Paulista" if entrega == "correios" else "",
        numero_endereco="1000" if entrega == "correios" else "",
        bairro="Bela Vista" if entrega == "correios" else "",
        cidade="São Paulo" if entrega == "correios" else "Fortaleza",
        uf="SP" if entrega == "correios" else "CE",
    )
    itens = [ItemNovo(produtos[n % 7].variacoes.first(), 1 + n % 2)]
    venda = registrar_venda(venda, itens, baixar_estoque=False, aplicar_pix=n % 2 == 0, usuario=dono)
    if n == 5:
        mudar_situacao(venda, "cancelado")
    elif entrega == "correios" and n > 3:
        mudar_situacao(venda, "enviado", codigo_rastreio="AA123456789BR")
venda_correios = Pedido.objects.filter(entrega="correios").order_by("numero").first()

navegador = Client()
navegador.force_login(dono)
telas = {
    "dashboard": "/gestao/",
    "produtos": "/gestao/produtos/",
    "produto": f"/gestao/produtos/{produtos[2].pk}/",
    "estoque": "/gestao/estoque/",
    "clientes": "/gestao/clientes/",
    "cliente": f"/gestao/clientes/{clientes[0].pk}/",
    "pedidos": "/gestao/pedidos/",
    "pedido": f"/gestao/pedidos/{PedidoHistorico.objects.first().pk}/",
    "banners": "/gestao/banners/",
    "configuracoes": "/gestao/configuracoes/",
    "vendas": "/gestao/vendas/",
    "venda_nova": f"/gestao/vendas/nova/?cliente={clientes[1].pk}",
    "venda_nova_busca": "/gestao/vendas/nova/?busca_cliente=a",
    "venda": f"/gestao/vendas/{venda_correios.pk}/",
    "etiqueta": f"/gestao/vendas/{venda_correios.pk}/etiqueta/",
    "cliente_novo": "/gestao/clientes/novo/?para=venda",
}
for nome, url in telas.items():
    html = navegador.get(url).content.decode()
    (saida / f"{nome}.html").write_text(
        html.replace('"/static/', '"static/').replace('"/media/', '"media/'), encoding="utf-8"
    )
(saida / "entrar.html").write_text(
    Client().get("/gestao/entrar/").content.decode().replace('"/static/', '"static/'), encoding="utf-8"
)
print("Prévia gerada em", saida)
