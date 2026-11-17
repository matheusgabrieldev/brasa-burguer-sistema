"""Tela de checkout (GET /checkout/) e envio do pedido (POST /checkout/enviar/)."""
import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.cache import cache
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from cardapio.models import Categoria, Produto
from clientes.models import Dispositivo
from clientes.servicos import COOKIE_DISPOSITIVO, lembrar
from loja.models import Configuracao
from pedidos.models import Pedido

LIMITE_MSG = "Muitos pedidos em pouco tempo. Aguarde alguns minutos ou fale com a loja no WhatsApp."
URL = "/checkout/enviar/"


@pytest.fixture(autouse=True)
def limpar_cache():
    """Cada teste começa com o cache vazio."""
    cache.clear()
    yield
    cache.clear()


def modo(valor):
    c = Configuracao.atual()
    c.modo_loja = valor
    c.save()


@pytest.fixture
def aberta(cenario):
    modo("aberta")
    return cenario


def enviar(client, dados, **extra):
    return client.post(URL, data=json.dumps(dados), content_type="application/json", **extra)


# ---- tela ---------------------------------------------------------------------------
def test_checkout_abre(client, aberta):
    r = client.get("/checkout/")
    assert r.status_code == 200
    html = r.content.decode()
    assert "Enviar pedido" in html
    assert "Paratibe" in html and "R$ 5,00" in html  # bairro com a taxa ao lado
    assert 'id="dados-checkout"' in html


def test_checkout_lista_so_formas_do_tipo(client, aberta):
    f = aberta.formas["credito"]
    f.aceita_delivery = False
    f.save()
    dados = client.get("/checkout/").context["dados_js"]
    assert "delivery" not in dados["formas"]["credito"]["tipos"]
    assert dados["formas"]["credito"]["tipos"] == ["retirada", "local"]
    assert dados["formas"]["pix"]["tipos"] == ["delivery", "retirada", "local"]
    assert dados["formas"]["credito"]["pct"] == "4.00"
    html = client.get("/checkout/").content.decode()
    assert 'data-tipos="retirada local"' in html  # o JS esconde no delivery


def test_usar_cadastro_anterior_so_do_proprio_aparelho(client, aberta):
    # aparelho A salvou endereço; cliente sem cookie (ou com cookie de B) não vê
    token_a = lembrar(None, "Ana", "81988887777", aberta.bairro, "Rua Secreta", "77", "")
    token_b = lembrar(None, "Bia", "81977776666", aberta.bairro, "Rua da Bia", "1", "")

    assert "Rua Secreta" not in client.get("/checkout/").content.decode()

    client.cookies[COOKIE_DISPOSITIVO] = token_b
    html = client.get("/checkout/").content.decode()
    assert "Rua Secreta" not in html and "Rua da Bia" in html

    client.cookies[COOKIE_DISPOSITIVO] = token_a
    html = client.get("/checkout/").content.decode()
    assert "Rua Secreta" in html and "Rua da Bia" not in html
    assert "Usar este" in html and "Outro endereço" in html


def test_cookie_falso_nao_mostra_nada(client, aberta):
    lembrar(None, "Ana", "81988887777", aberta.bairro, "Rua Secreta", "77", "")
    client.cookies[COOKIE_DISPOSITIVO] = "inventado"
    assert "Rua Secreta" not in client.get("/checkout/").content.decode()


