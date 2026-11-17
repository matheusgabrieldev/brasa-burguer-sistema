"""Regras de etapa do painel de pedidos (preparo -> pronto -> saiu -> concluído, e os desvios).

Toda função recebe o status que o aparelho VIU (`de`) quando a ação depende dele: se outra
pessoa mexeu no pedido antes, o status atual é outro e a função devolve False sem gravar nada.
Assim dois toques ao mesmo tempo (ou um aparelho desatualizado) nunca embaralham o histórico.
Devolvem True quando mudaram alguma coisa.
"""
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from pedidos.models import HistoricoStatus, Pedido

ETAPAS_ATIVAS = ("preparo", "pronto", "saiu")
ANTECEDENCIA_AGENDADO = timedelta(minutes=30)  # agendado para daqui a mais que isso espera como "agendado"


def minutos_de_espera(pedido, agora):
    """Minutos desde que o pedido começou a contar (nunca negativo).

    Agendado conta da hora em que entra no painel (hora marcada - 30 min), não de quando foi
    feito: senão um pedido feito dias antes já chegaria com centenas de minutos e vermelho.
    Aguardando aceite conta desde que foi feito (é o tempo que o cliente espera resposta).
    """
    agendado = pedido.agendado_para and pedido.status != "aguardando"
    inicio = pedido.agendado_para - ANTECEDENCIA_AGENDADO if agendado else pedido.criado_em
    return max(int((agora - inicio).total_seconds() // 60), 0)


def proxima_etapa(pedido):
    """(novo status, rótulo do botão) da etapa seguinte, ou None se não há botão de avançar."""
    if pedido.status == "preparo":
        return ("pronto", "✓ Pronto")
    if pedido.status == "pronto":
        if pedido.tipo == "delivery":
            return ("saiu", "🛵 Saiu para entrega")
        return ("concluido", "✓ Entregue")
    if pedido.status == "saiu":
        return ("concluido", "✓ Entregue")
    return None


def _trancar(pedido_id):
    """Busca o pedido travando a linha até o fim da transação (ninguém mexe junto)."""
    return Pedido.objects.select_for_update().get(pk=pedido_id)


def _mudar(pedido, status, usuario, nota="", **campos):
    """Grava o novo status e o registro no histórico (quem, quando, por quê)."""
    pedido.status = status
    for nome, valor in campos.items():
        setattr(pedido, nome, valor)
    pedido.save(update_fields=["status", *campos])
    HistoricoStatus.objects.create(pedido=pedido, status=status, usuario=usuario, nota=nota)


def avancar(pedido_id, de, usuario):
    with transaction.atomic():
        pedido = _trancar(pedido_id)
        etapa = proxima_etapa(pedido)
        if pedido.status != de or etapa is None:
            return False
        _mudar(pedido, etapa[0], usuario)
        return True


def _caminho(pedido):
    """Etapas percorridas, em ordem; cada "voltou" desfaz a última. Ignora aguardando/agendado/pago."""
    caminho = []
    for h in pedido.historico.order_by("em", "id"):
        if h.status not in (*ETAPAS_ATIVAS, "concluido"):
            continue
        if h.nota == "voltou":
            if caminho:
                caminho.pop()
        elif not caminho or caminho[-1] != h.status:
            caminho.append(h.status)
    return caminho


def etapa_anterior(pedido):
    """Para onde o "voltar" levaria o pedido agora, ou None (o detalhe só mostra o link se der)."""
    if pedido.status not in ("pronto", "saiu", "concluido"):
        return None
    caminho = _caminho(pedido)
    if len(caminho) < 2 or caminho[-1] != pedido.status:
        return None
    return caminho[-2]


def voltar(pedido_id, de, usuario):
    """Desfaz um toque errado: volta para a etapa anterior do histórico."""
    with transaction.atomic():
        pedido = _trancar(pedido_id)
        anterior = etapa_anterior(pedido)
        if pedido.status != de or anterior is None:
            return False
        _mudar(pedido, anterior, usuario, nota="voltou")
        return True


def aceitar(pedido_id, usuario, agora):
    """Loja aceita um pedido que estava aguardando. Agendado para bem mais tarde fica "agendado"."""
    with transaction.atomic():
        pedido = _trancar(pedido_id)
        if pedido.status != "aguardando":
            return False
        longe = pedido.agendado_para and pedido.agendado_para > agora + ANTECEDENCIA_AGENDADO
        _mudar(pedido, "agendado" if longe else "preparo", usuario, visto_em=timezone.now())
        return True


def recusar(pedido_id, usuario, motivo=""):
    with transaction.atomic():
        pedido = _trancar(pedido_id)
        if pedido.status != "aguardando":
            return False
        motivo = motivo.strip()
        _mudar(pedido, "cancelado", usuario, nota=(f"recusado: {motivo}" if motivo else "recusado")[:200],  # nota cabe em 200 (limite do campo)
               motivo_cancelamento=motivo[:200])
        return True


def cancelar(pedido_id, usuario, motivo):
    """Cancela de qualquer etapa (até de concluído, para estorno). Exige motivo."""
    motivo = (motivo or "").strip()
    if not motivo:
        raise ValueError("Informe o motivo do cancelamento.")
    with transaction.atomic():
        pedido = _trancar(pedido_id)
        if pedido.status == "cancelado":
            return False
        _mudar(pedido, "cancelado", usuario, nota=motivo[:200], motivo_cancelamento=motivo[:200])
        return True


def comecar_agora(pedido_id, usuario):
    """Antecipa um pedido agendado; volta a contar como "novo" (visto_em vazio)."""
    with transaction.atomic():
        pedido = _trancar(pedido_id)
        if pedido.status != "agendado":
            return False
        _mudar(pedido, "preparo", usuario, visto_em=None)
        return True


def marcar_pago(pedido_id, pago, usuario):
    """Muda só o "pago"; o histórico repete o status atual com a nota."""
    with transaction.atomic():
        pedido = _trancar(pedido_id)
        pedido.pago = pago
        pedido.save(update_fields=["pago"])
        HistoricoStatus.objects.create(pedido=pedido, status=pedido.status, usuario=usuario,
                                       nota="pago" if pago else "não pago")
        return True


def marcar_visto(pedido_id):
    """Tira o destaque de "novo". Não é mudança de status, então não entra no histórico."""
    return bool(Pedido.objects.filter(pk=pedido_id, visto_em__isnull=True).update(visto_em=timezone.now()))


def finalizar_todos(usuario):
    """Conclui tudo que está em preparo/pronto/saiu (de qualquer dia). Devolve quantos."""
    with transaction.atomic():
        pedidos = list(Pedido.objects.select_for_update().filter(status__in=ETAPAS_ATIVAS))
        for pedido in pedidos:
            _mudar(pedido, "concluido", usuario, nota="finalizar todos")
        return len(pedidos)
