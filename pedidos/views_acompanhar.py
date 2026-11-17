"""Confirmação do pedido e consulta do status pelo código compartilhável."""
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from loja.models import Configuracao

from .models import Pedido
from .whatsapp import link_whatsapp


def _status(pedido):
    if pedido.status == "aguardando":
        return "Aguardando a loja confirmar"
    if pedido.status == "agendado" and pedido.agendado_para:
        horario = timezone.localtime(pedido.agendado_para)
        dia = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")[horario.weekday()]
        return f"Agendado para {dia}, {horario:%d/%m} às {horario:%H:%M}"
    if pedido.status == "pronto" and pedido.tipo in {"retirada", "local"}:
        return "Pronto! Pode vir buscar"
    if pedido.status == "saiu":
        return "Saiu para entrega 🛵"
    if pedido.status == "concluido":
        return "Entregue"
    return pedido.get_status_display()


def _contexto_status(pedido):
    return {
        "pedido": pedido,
        "texto_status": _status(pedido),
        "finalizado": pedido.status in {"concluido", "cancelado"},
    }


@never_cache
@require_GET
def acompanhar(request, codigo):
    pedido = get_object_or_404(Pedido.objects.prefetch_related("itens"), codigo=codigo)
    loja = Configuracao.atual()
    contexto = _contexto_status(pedido)
    contexto.update(
        loja=loja,
        whatsapp=link_whatsapp(pedido, loja),
        mostrar_pix=pedido.forma_pagamento_codigo == "pix" and bool(loja.chave_pix),
    )
    return render(request, "pedidos/acompanhar.html", contexto)


@never_cache
@require_GET
def status(request, codigo):
    pedido = get_object_or_404(Pedido, codigo=codigo)
    return render(request, "pedidos/_status.html", _contexto_status(pedido))