def test_complemente_mostra_so_sugeridos_disponiveis(client, aberta):
    cat = aberta.burger.categoria
    oculta = Categoria.objects.create(nome="Oculta", visivel=False)
    hoje = timezone.localdate()
    criar = lambda slug, **kw: Produto.objects.create(categoria=kw.pop("categoria", cat), slug=slug, nome=slug.upper(), preco=Decimal("5"), **kw)
    criar("sugerido-ok", sugerir_no_checkout=True)
    criar("nao-sugerido")
    criar("sugerido-oculto", sugerir_no_checkout=True, visivel=False)
    criar("sugerido-esgotado", sugerir_no_checkout=True, esgotado_em=hoje)
    criar("sugerido-esgotado-ontem", sugerir_no_checkout=True, esgotado_em=hoje - timedelta(days=1))
    criar("sugerido-cat-oculta", sugerir_no_checkout=True, categoria=oculta)
    for i in range(8):
        criar(f"extra-{i}", sugerir_no_checkout=True)

    sugestoes = list(client.get("/checkout/").context["sugestoes"])
    slugs = {p.slug for p in sugestoes}
    assert len(sugestoes) == 6
    assert "sugerido-ok" in slugs and "sugerido-esgotado-ontem" in slugs
    assert not slugs & {"nao-sugerido", "sugerido-oculto", "sugerido-esgotado", "sugerido-cat-oculta"}
    html = client.get("/checkout/").content.decode()
    assert "Complemente seu pedido" in html
    assert reverse("produto_modal", args=["sugerido-ok"]) in html  # abre o mesmo modal do cardápio


def test_sem_sugestoes_nao_mostra_secao(client, aberta):
    assert "Complemente seu pedido" not in client.get("/checkout/").content.decode()


def test_loja_aberta_nao_mostra_horario(client, aberta):
    html = client.get("/checkout/").content.decode()
    assert 'id="horario"' not in html


def test_loja_fechada_agendavel_mostra_horarios(client, cenario, monkeypatch):
    from pedidos import views_checkout

    monkeypatch.setattr(views_checkout.timezone, "now", lambda: cenario.fechada)
    html = client.get("/checkout/").content.decode()
    assert 'id="horario"' in html
    assert 'value="2026-11-18T18:15:00-03:00"' in html and 'value="2026-11-18T22:30:00-03:00"' in html


def test_loja_forcada_fechada_avisa_e_trava_envio(client, cenario):
    modo("fechada")
    r = client.get("/checkout/")
    html = r.content.decode()
    assert "A loja está fechada no momento." in html
    assert 'id="horario"' not in html
    assert r.context["fechada_sem_horario"] is True
    assert 'id="enviar"' in html and "disabled" in html.split('id="enviar"')[1].split(">")[0]


# ---- envio ---------------------------------------------------------------------------
def test_enviar_cria_pedido_e_devolve_url(client, aberta):
    r = enviar(client, aberta.dados())
    assert r.status_code == 201
    corpo = r.json()
    p = Pedido.objects.get()
    assert corpo == {"codigo": p.codigo, "url": f"/pedido/{p.codigo}/"}
    assert p.total == Decimal("57.20")


def test_mesma_chave_devolve_o_mesmo_pedido(client, aberta):
    dados = aberta.dados()
    a, b = enviar(client, dados), enviar(client, dados)
    assert a.json() == b.json() and Pedido.objects.count() == 1


def test_enviar_com_erro_devolve_campo(client, aberta):
    r = enviar(client, aberta.dados(bairro_id=""))
    assert r.status_code == 400
    assert r.json() == {"erro": "Escolha o bairro de entrega.", "campo": "bairro"}
    assert not Pedido.objects.exists()


@pytest.mark.parametrize("corpo", ["isso não é json", "[1, 2]", ""])
def test_json_malformado_da_400(client, aberta, corpo):
    r = client.post(URL, data=corpo, content_type="application/json")
    assert r.status_code == 400 and "erro" in r.json()


def test_enviar_so_aceita_post(client, aberta):
    assert client.get(URL).status_code == 405


def test_loja_abriu_com_horario_pede_recarregar(client, aberta):
    r = enviar(client, aberta.dados(agendar_para="2026-11-18T18:15:00-03:00"))
    assert r.status_code == 400 and r.json()["campo"] == "horario"


def test_loja_forcada_fechada_recusa_envio(client, cenario):
    modo("fechada")
    r = enviar(client, cenario.dados())
    assert r.status_code == 400
    assert r.json() == {"erro": "A loja está fechada no momento.", "campo": "horario"}


