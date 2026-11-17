"""Painel de pedidos (/gerenciar/): a tela da cozinha e do balcão, para o Dono e a Equipe.

Caminho de uma atualização: o navegador pede `pedidos/colunas/` a cada 5 s mandando a versão
que já tem (`v`). Se nada mudou, a resposta é 204 (vazia) e a tela fica como está; se mudou,
volta o pedaço `_colunas.html` inteiro, que substitui o antigo.
O detalhe do pedido e os botões dele ficam em `views_pedido_acoes.py`.
"""
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from pedidos.models import Pedido
from pedidos.painel import ETAPAS_ATIVAS, minutos_de_espera, proxima_etapa
from pedidos.painel_consultas import (
    ABERTOS, LIMITE_CONCLUIDOS, montar_painel, promover_agendados, total_do_dia, versao_painel,
)

from .permissoes import eh_dono, equipe_obrigatorio

MINUTOS_VERMELHO = 40  # cartão com o tempo em vermelho a partir daqui
TIPOS = [
    ("", "Tudo", "tudo"), ("delivery", "🛵 Delivery", "delivery"), ("retirada", "🛍 Retirada", "retirada"),
    ("local", "🍽 No local", "local"), ("agendados", "📅 Agendados", "agendados"),
]
ICONES = {"delivery": "🛵", "retirada": "🛍", "local": "🍽"}
ABREVIADO = {"aguardando": "Aceite", "preparo": "Preparo", "pronto": "Pronto", "saiu": "Saiu",
             "concluido": "Fim", "resultado": "Busca", "agendados": "Agendados"}


def _enfeitar(pedido, agora):
    """Prepara o que o cartão mostra (sem conta no template): novo, tempo, ícone, botão e "feito em"."""
    # "novo" = ninguém abriu ainda; só conta nas etapas em que o alarme toca (igual a painel.novos)
    pedido.novo = pedido.visto_em is None and pedido.status in ("aguardando", "preparo")
    pedido.minutos = minutos_de_espera(pedido, agora)
    pedido.vermelho = pedido.minutos >= MINUTOS_VERMELHO and pedido.status not in ("concluido", "cancelado")
    pedido.icone = ICONES.get(pedido.tipo, "")
    pedido.qtd_itens = sum(i.quantidade for i in pedido.itens.all())
    pedido.etapa = proxima_etapa(pedido)
    # o número é do dia em que foi feito: evita confundir com outro igual (ex.: "#3" de ontem e de hoje)
    pedido.feito_em = None
    agendado_outro_dia = pedido.agendado_para and timezone.localdate(pedido.agendado_para) != pedido.dia
    aberto_outro_dia = pedido.status in ABERTOS and pedido.dia != timezone.localdate(agora)
    if agendado_outro_dia or aberto_outro_dia:
        pedido.feito_em = pedido.dia
    return pedido


def _contexto(request, agora, versao):
    """Lê os filtros do endereço e monta tudo que `_colunas.html` precisa.

    `versao` tem que ter sido lida ANTES dos pedidos (quem chama faz isso). Se um pedido chegar
    no meio, a tela vai sem ele mas com a versão antiga, e a próxima consulta redesenha. Na
    ordem inversa (pedidos antes, versão depois) a tela ficaria sem ele e com a versão nova:
    toda consulta seguinte daria 204 e o pedido sumiria até outra mudança.
    """
    hoje = timezone.localdate(agora)
    tipo = request.GET.get("tipo", "")
    if tipo not in {t for t, _, _ in TIPOS}:
        tipo = ""
    busca = request.GET.get("q", "").strip()[:60]
    todos = request.GET.get("todos") == "1"

    painel = montar_painel(hoje, tipo=tipo, busca=busca, todos_concluidos=todos)
    for coluna in painel.colunas:
        for p in coluna.pedidos:
            _enfeitar(p, agora)
        coluna.curto = ABREVIADO.get(coluna.status, coluna.titulo)
    for p in painel.agendados:
        _enfeitar(p, agora)

    so_agendados = tipo == "agendados" and not busca
    pilulas = [
        {"tipo": t, "rotulo": rotulo, "n": painel.contagem_tipo.get(chave, 0), "ativa": t == tipo}
        for t, rotulo, chave in TIPOS
    ]
    concluidos = next((c for c in painel.colunas if c.status == "concluido"), None)
    contexto = {
        "painel": painel,
        "pilulas": pilulas,
        "tipo": tipo,
        "busca": busca,
        "todos": todos,
        "so_agendados": so_agendados,
        "tem_mais_concluidos": bool(concluidos) and not todos and len(concluidos.pedidos) >= LIMITE_CONCLUIDOS,
        "versao": versao,
        "eh_dono": eh_dono(request.user),
        # "Finalizar todos" pega abertos de qualquer dia e de qualquer tipo: conta igual a ele
        "qtd_finalizar": Pedido.objects.filter(status__in=ETAPAS_ATIVAS).count(),
    }
    if contexto["eh_dono"]:
        # só o Dono: para a Equipe a quantidade e o total do dia nem chegam no HTML
        contexto["qtd_dia"], contexto["total_dia"] = total_do_dia(hoje)
    return contexto


@never_cache
@equipe_obrigatorio
@require_GET
def painel(request):
    """Página inteira do painel. Agendados que chegaram na hora já entram como 'Em preparo'."""
    agora = timezone.now()
    promover_agendados(agora)
    contexto = _contexto(request, agora, versao_painel(agora))  # versão antes dos pedidos (ver _contexto)
    contexto["somente_equipe"] = not contexto["eh_dono"]
    return render(request, "gerenciar/pedidos/painel.html", contexto)


@never_cache
@equipe_obrigatorio
@require_GET
def colunas(request):
    """Só as colunas (consulta de 5 s, busca, filtros). 204 = nada mudou desde a versão `v`."""
    agora = timezone.now()
    promover_agendados(agora)
    versao = versao_painel(agora)  # lida uma vez só, e antes dos pedidos (ver _contexto)
    if request.GET.get("v") == versao:
        return HttpResponse(status=204)
    contexto = _contexto(request, agora, versao)
    contexto["atualizacao"] = True  # o total do dia vai junto, "fora da caixa" (hx-swap-oob)
    return render(request, "gerenciar/pedidos/_colunas.html", contexto)

