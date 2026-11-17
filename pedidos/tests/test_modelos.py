"""Testes dos modelos do pedido e da numeração do dia."""
import uuid
from datetime import date
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from clientes.models import Cliente
from pedidos.models import ItemPedido, Pedido
from pedidos.numeracao import proximo_numero


@pytest.fixture
def cliente(db):
    return Cliente.objects.create(telefone="81999990000", nome="Ana")


def criar_pedido(cliente, numero=1, dia=date(2026, 11, 11), **extra):
    dados = dict(
        chave=uuid.uuid4(), numero=numero, dia=dia, origem="site", tipo="delivery",
        cliente=cliente, nome="Ana", telefone="81999990000",
        subtotal=Decimal("32.40"), taxa_entrega=Decimal("5.00"), total=Decimal("37.40"),
    )
    dados.update(extra)
    return Pedido.objects.create(**dados)


def test_numero_recomeca_no_dia_seguinte(db):
    assert proximo_numero(date(2026, 11, 11)) == 1
    assert proximo_numero(date(2026, 11, 11)) == 2
    assert proximo_numero(date(2026, 11, 12)) == 1


def test_numeros_em_sequencia_sem_repetir(db):
    numeros = [proximo_numero(date(2026, 11, 11)) for _ in range(20)]
    assert numeros == list(range(1, 21))


def test_codigo_unico_e_nao_sequencial(cliente):
    a = criar_pedido(cliente, numero=1)
    b = criar_pedido(cliente, numero=2)
    assert a.codigo != b.codigo
    assert len(a.codigo) >= 12


def test_numero_unico_no_dia(cliente):
    criar_pedido(cliente, numero=1)
    with pytest.raises(IntegrityError), transaction.atomic():
        criar_pedido(cliente, numero=1)
    criar_pedido(cliente, numero=1, dia=date(2026, 11, 12))


def test_troco(cliente):
    p = criar_pedido(cliente, troco_para=Decimal("50"))
    assert p.troco == Decimal("12.60")
    assert criar_pedido(cliente, numero=2).troco is None
    assert criar_pedido(cliente, numero=3, troco_para=Decimal("30")).troco == Decimal("0")


def test_rotulos_em_portugues(cliente):
    p = criar_pedido(cliente)
    assert p.get_tipo_display() == "Delivery"
    assert Pedido(tipo="local").get_tipo_display() == "No local"
    assert Pedido(status="saiu").get_status_display() == "Saiu para entrega"


def test_item_total_e_produto_set_null(cliente, produto):
    p = criar_pedido(cliente)
    item = ItemPedido.objects.create(
        pedido=p, produto=produto, nome="Brasa Premium", preco_unitario=Decimal("22.50"),
        quantidade=2, opcoes=[{"grupo": "Adicionais", "nome": "Bacon", "qtd": 1, "preco": "2.50"}],
    )
    assert item.total == Decimal("45.00")
    produto.delete()
    item.refresh_from_db()
    assert item.produto is None
    assert item.nome == "Brasa Premium"


def test_itens_saem_na_ordem_em_que_foram_pedidos():
    assert ItemPedido._meta.ordering == ["id"]


def test_observacao_geral_ate_500():
    assert Pedido._meta.get_field("observacao").max_length == 500
