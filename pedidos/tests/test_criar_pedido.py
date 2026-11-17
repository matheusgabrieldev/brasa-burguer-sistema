"""Regras do checkout: criar_pedido recalcula tudo e recusa o que está fora das regras."""
from datetime import date, datetime, timezone as dt_timezone
from decimal import Decimal

import pytest

from clientes.models import Cliente
from loja.models import Configuracao
from pedidos.models import ContadorDia, HistoricoStatus, ItemPedido, Pedido
from pedidos.servicos import PedidoInvalido, criar_pedido, ler_valor

BLOQUEADO = "Não conseguimos receber seu pedido agora. Fale com a loja no WhatsApp."


def erro(cenario, agora=None, **mudar):
    """Tenta criar e devolve o PedidoInvalido (o teste falha se não der erro)."""
    with pytest.raises(PedidoInvalido) as e:
        criar_pedido(cenario.dados(**mudar), agora=agora or cenario.aberta)
    return e.value


# ---- valores --------------------------------------------------------------------------
def test_total_com_taxa_e_acrescimo_do_credito(db, cenario):
    # burger 20 + bacon 2,50 x2, qtd 2 = 50,00; taxa 5; crédito 4% de 55 = 2,20 -> total 57,20
    p = criar_pedido(cenario.dados(), agora=cenario.aberta)
    assert (p.subtotal, p.taxa_entrega, p.acrescimo, p.total) == (
        Decimal("50.00"), Decimal("5.00"), Decimal("2.20"), Decimal("57.20"))
    assert (p.forma_pagamento_nome, p.forma_pagamento_codigo) == ("Cartão de crédito", "credito")
    assert (p.origem, p.tipo, p.status, p.numero, p.dia) == ("site", "delivery", "preparo", 1, date(2026, 11, 11))
    assert (p.nome, p.telefone, p.bairro_nome, p.rua, p.numero_end) == ("Ana", "81988887777", "Paratibe", "Rua das Flores", "505")
    item = p.itens.get()
    assert (item.nome, item.preco_unitario, item.quantidade, item.produto) == ("Brasa Premium", Decimal("25.00"), 2, cenario.burger)
    assert item.opcoes == [
        {"grupo": "Escolha o ponto da carne", "nome": "Ao ponto", "qtd": 1, "preco": "0.00"},
        {"grupo": "Adicionais à parte", "nome": "Bacon", "qtd": 2, "preco": "2.50"},
    ]
    assert list(p.historico.values_list("status", flat=True)) == ["preparo"]
    assert p.cliente == Cliente.objects.get(telefone="81988887777")


def test_preco_vem_do_banco_mesmo_se_navegador_mandar_total(db, cenario):
    dados = cenario.dados(total="1.00", subtotal="1.00", taxa_entrega="0")
    dados["itens"][0]["preco_unit"] = "0.01"
    p = criar_pedido(dados, agora=cenario.aberta)
    assert p.total == Decimal("57.20")
    assert p.itens.get().preco_unitario == Decimal("25.00")


def test_pix_sem_acrescimo_e_retirada_sem_taxa(db, cenario):
    p = criar_pedido(cenario.dados(tipo="retirada", pagamento="pix", bairro_id=None, rua="", numero=""), agora=cenario.aberta)
    assert (p.taxa_entrega, p.acrescimo, p.total) == (Decimal("0"), Decimal("0"), Decimal("50.00"))
    assert (p.bairro_nome, p.rua, p.numero_end) == ("", "", "")


def test_retirada_ignora_endereco_enviado(db, cenario):
    p = criar_pedido(cenario.dados(tipo="retirada", pagamento="pix"), agora=cenario.aberta)
    assert (p.bairro_nome, p.rua, p.numero_end, p.taxa_entrega) == ("", "", "", Decimal("0"))


