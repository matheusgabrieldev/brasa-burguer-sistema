"""Entrada dos pedidos do site: automática (padrão, vai direto para o preparo) ou manual
(fica aguardando a loja aceitar). É a mesma opção do OlaClick; quem escolhe é o Dono."""
import re
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from django.urls import reverse

from clientes.models import Cliente
from loja.models import Configuracao
from pedidos.models import Pedido
from pedidos.servicos import criar_pedido


def usar_entrada(modo):
    cfg = Configuracao.atual()
    cfg.entrada_pedidos = modo
    cfg.save()


def test_padrao_e_automatica(db):
    assert Configuracao.atual().entrada_pedidos == "auto"


def test_automatica_vai_direto_para_o_preparo(db, cenario):
    p = criar_pedido(cenario.dados(), agora=cenario.aberta)
    assert p.status == "preparo"


def test_manual_fica_aguardando_aceite(db, cenario):
    usar_entrada("manual")
    p = criar_pedido(cenario.dados(), agora=cenario.aberta)
    assert p.status == "aguardando"
    assert p.get_status_display() == "Aguardando aceite"
    assert list(p.historico.values_list("status", flat=True)) == ["aguardando"]


def test_manual_tambem_vale_para_agendado(db, cenario):
    usar_entrada("manual")
    p = criar_pedido(cenario.dados(agendar_para="2026-11-18T18:15:00-03:00"), agora=cenario.fechada)
    assert p.status == "aguardando"
    assert p.agendado_para is not None  # o horário escolhido continua guardado


def test_cliente_ve_que_esta_aguardando_a_loja(client, db):
    cliente = Cliente.objects.create(nome="Ana", telefone="81988887777")
    pedido = Pedido.objects.create(
        chave=uuid4(), numero=1, dia=date(2026, 11, 18), origem="site", tipo="retirada", status="aguardando",
        cliente=cliente, nome="Ana", telefone=cliente.telefone, subtotal=Decimal("20"),
        total=Decimal("20"), forma_pagamento_codigo="pix", forma_pagamento_nome="Pix",
    )
    r = client.get(reverse("pedidos:status", args=[pedido.codigo]))
    assert "Aguardando a loja confirmar" in r.content.decode()


# ---- tela do Dono ----------------------------------------------------------------------
DADOS_LOJA = {
    "nome": "Brasa Burguer", "slogan": "", "endereco": "Rua A, 1", "whatsapp": "(81) 99000-1234",
    "instagram": "brasaburguer", "chave_pix": "123", "pix_titular": "Ana", "pix_banco": "Nubank",
    "prazo": "15 - 80 min", "pedido_minimo": "10,00", "vias_padrao": "1", "entrada_pedidos": "auto",
}


@pytest.fixture
def client_dono(db, client):
    from django.contrib.auth.models import Group, User

    dono = User.objects.create_user("ana", password="senha-certa-123")
    dono.groups.add(Group.objects.get_or_create(name="Dono")[0])
    client.force_login(dono)
    return client


def test_tela_da_loja_mostra_as_duas_opcoes(client_dono):
    html = client_dono.get(reverse("gerenciar:loja")).content.decode()
    assert "Automática" in html and "Manual" in html
    marcados = re.findall(r'<input[^>]*name="entrada_pedidos"[^>]*checked[^>]*>', html)
    assert len(marcados) == 1 and 'value="auto"' in marcados[0]


def test_dono_muda_para_manual(client_dono):
    r = client_dono.post(reverse("gerenciar:loja"), {**DADOS_LOJA, "entrada_pedidos": "manual"})
    assert r.status_code == 302
    assert Configuracao.atual().entrada_pedidos == "manual"


def test_valor_inventado_e_recusado(client_dono):
    r = client_dono.post(reverse("gerenciar:loja"), {**DADOS_LOJA, "entrada_pedidos": "qualquer"})
    assert r.status_code == 200
    assert Configuracao.atual().entrada_pedidos == "auto"
