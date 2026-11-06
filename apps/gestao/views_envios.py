"""Integração com o Melhor Envio no painel: conectar a conta e comprar/imprimir/rastrear/cancelar etiquetas."""

import secrets
from decimal import Decimal
from types import SimpleNamespace
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.catalogo.models import Variacao
from apps.catalogo.templatetags.vitrine import brl
from apps.clientes.models import Cliente
from apps.core.auditoria import registrar
from apps.core.crypto import hash_busca
from apps.core.models import RegistroAuditoria
from apps.core.validators import so_digitos, validar_cnpj, validar_cpf
from apps.envios import melhorenvio, servicos
from apps.envios.melhorenvio import ErroMelhorEnvio, MelhorEnvio
from apps.envios.models import Envio
from apps.vendas.models import Pedido

from .acesso import equipe

PERMISSAO_INTEGRACAO = "envios.change_conexaomelhorenvio"


def _redirect_uri(request) -> str:
    return settings.MELHOR_ENVIO_REDIRECT_URI or request.build_absolute_uri(reverse("gestao:melhorenvio_retorno"))


def _ficha(pedido) -> str:
    return f"{reverse('gestao:venda', args=[pedido.pk])}#envio"


def _chave_cotacao(pk) -> str:
    return f"cotacao_{pk}"


# ---------------------------------------------------------------- conectar a conta


@equipe(permissao=PERMISSAO_INTEGRACAO)
def integracoes(request):
    conexao = melhorenvio.conexao_atual()
    saldo = erro_saldo = None
    if conexao and conexao.conectada:
        try:
            saldo = MelhorEnvio().saldo()
        except ErroMelhorEnvio as erro:
            erro_saldo = str(erro)
    return render(
        request,
        "gestao/integracoes.html",
        {
            "secao": "integracoes",
            "configurado": melhorenvio.configurado(),
            "ambiente": melhorenvio.ambiente(),
            "conexao": conexao,
            "saldo": Decimal(str(saldo)) if saldo not in (None, "") else None,
            "erro_saldo": erro_saldo,
            "redirect_uri": _redirect_uri(request),
            "painel_melhorenvio": melhorenvio.base(),
        },
    )


@equipe(permissao=PERMISSAO_INTEGRACAO)
def melhorenvio_conectar(request):
    if not melhorenvio.configurado():
        messages.error(request, "Preencha MELHOR_ENVIO_CLIENT_ID e MELHOR_ENVIO_CLIENT_SECRET no .env primeiro.")
        return redirect("gestao:integracoes")
    estado = secrets.token_urlsafe(24)
    request.session["melhorenvio_estado"] = estado
    return HttpResponseRedirect(melhorenvio.url_autorizacao(_redirect_uri(request), estado))


@equipe(permissao=PERMISSAO_INTEGRACAO)
def melhorenvio_retorno(request):
    estado = request.session.pop("melhorenvio_estado", None)
    if not estado or not secrets.compare_digest(estado, request.GET.get("state", "")):
        messages.error(request, "Não foi possível confirmar a conexão (link expirado). Tente conectar de novo.")
        return redirect("gestao:integracoes")
    codigo = request.GET.get("code", "")
    if not codigo:
        messages.error(request, "A autorização foi recusada no Melhor Envio.")
        return redirect("gestao:integracoes")
    try:
        conexao = melhorenvio.trocar_codigo(codigo, _redirect_uri(request))
    except ErroMelhorEnvio as erro:
        messages.error(request, f"Não foi possível conectar: {erro}")
        return redirect("gestao:integracoes")
    try:
        usuario = MelhorEnvio(conexao.access_token).usuario()
        nome = " ".join(p for p in (usuario.get("firstname"), usuario.get("lastname")) if p)
        if nome:
            conexao.conta = nome[:150]
            conexao.save(update_fields=["conta", "atualizado_em", "atualizado_por"])
    except ErroMelhorEnvio:
        pass
    registrar(RegistroAuditoria.Acao.ALTERACAO, conexao, None, {"evento": "conta conectada"}, request.user)
    messages.success(request, "Melhor Envio conectado. Já dá para cotar e comprar etiquetas nas vendas.")
    return redirect("gestao:integracoes")


