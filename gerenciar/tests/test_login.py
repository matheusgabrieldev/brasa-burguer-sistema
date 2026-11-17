"""Bloqueio de tentativas nos dois logins: área do Dono (/gerenciar/entrar/) e Django Admin.

Regra: 5 senhas erradas do mesmo IP bloqueiam esse IP por 15 minutos, mesmo que a 6ª
esteja certa. O registro fica no banco (django-axes), então reiniciar o servidor ou
limpar o cache não libera ninguém.
"""
from datetime import timedelta

import pytest
from django.conf import settings
from django.contrib.auth.models import Group, User
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.core.exceptions import ValidationError

MENSAGEM = "Muitas tentativas. Aguarde 15 minutos para tentar novamente."
SENHA = "senha-certa-123"
IP = "10.0.0.1"
LOGINS = ["/gerenciar/entrar/", "/admin/login/"]


@pytest.fixture
def dono(db):
    usuario = User.objects.create_user("ana", password=SENHA, is_staff=True, is_superuser=True)
    usuario.groups.add(Group.objects.get_or_create(name="Dono")[0])
    return usuario


def tentar(client, url, senha, ip=IP, **extra):
    return client.post(url, {"username": "ana", "password": senha}, REMOTE_ADDR=ip, **extra)


def errar_cinco(client, url, ip=IP):
    for _ in range(4):
        resposta = tentar(client, url, "errada", ip=ip)
        assert resposta.status_code == 200  # formulário de novo, com erro
    # A 5ª errada já responde avisando do bloqueio.
    assert tentar(client, url, "errada", ip=ip).status_code == 429


def entrou(resposta):
    return resposta.status_code == 302


@pytest.mark.parametrize("url", LOGINS)
def test_senha_certa_entra(client, dono, url):
    assert entrou(tentar(client, url, SENHA))


@pytest.mark.parametrize("url", LOGINS)
def test_cinco_erros_bloqueiam_mesmo_com_senha_certa(client, dono, url):
    errar_cinco(client, url)
    resposta = tentar(client, url, SENHA)
    assert resposta.status_code == 429
    assert MENSAGEM in resposta.content.decode()
    assert "_auth_user_id" not in client.session


@pytest.mark.parametrize("url", LOGINS)
def test_quatro_erros_ainda_deixam_entrar(client, dono, url):
    for _ in range(4):
        tentar(client, url, "errada")
    assert entrou(tentar(client, url, SENHA))


@pytest.mark.parametrize("url", LOGINS)
def test_outro_ip_continua_livre(client, dono, url):
    errar_cinco(client, url)
    assert entrou(tentar(client, url, SENHA, ip="10.0.0.2"))


@pytest.mark.parametrize("url", LOGINS)
def test_x_forwarded_for_inventado_nao_escapa_do_bloqueio(client, dono, url, settings):
    settings.CONFIAR_X_FORWARDED_FOR = False
    errar_cinco(client, url)
    resposta = tentar(client, url, SENHA, HTTP_X_FORWARDED_FOR="203.0.113.9")
    assert resposta.status_code == 429


@pytest.mark.parametrize("url", LOGINS)
def test_libera_depois_de_quinze_minutos(client, dono, url):
    from axes.models import AccessAttempt

    errar_cinco(client, url)
    assert tentar(client, url, SENHA).status_code == 429
    AccessAttempt.objects.update(attempt_time=AccessAttempt.objects.first().attempt_time - timedelta(minutes=16))
    assert entrou(tentar(client, url, SENHA))


@pytest.mark.parametrize("url", LOGINS)
def test_bloqueio_continua_depois_de_limpar_o_cache(client, dono, url):
    errar_cinco(client, url)
    cache.clear()
    assert tentar(client, url, SENHA).status_code == 429


def test_bloqueio_vale_para_os_dois_logins(client, dono):
    errar_cinco(client, "/gerenciar/entrar/")
    assert tentar(client, "/admin/login/", SENHA).status_code == 429


def test_tentativas_ficam_no_banco(client, dono):
    from axes.models import AccessAttempt

    assert settings.AXES_HANDLER == "axes.handlers.database.AxesDatabaseHandler"
    errar_cinco(client, "/gerenciar/entrar/")
    assert AccessAttempt.objects.filter(ip_address=IP, failures_since_start=5).exists()


def test_senha_de_nove_caracteres_e_recusada():
    with pytest.raises(ValidationError):
        validate_password("Ab3$efgh9")
    validate_password("Ab3$efgh9k")