# ---- chave (duplo toque) --------------------------------------------------------------
def test_mesma_chave_nao_cria_dois_pedidos(db, cenario):
    dados = cenario.dados()
    a = criar_pedido(dados, agora=cenario.aberta)
    b = criar_pedido(dict(dados, nome="Outro nome", pagamento="pix"), agora=cenario.aberta)
    assert a.pk == b.pk
    assert b.nome == "Ana"
    assert Pedido.objects.count() == 1
    assert ContadorDia.objects.get().ultimo == 1


def test_chave_repetida_ao_mesmo_tempo_devolve_o_primeiro(db, cenario, monkeypatch):
    """Dois envios simultâneos: os dois passam da checagem; o segundo bate no unique da chave."""
    import pedidos.servicos as servicos

    dados = cenario.dados()
    a = criar_pedido(dados, agora=cenario.aberta)
    monkeypatch.setattr(servicos, "_pedido_da_chave", lambda chave: None)
    b = criar_pedido(dados, agora=cenario.aberta)
    assert a.pk == b.pk
    assert Pedido.objects.count() == 1


@pytest.mark.parametrize("chave", ["", None, "abc", "123"])
def test_chave_invalida(db, cenario, chave):
    assert str(erro(cenario, chave=chave)) == "Pedido inválido. Recarregue a página."


@pytest.mark.parametrize("dados", [[], "texto", None])
def test_dados_que_nao_sao_objeto(db, dados):
    with pytest.raises(PedidoInvalido):
        criar_pedido(dados)


# ---- cliente --------------------------------------------------------------------------
def test_cliente_bloqueado_recebe_mensagem_neutra(db, cenario):
    Cliente.objects.create(telefone="81988887777", nome="Ana", bloqueado=True)
    assert str(erro(cenario)) == BLOQUEADO
    assert Pedido.objects.count() == 0


def test_nome_obrigatorio_e_ate_80(db, cenario):
    assert erro(cenario, nome="   ").campo == "nome"
    assert erro(cenario, nome="a" * 81).campo == "nome"
    p = criar_pedido(cenario.dados(nome="  " + "a" * 80 + "  "), agora=cenario.aberta)
    assert p.nome == "a" * 80


def test_telefone_invalido(db, cenario):
    e = erro(cenario, telefone="9999")
    assert (e.campo, str(e)) == ("telefone", "Informe o WhatsApp com DDD, ex.: (81) 9 8888-7777.")
    assert Cliente.objects.count() == 0


def test_tipo_invalido(db, cenario):
    assert erro(cenario, tipo="drone").campo == "tipo"


# ---- sacola ---------------------------------------------------------------------------
def test_sacola_vazia_ou_grande_demais(db, cenario):
    assert erro(cenario, itens=[]).campo == "itens"
    assert erro(cenario, itens="lixo").campo == "itens"
    item = cenario.dados()["itens"][0]
    assert erro(cenario, itens=[item] * 51).campo == "itens"
    assert criar_pedido(cenario.dados(itens=[item] * 50, pagamento="pix"), agora=cenario.aberta).itens.count() == 50


def test_erro_de_item_vira_pedido_invalido_com_a_mesma_mensagem(db, cenario):
    cenario.burger.visivel = False
    cenario.burger.save()
    e = erro(cenario)
    assert (e.campo, str(e)) == ("itens", "Brasa Premium não está mais disponível. Confira a sacola.")


def test_item_mal_formado(db, cenario):
    assert erro(cenario, itens=["x"]).campo == "itens"
    assert erro(cenario, itens=[{"quantidade": 1}]).campo == "itens"


def test_esgotado_hoje_usa_o_dia_de_agora(db, cenario):
    cenario.burger.esgotado_em = date(2026, 11, 11)
    cenario.burger.save()
    assert erro(cenario).campo == "itens"


# ---- entrega --------------------------------------------------------------------------
def test_pedido_minimo_so_no_delivery(db, cenario):
    cfg = Configuracao.atual()
    cfg.pedido_minimo = Decimal("60")
    cfg.save()
    e = erro(cenario)
    assert str(e) == "Pedido mínimo para entrega: R$ 60,00."
    p = criar_pedido(cenario.dados(tipo="retirada", pagamento="pix"), agora=cenario.aberta)
    assert p.total == Decimal("50.00")


