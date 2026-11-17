import json
from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest
from django.test import Client
from django.utils import timezone

from cardapio.models import Categoria, Produto
from cardapio.templatetags.brl import brl
from loja.models import Bairro, Configuracao, Horario


@pytest.fixture
def cardapio_basico(categoria):
    """Um produto visível, um oculto, um esgotado hoje e uma categoria oculta."""
    Produto.objects.create(categoria=categoria, slug="visivel", nome="Produto Visivel", preco=Decimal("15.00"), mais_pedido=True)
    Produto.objects.create(categoria=categoria, slug="oculto", nome="Produto Oculto", preco=Decimal("15.00"), visivel=False)
    Produto.objects.create(categoria=categoria, slug="acabou", nome="Produto Acabou", preco=Decimal("15.00"), esgotado_em=timezone.localdate())
    escondida = Categoria.objects.create(nome="Categoria Escondida", visivel=False)
    Produto.objects.create(categoria=escondida, slug="na-escondida", nome="Produto Na Escondida", preco=Decimal("9.00"))
    Bairro.objects.create(nome="Bairro Ativo", taxa=Decimal("5.00"))
    Bairro.objects.create(nome="Bairro Inativo", taxa=Decimal("7.00"), ativo=False)


@pytest.fixture
def loja_fechada(db):
    c = Configuracao.atual()
    c.modo_loja = "fechada"
    c.save()


def post_json(client, dados):
    return client.post("/sacola/validar/", data=json.dumps(dados), content_type="application/json")


def test_cardapio_mostra_produtos_visiveis_e_esconde_ocultos(client, cardapio_basico):
    html = client.get("/").content.decode()
    assert "Produto Visivel" in html
    assert "Mais pedido" in html
    assert "Produto Oculto" not in html
    assert "Categoria Escondida" not in html and "Produto Na Escondida" not in html
    # bairros: só os ativos, com taxa
    assert "Bairro Ativo" in html and "R$ 5,00" in html
    assert "Bairro Inativo" not in html


def test_cardapio_marca_turno_e_aberta_no_body(client, cardapio_basico):
    html = client.get("/").content.decode()
    assert 'data-turno="' in html and 'data-aberta="' in html


def test_produto_esgotado_aparece_com_selo_e_sem_botao(client, cardapio_basico):
    html = client.get("/").content.decode()
    assert "Produto Acabou" in html and "Esgotado" in html
    assert "/produto/acabou/" not in html
    assert "/produto/visivel/" in html


def test_status_fechado_aparece_no_topo(client, cardapio_basico, loja_fechada):
    assert "Fechado no momento" in client.get("/").content.decode()


def test_modal_tem_contador_obrigatorio(client, burger):
    html = client.get(f"/produto/{burger.slug}/").content.decode()
    assert "0/1 OBRIGATÓRIO" in html
    assert 'maxlength="140"' in html


def test_sem_abertura_futura_mostra_loja_fechada(client, burger, ponto, loja_fechada):
    # forçada a fechar: não dá para agendar
    html = client.get(f"/produto/{burger.slug}/").content.decode()
    assert "Loja fechada" in html
    assert 'data-agendavel="0"' in client.get("/").content.decode()


def test_loja_fechada_agendavel_deixa_adicionar(client, burger, ponto, db, monkeypatch):
    # loja no horário normal, mas fechada agora, com abertura prevista
    agora = timezone.make_aware(datetime(2026, 11, 11, 10, 0))  # quarta, 10:00
    Horario.objects.all().delete()
    Horario.objects.create(dia_semana=2, abre=time(18, 15), fecha=time(23, 0))
    monkeypatch.setattr(timezone, "localtime", lambda v=None, tz=None: agora if v is None else v)
    html = client.get(f"/produto/{burger.slug}/").content.decode()
    assert "Loja fechada" not in html
    assert 'id="btn-add"' in html
    pagina = client.get("/").content.decode()
    assert 'data-agendavel="1"' in pagina
    assert 'data-agendamento-texto="Pedido agendado para hoje, a partir de 18:15"' in pagina


def test_modal_de_produto_oculto_da_404(client, cardapio_basico):
    assert client.get("/produto/oculto/").status_code == 404
    assert client.get("/produto/na-escondida/").status_code == 404
    assert client.get("/produto/nao-existe/").status_code == 404


