"""Loja aberta ou fechada, a partir dos horários cadastrados (tabela Horario) e do modo da loja.

O "turno" é a data do dia de funcionamento: hoje, se a loja está aberta; o dia da próxima
abertura, se está fechada; "" se não há abertura prevista (ou a loja foi forçada a fechar).
O navegador guarda a sacola junto com o turno: se o turno mudar, a sacola é esvaziada.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.utils import timezone

from .models import Configuracao, Horario

DIAS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]


@dataclass
class StatusLoja:
    aberta: bool
    texto: str
    turno: str


def _horarios():
    return {h.dia_semana: h for h in Horario.objects.filter(ativo=True)}


def status_loja(agora=None):
    agora = timezone.localtime(agora) if agora else timezone.localtime()
    cfg = Configuracao.atual()
    if cfg.modo_loja == Configuracao.MODO_ABERTA:
        return StatusLoja(True, "Aberto agora", agora.date().isoformat())
    if cfg.modo_loja == Configuracao.MODO_FECHADA:
        return StatusLoja(False, "Fechado no momento", "")

    horarios = _horarios()
    hoje = horarios.get(agora.weekday())
    hora = agora.time().replace(second=0, microsecond=0)
    if hoje and hoje.abre <= hora <= hoje.fecha:
        return StatusLoja(True, f"Aberto até {hoje.fecha:%H:%M}", agora.date().isoformat())

    abertura = proxima_abertura(agora, horarios)
    if abertura is None:
        return StatusLoja(False, "Fechado", "")
    dias = (abertura.date() - agora.date()).days
    if dias == 0:
        quando = ""
    elif dias == 1:
        quando = "amanhã "
    else:
        quando = f"{DIAS[abertura.weekday()]} "
    # Fechada: o turno já é o dia da próxima abertura. Assim a sacola montada para um pedido
    # agendado não some; ela só é esvaziada quando esse dia passa.
    return StatusLoja(False, f"Fechado · Abrimos {quando}às {abertura:%H:%M}", abertura.date().isoformat())


def proxima_abertura(agora, horarios=None):
    """Próximo horário de abertura depois de `agora` (hoje, se ainda não abriu), ou None."""
    agora = timezone.localtime(agora)
    horarios = _horarios() if horarios is None else horarios
    for i in range(8):
        dia = agora.date() + timedelta(days=i)
        h = horarios.get(dia.weekday())
        if not h:
            continue
        abre = datetime.combine(dia, h.abre, tzinfo=agora.tzinfo)
        if abre > agora:
            return abre
    return None
