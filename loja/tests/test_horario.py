from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from loja.horario import proxima_abertura, status_loja
from loja.models import Configuracao

RECIFE = ZoneInfo("America/Recife")


def dt(texto):
    return datetime.strptime(texto, "%Y-%m-%d %H:%M").replace(tzinfo=RECIFE)


# 11/11/2026 é quarta-feira
@pytest.mark.parametrize("quando, aberta, texto", [
    ("2026-11-11 18:14", False, "Fechado · Abrimos às 18:15"),
    ("2026-11-11 18:15", True, "Aberto até 22:30"),
    ("2026-11-11 22:30", True, "Aberto até 22:30"),
    ("2026-11-11 22:31", False, "Fechado · Abrimos amanhã às 18:15"),
    ("2026-11-15 17:00", False, "Fechado · Abrimos às 18:00"),        # domingo
    ("2026-11-16 20:00", False, "Fechado · Abrimos quarta às 18:15"),  # segunda
    ("2026-11-14 23:00", False, "Fechado · Abrimos amanhã às 18:00"),  # sábado -> domingo
])
def test_status(horarios, quando, aberta, texto):
    s = status_loja(dt(quando))
    assert (s.aberta, s.texto) == (aberta, texto)


def test_forcar_aberta(horarios):
    cfg = Configuracao.atual()
    cfg.modo_loja = "aberta"
    cfg.save()
    s = status_loja(dt("2026-11-16 20:00"))
    assert (s.aberta, s.texto) == (True, "Aberto agora")


def test_forcar_fechada(horarios):
    cfg = Configuracao.atual()
    cfg.modo_loja = "fechada"
    cfg.save()
    s = status_loja(dt("2026-11-11 20:00"))
    assert (s.aberta, s.texto) == (False, "Fechado no momento")


def test_turno_e_a_data_quando_aberta(horarios):
    assert status_loja(dt("2026-11-11 20:00")).turno == "2026-11-11"


def test_turno_fechada_e_data_da_proxima_abertura(horarios):
    """Fechada: o turno já é o dia da próxima abertura (a sacola do pedido agendado não some)."""
    assert status_loja(dt("2026-11-11 23:00")).turno == "2026-11-12"
    assert status_loja(dt("2026-11-16 20:00")).turno == "2026-11-18"  # segunda -> quarta
    assert status_loja(dt("2026-11-11 10:00")).turno == "2026-11-11"  # antes de abrir: hoje


def test_turno_vazio_sem_proxima_abertura(db):
    assert status_loja(dt("2026-11-11 20:00")).turno == ""


def test_turno_vazio_quando_forcada_fechada(horarios):
    cfg = Configuracao.atual()
    cfg.modo_loja = "fechada"
    cfg.save()
    assert status_loja(dt("2026-11-16 20:00")).turno == ""


def test_sem_horario_cadastrado_fica_fechado(db):
    s = status_loja(dt("2026-11-11 20:00"))
    assert (s.aberta, s.texto) == (False, "Fechado")


def test_proxima_abertura_segunda_cai_na_quarta(horarios):
    assert proxima_abertura(dt("2026-11-16 20:00")) == dt("2026-11-18 18:15")


def test_proxima_abertura_antes_de_abrir_e_hoje(horarios):
    assert proxima_abertura(dt("2026-11-11 10:00")) == dt("2026-11-11 18:15")
