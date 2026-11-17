"""Configurações do sistema Brasa Burguer.

Tudo que muda entre o computador do Matheus e o servidor (senha, banco, modo de teste)
vem de variáveis de ambiente. No computador elas ficam no arquivo .env (copie de .env.exemplo).
"""
import os
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
if os.environ.get("LOAD_DOTENV", "1") == "1":
    load_dotenv(BASE_DIR / ".env")

DEBUG = os.environ.get("DEBUG", "0") == "1"
SECRET_KEY = os.environ.get("SECRET_KEY") or ("dev-inseguro" if DEBUG else None)
if not SECRET_KEY:
    raise RuntimeError("Defina SECRET_KEY nas variáveis de ambiente.")
ALLOWED_HOSTS = [h.strip() for h in os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()]
CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()]
if not DEBUG:
    if not os.environ.get("ALLOWED_HOSTS") or not ALLOWED_HOSTS or any(
        "*" in host or "/" in host or ":" in host or host.startswith(".") for host in ALLOWED_HOSTS
    ):
        raise RuntimeError("Defina ALLOWED_HOSTS com os nomes explícitos dos hosts de produção.")
    if not CSRF_TRUSTED_ORIGINS:
        raise RuntimeError("Defina CSRF_TRUSTED_ORIGINS com as origens HTTPS de produção.")
    for origem in CSRF_TRUSTED_ORIGINS:
        partes = urlsplit(origem)
        if (partes.scheme != "https" or not partes.hostname or "*" in origem
                or partes.username or partes.password or partes.path or partes.query or partes.fragment):
            raise RuntimeError("CSRF_TRUSTED_ORIGINS aceita somente origens HTTPS explícitas, sem caminho.")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "loja",
    "cardapio",
    "gerenciar",
    "clientes",
    "pedidos",
    "axes",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Por último: transforma o login bloqueado na página de "Muitas tentativas".
    "axes.middleware.AxesMiddleware",
]
if not DEBUG:
    MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")

# O proxy de produção deve substituir este cabeçalho e impedir acesso direto ao app.
SECURE_PROXY_SSL_HEADER = None if DEBUG else ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = not DEBUG
SECURE_HSTS_SECONDS = 0 if DEBUG else 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
X_FRAME_OPTIONS = "DENY"
# O Railway precisa receber 200 no healthcheck interno, que pode chegar em HTTP.
SECURE_REDIRECT_EXEMPT = [] if DEBUG else [r"^saude/$"]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Sem DATABASE_URL usa SQLite (computador do Matheus); no servidor, PostgreSQL.
DATABASES = {
    "default": dj_database_url.config(default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}", conn_max_age=600)
}
if not DEBUG and DATABASES["default"]["ENGINE"] != "django.db.backends.postgresql":
    raise RuntimeError("Defina DATABASE_URL com um banco PostgreSQL em produção.")

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
]

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Recife"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage" if DEBUG else
        "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
MAX_FOTO_BYTES = 10 * 1024 * 1024

LOGIN_URL = "/gerenciar/entrar/"
LOGIN_REDIRECT_URL = "/gerenciar/"
LOGOUT_REDIRECT_URL = "/gerenciar/entrar/"

# Bloqueio de tentativas de login (django-axes), vale para /gerenciar/entrar/ e /admin/.
# 5 senhas erradas do mesmo IP bloqueiam esse IP por 15 minutos. Fica gravado no banco,
# então reiniciar o servidor não libera. Para liberar antes: python manage.py axes_reset_ip <ip>
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",  # tem que ser o primeiro
    "django.contrib.auth.backends.ModelBackend",
]
AXES_HANDLER = "axes.handlers.database.AxesDatabaseHandler"
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = timedelta(minutes=15)
AXES_LOCKOUT_PARAMETERS = ["ip_address"]
AXES_RESET_ON_SUCCESS = True
# Errar de novo durante o bloqueio não recomeça os 15 minutos.
AXES_RESET_COOL_OFF_ON_FAILURE_DURING_LOCKOUT = False
AXES_LOCKOUT_TEMPLATE = "gerenciar/bloqueado.html"
# Mesmo IP usado no freio de pedidos do checkout: X-Forwarded-For só com CONFIAR_X_FORWARDED_FOR=1.
AXES_CLIENT_IP_CALLABLE = "pedidos.limite.ip_do_cliente"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Limite de pedidos por IP: só confie no cabeçalho X-Forwarded-For se o servidor estiver
# atrás de um proxy que o preenche (senão qualquer um inventa o próprio IP).
CONFIAR_X_FORWARDED_FOR = os.environ.get("CONFIAR_X_FORWARDED_FOR", "0") == "1"
