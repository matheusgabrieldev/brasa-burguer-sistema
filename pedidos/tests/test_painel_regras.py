"""Regras de etapa do painel: avançar, voltar, aceitar, recusar, cancelar, finalizar."""
from datetime import timedelta

import pytest
from django.contrib.auth.models import User

from gerenciar.permissoes import eh_equipe
from loja.models import Configuracao
from pedidos import painel
from pedidos.models import Pedido
from pedidos.servicos import criar_pedido


def novo(cenario, **mudar):
    return criar_pedido(cenario.dados(**mudar), agora=cenario.aberta)


def manual():
    cfg = Configuracao.atual()
    cfg.entrada_pedidos = "manual"
    cfg.save()


def com_status(pedido, status):
    Pedido.objects.filter(pk=pedido.pk).update(status=status)
    pedido.refresh_from_db()
    return pedido


def test_proxima_etapa_por_tipo(db, cenario):
    p = novo(cenario)
    assert painel.proxima_etapa(p) == ("pronto", "✓ Pronto")
    p.status = "pronto"
    assert painel.proxima_etapa(p) == ("saiu", "🛵 Saiu para entrega")
    p.tipo = "retirada"
    assert painel.proxima_etapa(p) == ("concluido", "✓ Entregue")
    p.tipo = "local"
    assert painel.proxima_etapa(p) == ("concluido", "✓ Entregue")
    p.status, p.tipo = "saiu", "delivery"
    assert painel.proxima_etapa(p) == ("concluido", "✓ Entregue")
    for s in ("concluido", "cancelado", "aguardando"):
        p.status = s
        assert painel.proxima_etapa(p) is None


def test_avancar_grava_historico_com_usuario(db, cenario, usuario_dono):
    p = novo(cenario)
    assert painel.avancar(p.id, "preparo", usuario_dono) is True
    p.refresh_from_db()
    assert p.status == "pronto"
    ultimo = p.historico.last()
    assert ultimo.status == "pronto" and ultimo.usuario == usuario_dono


def test_avancar_com_status_velho_nao_faz_nada(db, cenario, usuario_dono, usuario_equipe):
    p = novo(cenario)
    assert painel.cancelar(p.id, usuario_dono, "cliente desistiu") is True
    antes = p.historico.count()
    assert painel.avancar(p.id, "preparo", usuario_equipe) is False
    p.refresh_from_db()
    assert p.status == "cancelado"
    assert p.historico.count() == antes


def test_voltar_desfaz_toque_errado(db, cenario, usuario_equipe):
    p = novo(cenario)
    painel.avancar(p.id, "preparo", usuario_equipe)
    assert painel.voltar(p.id, "pronto", usuario_equipe) is True
    p.refresh_from_db()
    assert p.status == "preparo"
    assert p.historico.last().nota == "voltou"
    painel.cancelar(p.id, usuario_equipe, "erro")
    assert painel.voltar(p.id, "cancelado", usuario_equipe) is False


def test_aceitar_agendado_longe_vai_para_agendado(db, cenario, usuario_equipe):
    manual()
    p = criar_pedido(cenario.dados(agendar_para="2026-11-18T18:15:00-03:00"), agora=cenario.fechada)
    assert painel.aceitar(p.id, usuario_equipe, cenario.fechada) is True
    p.refresh_from_db()
    assert p.status == "agendado" and p.visto_em is not None


def test_aceitar_agendado_perto_vai_para_preparo(db, cenario, usuario_equipe):
    manual()
    p = criar_pedido(cenario.dados(agendar_para="2026-11-18T18:15:00-03:00"), agora=cenario.fechada)
    perto = p.agendado_para - timedelta(minutes=10)
    painel.aceitar(p.id, usuario_equipe, perto)
    p.refresh_from_db()
    assert p.status == "preparo"


def test_aceitar_sem_horario_vai_para_preparo(db, cenario, usuario_equipe):
    manual()
    p = novo(cenario)
    assert p.status == "aguardando"
    assert painel.aceitar(p.id, usuario_equipe, cenario.aberta) is True
    p.refresh_from_db()
    assert p.status == "preparo" and p.visto_em is not None
    assert painel.aceitar(p.id, usuario_equipe, cenario.aberta) is False


def test_recusar_so_de_aguardando(db, cenario, usuario_equipe):
    p = novo(cenario)
    assert painel.recusar(p.id, usuario_equipe) is False  # já está em preparo
    manual()
    q = novo(cenario)
    assert painel.recusar(q.id, usuario_equipe, "sem entrega") is True
    q.refresh_from_db()
    assert q.status == "cancelado"
    assert q.historico.last().nota == "recusado: sem entrega"


def test_cancelar_exige_motivo(db, cenario, usuario_dono):
    p = novo(cenario)
    with pytest.raises(ValueError):
        painel.cancelar(p.id, usuario_dono, "  ")
    p.refresh_from_db()
    assert p.status == "preparo"


def test_cancelar_de_concluido(db, cenario, usuario_dono):
    p = com_status(novo(cenario), "concluido")
    assert painel.cancelar(p.id, usuario_dono, "estorno") is True
    p.refresh_from_db()
    assert p.status == "cancelado" and p.motivo_cancelamento == "estorno"


