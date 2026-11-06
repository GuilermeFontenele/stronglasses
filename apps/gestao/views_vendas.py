"""Vendas lançadas no painel (WhatsApp, hotel, barbearia...), etiqueta de envio e declaração de conteúdo."""

from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.catalogo.templatetags.vitrine import brl
from apps.clientes.models import Cliente, Endereco
from apps.core.auditoria import registrar
from apps.core.crypto import hash_busca
from apps.core.models import RegistroAuditoria
from apps.core.parametros import get_parametros
from apps.core.validators import so_digitos
from apps.vendas.models import Pedido, sigla_uf
from apps.vendas.servicos import EstoqueInsuficiente, ItemNovo, mudar_situacao, registrar_venda

from . import metricas
from .acesso import equipe
from .forms import ClienteNovoForm, ItemVendaFormSet, SituacaoVendaForm, VendaForm, opcoes_variacoes
from .views import _auditar, _consulta_sem_pagina, _foto_do_item, _itens_venda_com_foto, _paginar

PESO_PADRAO_G = 300
ENVIO = [Pedido.Entrega.CORREIOS, Pedido.Entrega.TRANSPORTADORA]


def _buscar_clientes(termo: str):
    qs = Cliente.objects.filter(anonimizado_em__isnull=True)
    filtro = Q(nome__icontains=termo) | Q(email__icontains=termo) | Q(razao_social__icontains=termo)
    digitos = so_digitos(termo)
    if len(digitos) >= 8:
        filtro |= Q(whatsapp__contains=digitos)
    if len(digitos) in (11, 14):
        filtro |= Q(documento_hash=hash_busca(digitos))
    return qs.filter(filtro).order_by("nome")


def _numero_da_busca(termo: str) -> int | None:
    """'SG00012', 'sg12', '#12' ou '12' -> 12."""
    limpo = termo.upper().removeprefix("SG").lstrip("#").strip()
    return int(limpo) if limpo.isdigit() else None


# ---------------------------------------------------------------- lista


@equipe(permissao="vendas.view_pedido")
def vendas(request):
    qs = Pedido.objects.select_related("cliente").annotate(n_itens=Sum("itens__quantidade"))
    termo = request.GET.get("q", "").strip()
    if termo:
        filtro = (
            Q(cliente__nome__icontains=termo)
            | Q(parceiro__icontains=termo)
            | Q(cupom__iexact=termo)
            | Q(codigo_rastreio__iexact=termo)
        )
        numero = _numero_da_busca(termo)
        if numero is not None:
            filtro |= Q(numero=numero)
        qs = qs.filter(filtro)
    situacao = request.GET.get("situacao", "")
    if situacao == "pagas":
        qs = qs.filter(situacao__in=Pedido.PAGOS)
    elif situacao == "a-enviar":
        qs = qs.filter(
            situacao=Pedido.Situacao.PAGO, entrega__in=[Pedido.Entrega.CORREIOS, Pedido.Entrega.TRANSPORTADORA]
        )
    elif situacao in Pedido.Situacao.values:
        qs = qs.filter(situacao=situacao)
    canal = request.GET.get("canal", "")
    if canal in Pedido.Canal.values:
        qs = qs.filter(canal=canal)
    periodo = request.GET.get("periodo", "")
    inicio, _ = metricas.intervalo(periodo) if periodo in metricas.PERIODOS else (None, None)
    if inicio:
        qs = qs.filter(realizado_em__gte=inicio)
    soma = qs.filter(situacao__in=Pedido.PAGOS).aggregate(t=Sum("total"))["t"]
    a_enviar = Pedido.objects.filter(situacao=Pedido.Situacao.PAGO, entrega__in=ENVIO).count()
    return render(
        request,
        "gestao/vendas.html",
        {
            "secao": "vendas",
            "pagina": _paginar(request, qs.order_by("-realizado_em", "-numero")),
            "termo": termo,
            "situacao": situacao,
            "situacoes": Pedido.Situacao.choices,
            "canal": canal,
            "canais": Pedido.Canal.choices,
            "periodo": periodo,
            "periodos": metricas.PERIODOS,
            "consulta": _consulta_sem_pagina(request),
            "soma_pagas": soma or metricas.ZERO,
            "a_enviar": a_enviar,
        },
    )


# ---------------------------------------------------------------- lançar venda


def _inicial(cliente: Cliente | None) -> dict:
    inicial = {"realizado_em": timezone.localtime().replace(second=0, microsecond=0), "uf": "CE"}
    if not cliente:
        return inicial
    inicial["destinatario"] = cliente.nome
    endereco = cliente.enderecos.order_by("-padrao", "-id").first()
    if endereco:
        inicial.update(
            destinatario=endereco.destinatario or cliente.nome,
            cep=endereco.cep,
            logradouro=endereco.logradouro,
            numero_endereco=endereco.numero,
            complemento=endereco.complemento,
            bairro=endereco.bairro,
            cidade=endereco.cidade,
            uf=sigla_uf(endereco.uf) or "CE",
        )
    return inicial


