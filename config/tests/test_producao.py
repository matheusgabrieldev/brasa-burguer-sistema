"""Verifica settings isolados, sem conectar ao banco ou iniciar o Django."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.fixture
def carregar_settings(tmp_path):
    pasta = tmp_path / "config"
    pasta.mkdir()
    origem = Path(__file__).resolve().parents[1] / "settings.py"
    destino = pasta / "settings.py"
    destino.write_text(origem.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / ".env").write_text("DEBUG=1\nSECRET_KEY=segredo-do-dotenv-de-teste\n", encoding="utf-8")

    def carregar(**variaveis):
        ambiente = os.environ.copy()
        for nome in ("DEBUG", "SECRET_KEY", "DATABASE_URL", "ALLOWED_HOSTS", "CSRF_TRUSTED_ORIGINS", "LOAD_DOTENV"):
            ambiente.pop(nome, None)
        ambiente.update({
            "LOAD_DOTENV": "0", "DEBUG": "0", "SECRET_KEY": "segredo-isolado-de-teste",
            "DATABASE_URL": "postgresql://usuario:senha@banco.invalid/loja",
            "ALLOWED_HOSTS": "brasaburguer.com.br,healthcheck.railway.app",
            "CSRF_TRUSTED_ORIGINS": "https://brasaburguer.com.br",
        })
        for nome, valor in variaveis.items():
            if valor is None:
                ambiente.pop(nome, None)
            else:
                ambiente[nome] = valor
        codigo = (
            "import importlib.util, json, sys\n"
            f"sys.path = {sys.path!r}\n"
            f"spec = importlib.util.spec_from_file_location('isolado', {str(destino)!r})\n"
            "modulo = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(modulo)\n"
            "nomes = ['DEBUG', 'MIDDLEWARE', 'STORAGES', 'DATABASES', 'ALLOWED_HOSTS', "
            "'CSRF_TRUSTED_ORIGINS', 'AUTH_PASSWORD_VALIDATORS', 'SECURE_PROXY_SSL_HEADER', "
            "'SESSION_COOKIE_SECURE', 'CSRF_COOKIE_SECURE', 'SECURE_SSL_REDIRECT', "
            "'SECURE_HSTS_SECONDS', 'SECURE_HSTS_INCLUDE_SUBDOMAINS', 'SECURE_HSTS_PRELOAD', "
            "'SECURE_REDIRECT_EXEMPT', 'X_FRAME_OPTIONS']\n"
            "print(json.dumps({nome: getattr(modulo, nome, None) for nome in nomes}))\n"
        )
        return subprocess.run([sys.executable, "-c", codigo], env=ambiente, capture_output=True, text=True, timeout=20)

    return carregar


def test_producao_ativa_https_e_estaticos(carregar_settings):
    resultado = carregar_settings()
    assert resultado.returncode == 0, resultado.stderr
    cfg = json.loads(resultado.stdout)
    assert cfg["DEBUG"] is False
    assert cfg["DATABASES"]["default"]["ENGINE"] == "django.db.backends.postgresql"
    assert cfg["MIDDLEWARE"][:2] == [
        "django.middleware.security.SecurityMiddleware", "whitenoise.middleware.WhiteNoiseMiddleware",
    ]
    assert cfg["STORAGES"]["staticfiles"]["BACKEND"] == "whitenoise.storage.CompressedManifestStaticFilesStorage"
    assert cfg["STORAGES"]["default"]["BACKEND"] == "django.core.files.storage.FileSystemStorage"
    assert cfg["SECURE_PROXY_SSL_HEADER"] == ["HTTP_X_FORWARDED_PROTO", "https"]
    for nome in ("SESSION_COOKIE_SECURE", "CSRF_COOKIE_SECURE", "SECURE_SSL_REDIRECT", "SECURE_HSTS_INCLUDE_SUBDOMAINS", "SECURE_HSTS_PRELOAD"):
        assert cfg[nome] is True
    assert cfg["SECURE_HSTS_SECONDS"] == 31536000
    assert cfg["SECURE_REDIRECT_EXEMPT"] == ["^saude/$"]
    assert cfg["X_FRAME_OPTIONS"] == "DENY"
    assert cfg["AUTH_PASSWORD_VALIDATORS"][0]["OPTIONS"]["min_length"] == 10


def test_desenvolvimento_funciona_sem_dependencias_de_producao(carregar_settings):
    resultado = carregar_settings(DEBUG="1", DATABASE_URL=None, ALLOWED_HOSTS=None, CSRF_TRUSTED_ORIGINS=None)
    assert resultado.returncode == 0, resultado.stderr
    cfg = json.loads(resultado.stdout)
    assert cfg["DATABASES"]["default"]["ENGINE"] == "django.db.backends.sqlite3"
    assert "whitenoise.middleware.WhiteNoiseMiddleware" not in cfg["MIDDLEWARE"]
    assert cfg["STORAGES"]["staticfiles"]["BACKEND"] == "django.contrib.staticfiles.storage.StaticFilesStorage"
    assert cfg["SECURE_PROXY_SSL_HEADER"] is None
    assert cfg["SECURE_SSL_REDIRECT"] is False
    assert cfg["SESSION_COOKIE_SECURE"] is False
    assert cfg["CSRF_COOKIE_SECURE"] is False
    assert cfg["SECURE_HSTS_SECONDS"] == 0


@pytest.mark.parametrize("variaveis,mensagem", [
    ({"SECRET_KEY": None}, "SECRET_KEY"),
    ({"DATABASE_URL": None}, "PostgreSQL"),
    ({"DATABASE_URL": "sqlite:///local.sqlite3"}, "PostgreSQL"),
    ({"ALLOWED_HOSTS": None}, "ALLOWED_HOSTS"),
    ({"ALLOWED_HOSTS": ""}, "ALLOWED_HOSTS"),
    ({"ALLOWED_HOSTS": "brasaburguer.com.br,*"}, "ALLOWED_HOSTS"),
    ({"ALLOWED_HOSTS": "https://brasaburguer.com.br"}, "ALLOWED_HOSTS"),
    ({"CSRF_TRUSTED_ORIGINS": None}, "CSRF_TRUSTED_ORIGINS"),
    ({"CSRF_TRUSTED_ORIGINS": "http://brasaburguer.com.br"}, "CSRF_TRUSTED_ORIGINS"),
    ({"CSRF_TRUSTED_ORIGINS": "https://*.example.com"}, "CSRF_TRUSTED_ORIGINS"),
    ({"CSRF_TRUSTED_ORIGINS": "https://brasaburguer.com.br/caminho"}, "CSRF_TRUSTED_ORIGINS"),
])
def test_producao_recusa_configuracao_incompleta(carregar_settings, variaveis, mensagem):
    resultado = carregar_settings(**variaveis)
    assert resultado.returncode != 0
    assert mensagem in resultado.stderr


def test_dotenv_so_preenche_quando_habilitado(carregar_settings):
    desabilitado = carregar_settings(DEBUG=None, SECRET_KEY=None)
    assert desabilitado.returncode != 0
    assert "SECRET_KEY" in desabilitado.stderr
    habilitado = carregar_settings(LOAD_DOTENV="1", DEBUG=None, SECRET_KEY=None)
    assert habilitado.returncode == 0, habilitado.stderr
    assert json.loads(habilitado.stdout)["DEBUG"] is True


def test_variaveis_do_servidor_prevalecem_sobre_dotenv(carregar_settings):
    resultado = carregar_settings(LOAD_DOTENV="1")
    assert resultado.returncode == 0, resultado.stderr
    assert json.loads(resultado.stdout)["DEBUG"] is False
