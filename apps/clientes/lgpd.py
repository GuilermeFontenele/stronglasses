"""Direitos do titular (art. 18 da LGPD) e rotinas de retenção."""

from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.core.auditoria import registrar
from apps.core.middleware import ip_da_requisicao
from apps.core.models import RegistroAuditoria

from .models import Cliente, Consentimento


def registrar_consentimento(cliente: Cliente, finalidade: str, origem: str, request=None) -> Consentimento:
    return Consentimento.objects.create(
        cliente=cliente,
        finalidade=finalidade,
        concedido=True,
        versao_politica=settings.LGPD_VERSAO_POLITICA,
        origem=origem,
        ip=ip_da_requisicao(request) if request else None,
        user_agent=(request.META.get("HTTP_USER_AGENT", "")[:255] if request else ""),
    )


def revogar_consentimento(cliente: Cliente, finalidade: str) -> int:
    return cliente.consentimentos.filter(finalidade=finalidade, revogado_em__isnull=True).update(
        revogado_em=timezone.now()
    )


def exportar_dados(cliente: Cliente, usuario=None) -> dict:
    """Portabilidade/acesso: tudo que guardamos sobre o titular, em formato legível."""
    dados = {
        "gerado_em": timezone.now().isoformat(),
        "controlador": "Strong Glasses",
        "contato_encarregado": settings.LGPD_CONTATO_ENCARREGADO,
        "cliente": {
            "identificador": str(cliente.uuid),
            "tipo": cliente.get_tipo_display(),
            "nome": cliente.nome,
            "razao_social": cliente.razao_social,
            "email": cliente.email,
            "whatsapp": cliente.whatsapp,
            "documento": cliente.documento,
            "cadastrado_em": cliente.criado_em.isoformat(),
        },
        "enderecos": [
            {
                "destinatario": e.destinatario,
                "cep": e.cep,
                "logradouro": e.logradouro,
                "numero": e.numero,
                "complemento": e.complemento,
                "bairro": e.bairro,
                "cidade": e.cidade,
                "uf": e.uf,
                "padrao": e.padrao,
            }
            for e in cliente.enderecos.all()
        ],
        "consentimentos": [
            {
                "finalidade": c.get_finalidade_display(),
                "concedido": c.concedido,
                "versao_politica": c.versao_politica,
                "origem": c.get_origem_display(),
                "registrado_em": c.registrado_em.isoformat(),
                "revogado_em": c.revogado_em.isoformat() if c.revogado_em else None,
            }
            for c in cliente.consentimentos.all()
        ],
        "pedidos_anteriores": [
            {
                "numero": p.numero,
                "data": p.realizado_em.isoformat(),
                "total": str(p.total),
                "pagamento": p.status_pagamento,
                "cidade": p.cidade,
                "uf": p.uf,
                "itens": [
                    {
                        "produto": i.nome,
                        "variante": i.variante,
                        "quantidade": i.quantidade,
                        "preco": str(i.preco_unitario),
                    }
                    for i in p.itens.all()
                ],
            }
            for p in cliente.pedidos_historicos.prefetch_related("itens")
        ],
        "compras": [
            {
                "codigo": v.codigo,
                "data": v.realizado_em.isoformat(),
                "situacao": v.get_situacao_display(),
                "canal": v.get_canal_display(),
                "forma_pagamento": v.get_forma_pagamento_display(),
                "total": str(v.total),
                "entrega": v.get_entrega_display(),
                "destinatario": v.destinatario,
                "endereco": ", ".join(
                    parte
                    for parte in (v.logradouro, v.numero_endereco, v.complemento, v.bairro, v.cidade, v.uf, v.cep)
                    if parte
                ),
                "codigo_rastreio": v.codigo_rastreio,
                "itens": [
                    {"produto": i.nome, "cor": i.cor, "quantidade": i.quantidade, "preco": str(i.preco_unitario)}
                    for i in v.itens.all()
                ],
            }
            for v in cliente.vendas.prefetch_related("itens")
        ],
    }
    registrar(RegistroAuditoria.Acao.EXPORTACAO, cliente, None, None, usuario)
    return dados


@transaction.atomic
def anonimizar(cliente: Cliente, usuario=None) -> Cliente:
    """Eliminação (art. 18, VI). Mantém o registro para preservar o histórico de
    vendas (obrigações legais), mas remove tudo que identifica a pessoa."""
    cliente.nome = "Titular anonimizado"
    cliente.razao_social = ""
    cliente.email = ""
    cliente.whatsapp = ""
    cliente.documento = ""
    cliente.anonimizado_em = timezone.now()
    cliente.save()
    cliente.enderecos.all().delete()
    # Vendas ficam (obrigação fiscal), mas sem o endereço de entrega; cidade/UF bastam para as estatísticas.
    cliente.vendas.update(
        destinatario="",
        cep="",
        logradouro="",
        numero_endereco="",
        complemento="",
        bairro="",
        codigo_rastreio="",
        observacoes="",
    )
    cliente.consentimentos.filter(revogado_em__isnull=True).update(revogado_em=timezone.now())
    cliente.consentimentos.update(ip=None, user_agent="")
    registrar(RegistroAuditoria.Acao.ANONIMIZACAO, cliente, None, None, usuario)
    return cliente


def expurgar_dados_tecnicos(dias: int | None = None) -> int:
    """Apaga IP e navegador de consentimentos mais antigos que a retenção definida."""
    dias = settings.LGPD_RETENCAO_IP_DIAS if dias is None else dias
    limite = timezone.now() - timedelta(days=dias)
    return (
        Consentimento.objects.filter(registrado_em__lt=limite)
        .exclude(ip__isnull=True, user_agent="")
        .update(ip=None, user_agent="")
    )
