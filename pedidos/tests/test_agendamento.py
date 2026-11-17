"""Horários para agendar: só com a loja fechada, de 15 em 15 min, na próxima abertura."""
from datetime import datetime, time
from zoneinfo import ZoneInfo

from loja.models import Configuracao, Horario
from pedidos.agendamento import horarios_agendamento

RECIFE = ZoneInfo("America/Recife")


def dt(texto):
    return datetime.strptime(texto, "%Y-%m-%d %H:%M").replace(tzinfo=RECIFE)


def test_horarios_da_proxima_abertura_de_15_em_15(db, horarios):
    lista = horarios_agendamento(dt("2026-11-16 20:00"))  # segunda (fechado) -> quarta
    assert len(lista) == 18
    assert lista[0] == dt("2026-11-18 18:15")
    assert lista[1] == dt("2026-11-18 18:30")
    assert lista[-1] == dt("2026-11-18 22:30")


def test_sem_horarios_com_loja_aberta(db, horarios):
    assert horarios_agendamento(dt("2026-11-11 20:00")) == []


def test_antes_de_abrir_agenda_para_hoje(db, horarios):
    lista = horarios_agendamento(dt("2026-11-11 10:00"))
    assert lista[0] == dt("2026-11-11 18:15")


def test_domingo_comeca_as_18(db, horarios):
    lista = horarios_agendamento(dt("2026-11-14 23:00"))  # sábado à noite -> domingo
    assert lista[0] == dt("2026-11-15 18:00")
    assert len(lista) == 19


def test_sem_horario_cadastrado_nao_agenda(db):
    assert horarios_agendamento(dt("2026-11-16 20:00")) == []


def test_fecha_em_horario_quebrado_nao_passa_do_fechamento(db):
    Horario.objects.create(dia_semana=2, abre=time(18, 0), fecha=time(18, 40))
    lista = horarios_agendamento(dt("2026-11-16 20:00"))
    assert lista == [dt("2026-11-18 18:00"), dt("2026-11-18 18:15"), dt("2026-11-18 18:30")]


def test_loja_forcada_fechada_nao_agenda(db, horarios):
    cfg = Configuracao.atual()
    cfg.modo_loja = Configuracao.MODO_FECHADA
    cfg.save()
    assert horarios_agendamento(dt("2026-11-16 20:00")) == []