def _salvar_endereco(request, cliente: Cliente, pedido: Pedido):
    dados = {
        "destinatario": pedido.destinatario,
        "cep": pedido.cep,
        "logradouro": pedido.logradouro,
        "numero": pedido.numero_endereco,
        "complemento": pedido.complemento,
        "bairro": pedido.bairro,
        "cidade": pedido.cidade,
        "uf": pedido.uf,
    }
    existente = cliente.enderecos.filter(cep=pedido.cep, logradouro=pedido.logradouro, numero=pedido.numero_endereco)
    if existente.exists():
        return
    endereco = Endereco.objects.create(cliente=cliente, padrao=not cliente.enderecos.exists(), **dados)
    _auditar(request, endereco, None)


@equipe(permissao="vendas.add_pedido")
def venda_nova(request):
    cliente_id = request.POST.get("cliente") or request.GET.get("cliente") or ""
    cliente = (
        Cliente.objects.filter(pk=int(cliente_id), anonimizado_em__isnull=True).first()
        if cliente_id.isdigit()
        else None
    )
    busca = request.GET.get("busca_cliente", "").strip()
    resultados = list(_buscar_clientes(busca)[:8]) if busca and not cliente else []
    opcoes = opcoes_variacoes()
    if request.method == "POST":
        form = VendaForm(request.POST, initial=_inicial(cliente))
        itens = ItemVendaFormSet(request.POST, prefix="itens", form_kwargs={"opcoes": opcoes})
        if form.is_valid() and itens.is_valid():
            pedido = form.save(commit=False)
            pedido.cliente = cliente
            novos = [
                ItemNovo(f.cleaned_data["variacao"], f.cleaned_data["quantidade"], f.cleaned_data.get("preco_unitario"))
                for f in itens.forms
                if f.cleaned_data
            ]
            try:
                with transaction.atomic():
                    pedido = registrar_venda(
                        pedido,
                        novos,
                        baixar_estoque=form.cleaned_data["baixar_estoque"],
                        aplicar_pix=form.cleaned_data["aplicar_pix"],
                        usuario=request.user,
                    )
                    if cliente and form.cleaned_data["salvar_endereco"] and pedido.tem_endereco:
                        _salvar_endereco(request, cliente, pedido)
            except EstoqueInsuficiente as erro:
                for falta in erro.faltas:
                    messages.error(request, f"Estoque insuficiente: {falta}.")
                messages.info(request, "Ajuste a quantidade ou desligue “Baixar do estoque”.")
            else:
                messages.success(request, f"Venda {pedido.codigo} registrada · total {brl(pedido.total)}.")
                return redirect("gestao:venda", pk=pedido.pk)
        else:
            messages.error(request, "Confira os campos destacados.")
    else:
        form = VendaForm(initial=_inicial(cliente))
        itens = ItemVendaFormSet(prefix="itens", form_kwargs={"opcoes": opcoes})
    pix = get_parametros("PIX_DESCONTO_PERCENTUAL", padroes={"PIX_DESCONTO_PERCENTUAL": 0})["PIX_DESCONTO_PERCENTUAL"]
    pix = Decimal(str(pix or 0))
    if pix:
        form.fields["aplicar_pix"].label = f"Desconto do Pix ({format(pix.normalize(), 'f').replace('.', ',')}%)"
    return render(
        request,
        "gestao/venda_form.html",
        {
            "secao": "vendas",
            "form": form,
            "itens": itens,
            "cliente": cliente,
            "busca": busca,
            "resultados": resultados,
            "pix_percentual": pix,
        },
    )


@equipe(permissao="clientes.add_cliente")
def cliente_novo(request):
    """Cadastro rápido. Vindo do lançamento de venda, volta para ele com o cliente já escolhido."""
    para_venda = request.GET.get("para") == "venda" or request.POST.get("para") == "venda"
    form = ClienteNovoForm(request.POST or None, initial={"nome": request.GET.get("nome", "")[:150]})
    if request.method == "POST":
        if form.is_valid():
            obj = form.save()
            _auditar(request, obj, None)
            messages.success(request, f"Cliente “{obj.nome}” cadastrado.")
            if para_venda:
                return redirect(f"{reverse('gestao:venda_nova')}?cliente={obj.pk}")
            return redirect("gestao:cliente", pk=obj.pk)
        messages.error(request, "Confira os campos destacados.")
    return render(request, "gestao/cliente_novo.html", {"secao": "clientes", "form": form, "para_venda": para_venda})


# ---------------------------------------------------------------- detalhe


