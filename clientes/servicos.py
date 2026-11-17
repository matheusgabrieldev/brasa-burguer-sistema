"""Regras de clientes: telefone, cliente por telefone e 'Lembrar de mim'."""
import hashlib
import re
import secrets

from django.conf import settings
from django.utils import timezone

from .models import Cliente, Dispositivo, EnderecoSalvo

COOKIE_DISPOSITIVO = "lb_aparelho"
COOKIE_MAX_AGE = 60 * 60 * 24 * 365  # 1 ano
# Para gravar use gravar_cookie(response, token): ele junta estas opções com o "secure".
COOKIE_OPCOES = {"max_age": COOKIE_MAX_AGE, "httponly": True, "samesite": "Lax"}

ERRO_TELEFONE = "Informe o WhatsApp com DDD, ex.: (81) 9 8888-7777."


def normalizar_telefone(texto) -> str:
    """Devolve só os dígitos (sem o 55). Erro se não tiver DDD + 8 ou 9 dígitos."""
    d = re.sub(r"\D", "", str(texto or ""))
    if len(d) in (12, 13) and d.startswith("55"):
        d = d[2:]
    if len(d) not in (10, 11):
        raise ValueError(ERRO_TELEFONE)
    return d


def formatar_telefone(digitos: str) -> str:
    """'81988887777' vira '(81) 98888-7777'."""
    return f"({digitos[:2]}) {digitos[2:-4]}-{digitos[-4:]}"


def cliente_do_telefone(telefone: str, nome: str) -> Cliente:
    """Acha ou cria o cliente. Quem já existe mantém o nome."""
    cliente, _ = Cliente.objects.get_or_create(
        telefone=normalizar_telefone(telefone), defaults={"nome": (nome or "").strip()[:80]}
    )
    return cliente


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def dispositivo_do_token(token) -> Dispositivo | None:
    """Acha o aparelho pelo token do cookie; token vazio ou errado dá None."""
    if not token:
        return None
    return Dispositivo.objects.filter(token_hash=_hash(token)).first()


def gravar_cookie(response, token):
    """Grava o cookie do aparelho. Fora do modo de desenvolvimento, só viaja em HTTPS (secure)."""
    response.set_cookie(COOKIE_DISPOSITIVO, token, secure=not settings.DEBUG, **COOKIE_OPCOES)


def lembrar(token, nome, telefone, bairro, rua, numero, referencia) -> str:
    """Guarda nome, telefone e endereço neste aparelho. Devolve o token (novo ou o mesmo).

    Sem rua ou número (retirada / no local) guarda só nome e telefone."""
    disp = dispositivo_do_token(token)
    if disp is None:
        token = secrets.token_urlsafe(32)
        disp = Dispositivo(token_hash=_hash(token))
    disp.nome = (nome or "").strip()[:80]
    disp.telefone = normalizar_telefone(telefone)
    disp.usado_em = timezone.now()
    disp.save()

    rua, numero = (rua or "").strip(), (numero or "").strip()
    if not rua or not numero:
        return token
    existente = disp.enderecos.filter(bairro=bairro, rua__iexact=rua, numero__iexact=numero).first()
    if existente:
        existente.referencia = (referencia or "").strip()
        existente.save()  # auto_now atualiza usado_em
    else:
        EnderecoSalvo.objects.create(
            dispositivo=disp, bairro=bairro, rua=rua, numero=numero, referencia=(referencia or "").strip()
        )
    return token
