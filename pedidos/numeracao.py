"""Número do pedido, que recomeça em 1 a cada dia."""
from django.db import transaction
from django.db.models import F

from .models import ContadorDia


def proximo_numero(dia) -> int:
    """Devolve o próximo número do dia, sem repetir mesmo com pedidos simultâneos.

    A linha do contador fica travada (select_for_update) até o fim da transação.
    """
    with transaction.atomic():
        contador, _ = ContadorDia.objects.select_for_update().get_or_create(dia=dia)
        ContadorDia.objects.filter(pk=contador.pk).update(ultimo=F("ultimo") + 1)
        contador.refresh_from_db()
        return contador.ultimo
