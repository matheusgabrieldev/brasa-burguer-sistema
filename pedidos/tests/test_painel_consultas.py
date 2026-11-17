"""Consultas do painel: colunas, filtros, busca, total do dia e versão."""
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone

from loja.models import Configuracao
from pedidos.agendamento import horarios_agendamento
from pedidos.models import HistoricoStatus, Pedido
from pedidos.painel import avancar, marcar_pago, marcar_visto
from pedidos.painel_consultas import montar_painel, promover_agendados, total_do_dia, versao_painel
from pedidos.servicos import criar_pedido

HOJE = date(2026, 11, 11)  # quarta, o dia de cenario.aberta
RECIFE = ZoneInfo("America/Recife")


def fazer(cenario, status="preparo", **mudar):
    """Cria um pedido de hoje e força o status (para montar cenários sem passar por cada etapa)."""
    p = criar_pedido(cenario.dados(**mudar), agora=cenario.aberta)
    Pedido.objects.filter(pk=p.pk).update(status=status)
    p.refresh_from_db()
    return p


def agendar(cenario):
    """Pedido feito na segunda (loja fechada) para a primeira vaga de quarta 18/11."""
    quando = horarios_agendamento(cenario.fechada)[0]
    return criar_pedido(cenario.dados(agendar_para=quando.isoformat()), agora=cenario.fechada)


def status_das_colunas(painel):
    return [c.status for c in painel.colunas]


def test_colunas_na_ordem_sem_aguardando_no_automatico(cenario):
    fazer(cenario, "preparo")
    assert status_das_colunas(montar_painel(HOJE)) == ["preparo", "pronto", "saiu", "concluido"]


def test_coluna_aguardando_no_manual(cenario):
    cfg = Configuracao.atual()
    cfg.entrada_pedidos = "manual"
    cfg.save()
    assert status_das_colunas(montar_painel(HOJE)) == ["aguardando", "preparo", "pronto", "saiu", "concluido"]


def test_coluna_aguardando_aparece_se_sobrou_pedido_no_automatico(cenario):
    fazer(cenario, "aguardando")
    assert status_das_colunas(montar_painel(HOJE))[0] == "aguardando"


def test_pedido_de_ontem_aberto_fica_nas_colunas_mas_fora_do_total(cenario):
    p = fazer(cenario, "preparo")
    Pedido.objects.filter(pk=p.pk).update(dia=HOJE - timedelta(days=1))
    painel = montar_painel(HOJE)
    assert [x.pk for x in painel.colunas[0].pedidos] == [p.pk]
    assert total_do_dia(HOJE) == (0, Decimal("0"))


def test_abertos_do_mais_antigo_para_o_mais_novo_e_total_de_itens(cenario):
    a = fazer(cenario)
    b = fazer(cenario)
    Pedido.objects.filter(pk=a.pk).update(criado_em=cenario.aberta)
    Pedido.objects.filter(pk=b.pk).update(criado_em=cenario.aberta - timedelta(hours=1))
    col = montar_painel(HOJE).colunas[0]
    assert [x.pk for x in col.pedidos] == [b.pk, a.pk]
    assert col.total_itens == 4  # 2 pedidos x 2 burguers


def test_concluido_so_de_hoje_e_ate_20(cenario):
    for _ in range(21):
        fazer(cenario, "concluido")
    velho = fazer(cenario, "concluido")
    Pedido.objects.filter(pk=velho.pk).update(dia=HOJE - timedelta(days=1))
    assert len(montar_painel(HOJE).colunas[-1].pedidos) == 20
    assert len(montar_painel(HOJE, todos_concluidos=True).colunas[-1].pedidos) == 21


def test_agendado_conta_no_dia_da_entrega(cenario):
    p = agendar(cenario)
    Pedido.objects.filter(pk=p.pk).update(status="concluido")  # só para entrar no total
    quarta = date(2026, 11, 18)
    assert total_do_dia(quarta)[0] == 1
    assert total_do_dia(date(2026, 11, 16))[0] == 0


def test_promover_agendados_30_min_antes(cenario):
    p = agendar(cenario)
    assert p.status == "agendado"
    assert montar_painel(date(2026, 11, 18)).agendados[0].pk == p.pk
    assert promover_agendados(p.agendado_para - timedelta(minutes=31)) == 0
    assert promover_agendados(p.agendado_para - timedelta(minutes=30)) == 1
    p.refresh_from_db()
    assert p.status == "preparo" and p.visto_em is None
    h = p.historico.latest("id")
    assert (h.status, h.nota, h.usuario) == ("preparo", "agendado: começou", None)
    assert montar_painel(date(2026, 11, 18)).novos == 1


