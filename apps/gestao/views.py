"""Painel de gestão da loja (/gestao/). Só equipe; toda alteração vai para a trilha de auditoria."""

import json

from django.contrib import messages
from django.contrib.auth import login as entrar_django
from django.contrib.auth import logout as sair_django
from django.contrib.auth.forms import AuthenticationForm
from django.core.files.base import ContentFile
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Max, OuterRef, Prefetch, Q, Subquery, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST

from apps.catalogo.models import Banner, Categoria, ImagemProduto, Produto, Variacao
from apps.clientes import lgpd
from apps.clientes.models import Cliente, Endereco
from apps.core.auditoria import diferenca, foto, registrar
from apps.core.crypto import hash_busca
from apps.core.models import Pagina, RegistroAuditoria
from apps.core.validators import so_digitos
from apps.historico.models import STATUS_PAGOS, ItemPedidoHistorico, PedidoHistorico

from . import graficos, metricas
from .acesso import bloqueado, equipe, limpar_falhas, registrar_falha
from .forms import (
    BannerForm,
    ClienteForm,
    ConfiguracoesForm,
    EstoqueFormSet,
    ImagemFormSet,
    PaginaForm,
    ProdutoForm,
    VariacaoFormSet,
    VariacaoFormSetNovo,
)

POR_PAGINA = 30

STATUS_PAGAMENTO = {
    "paid": ("Pago", "ok"),
    "partially_paid": ("Pago em parte", "ok"),
    "partially_refunded": ("Reembolso parcial", "aviso"),
    "pending": ("Pendente", "aviso"),
    "authorized": ("Autorizado", "aviso"),
    "refunded": ("Reembolsado", "neutro"),
    "voided": ("Cancelado", "erro"),
    "abandoned": ("Abandonado", "neutro"),
}
STATUS_ENVIO = {
    "unpacked": "Não embalado",
    "unfulfilled": "Não enviado",
    "unshipped": "Não enviado",
    "fulfilled": "Enviado",
    "shipped": "Enviado",
    "delivered": "Entregue",
}


# ---------------------------------------------------------------- utilidades


def _paginar(request, qs, por=POR_PAGINA):
    return Paginator(qs, por).get_page(request.GET.get("pagina"))


def _consulta_sem_pagina(request) -> str:
    parametros = request.GET.copy()
    parametros.pop("pagina", None)
    return parametros.urlencode()


def _auditar(request, obj, antes: dict | None):
    depois = foto(obj)
    if antes is None:
        registrar(RegistroAuditoria.Acao.CRIACAO, obj, None, depois, request.user)
        return
    antes_dif, depois_dif = diferenca(antes, depois)
    if antes_dif or depois_dif:
        registrar(RegistroAuditoria.Acao.ALTERACAO, obj, antes_dif, depois_dif, request.user)


def _auditar_formset(request, formset):
    for obj in formset.new_objects:
        registrar(RegistroAuditoria.Acao.CRIACAO, obj, None, foto(obj), request.user)
    for obj, _campos in formset.changed_objects:
        registrar(RegistroAuditoria.Acao.ALTERACAO, obj, None, foto(obj), request.user)
    for obj in formset.deleted_objects:
        registrar(RegistroAuditoria.Acao.EXCLUSAO, obj, None, None, request.user)


def _itens_com_foto():
    """Itens de pedido já com a foto do produto (a da cor vendida, se houver)."""
    fotos = Prefetch("produto__imagens", queryset=ImagemProduto.objects.order_by("ordem", "id"), to_attr="fotos")
    return ItemPedidoHistorico.objects.select_related("produto").prefetch_related(fotos)


def _foto_do_item(item):
    fotos = getattr(item.produto, "fotos", None) if item.produto_id else None
    if not fotos:
        return None
    return next((f for f in fotos if item.variacao_id and f.variacao_id == item.variacao_id), fotos[0])


def _status_pedido(pedido) -> dict:
    if pedido.status == "cancelled":
        return {"rotulo": "Cancelado", "tom": "erro"}
    rotulo, tom = STATUS_PAGAMENTO.get(pedido.status_pagamento, (pedido.status_pagamento or "—", "neutro"))
    return {"rotulo": rotulo, "tom": tom}


# ---------------------------------------------------------------- acesso


