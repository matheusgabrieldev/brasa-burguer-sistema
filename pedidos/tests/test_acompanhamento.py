from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from django.urls import reverse
from django.utils import timezone

from clientes.models import Cliente
from loja.models import Configuracao
from pedidos.models import Pedido


@pytest.fixture
def pedido(db):
    cliente = Cliente.objects.create(nome="Ana", telefone="81988887777")
    return Pedido.objects.create(
        chave=uuid4(), numero=12, dia=date(2026, 11, 18), origem="site",
        tipo="delivery", cliente=cliente, nome="Ana", telefone=cliente.telefone,
        rua="Rua A", numero_end="505", bairro_nome="Paratibe", referencia="Portão azul",
        subtotal=Decimal("50"), taxa_entrega=Decimal("5"), acrescimo=Decimal("2.20"),
        total=Decimal("57.20"), forma_pagamento_codigo="credito",
        forma_pagamento_nome="Cartão de crédito",
    )


def test_mensagem_delivery_credito(pedido):
    from pedidos.whatsapp import mensagem_pedido

    pedido.itens.create(
        nome="Brasa Premium", quantidade=2, preco_unitario=Decimal("25"),
        opcoes=[{"nome": "Ao ponto", "qtd": 1, "preco": "0"},
                {"nome": "Bacon", "qtd": 2, "preco": "2.50"}],
        observacao="sem picles",
    )
    assert mensagem_pedido(pedido).splitlines() == [
        "Olá! Quero confirmar meu pedido 🍔",
        f"*Pedido #12* · {pedido.codigo}",
        "*Tipo de serviço: Delivery*",
        "Nome: Ana",
        "Telefone: (81) 98888-7777",
        "Endereço: Rua A, 505 — Paratibe",
        "Referência: Portão azul",
        "*📝 Produtos*",
        "*2x Brasa Premium  R$ 50,00*",
        "    + Ao ponto",
        "    + 2x Bacon R$ 5,00",
        "    _Obs.: sem picles_",
        "Subtotal: R$ 50,00",
        "Entrega: R$ 5,00",
        "Acréscimo cartão: R$ 2,20",
        "*Total: R$ 57,20*",
        "*💲 Pagamento:* Cartão de crédito",
    ]


def test_mensagem_agendado_tem_data_e_hora(pedido):
    from pedidos.whatsapp import mensagem_pedido

    pedido.agendado_para = timezone.make_aware(datetime(2026, 11, 18, 18, 15))
    assert "🗓️ 18/11/2026 ⏰ 18:15" in mensagem_pedido(pedido)


def test_mensagem_pix_com_titular_e_banco(pedido):
    from pedidos.whatsapp import mensagem_pedido

    Configuracao(chave_pix="chave", pix_titular="Ana", pix_banco="Banco").save()
    pedido.forma_pagamento_codigo = "pix"
    assert "Chave Pix: chave · Titular: Ana · Banco: Banco" in mensagem_pedido(pedido)


def test_link_whatsapp_usa_numero_da_loja_e_codifica_texto(pedido):
    from urllib.parse import parse_qs, urlsplit

    from pedidos.whatsapp import link_whatsapp, mensagem_pedido

    Configuracao(whatsapp="5581988887777").save()
    url = urlsplit(link_whatsapp(pedido))
    assert (url.scheme, url.netloc, url.path) == ("https", "wa.me", "/5581988887777")
    assert parse_qs(url.query)["text"] == [mensagem_pedido(pedido)]


def test_acompanhar_404_codigo_errado(client, db):
    assert client.get(reverse("pedidos:acompanhar", args=["errado"])).status_code == 404
    assert client.get(reverse("pedidos:status", args=["errado"])).status_code == 404


def test_status_texto_retirada_pronto(client, pedido):
    pedido.tipo = "retirada"
    pedido.status = "pronto"
    pedido.save()
    url = reverse("pedidos:status", args=[pedido.codigo])
    resposta = client.get(url)
    assert "Pronto! Pode vir buscar" in resposta.content.decode()
    assert 'hx-trigger="every 15s"' in resposta.content.decode()
    pedido.status = "concluido"
    pedido.save()
    resposta = client.get(url)
    assert "Entregue" in resposta.content.decode()
    assert "hx-trigger" not in resposta.content.decode()


def test_acompanhar_nao_mostra_outro_pedido(client, pedido):
    codigo = pedido.codigo
    pedido.pk = None
    pedido.codigo = "segundo-pedido"
    pedido.chave = uuid4()
    pedido.numero = 13
    pedido.nome = "Cliente diferente"
    pedido.save()
    resposta = client.get(reverse("pedidos:acompanhar", args=[codigo]))
    assert resposta.status_code == 200
    html = resposta.content.decode()
    assert "Ana" in html
    assert "Cliente diferente" not in html
    assert "no-store" in resposta["Cache-Control"]