def test_cancelado_fora_do_total_e_no_concluido(cenario):
    fazer(cenario, "concluido")
    c = fazer(cenario, "cancelado")
    fazer(cenario, "aguardando")
    assert total_do_dia(HOJE)[0] == 1
    assert c.pk in [x.pk for x in montar_painel(HOJE).colunas[-1].pedidos]


def test_total_do_dia_soma_valores(cenario):
    a = fazer(cenario, "concluido")
    b = fazer(cenario, "preparo")
    assert total_do_dia(HOJE) == (2, a.total + b.total)


def test_filtro_tipo_e_contadores(cenario):
    fazer(cenario, "preparo")
    fazer(cenario, "pronto", tipo="retirada")
    fazer(cenario, "saiu", tipo="local")
    fazer(cenario, "concluido")  # não conta: contador é só de abertos
    agendar(cenario)
    painel = montar_painel(HOJE)
    assert painel.contagem_tipo == {"tudo": 3, "delivery": 1, "retirada": 1, "local": 1, "agendados": 1}
    filtrado = montar_painel(HOJE, tipo="retirada")
    assert [len(c.pedidos) for c in filtrado.colunas] == [0, 1, 0, 0]
    ag = montar_painel(HOJE, tipo="agendados")
    assert ag.colunas == [] and len(ag.agendados) == 1


def test_busca_por_numero_nome_e_telefone_formatado(cenario):
    ana = fazer(cenario, nome="Ana", telefone="(81) 98888-7777")
    bia = fazer(cenario, nome="Bia", telefone="(81) 97777-1111")
    c = fazer(cenario, "concluido", nome="Caio", telefone="(81) 96666-2222")

    def achar(texto):
        painel = montar_painel(HOJE, busca=texto)
        assert [(x.status, x.titulo) for x in painel.colunas] == [("resultado", "Resultado")]
        return {p.pk for p in painel.colunas[0].pedidos}

    assert achar("(81) 98888-7777") == {ana.pk}
    assert achar("988887777") == {ana.pk}
    assert achar("ana") == {ana.pk}
    assert achar("3") == {c.pk}  # nº do dia
    assert achar("bia") == {bia.pk}


def test_versao_muda_com_historico_e_visto(cenario):
    agora = cenario.aberta
    v0 = versao_painel(agora)
    p = fazer(cenario, "preparo")  # criar_pedido grava histórico
    v = versao_painel(agora)
    assert v != v0
    assert versao_painel(agora) == v
    marcar_visto(p.pk)
    v2 = versao_painel(agora)
    assert v2 != v
    assert avancar(p.pk, "preparo", None)
    v3 = versao_painel(agora)
    assert v3 != v2
    assert marcar_pago(p.pk, True, None)
    v4 = versao_painel(agora)
    assert v4 != v3
    assert versao_painel(agora + timedelta(days=1)) != v4


def test_versao_muda_a_cada_minuto(cenario):
    """Os "12 min" do cartão e o vermelho dos 40 min só andam se a versão mudar com o relógio."""
    agora = cenario.aberta
    v = versao_painel(agora)
    assert versao_painel(agora + timedelta(seconds=30)) == v  # mesmo minuto: nada a redesenhar
    assert versao_painel(agora + timedelta(minutes=1)) != v


def test_dia_efetivo_usa_o_fuso_de_recife(cenario):
    """23:30 em Recife já é o dia seguinte em UTC: tem que contar no dia de Recife,
    mesmo com o fuso ativo da requisição em UTC (por isso o tzinfo explícito)."""
    p = fazer(cenario, "concluido")
    Pedido.objects.filter(pk=p.pk).update(
        agendado_para=datetime(2026, 11, 11, 23, 30, tzinfo=RECIFE))  # = 12/11 02:30 UTC
    with timezone.override("UTC"):
        assert total_do_dia(HOJE)[0] == 1
        assert total_do_dia(date(2026, 11, 12))[0] == 0
        assert [x.pk for x in montar_painel(HOJE).colunas[-1].pedidos] == [p.pk]


def test_versao_muda_com_historico_de_id_menor(cenario):
    """No Postgres o id é reservado no INSERT, não no commit: uma linha com id MENOR que o
    máximo pode aparecer depois. A versão tem que mudar mesmo assim (conta as linhas)."""
    agora = cenario.aberta
    fazer(cenario)
    fazer(cenario)
    meio = HistoricoStatus.objects.order_by("id")[0]
    dados = {f.attname: getattr(meio, f.attname) for f in HistoricoStatus._meta.concrete_fields}
    meio.delete()  # finge que esta linha ainda não "commitou"
    v = versao_painel(agora)
    HistoricoStatus.objects.create(**dados)  # agora apareceu, com id abaixo do máximo
    assert versao_painel(agora) != v