@require_http_methods(["GET", "POST"])
def entrar(request):
    destino = request.POST.get("next") or request.GET.get("next") or reverse("gestao:dashboard")
    if not url_has_allowed_host_and_scheme(
        destino, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        destino = reverse("gestao:dashboard")
    if request.user.is_authenticated and request.user.is_staff:
        return redirect(destino)
    form = AuthenticationForm(request, data=request.POST or None)
    usuario = request.POST.get("username", "")
    erro_bloqueio = False
    if request.method == "POST":
        if bloqueado(request, usuario):
            erro_bloqueio = True
        elif form.is_valid() and form.get_user().is_staff:
            limpar_falhas(request, usuario)
            entrar_django(request, form.get_user())
            return redirect(destino)
        else:
            registrar_falha(request, usuario)
            if form.is_valid():  # senha certa, mas não é da equipe
                form.add_error(None, "Este usuário não tem acesso ao painel.")
    resposta = render(request, "gestao/entrar.html", {"form": form, "next": destino, "erro_bloqueio": erro_bloqueio})
    if erro_bloqueio:
        resposta.status_code = 429
    return resposta


@require_POST
def sair(request):
    sair_django(request)
    messages.info(request, "Você saiu do painel.")
    return redirect("gestao:entrar")


# ---------------------------------------------------------------- dashboard


@equipe
def dashboard(request):
    chave = request.GET.get("periodo", "12m")
    if chave not in metricas.PERIODOS:
        chave = "12m"
    dados = metricas.periodo(chave)
    mensal = metricas.faturamento_mensal(12)
    visitas = metricas.visitas_mensais(12)
    ultimos = list(PedidoHistorico.objects.select_related("cliente").order_by("-realizado_em")[:6])
    for pedido in ultimos:
        pedido.situacao = _status_pedido(pedido)
    return render(
        request,
        "gestao/dashboard.html",
        {
            "secao": "dashboard",
            "periodos": metricas.PERIODOS,
            "periodo": chave,
            "periodo_rotulo": dados["rotulo"],
            "numeros": dados["numeros"],
            "grafico_faturamento": graficos.barras([(m["rotulo"], m["valor"]) for m in mensal]),
            "grafico_pedidos": graficos.linha([(m["rotulo"], m["pedidos"]) for m in mensal]),
            "grafico_visitas": graficos.linha([(v["rotulo"], v["visitas"]) for v in visitas]) if visitas else None,
            "mais_vendidos": metricas.mais_vendidos(dados["qs"]),
            "estados": metricas.vendas_por_estado(dados["qs"]),
            "ultimos": ultimos,
            "alertas": metricas.alertas(),
        },
    )


# ---------------------------------------------------------------- produtos


@equipe(permissao="catalogo.view_produto")
def produtos(request):
    if request.method == "POST":
        return _acao_em_massa(request)
    qs = (
        Produto.objects.annotate(
            estoque_total=Sum("variacoes__estoque", filter=Q(variacoes__ativa=True)),
            n_variacoes=Count("variacoes", distinct=True),
        )
        .prefetch_related(
            Prefetch("imagens", queryset=ImagemProduto.objects.order_by("ordem", "id"), to_attr="fotos"), "categorias"
        )
        .order_by("nome")
    )
    termo = request.GET.get("q", "").strip()
    if termo:
        qs = qs.filter(Q(nome__icontains=termo) | Q(variacoes__sku__icontains=termo) | Q(slug__icontains=termo))
    filtros = {
        "status": request.GET.get("status", ""),
        "categoria": request.GET.get("categoria", ""),
        "estoque": request.GET.get("estoque", ""),
        "pendencia": request.GET.get("pendencia", ""),
    }
    if filtros["status"] == "publicados":
        qs = qs.filter(ativo=True)
    elif filtros["status"] == "rascunhos":
        qs = qs.filter(ativo=False)
    if filtros["categoria"].isdigit():
        qs = qs.filter(categorias=int(filtros["categoria"]))
    if filtros["estoque"] == "zerado":
        qs = qs.filter(Q(estoque_total__lte=0) | Q(estoque_total__isnull=True))
    elif filtros["estoque"] == "baixo":
        qs = qs.filter(estoque_total__gt=0, estoque_total__lte=2)
    if filtros["pendencia"] == "sem-foto":
        qs = qs.filter(imagens__isnull=True)
    elif filtros["pendencia"] == "sem-categoria":
        qs = qs.filter(categorias__isnull=True)
    ordem = request.GET.get("ordem", "")
    ordens = {"preco": "preco", "-preco": "-preco", "estoque": "estoque_total", "-estoque": "-estoque_total"}
    if ordem in ordens:
        qs = qs.order_by(ordens[ordem], "nome")
    pagina = _paginar(request, qs.distinct())
    return render(
        request,
        "gestao/produtos.html",
        {
            "secao": "produtos",
            "pagina": pagina,
            "termo": termo,
            "filtros": filtros,
            "ordem": ordem,
            "categorias": Categoria.objects.order_by("ordem", "nome"),
            "consulta": _consulta_sem_pagina(request),
            "total": Produto.objects.count(),
        },
    )


def _acao_em_massa(request):
    if not request.user.has_perm("catalogo.change_produto"):
        messages.error(request, "Você não tem permissão para alterar produtos.")
        return redirect(request.get_full_path())
    ids = [int(i) for i in request.POST.getlist("selecionados") if i.isdigit()]
    acao = request.POST.get("acao")
    campos = {
        "publicar": {"ativo": True},
        "despublicar": {"ativo": False},
        "destacar": {"destaque": True},
        "tirar-destaque": {"destaque": False},
    }.get(acao)
    if not ids or not campos:
        messages.error(request, "Escolha produtos e uma ação.")
        return redirect(request.get_full_path())
    with transaction.atomic():
        for produto in Produto.objects.filter(pk__in=ids):
            antes = foto(produto)
            for campo, valor in campos.items():
                setattr(produto, campo, valor)
            produto.save(update_fields=[*campos, "atualizado_em", "atualizado_por"])
            _auditar(request, produto, antes)
    messages.success(request, f"{len(ids)} produto(s) atualizado(s).")
    return redirect(request.get_full_path())


@equipe(permissao="catalogo.view_produto")
def produto_editar(request, pk=None):
    produto = get_object_or_404(Produto, pk=pk) if pk else Produto()
    pode_editar = request.user.has_perm("catalogo.change_produto" if pk else "catalogo.add_produto")
    if request.method == "POST" and pode_editar:
        antes = foto(produto) if pk else None
        form = ProdutoForm(request.POST, request.FILES, instance=produto)
        variacoes = (VariacaoFormSet if pk else VariacaoFormSetNovo)(request.POST, instance=produto, prefix="variacoes")
        imagens = ImagemFormSet(request.POST, instance=produto, prefix="imagens")
        if form.is_valid() and variacoes.is_valid() and imagens.is_valid():
            with transaction.atomic():
                produto = form.save()
                _auditar(request, produto, antes)
                variacoes.instance = produto
                variacoes.save()
                _auditar_formset(request, variacoes)
                imagens.instance = produto
                imagens.save()
                _auditar_formset(request, imagens)
                ordem = (produto.imagens.aggregate(m=Max("ordem"))["m"] or 0) + 1
                for i, arquivo in enumerate(form.cleaned_data.get("novas_fotos") or []):
                    imagem = ImagemProduto(produto=produto, texto_alternativo=produto.nome[:150], ordem=ordem + i)
                    imagem.imagem.save(arquivo.name, ContentFile(arquivo.read()), save=True)
                    registrar(RegistroAuditoria.Acao.CRIACAO, imagem, None, foto(imagem), request.user)
            messages.success(request, f"“{produto.nome}” salvo.")
            if "continuar" in request.POST:
                return redirect("gestao:produto", pk=produto.pk)
            return redirect("gestao:produtos")
        messages.error(request, "Confira os campos destacados.")
    else:
        form = ProdutoForm(instance=produto)
        variacoes = (VariacaoFormSet if pk else VariacaoFormSetNovo)(instance=produto, prefix="variacoes")
        imagens = ImagemFormSet(instance=produto, prefix="imagens")
    return render(
        request,
        "gestao/produto_form.html",
        {
            "secao": "produtos",
            "produto": produto,
            "form": form,
            "variacoes": variacoes,
            "imagens": imagens,
            "pode_editar": pode_editar,
        },
    )


@equipe(permissao="catalogo.change_variacao")
def estoque(request):
    qs = (
        Variacao.objects.filter(produto__isnull=False)
        .select_related("produto", "armacao", "lente")
        .order_by("produto__nome", "ordem", "id")
    )
    termo = request.GET.get("q", "").strip()
    if termo:
        qs = qs.filter(Q(produto__nome__icontains=termo) | Q(sku__icontains=termo))
    filtro = request.GET.get("filtro", "")
    if filtro == "baixo":
        qs = qs.filter(estoque__lte=metricas.ESTOQUE_BAIXO)
    elif filtro == "publicados":
        qs = qs.filter(produto__ativo=True, ativa=True)
    pagina = _paginar(request, qs, por=50)
    ids = [v.pk for v in pagina.object_list]
    if request.method == "POST":
        formset = EstoqueFormSet(request.POST, queryset=Variacao.objects.filter(pk__in=ids))
        if formset.is_valid():
            with transaction.atomic():
                for form in formset.forms:
                    if form.has_changed():
                        antes = foto(Variacao.objects.get(pk=form.instance.pk))
                        obj = form.save()
                        _auditar(request, obj, antes)
            alterados = sum(1 for f in formset.forms if f.has_changed())
            messages.success(request, f"Estoque salvo ({alterados} alteração(ões)).")
            return redirect(request.get_full_path())
        messages.error(request, "Confira os valores destacados.")
    else:
        formset = EstoqueFormSet(queryset=Variacao.objects.filter(pk__in=ids).order_by("produto__nome", "ordem", "id"))
    linhas = {form.instance.pk: form for form in formset.forms}
    return render(
        request,
        "gestao/estoque.html",
        {
            "secao": "estoque",
            "pagina": pagina,
            "formset": formset,
            "linhas": [(v, linhas.get(v.pk)) for v in pagina.object_list],
            "termo": termo,
            "filtro": filtro,
            "consulta": _consulta_sem_pagina(request),
        },
    )


# ---------------------------------------------------------------- clientes


@equipe(permissao="clientes.view_cliente")
def clientes(request):
    pagos = PedidoHistorico.objects.filter(status_pagamento__in=STATUS_PAGOS).exclude(status="cancelled")
    qs = Cliente.objects.annotate(
        n_pedidos=Count("pedidos_historicos", filter=Q(pedidos_historicos__in=pagos), distinct=True),
        total_gasto=Sum("pedidos_historicos__total", filter=Q(pedidos_historicos__in=pagos)),
        ultimo_pedido=Max("pedidos_historicos__realizado_em"),
        cidade=Subquery(
            Endereco.objects.filter(cliente=OuterRef("pk")).order_by("-padrao", "-id").values("cidade")[:1]
        ),
    ).order_by("nome")
    termo = request.GET.get("q", "").strip()
    if termo:
        filtro = Q(nome__icontains=termo) | Q(email__icontains=termo)
        digitos = so_digitos(termo)
        if len(digitos) >= 8:
            filtro |= Q(whatsapp__contains=digitos)
        if len(digitos) in (11, 14):
            filtro |= Q(documento_hash=hash_busca(digitos))
        qs = qs.filter(filtro)
    ordem = request.GET.get("ordem", "")
    ordens = {"gasto": "-total_gasto", "pedidos": "-n_pedidos", "recentes": "-ultimo_pedido"}
    if ordem in ordens:
        qs = qs.order_by(f"{ordens[ordem]}", "nome").exclude(**{ordens[ordem].lstrip("-") + "__isnull": True})
    return render(
        request,
        "gestao/clientes.html",
        {
            "secao": "clientes",
            "pagina": _paginar(request, qs),
            "termo": termo,
            "ordem": ordem,
            "consulta": _consulta_sem_pagina(request),
            "total": Cliente.objects.count(),
        },
    )


@equipe(permissao="clientes.view_cliente")
def cliente(request, pk):
    obj = get_object_or_404(Cliente, pk=pk)
    pode_editar = request.user.has_perm("clientes.change_cliente")
    if request.method == "POST" and pode_editar:
        antes = foto(obj)
        form = ClienteForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            _auditar(request, obj, antes)
            messages.success(request, "Dados do cliente salvos.")
            return redirect("gestao:cliente", pk=obj.pk)
        messages.error(request, "Confira os campos destacados.")
    else:
        form = ClienteForm(instance=obj)
    # Abrir a ficha é acesso a dado pessoal: fica registrado (LGPD).
    registrar(RegistroAuditoria.Acao.ACESSO, obj, None, None, request.user)
    pedidos = list(
        obj.pedidos_historicos.prefetch_related(Prefetch("itens", queryset=_itens_com_foto())).order_by("-realizado_em")
    )
    for pedido in pedidos:
        for item in pedido.itens.all():
            item.foto = _foto_do_item(item)
    for pedido in pedidos:
        pedido.situacao = _status_pedido(pedido)
    pagos = [p for p in pedidos if p.pago]
    total_gasto = sum((p.total for p in pagos), start=metricas.ZERO)
    return render(
        request,
        "gestao/cliente.html",
        {
            "secao": "clientes",
            "cliente": obj,
            "form": form,
            "pode_editar": pode_editar,
            "pedidos": pedidos,
            "total_gasto": total_gasto,
            "n_pagos": len(pagos),
            "ticket": (total_gasto / len(pagos)).quantize(metricas.ZERO) if pagos else None,
            "enderecos": obj.enderecos.order_by("-padrao", "-id"),
            "consentimentos": obj.consentimentos.order_by("-registrado_em"),
            "documento": request.session.pop(f"documento_{obj.pk}", None),
        },
    )


@require_POST
@equipe(permissao="clientes.change_cliente")
def cliente_documento(request, pk):
    """Mostra o CPF/CNPJ completo uma única vez, com registro de acesso."""
    obj = get_object_or_404(Cliente, pk=pk)
    if obj.documento:
        registrar(RegistroAuditoria.Acao.ACESSO, obj, None, {"campo": "documento"}, request.user)
        request.session[f"documento_{obj.pk}"] = obj.documento
    return redirect("gestao:cliente", pk=obj.pk)


@require_POST
@equipe(permissao="clientes.change_cliente")
def cliente_exportar(request, pk):
    obj = get_object_or_404(Cliente, pk=pk)
    dados = lgpd.exportar_dados(obj, usuario=request.user)
    resposta = HttpResponse(
        json.dumps(dados, ensure_ascii=False, indent=2, default=str), content_type="application/json; charset=utf-8"
    )
    resposta["Content-Disposition"] = f'attachment; filename="dados-cliente-{obj.uuid}.json"'
    return resposta


@require_POST
@equipe(permissao="clientes.delete_cliente")
def cliente_anonimizar(request, pk):
    obj = get_object_or_404(Cliente, pk=pk)
    if request.POST.get("confirmacao", "").strip().upper() != "ANONIMIZAR":
        messages.error(request, "Digite ANONIMIZAR para confirmar.")
        return redirect("gestao:cliente", pk=obj.pk)
    lgpd.anonimizar(obj, usuario=request.user)
    messages.success(request, "Cliente anonimizado. O histórico de vendas foi mantido sem dados pessoais.")
    return redirect("gestao:cliente", pk=obj.pk)


# ---------------------------------------------------------------- pedidos


@equipe(permissao="historico.view_pedidohistorico")
def pedidos(request):
    qs = PedidoHistorico.objects.select_related("cliente").annotate(n_itens=Sum("itens__quantidade"))
    termo = request.GET.get("q", "").strip()
    if termo:
        filtro = Q(cliente__nome__icontains=termo) | Q(cupom__iexact=termo)
        if termo.lstrip("#").isdigit():
            filtro |= Q(numero=int(termo.lstrip("#")))
        qs = qs.filter(filtro)
    situacao = request.GET.get("situacao", "")
    if situacao == "pagos":
        qs = qs.filter(status_pagamento__in=STATUS_PAGOS).exclude(status="cancelled")
    elif situacao == "pendentes":
        qs = qs.filter(status_pagamento__in=["pending", "authorized"]).exclude(status="cancelled")
    elif situacao == "cancelados":
        qs = qs.filter(Q(status="cancelled") | Q(status_pagamento__in=["voided", "refunded"]))
    if request.GET.get("cupom") == "1":
        qs = qs.exclude(cupom="")
    periodo = request.GET.get("periodo", "")
    inicio, _ = metricas.intervalo(periodo) if periodo in metricas.PERIODOS else (None, None)
    if inicio:
        qs = qs.filter(realizado_em__gte=inicio)
    pagina = _paginar(request, qs.order_by("-realizado_em"))
    for pedido in pagina.object_list:
        pedido.situacao = _status_pedido(pedido)
        pedido.envio = STATUS_ENVIO.get(pedido.status_envio, pedido.status_envio or "—")
    soma = qs.filter(status_pagamento__in=STATUS_PAGOS).exclude(status="cancelled").aggregate(t=Sum("total"))["t"]
    return render(
        request,
        "gestao/pedidos.html",
        {
            "secao": "pedidos",
            "pagina": pagina,
            "termo": termo,
            "situacao": situacao,
            "periodo": periodo,
            "periodos": metricas.PERIODOS,
            "cupom": request.GET.get("cupom", ""),
            "consulta": _consulta_sem_pagina(request),
            "soma_pagos": soma or metricas.ZERO,
        },
    )


@equipe(permissao="historico.view_pedidohistorico")
def pedido(request, pk):
    obj = get_object_or_404(PedidoHistorico.objects.select_related("cliente"), pk=pk)
    obj.situacao = _status_pedido(obj)
    obj.envio = STATUS_ENVIO.get(obj.status_envio, obj.status_envio or "—")
    itens = list(_itens_com_foto().filter(pedido=obj))
    for item in itens:
        item.subtotal = item.preco_unitario * item.quantidade
        item.foto = _foto_do_item(item)
    if obj.cliente_id:
        registrar(RegistroAuditoria.Acao.ACESSO, obj.cliente, None, {"pedido": obj.numero}, request.user)
    return render(request, "gestao/pedido.html", {"secao": "pedidos", "pedido": obj, "itens": itens})


# ---------------------------------------------------------------- banners e páginas


@equipe(permissao="catalogo.view_banner")
def banners(request):
    agora = timezone.now()
    lista = list(Banner.objects.order_by("ordem", "-id"))
    no_ar = set(Banner.no_ar().values_list("pk", flat=True))
    for banner in lista:
        if banner.pk in no_ar:
            banner.situacao = ("No ar", "ok")
        elif banner.ativo and banner.inicio and banner.inicio > agora:
            banner.situacao = ("Agendado", "aviso")
        elif banner.ativo and banner.fim and banner.fim <= agora:
            banner.situacao = ("Encerrado", "neutro")
        else:
            banner.situacao = ("Desligado", "neutro")
    return render(request, "gestao/banners.html", {"secao": "banners", "banners": lista})


@equipe(permissao="catalogo.view_banner")
def banner_editar(request, pk=None):
    banner = get_object_or_404(Banner, pk=pk) if pk else Banner()
    pode_editar = request.user.has_perm("catalogo.change_banner" if pk else "catalogo.add_banner")
    if request.method == "POST" and pode_editar:
        if "excluir" in request.POST and pk and request.user.has_perm("catalogo.delete_banner"):
            registrar(RegistroAuditoria.Acao.EXCLUSAO, banner, foto(banner), None, request.user)
            banner.delete()
            messages.success(request, "Banner excluído.")
            return redirect("gestao:banners")
        antes = foto(banner) if pk else None
        form = BannerForm(request.POST, request.FILES, instance=banner)
        if form.is_valid():
            banner = form.save()
            _auditar(request, banner, antes)
            messages.success(request, "Banner salvo.")
            return redirect("gestao:banners")
        messages.error(request, "Confira os campos destacados.")
    else:
        form = BannerForm(instance=banner)
    return render(
        request,
        "gestao/banner_form.html",
        {"secao": "banners", "banner": banner, "form": form, "pode_editar": pode_editar},
    )


@equipe(permissao="core.view_pagina")
def paginas(request):
    return render(request, "gestao/paginas.html", {"secao": "paginas", "paginas": Pagina.objects.order_by("titulo")})


@equipe(permissao="core.view_pagina")
def pagina_editar(request, pk=None):
    pagina = get_object_or_404(Pagina, pk=pk) if pk else Pagina()
    pode_editar = request.user.has_perm("core.change_pagina" if pk else "core.add_pagina")
    if request.method == "POST" and pode_editar:
        antes = foto(pagina) if pk else None
        form = PaginaForm(request.POST, instance=pagina)
        if form.is_valid():
            pagina = form.save()
            _auditar(request, pagina, antes)
            messages.success(request, "Página salva.")
            return redirect("gestao:paginas")
        messages.error(request, "Confira os campos destacados.")
    else:
        form = PaginaForm(instance=pagina)
    return render(
        request,
        "gestao/pagina_form.html",
        {"secao": "paginas", "pagina": pagina, "form": form, "pode_editar": pode_editar},
    )


# ---------------------------------------------------------------- configurações


@equipe(permissao="core.change_parametro")
def configuracoes(request):
    form = ConfiguracoesForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            mudancas = form.alterados()
            with transaction.atomic():
                for parametro, valor in mudancas:
                    antes = foto(parametro)
                    parametro.valor = valor
                    parametro.full_clean()
                    parametro.save()
                    _auditar(request, parametro, antes)
            messages.success(request, f"Configurações salvas ({len(mudancas)} alteração(ões)).")
            return redirect("gestao:configuracoes")
        messages.error(request, "Confira os campos destacados.")
    return render(request, "gestao/configuracoes.html", {"secao": "configuracoes", "form": form})
