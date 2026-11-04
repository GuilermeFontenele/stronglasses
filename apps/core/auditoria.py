"""Serviço de auditoria e mixin de admin que registra criações, alterações e exclusões."""

import json

from django.contrib import admin
from django.core.serializers.json import DjangoJSONEncoder
from django.forms.models import model_to_dict

from .middleware import get_ip_atual, get_usuario_atual
from .models import RegistroAuditoria

MASCARA = "***"
_IGNORADOS = {"criado_em", "atualizado_em", "criado_por", "atualizado_por"}


def _campos_sensiveis(obj) -> set[str]:
    return set(getattr(obj, "CAMPOS_SENSIVEIS_AUDITORIA", ()))


def foto(obj) -> dict:
    """Retrato serializável do objeto, com campos sensíveis mascarados."""
    dados = model_to_dict(obj)
    sensiveis = _campos_sensiveis(obj)
    resultado = {}
    for campo, valor in dados.items():
        if campo in _IGNORADOS:
            continue
        if campo in sensiveis:
            resultado[campo] = MASCARA if valor not in (None, "") else valor
            continue
        if hasattr(valor, "name"):  # arquivos
            valor = valor.name or None
        elif isinstance(valor, list):  # M2M
            valor = [getattr(item, "pk", item) for item in valor]
        resultado[campo] = valor
    return json.loads(json.dumps(resultado, cls=DjangoJSONEncoder))


def diferenca(antes: dict, depois: dict) -> tuple[dict, dict]:
    campos = {c for c in set(antes) | set(depois) if antes.get(c) != depois.get(c)}
    return ({c: antes.get(c) for c in sorted(campos)}, {c: depois.get(c) for c in sorted(campos)})


def registrar(acao: str, obj, antes: dict | None = None, depois: dict | None = None, usuario=None):
    usuario = usuario or get_usuario_atual()
    return RegistroAuditoria.objects.create(
        usuario=usuario,
        usuario_nome=getattr(usuario, "get_username", lambda: "")() if usuario else "sistema",
        ip=get_ip_atual(),
        acao=acao,
        modelo=obj._meta.label,
        objeto_id=str(obj.pk),
        objeto_repr=str(obj)[:200],
        antes=antes,
        depois=depois,
    )


class AuditoriaAdminMixin:
    """Grava na trilha de auditoria tudo que é feito pelo painel."""

    def save_model(self, request, obj, form, change):
        antes = None
        if change and obj.pk:
            original = type(obj)._default_manager.filter(pk=obj.pk).first()
            antes = foto(original) if original else None
        super().save_model(request, obj, form, change)
        # Guardado na requisição (a instância do ModelAdmin é compartilhada entre threads).
        request._auditoria_antes = antes

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        obj = form.instance
        antes = getattr(request, "_auditoria_antes", None)
        depois = foto(obj)
        if change:
            antes_dif, depois_dif = diferenca(antes or {}, depois)
            if antes_dif or depois_dif:
                registrar(RegistroAuditoria.Acao.ALTERACAO, obj, antes_dif, depois_dif, request.user)
        else:
            registrar(RegistroAuditoria.Acao.CRIACAO, obj, None, depois, request.user)

    def delete_model(self, request, obj):
        registrar(RegistroAuditoria.Acao.EXCLUSAO, obj, foto(obj), None, request.user)
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            registrar(RegistroAuditoria.Acao.EXCLUSAO, obj, foto(obj), None, request.user)
        super().delete_queryset(request, queryset)


@admin.register(RegistroAuditoria)
class RegistroAuditoriaAdmin(admin.ModelAdmin):
    list_display = ("quando", "acao", "modelo", "objeto_repr", "usuario_nome", "ip")
    list_filter = ("acao", "modelo")
    search_fields = ("objeto_id", "objeto_repr", "usuario_nome")
    date_hierarchy = "quando"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