@require_POST
@equipe(permissao=PERMISSAO_INTEGRACAO)
def melhorenvio_desconectar(request):
    conexao = melhorenvio.conexao_atual()
    if conexao:
        registrar(RegistroAuditoria.Acao.EXCLUSAO, conexao, None, None, request.user)
        conexao.delete()
    messages.success(request, "Conta do Melhor Envio desconectada deste painel.")
    return redirect("gestao:integracoes")


# ---------------------------------------------------------------- etiquetas da venda


@require_POST
@equipe(permissao="vendas.add_pedido")
def frete_simular(request):
    """Cotação na tela de lançar venda (antes de a venda existir): devolve as opções em JSON."""
    quantidades: dict[int, int] = {}
    for pk, qtd in zip(request.POST.getlist("variacao"), request.POST.getlist("quantidade"), strict=False):
        if pk.isdigit() and qtd.isdigit() and 0 < int(qtd) < 1000:
            quantidades[int(pk)] = quantidades.get(int(pk), 0) + int(qtd)
    variacoes = Variacao.objects.select_related("produto").filter(pk__in=quantidades, produto__isnull=False)
    itens = [
        SimpleNamespace(produto=v.produto, produto_id=v.produto_id, quantidade=quantidades[v.pk], preco=v.preco_final)
        for v in variacoes
    ]
    peso = request.POST.get("peso_g", "")
    try:
        opcoes = servicos.simular(
            request.POST.get("cep", ""),
            itens,
            sum((i.preco * i.quantidade for i in itens), Decimal("0.00")),
            peso_g=int(peso) if peso.isdigit() and int(peso) > 0 else None,
        )
    except ErroMelhorEnvio as erro:
        return JsonResponse({"erro": str(erro)}, status=400)
    return JsonResponse({"opcoes": opcoes})


@require_POST
@equipe(permissao="vendas.change_pedido")
def frete_cotar(request, pk):
    pedido = get_object_or_404(Pedido, pk=pk)
    try:
        opcoes = servicos.cotar(pedido)
    except ErroMelhorEnvio as erro:
        messages.error(request, str(erro))
    else:
        quando = timezone.localtime().strftime("%d/%m às %H:%M")
        request.session[_chave_cotacao(pk)] = {"opcoes": opcoes, "quando": quando}
        if not any(not o["erro"] for o in opcoes):
            messages.warning(request, "Nenhuma transportadora atende esse CEP com esse pacote.")
    return redirect(_ficha(pedido))


def _documento_para_envio(request, pedido: Pedido, informado: str, com_nota: bool) -> str:
    """CPF/CNPJ do destinatário: o digitado ou o do cadastro (acesso registrado). Obrigatório na declaração."""
    informado = so_digitos(informado)
    cliente = pedido.cliente
    if informado:
        if len(informado) == 14:
            validar_cnpj(informado)
        else:
            validar_cpf(informado)
        if cliente and not cliente.documento and request.POST.get("salvar_documento"):
            outro = Cliente.objects.filter(documento_hash=hash_busca(informado)).exclude(pk=cliente.pk).exists()
            if not outro:  # o mesmo documento não pode ficar em dois cadastros
                cliente.documento = informado
                if len(informado) == 14:
                    cliente.tipo = Cliente.Tipo.PESSOA_JURIDICA
                cliente.save()
                registrar(RegistroAuditoria.Acao.ALTERACAO, cliente, None, {"campo": "documento"}, request.user)
        return informado
    if cliente and cliente.documento:
        registrar(
            RegistroAuditoria.Acao.ACESSO,
            cliente,
            None,
            {"campo": "documento", "motivo": "etiqueta de envio", "venda": pedido.codigo},
            request.user,
        )
        return cliente.documento
    if not com_nota:
        raise ValidationError("Informe o CPF/CNPJ do destinatário: a declaração de conteúdo exige.")
    return ""