def test_validar_sacola_recalcula_e_remove_esgotado(client, burger, batata, ponto):
    batata.esgotado_em = timezone.localdate()
    batata.save()
    r = post_json(
        client,
        {
            "itens": [
                {"produto_id": burger.id, "quantidade": 2, "opcoes": {str(ponto.id): 1}, "preco": "0.01"},
                {"produto_id": batata.id, "quantidade": 1, "opcoes": {}},
            ]
        },
    )
    assert r.status_code == 200
    dados = r.json()
    assert dados["subtotal"] == "40.00"
    assert [i["indice"] for i in dados["itens"]] == [0]
    assert dados["itens"][0]["preco_unitario"] == "20.00"
    assert dados["itens"][0]["total"] == "40.00"
    assert dados["itens"][0]["opcoes"] == [{"grupo": "Escolha o ponto da carne", "nome": "Ao ponto", "qtd": 1, "preco": "0.00"}]
    assert dados["removidos"][0]["indice"] == 1
    assert "Batata" in dados["removidos"][0]["motivo"]


def test_validar_sacola_item_malformado_vai_para_removidos(client, burger):
    r = post_json(client, {"itens": ["lixo", {"produto_id": "abc"}, {"produto_id": burger.id, "opcoes": [1, 2]}]})
    assert r.status_code == 200
    assert [x["indice"] for x in r.json()["removidos"]] == [0, 1, 2]
    assert r.json()["itens"] == []


@pytest.mark.parametrize("corpo", ["nao e json", json.dumps({"x": 1}), json.dumps({"itens": "abc"}), json.dumps([1])])
def test_validar_sacola_entrada_ruim_da_400(client, corpo):
    r = client.post("/sacola/validar/", data=corpo, content_type="application/json")
    assert r.status_code == 400
    assert "erro" in r.json()


def test_validar_sacola_limita_itens(client, burger):
    r = post_json(client, {"itens": [{"produto_id": burger.id}] * 51})
    assert r.status_code == 400


def test_validar_sacola_exige_post_e_csrf(burger):
    c = Client(enforce_csrf_checks=True)
    assert c.get("/sacola/validar/").status_code == 405
    r = c.post("/sacola/validar/", data="{}", content_type="application/json")
    assert r.status_code == 403


def test_brl():
    assert brl(Decimal("1234.5")) == "R$ 1.234,50"
    assert brl(None) == "R$ 0,00"


def test_pagina_marca_esgotado_junto_ao_produto(client, cardapio_basico):
    """O selo de esgotado fica no bloco do produto certo (e o disponível não ganha selo)."""
    html = client.get("/").content.decode()
    esgotados = [b for b in html.split('<div class="prod esgotado"')[1:]]
    assert len(esgotados) == 1
    trecho = esgotados[0].split("</span>\n    </span>")[0]
    assert 'badge-esgotado">Esgotado' in trecho and "Produto Acabou" in trecho
    assert "Produto Visivel" not in trecho


def test_modal_opcao_esgotada_hoje_mostra_esgotado_e_nao_e_selecionavel(client, burger, bacon):
    bacon.esgotado_em = timezone.localdate()
    bacon.save()
    html = client.get(f"/produto/{burger.slug}/").content.decode()
    assert "opt esgotada" in html and "Esgotado" in html
    assert f'data-opcao="{bacon.id}"' not in html


@pytest.mark.parametrize("capacidade_parcial", [False, True])
def test_modal_indisponivel_por_grupo_obrigatorio_e_recupera(
    client, burger, ponto, bacon, grupo_varias, monkeypatch, capacidade_parcial,
):
    from cardapio.models import Opcao

    hoje = date(2026, 11, 10)
    loja = Configuracao.atual()
    loja.modo_loja = "aberta"
    loja.save()
    if capacidade_parcial:
        grupo_varias.obrigatorio = True
        grupo_varias.minimo = grupo_varias.maximo = 4
        grupo_varias.save()
        Opcao.objects.create(grupo=grupo_varias, nome="Ovo", qtd_maxima=1, esgotado_em=hoje)
        nome_grupo = grupo_varias.nome
    else:
        ponto.esgotado_em = hoje
        ponto.save()
        nome_grupo = ponto.grupo.nome
    monkeypatch.setattr(timezone, "localdate", lambda: hoje)
    html = client.get(f"/produto/{burger.slug}/").content.decode()
    assert "Indisponível no momento" in html
    assert nome_grupo in html
    assert 'disabled>Indisponível no momento</button>' in html
    assert 'id="btn-add"' not in html
    monkeypatch.setattr(timezone, "localdate", lambda: hoje + timedelta(days=1))
    html = client.get(f"/produto/{burger.slug}/").content.decode()
    assert "Indisponível no momento" not in html
    assert 'id="btn-add"' in html


def test_modal_grupo_opcional_esgotado_permite_adicionar(client, burger, ponto, bacon):
    loja = Configuracao.atual()
    loja.modo_loja = "aberta"
    loja.save()
    bacon.esgotado_em = timezone.localdate()
    bacon.save()
    html = client.get(f"/produto/{burger.slug}/").content.decode()
    assert "Indisponível no momento" not in html
    assert 'id="btn-add"' in html
