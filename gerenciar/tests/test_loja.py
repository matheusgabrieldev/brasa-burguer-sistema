"""Configuração da loja pelo Dono: modo, dados, horários, bairros e pagamentos."""
from datetime import time
from decimal import Decimal

import pytest
from django.urls import reverse

from loja.horario import status_loja
from loja.models import Bairro, Configuracao, FormaPagamento, Horario

DADOS_LOJA = {
    "nome": "Brasa Burguer", "slogan": "", "endereco": "Rua A, 1", "whatsapp": "(81) 99000-1234",
    "instagram": "brasaburguer", "chave_pix": "123", "pix_titular": "Ana", "pix_banco": "Nubank",
    "prazo": "15 - 80 min", "pedido_minimo": "10,00", "vias_padrao": "1", "entrada_pedidos": "auto",
}


def post_loja(client, **mudancas):
    return client.post(reverse("gerenciar:loja"), {**DADOS_LOJA, **mudancas})


def test_pagina_loja_mostra_status(client_dono, horarios):
    r = client_dono.get(reverse("gerenciar:loja"))
    assert r.status_code == 200
    assert status_loja().texto in r.content.decode()


def test_dono_forca_loja_fechada(client_dono, horarios):
    r = client_dono.post(reverse("gerenciar:loja"), {"modo": "fechada"})
    assert r.status_code == 302
    assert status_loja().texto == "Fechado no momento"


def test_modo_invalido_e_recusado(client_dono):
    client_dono.post(reverse("gerenciar:loja"), {"modo": "xyz"})
    assert Configuracao.atual().modo_loja == "auto"


def test_whatsapp_aceita_formatado_e_guarda_digitos(client_dono):
    assert post_loja(client_dono).status_code == 302
    assert Configuracao.atual().whatsapp == "5581990001234"


@pytest.mark.parametrize("digitado", ["81990001234", "+55 81 99000-1234", "5581990001234"])
def test_whatsapp_outros_formatos(client_dono, digitado):
    post_loja(client_dono, whatsapp=digitado)
    assert Configuracao.atual().whatsapp == "5581990001234"


@pytest.mark.parametrize("digitado", ["12345", "(81) 8789-80", "abc"])
def test_whatsapp_invalido_da_erro(client_dono, digitado):
    r = post_loja(client_dono, whatsapp=digitado)
    assert r.status_code == 200 and "WhatsApp" in r.content.decode()
    assert Configuracao.atual().whatsapp != "5581990001234"


def test_pedido_minimo_em_reais_e_pix(client_dono):
    post_loja(client_dono, pedido_minimo="12,50", pix_titular="Ana Silva")
    cfg = Configuracao.atual()
    assert cfg.pedido_minimo == Decimal("12.50") and cfg.pix_titular == "Ana Silva"


def test_pedido_minimo_negativo_da_erro(client_dono):
    assert post_loja(client_dono, pedido_minimo="-5").status_code == 200


def dados_horarios(**mudancas):
    d = {"form-TOTAL_FORMS": "7", "form-INITIAL_FORMS": "7", "form-MIN_NUM_FORMS": "0", "form-MAX_NUM_FORMS": "1000"}
    for h in Horario.objects.order_by("dia_semana"):
        i = h.dia_semana
        d[f"form-{i}-id"] = h.pk
        d[f"form-{i}-abre"] = f"{h.abre:%H:%M}"
        d[f"form-{i}-fecha"] = f"{h.fecha:%H:%M}"
        if h.ativo:
            d[f"form-{i}-ativo"] = "on"
    d.update(mudancas)
    return d


def test_horarios_mostra_7_dias(client_dono, horarios):
    r = client_dono.get(reverse("gerenciar:horarios"))
    assert len(r.context["formset"].forms) == 7


def test_horarios_cria_dias_que_faltam(client_dono, db):
    client_dono.get(reverse("gerenciar:horarios"))
    assert Horario.objects.count() == 7


def test_horario_altera(client_dono, horarios):
    r = client_dono.post(reverse("gerenciar:horarios"), dados_horarios(**{"form-2-fecha": "23:00"}))
    assert r.status_code == 302
    assert Horario.objects.get(dia_semana=2).fecha == time(23, 0)


@pytest.mark.parametrize("fecha", ["17:00", "18:15"])
def test_horario_fecha_antes_ou_igual_abrir_da_erro(client_dono, horarios, fecha):
    r = client_dono.post(reverse("gerenciar:horarios"), dados_horarios(**{"form-2-fecha": fecha}))
    assert r.status_code == 200
    assert "O horário de fechar precisa ser depois do de abrir." in r.content.decode()
    assert Horario.objects.get(dia_semana=2).fecha == time(22, 30)


def test_horario_dia_fechado_ignora_horas_erradas(client_dono, horarios):
    d = dados_horarios(**{"form-0-abre": "20:00", "form-0-fecha": "10:00"})
    assert client_dono.post(reverse("gerenciar:horarios"), d).status_code == 302


