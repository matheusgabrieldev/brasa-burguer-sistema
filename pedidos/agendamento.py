"""Horários que o cliente pode escolher para agendar um pedido.

Regra da loja: só dá para agendar com a loja FECHADA, e só para a próxima abertura
(de 15 em 15 minutos, do horário de abrir até o de fechar, inclusive).
Com a loja aberta o pedido é sempre "para agora".
"""
from datetime import datetime, timedelta

from django.utils import timezone

from loja.horario import proxima_abertura, status_loja
from loja.models import Configuracao, Horario

INTERVALO = timedelta(minutes=15)


def horarios_agendamento(agora: datetime | None = None) -> list[datetime]:
    """Lista de horários (com fuso de Recife) para agendar. Vazia se a loja está aberta,
    se foi forçada a fechar no /gerenciar, ou se não há abertura prevista."""
    agora = timezone.localtime(agora) if agora else timezone.localtime()
    if status_loja(agora).aberta or Configuracao.atual().modo_loja == Configuracao.MODO_FECHADA:
        return []
    abre = proxima_abertura(agora)
    if abre is None:
        return []
    horario = Horario.objects.get(dia_semana=abre.weekday(), ativo=True)
    fecha = datetime.combine(abre.date(), horario.fecha, tzinfo=abre.tzinfo)

    lista, hora = [], abre
    while hora <= fecha:
        lista.append(hora)
        hora += INTERVALO
    return lista