def test_pedido_minimo_padrao_dez_reais(db, cenario):
    from cardapio.models import Produto

    agua = Produto.objects.create(categoria=cenario.burger.categoria, slug="agua", nome="Água", preco=Decimal("3"))
    e = erro(cenario, itens=[{"produto_id": agua.id, "quantidade": 1, "opcoes": {}}])
    assert str(e) == "Pedido mínimo para entrega: R$ 10,00."


def test_bairro_inativo_nao_entrega(db, cenario):
    cenario.bairro.ativo = False
    cenario.bairro.save()
    assert erro(cenario).campo == "bairro"


def test_bairro_faltando_ou_lixo(db, cenario):
    assert erro(cenario, bairro_id="").campo == "bairro"
    assert erro(cenario, bairro_id="abc").campo == "bairro"
    assert erro(cenario, bairro_id=99999).campo == "bairro"


def test_rua_e_numero_obrigatorios_e_com_limite(db, cenario):
    assert erro(cenario, rua="  ").campo == "rua"
    assert erro(cenario, numero="").campo == "numero"
    assert erro(cenario, rua="r" * 121).campo == "rua"
    assert erro(cenario, numero="1" * 21).campo == "numero"


def test_referencia_e_observacao_cortadas_no_limite(db, cenario):
    p = criar_pedido(cenario.dados(referencia="r" * 300, observacao="o" * 600), agora=cenario.aberta)
    assert len(p.referencia) == 200
    assert len(p.observacao) == 500
    p.full_clean()  # cabe nos campos do modelo


# ---- pagamento ------------------------------------------------------------------------
def test_dinheiro_desligado_no_delivery(db, cenario):
    din = cenario.formas["dinheiro"]
    din.aceita_delivery = False
    din.save()
    e = erro(cenario, pagamento="dinheiro")
    assert (e.campo, str(e)) == ("pagamento", "Dinheiro não é aceito na entrega.")
    p = criar_pedido(cenario.dados(tipo="retirada", pagamento="dinheiro"), agora=cenario.aberta)
    assert p.forma_pagamento_codigo == "dinheiro"


def test_forma_de_pagamento_inexistente(db, cenario):
    assert erro(cenario, pagamento="cheque").campo == "pagamento"


def test_troco_menor_que_total_da_erro(db, cenario):
    e = erro(cenario, pagamento="dinheiro", troco_para="50")  # total 55,00
    assert (e.campo, str(e)) == ("troco", "O troco precisa ser para um valor igual ou maior que o total (R$ 55,00).")


def test_troco_ok_e_so_para_dinheiro(db, cenario):
    p = criar_pedido(cenario.dados(pagamento="dinheiro", troco_para="R$ 100"), agora=cenario.aberta)
    assert (p.total, p.troco_para, p.troco) == (Decimal("55.00"), Decimal("100.00"), Decimal("45.00"))
    p2 = criar_pedido(cenario.dados(pagamento="pix", troco_para="100"), agora=cenario.aberta)
    assert p2.troco_para is None
    p3 = criar_pedido(cenario.dados(pagamento="dinheiro", troco_para=""), agora=cenario.aberta)
    assert p3.troco_para is None


def test_troco_invalido(db, cenario):
    assert erro(cenario, pagamento="dinheiro", troco_para="cinquenta").campo == "troco"


@pytest.mark.parametrize("texto, valor", [
    ("50", "50.00"), ("50,00", "50.00"), ("R$ 50", "50.00"), ("1.000,00", "1000.00"), ("1.000", "1000.00"), ("50.5", "50.50"),
])
def test_ler_valor(texto, valor):
    assert ler_valor(texto) == Decimal(valor)


@pytest.mark.parametrize("texto", ["abc", "-5", "0", "NaN", "Infinity", "1000000"])
def test_ler_valor_recusa_lixo(texto):
    with pytest.raises(PedidoInvalido) as e:
        ler_valor(texto)
    assert e.value.campo == "troco"