@equipe(permissao="vendas.view_pedido")
def venda(request, pk):
    obj = get_object_or_404(Pedido.objects.select_related("cliente"), pk=pk)
    pode_editar = request.user.has_perm("vendas.change_pedido")
    form = SituacaoVendaForm(initial={"situacao": obj.situacao, "codigo_rastreio": obj.codigo_rastreio})
    if request.method == "POST" and pode_editar:
        if obj.situacao == Pedido.Situacao.CANCELADO:
            messages.error(request, "Venda cancelada não pode ser alterada.")
            return redirect("gestao:venda", pk=obj.pk)
        if request.POST.get("acao") == "cancelar":
            devolveu = obj.estoque_baixado
            mudar_situacao(obj, Pedido.Situacao.CANCELADO, usuario=request.user)
            aviso = " Os itens voltaram para o estoque." if devolveu else ""
            messages.success(request, f"Venda {obj.codigo} cancelada.{aviso}")
            return redirect("gestao:venda", pk=obj.pk)
        form = SituacaoVendaForm(request.POST)
        if form.is_valid():
            mudar_situacao(
                obj,
                form.cleaned_data["situacao"],
                usuario=request.user,
                codigo_rastreio=form.cleaned_data["codigo_rastreio"],
            )
            messages.success(request, "Venda atualizada.")
            return redirect("gestao:venda", pk=obj.pk)
        messages.error(request, "Confira os campos destacados.")
    itens = list(_itens_venda_com_foto().filter(pedido=obj))
    for item in itens:
        item.foto = _foto_do_item(item)
    if obj.cliente_id:  # a ficha da venda mostra endereço: acesso a dado pessoal fica registrado
        registrar(RegistroAuditoria.Acao.ACESSO, obj.cliente, None, {"venda": obj.codigo}, request.user)
    return render(
        request,
        "gestao/venda.html",
        {"secao": "vendas", "pedido": obj, "itens": itens, "form": form, "pode_editar": pode_editar},
    )


# ---------------------------------------------------------------- etiqueta e declaração de conteúdo


def peso_do_pacote(pedido: Pedido, itens, padrao: int) -> int:
    if pedido.peso_g:
        return pedido.peso_g
    return sum(
        ((item.produto.peso_g if item.produto and item.produto.peso_g else padrao) * item.quantidade) for item in itens
    )


@equipe(permissao="vendas.imprimir_etiqueta")
def venda_etiqueta(request, pk):
    obj = get_object_or_404(Pedido.objects.select_related("cliente"), pk=pk)
    p = get_parametros(
        "REMETENTE_NOME",
        "REMETENTE_ENDERECO",
        "REMETENTE_BAIRRO",
        "REMETENTE_CIDADE",
        "REMETENTE_UF",
        "REMETENTE_CEP",
        "CNPJ_LOJA",
        "PESO_PADRAO_G",
        padroes={"REMETENTE_NOME": "Strong Glasses", "PESO_PADRAO_G": PESO_PADRAO_G},
    )
    remetente = {
        "nome": p["REMETENTE_NOME"] or "Strong Glasses",
        "endereco": p["REMETENTE_ENDERECO"] or "",
        "bairro": p["REMETENTE_BAIRRO"] or "",
        "cidade": p["REMETENTE_CIDADE"] or "",
        "uf": (p["REMETENTE_UF"] or "").upper(),
        "cep": so_digitos(p["REMETENTE_CEP"] or ""),
        "documento": so_digitos(p["CNPJ_LOJA"] or ""),
    }
    remetente["completo"] = all(remetente[c] for c in ("endereco", "cidade", "uf", "cep"))
    itens = list(obj.itens.select_related("produto"))
    peso = peso_do_pacote(obj, itens, int(p["PESO_PADRAO_G"] or PESO_PADRAO_G))
    documento = ""
    if obj.cliente_id and obj.cliente.documento:
        documento = obj.cliente.documento
        registrar(
            RegistroAuditoria.Acao.ACESSO,
            obj.cliente,
            None,
            {"campo": "documento", "motivo": "declaração de conteúdo", "venda": obj.codigo},
            request.user,
        )
    elif obj.cliente_id:
        registrar(RegistroAuditoria.Acao.ACESSO, obj.cliente, None, {"etiqueta": obj.codigo}, request.user)
    folha = request.GET.get("folha", "")
    if folha not in ("etiqueta", "declaracao"):
        folha = ""
    return render(
        request,
        "gestao/etiqueta.html",
        {
            "pedido": obj,
            "itens": itens,
            "remetente": remetente,
            "documento": documento,
            "peso_kg": Decimal(peso) / 1000,
            "valor_itens": sum((item.subtotal for item in itens), Decimal("0.00")),
            "quantidade_itens": sum(item.quantidade for item in itens),
            "folha": folha,
            "hoje": timezone.localdate(),
        },
    )
