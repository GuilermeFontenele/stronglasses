"""Gera o HTML das telas do painel com dados fictícios, para conferir o visual fora da máquina local.

Uso (CI): DJANGO_SETTINGS_MODULE=config.settings.test python scripts/previa_gestao.py saida/
Nunca rode contra o banco real: cria dados de demonstração.
"""

import random
import secrets
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import django

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
django.setup()

from io import BytesIO  # noqa: E402

from django.contrib.auth import get_user_model  # noqa: E402
from django.core.files.base import ContentFile  # noqa: E402
from django.core.files.storage import default_storage  # noqa: E402
from django.test import Client  # noqa: E402
from django.utils import timezone  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

from apps.catalogo import provador  # noqa: E402
from apps.catalogo import views as catalogo_views  # noqa: E402
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
from apps.envios.models import ConexaoMelhorEnvio, Envio  # noqa: E402
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


def _foto(armacao: str, lente: str, deslocamento: int = 0) -> ContentFile:
    """Foto de produto de mentira: óculos de frente em fundo claro, como as fotos reais da loja."""
    img = Image.new("RGB", (800, 800), "#f4f4f2")
    d = ImageDraw.Draw(img)
    y = 320 + deslocamento
    for x in (140, 450):
        d.rounded_rectangle((x, y, x + 210, y + 150), radius=62, fill=lente, outline=armacao, width=16)
    d.rectangle((350, y + 36, 450, y + 50), fill=armacao)
    d.rectangle((30, y + 30, 140, y + 40), fill=armacao)
    d.rectangle((660, y + 30, 770, y + 40), fill=armacao)
    buf = BytesIO()
    img.save(buf, "WEBP", quality=70)
    return ContentFile(buf.getvalue())


def _banner(largura: int, altura: int, texto: str) -> ContentFile:
    img = Image.new("RGB", (largura, altura), "#1c2530")
    d = ImageDraw.Draw(img)
    for n in range(0, largura, 6):
        tom = 28 + int(60 * n / largura)
        d.rectangle((n, 0, n + 6, altura), fill=(tom, tom + 12, tom + 28))
    d.text((largura // 12, altura // 2), texto, fill="white")
    buf = BytesIO()
    img.save(buf, "WEBP", quality=60)
    return ContentFile(buf.getvalue())


for p in produtos:
    for ordem, v in enumerate(p.variacoes.select_related("armacao", "lente")):
        for angulo in (0, 1):
            foto = ImagemProduto(
                produto=p,
                variacao=v if angulo == 0 else None,
                texto_alternativo=f"{p.nome} {v.descricao_cor.lower()}",
                ordem=ordem * 2 + angulo,
            )
            foto.imagem.save("foto.webp", _foto(v.armacao.cor_hex, v.lente.cor_hex if v.lente else "#333", angulo * 40))
    provador.preencher(p)
catalogo_views.provador_instalado = lambda: True  # na prévia, mostra o botão do provador sem baixar o MediaPipe
banner = Banner(titulo="Coleção de verão")
banner.imagem.save("banner.webp", _banner(1920, 800, "COLECAO DE VERAO"), save=False)
banner.imagem_mobile.save("banner-cel.webp", _banner(1080, 1350, "COLECAO DE VERAO"), save=False)
banner.save()

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
Parametro.objects.filter(chave="REMETENTE_NUMERO").update(valor="100")
ConexaoMelhorEnvio.objects.create(
    ambiente="sandbox", access_token=secrets.token_hex(8), expira_em=agora + timedelta(days=20)
)
venda_com_etiqueta = Pedido.objects.filter(entrega="correios").order_by("numero")[1]
Envio.objects.create(
    pedido=venda_com_etiqueta,
    ambiente="sandbox",
    me_id="demo-0001",
    transportadora="Correios",
    servico="PAC",
    servico_id=1,
    preco=Decimal("22.50"),
    prazo_dias=8,
    status="gerado",
    rastreio="AA123456789BR",
)

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
    "venda_etiqueta_me": f"/gestao/vendas/{venda_com_etiqueta.pk}/",
}
for nome, url in telas.items():
    html = navegador.get(url).content.decode()
    (saida / f"{nome}.html").write_text(
        html.replace('"/static/', '"static/').replace('"/media/', '"media/'), encoding="utf-8"
    )
(saida / "entrar.html").write_text(
    Client().get("/gestao/entrar/").content.decode().replace('"/static/', '"static/'), encoding="utf-8"
)

# Loja: finalizar compra e página do pedido com Pix (credenciais fictícias só para renderizar)
from django.test import override_settings  # noqa: E402

from apps.pagamentos.models import Pagamento  # noqa: E402

with override_settings(MERCADOPAGO_ACCESS_TOKEN=secrets.token_hex(8), MERCADOPAGO_PUBLIC_KEY=secrets.token_hex(8)):
    loja = Client()
    variacao = next(v for p in produtos for v in p.variacoes.all() if v.estoque > 0)
    loja.post("/carrinho/adicionar/", {"variacao": variacao.pk, "quantidade": 1})
    paginas = {
        "loja_home": "/",
        "loja_categoria": "/feminino/",
        "loja_produto": f"/produtos/{produtos[0].slug}/",
        "loja_busca": "/busca/?q=oculos",
        "loja_busca_vazia": "/busca/?q=xyzabc",
        "loja_404": "/nao-existe/",
        "loja_privacidade": "/politica-de-privacidade/",
        "loja_carrinho": "/carrinho/",
        "loja_finalizar": "/finalizar/",
    }
    pedido_site = Pedido.objects.create(
        numero=9999,
        realizado_em=agora,
        canal="site",
        situacao="pendente",
        forma_pagamento="pix",
        subtotal=Decimal("189.80"),
        desconto_pix=Decimal("9.49"),
        frete=Decimal("10.00"),
        total=Decimal("190.31"),
        cidade="Fortaleza",
        uf="CE",
        token_acesso="previa" + secrets.token_hex(8),
        expira_em=agora + timedelta(minutes=30),
        cliente=clientes[0],
        frete_servico="Motoboy (Fortaleza)",
    )
    pedido_site.itens.create(nome="Óculos de Sol Zaik", cor="Tartaruga", quantidade=2, preco_unitario=Decimal("94.90"))
    Pagamento.objects.create(
        pedido=pedido_site,
        provedor_id="previa-1",
        metodo="pix",
        valor=pedido_site.total,
        pix_copia_e_cola="00020126580014br.gov.bcb.pix0136previa-codigo-pix-copia-e-cola-5204000053039865802BR",
        expira_em=agora + timedelta(minutes=30),
    )
    paginas["loja_pedido_pix"] = f"/pedido/{pedido_site.token_acesso}/"
    for nome, url in paginas.items():
        html = loja.get(url).content.decode()
        (saida / f"{nome}.html").write_text(
            html.replace('"/static/', '"static/').replace('"/media/', '"media/'), encoding="utf-8"
        )


def _despejar(pasta: str = "") -> None:
    """Copia as imagens (guardadas em memória nos testes) para a pasta da prévia."""
    pastas, arquivos = default_storage.listdir(pasta)
    for nome in arquivos:
        caminho = f"{pasta}/{nome}".lstrip("/")
        destino = saida / "media" / caminho
        destino.parent.mkdir(parents=True, exist_ok=True)
        with default_storage.open(caminho) as arquivo:
            destino.write_bytes(arquivo.read())
    for nome in pastas:
        _despejar(f"{pasta}/{nome}".lstrip("/"))


_despejar()
print("Prévia gerada em", saida)