def test_ler_valor_vazio_e_none():
    assert ler_valor("") is None
    assert ler_valor(None) is None


# ---- horário e agendamento ------------------------------------------------------------
def test_loja_fechou_antes_de_enviar_pede_horario(db, cenario):
    e = erro(cenario, agora=cenario.fechada)
    assert (e.campo, str(e)) == ("horario", "A loja está fechada. Escolha um horário para agendar.")
    assert Pedido.objects.count() == 0


def test_loja_forcada_fechada_nao_pede_horario(db, cenario):
    """Sem horários para agendar (forçada a fechar): não adianta pedir um horário."""
    c = Configuracao.atual()
    c.modo_loja = "fechada"
    c.save()
    e = erro(cenario, agora=cenario.aberta)
    assert (e.campo, str(e)) == ("horario", "A loja está fechada no momento.")
    e = erro(cenario, agora=cenario.aberta, agendar_para="2026-11-18T18:15")
    assert (e.campo, str(e)) == ("horario", "A loja está fechada no momento.")


def test_agendado_fica_com_status_agendado(db, cenario):
    p = criar_pedido(cenario.dados(agendar_para="2026-11-18T18:15:00-03:00"), agora=cenario.fechada)
    assert p.status == "agendado"
    assert p.agendado_para == datetime(2026, 11, 18, 21, 15, tzinfo=dt_timezone.utc)
    assert list(p.historico.values_list("status", flat=True)) == ["agendado"]
    assert p.dia == date(2026, 11, 16)  # o número é do dia em que foi feito


def test_agendar_aceita_hora_sem_fuso_como_recife(db, cenario):
    p = criar_pedido(cenario.dados(agendar_para="2026-11-18T22:30"), agora=cenario.fechada)
    assert p.agendado_para == datetime(2026, 11, 19, 1, 30, tzinfo=dt_timezone.utc)


@pytest.mark.parametrize("quando", ["2026-11-18T18:20", "2026-11-18T22:45", "2026-11-19T18:15", "amanhã", "2026-11-18T18:00"])
def test_horario_fora_da_lista_e_recusado(db, cenario, quando):
    assert erro(cenario, agora=cenario.fechada, agendar_para=quando).campo == "horario"


def test_loja_aberta_nao_aceita_agendamento(db, cenario):
    assert erro(cenario, agendar_para="2026-11-18T18:15").campo == "horario"


# ---- número do dia e transação --------------------------------------------------------
def test_dia_e_a_data_de_recife_nao_utc(db, cenario):
    agora = datetime(2026, 11, 12, 1, 0, tzinfo=dt_timezone.utc)  # = 11/11 22:00 em Recife
    p = criar_pedido(cenario.dados(), agora=agora)
    assert p.dia == date(2026, 11, 11)


def test_numeros_em_sequencia(db, cenario):
    numeros = [criar_pedido(cenario.dados(), agora=cenario.aberta).numero for _ in range(3)]
    assert numeros == [1, 2, 3]


def test_falha_ao_gravar_nao_gasta_numero_nem_deixa_restos(db, cenario, monkeypatch):
    def quebra(*a, **k):
        raise RuntimeError("banco caiu")

    monkeypatch.setattr(HistoricoStatus.objects, "create", quebra)
    with pytest.raises(RuntimeError):
        criar_pedido(cenario.dados(), agora=cenario.aberta)
    assert (Pedido.objects.count(), ItemPedido.objects.count(), Cliente.objects.count()) == (0, 0, 0)
    assert not ContadorDia.objects.exists()
    monkeypatch.undo()
    assert criar_pedido(cenario.dados(), agora=cenario.aberta).numero == 1


def test_cliente_existente_mantem_nome(db, cenario):
    Cliente.objects.create(telefone="81988887777", nome="Ana Maria")
    p = criar_pedido(cenario.dados(nome="Aninha"), agora=cenario.aberta)
    assert p.cliente.nome == "Ana Maria"
    assert p.nome == "Aninha"  # o pedido guarda o nome digitado