def test_bairro_novo_e_taxa_em_reais(client_dono):
    r = client_dono.post(reverse("gerenciar:bairros"), {"nome": "Paratibe", "taxa": "5,00", "ativo": "on"})
    assert r.status_code == 302
    b = Bairro.objects.get(nome="Paratibe")
    assert b.taxa == Decimal("5.00") and b.ativo


def test_bairro_taxa_zero_vale(client_dono):
    client_dono.post(reverse("gerenciar:bairros"), {"nome": "Perto", "taxa": "0"})
    assert Bairro.objects.get(nome="Perto").taxa == Decimal("0.00")


def test_bairro_taxa_negativa_da_erro(client_dono):
    r = client_dono.post(reverse("gerenciar:bairros"), {"nome": "X", "taxa": "-3"})
    assert r.status_code == 200 and not Bairro.objects.exists()


def test_bairro_nome_repetido_da_erro(client_dono):
    Bairro.objects.create(nome="Paratibe", taxa=5)
    r = client_dono.post(reverse("gerenciar:bairros"), {"nome": "paratibe", "taxa": "4"})
    assert r.status_code == 200 and "Já existe um bairro com esse nome." in r.content.decode()
    assert Bairro.objects.count() == 1


def test_bairro_edita_taxa_e_ativo(client_dono):
    b = Bairro.objects.create(nome="Paratibe", taxa=5)
    r = client_dono.post(reverse("gerenciar:bairro_editar", args=[b.pk]), {"nome": "Paratibe", "taxa": "6,50"})
    assert r.status_code == 302
    b.refresh_from_db()
    assert b.taxa == Decimal("6.50") and not b.ativo


def test_bairro_edicao_invalida_mostra_erro(client_dono):
    b = Bairro.objects.create(nome="Paratibe", taxa=5)
    r = client_dono.post(reverse("gerenciar:bairro_editar", args=[b.pk]), {"nome": "Paratibe", "taxa": "abc"})
    assert r.status_code == 200
    b.refresh_from_db()
    assert b.taxa == Decimal("5.00")


def test_bairro_excluir_pede_confirmacao_e_apaga(client_dono):
    b = Bairro.objects.create(nome="Paratibe", taxa=5)
    url = reverse("gerenciar:bairro_excluir", args=[b.pk])
    assert client_dono.get(url).status_code == 200 and Bairro.objects.exists()
    assert client_dono.post(url).status_code == 302
    assert not Bairro.objects.exists()


def dados_pagamentos(**mudancas):
    d = {"form-TOTAL_FORMS": "2", "form-INITIAL_FORMS": "2", "form-MIN_NUM_FORMS": "0", "form-MAX_NUM_FORMS": "1000"}
    for i, f in enumerate(FormaPagamento.objects.order_by("ordem")):
        d[f"form-{i}-id"] = f.pk
        d[f"form-{i}-acrescimo_pct"] = str(f.acrescimo_pct)
        for campo in ("aceita_delivery", "aceita_retirada", "aceita_local"):
            if getattr(f, campo):
                d[f"form-{i}-{campo}"] = "on"
    d.update(mudancas)
    return d


@pytest.fixture
def formas(db):
    FormaPagamento.objects.create(codigo="dinheiro", nome="Dinheiro", ordem=1)
    FormaPagamento.objects.create(codigo="credito", nome="Crédito", ordem=2, acrescimo_pct=4)


def test_desligar_dinheiro_no_delivery(client_dono, formas):
    d = dados_pagamentos()
    del d["form-0-aceita_delivery"]
    assert client_dono.post(reverse("gerenciar:pagamentos"), d).status_code == 302
    f = FormaPagamento.objects.get(codigo="dinheiro")
    assert not f.aceita_delivery and f.aceita_retirada and f.aceita_local


@pytest.mark.parametrize("digitado,esperado", [("4", "4.00"), ("4,5", "4.50"), ("1.5", "1.50"), ("0", "0.00")])
def test_acrescimo_aceita_formatos(client_dono, formas, digitado, esperado):
    client_dono.post(reverse("gerenciar:pagamentos"), dados_pagamentos(**{"form-1-acrescimo_pct": digitado}))
    assert FormaPagamento.objects.get(codigo="credito").acrescimo_pct == Decimal(esperado)


def test_acrescimo_negativo_da_erro(client_dono, formas):
    r = client_dono.post(reverse("gerenciar:pagamentos"), dados_pagamentos(**{"form-1-acrescimo_pct": "-2"}))
    assert r.status_code == 200
    assert FormaPagamento.objects.get(codigo="credito").acrescimo_pct == Decimal("4.00")


def test_acrescimo_absurdo_da_erro(client_dono, formas):
    r = client_dono.post(reverse("gerenciar:pagamentos"), dados_pagamentos(**{"form-1-acrescimo_pct": "150"}))
    assert r.status_code == 200
