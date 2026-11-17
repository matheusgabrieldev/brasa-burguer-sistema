"""Valores negativos não passam pela validação dos modelos (admin)."""
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from cardapio.models import Categoria, GrupoOpcao, Opcao, Produto
from loja.models import Bairro, Configuracao, FormaPagamento


def _erra(obj, campo):
    with pytest.raises(ValidationError) as e:
        obj.full_clean()
    assert campo in e.value.message_dict


def test_produto_preco_negativo(db):
    cat = Categoria.objects.create(nome="C")
    _erra(Produto(categoria=cat, nome="X", slug="x", preco=Decimal("-1")), "preco")


def test_opcao_preco_negativo(db):
    g = GrupoOpcao.objects.create(codigo="g", nome="G")
    _erra(Opcao(grupo=g, nome="O", preco=Decimal("-1")), "preco")


def test_bairro_taxa_negativa(db):
    _erra(Bairro(nome="B", taxa=Decimal("-1")), "taxa")


def test_forma_acrescimo_negativo(db):
    _erra(FormaPagamento(codigo="z", nome="Z", acrescimo_pct=Decimal("-1")), "acrescimo_pct")


def test_pedido_minimo_negativo(db):
    c = Configuracao.atual()
    c.pedido_minimo = Decimal("-1")
    _erra(c, "pedido_minimo")