def test_cancelar_duas_vezes(db, cenario, usuario_dono):
    p = novo(cenario)
    assert painel.cancelar(p.id, usuario_dono, "x") is True
    assert painel.cancelar(p.id, usuario_dono, "x") is False


def test_comecar_agora_conta_como_novo(db, cenario, usuario_equipe):
    p = com_status(novo(cenario), "agendado")
    Pedido.objects.filter(pk=p.pk).update(visto_em=cenario.aberta)
    assert painel.comecar_agora(p.id, usuario_equipe) is True
    p.refresh_from_db()
    assert p.status == "preparo" and p.visto_em is None


def test_finalizar_todos_nao_mexe_em_aguardando_nem_agendado(db, cenario, usuario_equipe):
    a = novo(cenario)
    b = com_status(novo(cenario), "pronto")
    c = com_status(novo(cenario), "saiu")
    d = com_status(novo(cenario), "aguardando")
    e = com_status(novo(cenario), "agendado")
    assert painel.finalizar_todos(usuario_equipe) == 3
    for x, esperado in ((a, "concluido"), (b, "concluido"), (c, "concluido"), (d, "aguardando"), (e, "agendado")):
        x.refresh_from_db()
        assert x.status == esperado
    assert a.historico.last().nota == "finalizar todos"


def test_marcar_pago_nao_muda_status(db, cenario, usuario_equipe):
    p = novo(cenario)
    assert painel.marcar_pago(p.id, True, usuario_equipe) is True
    p.refresh_from_db()
    assert p.pago and p.status == "preparo"
    ultimo = p.historico.last()
    assert ultimo.status == "preparo" and ultimo.nota == "pago"
    painel.marcar_pago(p.id, False, usuario_equipe)
    assert p.historico.last().nota == "não pago"


def test_marcar_visto_nao_grava_historico(db, cenario):
    p = novo(cenario)
    antes = p.historico.count()
    painel.marcar_visto(p.id)
    p.refresh_from_db()
    assert p.visto_em is not None and p.historico.count() == antes


def test_eh_equipe(db, usuario_equipe, usuario_dono):
    assert eh_equipe(usuario_equipe) and eh_equipe(usuario_dono)
    assert not eh_equipe(User.objects.create_user("comum", password="x"))


def test_recusar_motivo_longo_cabe_na_nota(db, cenario, usuario_equipe):
    manual()
    p = novo(cenario)
    assert painel.recusar(p.id, usuario_equipe, "x" * 200) is True
    p.refresh_from_db()
    assert len(p.historico.last().nota) <= 200
    assert len(p.motivo_cancelamento) <= 200


def test_voltar_com_status_velho_nao_faz_nada(db, cenario, usuario_equipe):
    p = novo(cenario)
    painel.avancar(p.id, "preparo", usuario_equipe)  # pronto
    painel.avancar(p.id, "pronto", usuario_equipe)  # saiu
    antes = p.historico.count()
    assert painel.voltar(p.id, "pronto", usuario_equipe) is False  # o aparelho viu "pronto", agora é "saiu"
    painel.cancelar(p.id, usuario_equipe, "erro")
    antes = p.historico.count()
    assert painel.voltar(p.id, "saiu", usuario_equipe) is False
    p.refresh_from_db()
    assert p.status == "cancelado" and p.historico.count() == antes


def test_voltar_de_saiu_e_de_concluido(db, cenario, usuario_equipe):
    p = novo(cenario)
    for de in ("preparo", "pronto", "saiu"):
        painel.avancar(p.id, de, usuario_equipe)
    p.refresh_from_db()
    assert p.status == "concluido"
    assert painel.voltar(p.id, "concluido", usuario_equipe) is True
    p.refresh_from_db()
    assert p.status == "saiu" and p.historico.last().nota == "voltou"
    assert painel.voltar(p.id, "saiu", usuario_equipe) is True
    p.refresh_from_db()
    assert p.status == "pronto" and p.historico.last().nota == "voltou"


def test_voltar_duas_vezes_termina_em_preparo(db, cenario, usuario_equipe):
    p = novo(cenario)
    painel.avancar(p.id, "preparo", usuario_equipe)
    painel.avancar(p.id, "pronto", usuario_equipe)  # saiu
    assert painel.voltar(p.id, "saiu", usuario_equipe) is True
    p.refresh_from_db()
    assert p.status == "pronto" and p.historico.last().nota == "voltou"
    assert painel.voltar(p.id, "pronto", usuario_equipe) is True
    p.refresh_from_db()
    assert p.status == "preparo" and p.historico.last().nota == "voltou"
    assert painel.voltar(p.id, "preparo", usuario_equipe) is False


def test_etapa_anterior_mostra_para_onde_voltar(db, cenario, usuario_equipe):
    p = novo(cenario)
    assert painel.etapa_anterior(p) is None  # em preparo não há para onde voltar
    painel.avancar(p.id, "preparo", usuario_equipe)
    p.refresh_from_db()
    assert painel.etapa_anterior(p) == "preparo"
    painel.voltar(p.id, "pronto", usuario_equipe)
    p.refresh_from_db()
    assert painel.etapa_anterior(p) is None