def test_lembrar_de_mim_seta_cookie_httponly(client, aberta):
    r = enviar(client, aberta.dados(lembrar=True, referencia="Perto da praça"))
    assert r.status_code == 201
    cookie = r.cookies[COOKIE_DISPOSITIVO]
    assert cookie["httponly"] and cookie["samesite"] == "Lax"
    assert cookie["max-age"] == 60 * 60 * 24 * 365
    assert cookie["secure"]  # DEBUG desligado nos testes
    disp = Dispositivo.objects.get()
    assert (disp.nome, disp.telefone) == ("Ana", "81988887777")
    end = disp.enderecos.get()
    assert (end.bairro, end.rua, end.numero, end.referencia) == (aberta.bairro, "Rua das Flores", "505", "Perto da praça")
    # na próxima visita, este aparelho vê o endereço
    assert "Rua das Flores" in client.get("/checkout/").content.decode()


def test_cookie_sem_secure_em_desenvolvimento(client, aberta, settings):
    settings.DEBUG = True
    r = enviar(client, aberta.dados(lembrar=True))
    assert not r.cookies[COOKIE_DISPOSITIVO]["secure"]


def test_lembrar_reaproveita_o_aparelho(client, aberta):
    token = lembrar(None, "Ana", "81988887777", aberta.bairro, "Rua Velha", "1", "")
    client.cookies[COOKIE_DISPOSITIVO] = token
    enviar(client, aberta.dados(lembrar=True))
    disp = Dispositivo.objects.get()
    assert disp.enderecos.count() == 2


def test_sem_lembrar_nao_cria_aparelho_nem_apaga(client, aberta):
    r = enviar(client, aberta.dados(lembrar=False))
    assert COOKIE_DISPOSITIVO not in r.cookies
    assert not Dispositivo.objects.exists()

    token = lembrar(None, "Ana", "81988887777", aberta.bairro, "Rua Velha", "1", "")
    client.cookies[COOKIE_DISPOSITIVO] = token
    r = enviar(client, aberta.dados(lembrar=False))
    assert COOKIE_DISPOSITIVO not in r.cookies
    assert Dispositivo.objects.get().enderecos.count() == 1


def test_lembrar_na_retirada_guarda_so_nome_e_telefone(client, aberta):
    r = enviar(client, aberta.dados(tipo="retirada", bairro_id="", rua="", numero="", lembrar=True))
    assert r.status_code == 201
    disp = Dispositivo.objects.get()
    assert disp.nome == "Ana" and not disp.enderecos.exists()


def test_erro_nao_lembra(client, aberta):
    r = enviar(client, aberta.dados(bairro_id="", lembrar=True))
    assert r.status_code == 400 and COOKIE_DISPOSITIVO not in r.cookies
    assert not Dispositivo.objects.exists()


# ---- freio contra robô ------------------------------------------------------------------
# Só um limite, bem folgado: 30 pedidos criados em 10 min pela mesma rede (IP).
# Telefone não tem limite (cliente indeciso pede quantas vezes quiser) e Dono logado não conta.
@pytest.fixture
def freio_3(monkeypatch):
    """Limite 3 nos testes, para não precisar criar 30 pedidos."""
    from pedidos import limite

    monkeypatch.setattr(limite, "MAXIMO", 3)


def test_freio_e_30_pedidos_em_10_minutos():
    from pedidos import limite

    assert (limite.MAXIMO, limite.JANELA) == (30, timedelta(minutes=10))


def test_mesmo_telefone_pode_pedir_varias_vezes(client, aberta):
    for i in range(8):
        assert enviar(client, aberta.dados(), REMOTE_ADDR=f"10.0.0.{i}").status_code == 201
    assert Pedido.objects.count() == 8