@require_POST
@equipe(permissao="vendas.change_pedido")
def frete_comprar(request, pk):
    pedido = get_object_or_404(Pedido.objects.select_related("cliente"), pk=pk)
    servico = request.POST.get("servico", "")
    chave = so_digitos(request.POST.get("chave_nfe", ""))
    if not servico.isdigit():
        messages.error(request, "Escolha uma das opções de frete.")
        return redirect(_ficha(pedido))
    if chave and len(chave) != 44:
        messages.error(request, "A chave da nota fiscal tem 44 números.")
        return redirect(_ficha(pedido))
    try:
        documento = _documento_para_envio(request, pedido, request.POST.get("documento", ""), bool(chave))
        envio = servicos.comprar_etiqueta(
            pedido, int(servico), documento=documento, chave_nfe=chave, usuario=request.user
        )
    except ValidationError as erro:
        messages.error(request, " ".join(erro.messages))
        return redirect(_ficha(pedido))
    except ErroMelhorEnvio as erro:
        messages.error(request, str(erro))
        return redirect(_ficha(pedido))
    request.session.pop(_chave_cotacao(pk), None)
    if envio.status == Envio.Status.GERADO:
        messages.success(
            request, f"Etiqueta {envio.transportadora} {envio.servico} comprada ({brl(envio.preco)}). Pode imprimir."
        )
    else:
        messages.warning(request, f"Etiqueta paga, mas ainda não gerada: {envio.erro or 'tente gerar de novo'}.")
    return redirect(_ficha(pedido))


def _envio(pk) -> Envio:
    return get_object_or_404(Envio.objects.select_related("pedido"), pk=pk)


def _redirecionar_para_arquivo(request, envio: Envio, url: str):
    partes = urlsplit(url or "")
    if partes.scheme != "https" or not partes.netloc:
        messages.error(request, "O Melhor Envio não devolveu o arquivo. Tente de novo em instantes.")
        return redirect(_ficha(envio.pedido))
    return HttpResponseRedirect(url)


@equipe(permissao="vendas.imprimir_etiqueta")
def envio_imprimir(request, pk):
    envio = _envio(pk)
    if not envio.pode_imprimir:
        messages.error(request, "A etiqueta ainda não está pronta para impressão.")
        return redirect(_ficha(envio.pedido))
    try:
        url = MelhorEnvio().imprimir(envio.me_id)
    except ErroMelhorEnvio as erro:
        messages.error(request, str(erro))
        return redirect(_ficha(envio.pedido))
    registrar(RegistroAuditoria.Acao.ACESSO, envio, None, {"evento": "etiqueta impressa"}, request.user)
    return _redirecionar_para_arquivo(request, envio, url)


@equipe(permissao="vendas.imprimir_etiqueta")
def envio_dace(request, pk):
    envio = _envio(pk)
    try:
        url = MelhorEnvio().dace(envio.me_id)
    except ErroMelhorEnvio as erro:
        messages.error(request, f"Declaração eletrônica indisponível: {erro}")
        return redirect(_ficha(envio.pedido))
    return _redirecionar_para_arquivo(request, envio, url)


@require_POST
@equipe(permissao="vendas.change_pedido")
def envio_acao(request, pk, acao):
    envio = _envio(pk)
    try:
        if acao == "gerar":
            servicos.gerar(envio, usuario=request.user)
            messages.success(request, "Etiqueta gerada. Pode imprimir.")
        elif acao == "rastrear":
            servicos.atualizar_rastreio(envio, usuario=request.user)
            envio.refresh_from_db()
            messages.success(request, f"Rastreio atualizado: {envio.get_status_display().lower()}.")
        elif acao == "cancelar":
            servicos.cancelar(envio, usuario=request.user)
            messages.success(request, "Etiqueta cancelada. O valor volta para o saldo do Melhor Envio em até 12 horas.")
        else:
            messages.error(request, "Ação desconhecida.")
    except ErroMelhorEnvio as erro:
        messages.error(request, str(erro))
    return redirect(_ficha(envio.pedido))
