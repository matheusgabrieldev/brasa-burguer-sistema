"""Quem pode entrar na área do Dono."""
from functools import wraps

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import resolve_url


def _pedir_login(request):
    """Manda para a tela de entrar.

    Pedido feito pelo HTMX (a consulta de 5 s do painel, um botão) não pode receber o 302:
    o HTMX seguiria o redirecionamento e colaria a tela de login dentro das colunas.
    Por isso ele recebe 200 com o cabeçalho `HX-Redirect`, que faz o navegador trocar de página.
    """
    if request.headers.get("HX-Request") == "true":
        resposta = HttpResponse()
        resposta["HX-Redirect"] = resolve_url(settings.LOGIN_URL)
        return resposta
    return redirect_to_login(request.get_full_path())


def eh_dono(user):
    """Dono = está no grupo "Dono" ou é superusuário (a conta criada com createsuperuser)."""
    return user.is_authenticated and (user.is_superuser or user.groups.filter(name="Dono").exists())


def dono_obrigatorio(view):
    """Sem login -> tela de entrar. Logado mas sem ser Dono -> erro 403 (proibido)."""

    @wraps(view)
    def envolvida(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return _pedir_login(request)
        if not eh_dono(request.user):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return envolvida


def eh_equipe(user):
    """Equipe = está no grupo "Equipe" ou é Dono (o Dono também pode tudo que a equipe faz)."""
    return user.is_authenticated and (eh_dono(user) or user.groups.filter(name="Equipe").exists())


def equipe_obrigatorio(view):
    """Igual ao dono_obrigatorio, mas deixa a Equipe entrar também (painel de pedidos)."""

    @wraps(view)
    def envolvida(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return _pedir_login(request)
        if not eh_equipe(request.user):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return envolvida