def test_freio_por_ip(client, aberta, freio_3):
    for i in range(3):
        assert enviar(client, aberta.dados(telefone=f"8199999000{i}")).status_code == 201
    r = enviar(client, aberta.dados(telefone="81999990009"))
    assert r.status_code == 429 and r.json() == {"erro": LIMITE_MSG}
    assert Pedido.objects.count() == 3
    # outra rede continua livre, e o número do dia não pulou com o pedido recusado
    assert enviar(client, aberta.dados(), REMOTE_ADDR="10.9.9.9").status_code == 201
    assert Pedido.objects.order_by("-numero").first().numero == 4


def test_freio_libera_depois_de_10_minutos(client, aberta, freio_3):
    for i in range(3):
        enviar(client, aberta.dados(telefone=f"8199999000{i}"))
    assert enviar(client, aberta.dados()).status_code == 429
    Pedido.objects.update(criado_em=timezone.now() - timedelta(minutes=11))
    assert enviar(client, aberta.dados()).status_code == 201


def test_erros_de_regra_nao_contam(client, aberta, freio_3):
    for _ in range(5):
        assert enviar(client, aberta.dados(bairro_id="")).status_code == 400
    assert enviar(client, aberta.dados()).status_code == 201


def test_reenvio_com_mesma_chave_passa_mesmo_no_limite(client, aberta, freio_3):
    dados = aberta.dados()
    assert enviar(client, dados).status_code == 201
    for i in range(2):
        enviar(client, aberta.dados(telefone=f"8199999000{i}"))
    r = enviar(client, dados)  # a internet caiu e o cliente tocou de novo
    assert r.status_code == 201 and Pedido.objects.count() == 3


def test_dono_logado_nao_tem_freio(client, aberta, freio_3):
    from django.contrib.auth.models import Group, User

    dono = User.objects.create_user("ana", password="senha-certa-123")
    dono.groups.add(Group.objects.get_or_create(name="Dono")[0])
    client.force_login(dono)
    for i in range(5):
        assert enviar(client, aberta.dados(telefone=f"8199999000{i}")).status_code == 201


def test_ip_guardado_so_como_codigo(client, aberta):
    enviar(client, aberta.dados(), REMOTE_ADDR="10.1.2.3")
    guardado = Pedido.objects.get().ip_hash
    assert guardado and "10.1.2.3" not in guardado and len(guardado) == 64


def test_x_forwarded_for_so_com_configuracao(client, aberta, settings, freio_3):
    # sem confiar no cabeçalho: todos vêm do mesmo REMOTE_ADDR
    for i in range(3):
        enviar(client, aberta.dados(telefone=f"8199999000{i}"), HTTP_X_FORWARDED_FOR=f"1.1.1.{i}")
    assert enviar(client, aberta.dados(telefone="81999990009"), HTTP_X_FORWARDED_FOR="1.1.1.9").status_code == 429

    settings.CONFIAR_X_FORWARDED_FOR = True
    for i in range(4):
        r = enviar(client, aberta.dados(telefone=f"8199999100{i}"), HTTP_X_FORWARDED_FOR=f"2.2.2.{i}, 10.0.0.1")
        assert r.status_code == 201


# ---- segurança -----------------------------------------------------------------------
def test_enviar_exige_csrf(cenario):
    modo("aberta")
    c = Client(enforce_csrf_checks=True)
    r = c.post(URL, data=json.dumps(cenario.dados()), content_type="application/json")
    assert r.status_code == 403
    assert not Pedido.objects.exists()
    c.get("/checkout/")  # a tela entrega o token
    token = c.cookies["csrftoken"].value
    r = c.post(URL, data=json.dumps(cenario.dados()), content_type="application/json", HTTP_X_CSRFTOKEN=token)
    assert r.status_code == 201


# ---- acompanhar (provisório; a Task 7 troca) ----------------------------------------------
def test_acompanhar_mostra_numero(client, aberta):
    codigo = enviar(client, aberta.dados()).json()["codigo"]
    r = client.get(f"/pedido/{codigo}/")
    assert r.status_code == 200 and "Pedido nº 1" in r.content.decode()


def test_acompanhar_codigo_errado_da_404(client, db):
    assert client.get("/pedido/naoexiste/").status_code == 404
