"""Freio contra robô no checkout: no máximo 30 pedidos criados em 10 minutos pela mesma rede (IP).

É bem folgado de propósito: cliente indeciso, mesas e Wi-Fi compartilhado nunca chegam perto
(o pico da loja é ~20 pedidos em 2 horas). Telefone não tem limite e o Dono logado não conta.

A conta é feita no banco, dentro da mesma transação que reserva o número do dia (linha travada),
então dois envios ao mesmo tempo não furam o freio, com qualquer número de workers e sem Redis.
O IP é guardado só como código (HMAC com a SECRET_KEY), não dá para ler o IP de volta.
"""
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from django.utils.crypto import salted_hmac

MAXIMO = 30
JANELA = timedelta(minutes=10)
MENSAGEM = "Muitos pedidos em pouco tempo. Aguarde alguns minutos ou fale com a loja no WhatsApp."


class LimiteExcedido(Exception):
    """Passou do freio: a view responde 429 e nada é gravado."""


def ip_do_cliente(request):
    """IP de quem enviou. O X-Forwarded-For só vale se a configuração mandar confiar nele."""
    if getattr(settings, "CONFIAR_X_FORWARDED_FOR", False):
        encaminhado = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
        if encaminhado:
            return encaminhado
    return request.META.get("REMOTE_ADDR", "")


def codigo_ip(ip):
    """Código de 64 letras que identifica a rede sem guardar o IP."""
    return salted_hmac("pedidos.limite.ip", ip, algorithm="sha256").hexdigest() if ip else ""


def conferir(ip_hash):
    """Levanta LimiteExcedido se essa rede já criou MAXIMO pedidos na JANELA. Chame dentro da transação."""
    from .models import Pedido

    if not ip_hash:
        return
    desde = timezone.now() - JANELA
    if Pedido.objects.filter(ip_hash=ip_hash, criado_em__gte=desde).count() >= MAXIMO:
        raise LimiteExcedido(MENSAGEM)
