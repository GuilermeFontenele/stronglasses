from django.conf import settings
from django.db import connection
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET


@require_GET
def home(request):
    return render(request, "core/home.html")


@never_cache
@require_GET
def saude(request):
    """Health check para a hospedagem. Não expõe versões nem detalhes internos."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return JsonResponse({"status": "ok"})
    except Exception:  # noqa: BLE001
        return JsonResponse({"status": "erro"}, status=503)


@require_GET
def security_txt(request):
    """RFC 9116: como reportar vulnerabilidades."""
    conteudo = (
        f"Contact: mailto:{settings.SECURITY_CONTATO}\nExpires: 2027-12-31T23:59:59Z\nPreferred-Languages: pt-BR, en\n"
    )
    return HttpResponse(conteudo, content_type="text/plain; charset=utf-8")
