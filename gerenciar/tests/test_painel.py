"""Tela do painel de pedidos: quem vê o quê, colunas, busca, filtros e a consulta a cada 5 s."""
import json
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from pedidos.agendamento import horarios_agendamento
from pedidos.models import Pedido
from pedidos.painel_consultas import versao_painel
from pedidos.servicos import criar_pedido

PAINEL = "/gerenciar/"
COLUNAS = "/gerenciar/pedidos/colunas/"


@pytest.fixture
def relogio(monkeypatch, cenario):
    """Congela o "agora" das views na quarta 11/11 às 20:00 (loja aberta). Devolve um ajustador."""
    estado = {"agora": cenario.aberta}
    monkeypatch.setattr(timezone, "now", lambda: estado["agora"])

    def mudar(**delta):
        estado["agora"] = cenario.aberta + timedelta(**delta)
    return mudar


def fazer(cenario, status="preparo", **mudar):
    """Pedido de hoje com o status forçado (sem passar por cada etapa)."""
    p = criar_pedido(cenario.dados(**mudar), agora=cenario.aberta)
    Pedido.objects.filter(pk=p.pk).update(status=status, criado_em=cenario.aberta)
    p.refresh_from_db()
    return p


def test_dono_e_equipe_caem_no_painel(client, relogio, usuario_dono, usuario_equipe):
    for usuario in (usuario_dono, usuario_equipe):
        client.force_login(usuario)
        r = client.get(PAINEL)
        assert r.status_code == 200
        assert b'id="colunas"' in r.content


def test_equipe_nao_recebe_total_do_dia(client_equipe, relogio, cenario):
    fazer(cenario)
    r = client_equipe.get(PAINEL)
    assert b'id="total-dia"' not in r.content
    # nem na atualização das colunas
    assert b'id="total-dia"' not in client_equipe.get(COLUNAS).content


def test_dono_recebe_total_do_dia(client, usuario_dono, relogio, cenario):
    client.force_login(usuario_dono)
    p = fazer(cenario)
    r = client.get(PAINEL)
    html = r.content.decode()
    assert 'id="total-dia"' in html
    bloco = html.split('id="total-dia"')[1].split("</div>")[0]
    assert "1 pedido" in bloco
    assert f"{p.total:.2f}".replace(".", ",") in bloco
    # na consulta de 5 s o total vem junto, para trocar fora das colunas
    assert b'id="total-dia" class="painel-total" hx-swap-oob="true"' in client.get(COLUNAS).content


def test_equipe_ve_valor_do_pedido(client_equipe, relogio, cenario):
    p = fazer(cenario)
    html = client_equipe.get(PAINEL).content.decode()
    assert f"#{p.numero}" in html
    assert f"{p.total:.2f}".replace(".", ",") in html


def test_colunas_204_quando_versao_igual(client_equipe, relogio, cenario):
    fazer(cenario)
    versao = versao_painel(timezone.now())
    r = client_equipe.get(COLUNAS, {"v": versao})
    assert r.status_code == 204


def test_colunas_200_quando_versao_diferente(client_equipe, relogio, cenario):
    fazer(cenario)
    r = client_equipe.get(COLUNAS, {"v": "velha"})
    assert r.status_code == 200
    html = r.content.decode()
    assert f'data-versao="{versao_painel(timezone.now())}"' in html
    assert 'data-novos="1"' in html


def test_minutos_andam_mesmo_sem_mudanca_no_banco(client_equipe, relogio, cenario):
    """Sem pedido novo nem toque, o relógio sozinho tem que redesenhar (tempo e vermelho)."""
    fazer(cenario)
    r = client_equipe.get(COLUNAS, {"v": "velha"})
    versao = r.content.decode().split('data-versao="')[1].split('"')[0]
    assert b"tempo-vermelho" not in r.content
    assert client_equipe.get(COLUNAS, {"v": versao}).status_code == 204
    relogio(minutes=40)
    r = client_equipe.get(COLUNAS, {"v": versao})
    assert r.status_code == 200
    assert b"tempo-vermelho" in r.content
    assert b"40 min" in r.content


def test_pedido_que_chega_durante_a_montagem_nao_some(client_equipe, relogio, cenario, monkeypatch):
    """Se um pedido chega entre ler a versão e ler os pedidos, a tela pode até não mostrá-lo,
    mas a versão entregue tem que ser a ANTIGA: assim a próxima consulta redesenha."""
    from gerenciar import views_pedidos

    original = views_pedidos.montar_painel
    chegou = {}

    def montar_com_corrida(*args, **kwargs):
        painel = original(*args, **kwargs)  # leu os pedidos...
        chegou["p"] = fazer(cenario, nome="Atrasado")  # ...e só então chegou um novo
        return painel
    monkeypatch.setattr(views_pedidos, "montar_painel", montar_com_corrida)
    html = client_equipe.get(COLUNAS, {"v": "velha"}).content.decode()
    assert "Atrasado" not in html
    versao = html.split('data-versao="')[1].split('"')[0]
    monkeypatch.setattr(views_pedidos, "montar_painel", original)
    r = client_equipe.get(COLUNAS, {"v": versao})
    assert r.status_code == 200 and b"Atrasado" in r.content


def test_colunas_promove_agendado_que_esta_na_hora(client_equipe, relogio, cenario):
    quando = horarios_agendamento(cenario.fechada)[0]
    p = criar_pedido(cenario.dados(agendar_para=quando.isoformat()), agora=cenario.fechada)
    assert p.status == "agendado"
    relogio(days=7)  # já passou da hora marcada
    client_equipe.get(COLUNAS)
    p.refresh_from_db()
    assert p.status == "preparo"


def test_cartao_vermelho_aos_40_min(client_equipe, relogio, cenario):
    fazer(cenario)
    relogio(minutes=39)
    assert b"tempo-vermelho" not in client_equipe.get(PAINEL).content
    relogio(minutes=40)
    assert b"tempo-vermelho" in client_equipe.get(PAINEL).content


def test_cartao_novo_e_botao_da_proxima_etapa(client_equipe, relogio, cenario):
    p = fazer(cenario)
    html = client_equipe.get(PAINEL).content.decode()
    assert "cartao novo" in html
    assert reverse("gerenciar:pedido_avancar", args=[p.pk]) in html
    assert 'name="de" value="preparo"' in html
    assert "✓ Pronto" in html


def test_cancelado_mostra_motivo_e_total_riscado(client_equipe, relogio, cenario):
    p = fazer(cenario, "cancelado")
    Pedido.objects.filter(pk=p.pk).update(motivo_cancelamento="Cliente desistiu")
    html = client_equipe.get(PAINEL).content.decode()
    assert "Cliente desistiu" in html
    assert "riscado" in html


def test_busca_mostra_resultado(client_equipe, relogio, cenario):
    fazer(cenario, nome="Bruna Souza")
    fazer(cenario, nome="Carlos")
    html = client_equipe.get(COLUNAS, {"q": "bruna"}).content.decode()
    assert "Bruna Souza" in html and "Carlos" not in html
    assert "limpar" in html


def test_filtro_agendados(client_equipe, relogio, cenario):
    quando = horarios_agendamento(cenario.fechada)[0]
    criar_pedido(cenario.dados(nome="Agendada", agendar_para=quando.isoformat()), agora=cenario.fechada)
    fazer(cenario, nome="Normal")
    painel = client_equipe.get(PAINEL).content.decode()
    assert "Agendada" not in painel  # fora das colunas
    html = client_equipe.get(PAINEL, {"tipo": "agendados"}).content.decode()
    assert "Agendada" in html and "Normal" not in html
    assert "feito em 16/11" in html  # feito na segunda, entrega na quarta


def test_filtro_por_tipo(client_equipe, relogio, cenario):
    fazer(cenario, nome="Entrega")
    fazer(cenario, nome="Balcao", tipo="retirada", bairro_id="", rua="", numero="")
    html = client_equipe.get(PAINEL, {"tipo": "retirada"}).content.decode()
    assert "Balcao" in html and "Entrega" not in html


def test_htmx_sem_login_recebe_hx_redirect(client, db):
    for url in (PAINEL, COLUNAS):
        r = client.get(url, HTTP_HX_REQUEST="true")
        assert r.status_code == 200
        assert r["HX-Redirect"] == "/gerenciar/entrar/"
        r = client.get(url)
        assert r.status_code == 302 and r.url.startswith("/gerenciar/entrar/")


def test_equipe_ve_so_aba_pedidos(client_equipe, relogio):
    html = client_equipe.get(PAINEL).content.decode()
    assert reverse("gerenciar:lista") not in html
    assert reverse("gerenciar:loja") not in html
    assert "Pedidos" in html


def test_dono_ve_todas_as_abas(client, usuario_dono, relogio):
    client.force_login(usuario_dono)
    html = client.get(PAINEL).content.decode()
    assert reverse("gerenciar:lista") in html and reverse("gerenciar:loja") in html


def test_avancar_avisa_o_painel(client_equipe, relogio, cenario):
    """O cartão posta com hx-swap="none": o que importa para ele é o HX-Trigger."""
    p = fazer(cenario)
    url = reverse("gerenciar:pedido_avancar", args=[p.pk])
    r = client_equipe.post(url, {"de": "preparo"})
    assert r.status_code == 200
    assert json.loads(r["HX-Trigger"]) == {"painel-mudou": True}
    p.refresh_from_db()
    assert p.status == "pronto"
    # aparelho desatualizado: mesma resposta, nada muda
    r = client_equipe.post(url, {"de": "preparo"})
    assert r.status_code == 200
    p.refresh_from_db()
    assert p.status == "pronto"


def test_avancar_pedido_inexistente_404(client_equipe, db):
    assert client_equipe.post(reverse("gerenciar:pedido_avancar", args=[999999]), {"de": "preparo"}).status_code == 404


# ----- correções da revisão final -----

def test_painel_sem_comentario_de_template_vazando(client_equipe, relogio, cenario):
    """Comentário `{# #}` de várias linhas aparece na tela: tem que ser {% comment %}."""
    fazer(cenario)
    for r in (client_equipe.get(PAINEL), client_equipe.get(COLUNAS)):
        assert "{#" not in r.content.decode()


def test_agendado_promovido_conta_minutos_da_hora_de_comecar(client_equipe, relogio, cenario):
    """Agendado feito dias antes: o tempo conta de (hora marcada - 30 min), não de quando foi feito."""
    quando = horarios_agendamento(cenario.fechada)[0]
    p = criar_pedido(cenario.dados(agendar_para=quando.isoformat()), agora=cenario.fechada)
    comeca = quando - timedelta(minutes=30)
    relogio(seconds=(comeca - cenario.aberta).total_seconds())
    html = client_equipe.get(PAINEL).content.decode()
    p.refresh_from_db()
    assert p.status == "preparo"
    cartao = html.split(f'id="pedido-{p.pk}"')[1].split("</article>")[0]
    assert "0 min" in cartao and "tempo-vermelho" not in cartao
    relogio(seconds=(comeca - cenario.aberta).total_seconds() + 12 * 60)
    cartao = client_equipe.get(PAINEL).content.decode().split(f'id="pedido-{p.pk}"')[1].split("</article>")[0]
    assert "12 min" in cartao and "tempo-vermelho" not in cartao
    # o detalhe usa a mesma conta
    assert "· 12 min" in client_equipe.get(reverse("gerenciar:pedido", args=[p.pk])).content.decode()


def test_comecado_antes_da_hora_nao_fica_negativo(client_equipe, relogio, cenario):
    p = fazer(cenario)
    Pedido.objects.filter(pk=p.pk).update(agendado_para=cenario.aberta + timedelta(hours=2))
    cartao = client_equipe.get(PAINEL).content.decode().split(f'id="pedido-{p.pk}"')[1].split("</article>")[0]
    assert "0 min" in cartao


def test_aberto_de_outro_dia_mostra_feito_em(client_equipe, relogio, cenario):
    """Busca pelo nº pode achar dois "#3" (hoje e ontem): o de ontem leva "feito em"."""
    ontem = fazer(cenario, nome="De ontem")
    Pedido.objects.filter(pk=ontem.pk).update(dia=ontem.dia - timedelta(days=1))
    fazer(cenario, nome="De hoje")
    html = client_equipe.get(PAINEL).content.decode()
    cartao = html.split(f'id="pedido-{ontem.pk}"')[1].split("</article>")[0]
    assert f"feito em {(ontem.dia - timedelta(days=1)):%d/%m}" in cartao
    assert html.count("feito em") == 1


def test_historico_do_htmx_desligado(client_equipe, relogio):
    """hx-push-url faria o htmx guardar a página (com o total do dia) no localStorage."""
    html = client_equipe.get(PAINEL).content.decode()
    assert '<meta name="htmx-config" content=\'{"historyCacheSize":0}\'>' in html


def test_pilula_mantem_a_busca(client_equipe, relogio, cenario):
    fazer(cenario, nome="Bruna")
    html = client_equipe.get(PAINEL, {"q": "bruna"}).content.decode()
    nav = html.split('class="painel-pilulas"')[1].split("</nav>")[0]
    assert nav.count('hx-include="#filtros [name=q]"') == 5
    assert "?tipo=retirada&amp;q=bruna" in nav  # sem JS e no endereço guardado


def test_busca_e_pilulas_cancelam_consulta_atrasada(client_equipe, relogio, cenario):
    html = client_equipe.get(PAINEL).content.decode()
    busca = html.split('name="q"')[1].split(">")[0]
    assert 'hx-sync="#colunas:replace"' in busca
    nav = html.split('class="painel-pilulas"')[1].split("</nav>")[0]
    assert nav.count('hx-sync="#colunas:replace"') == 5


def test_alvos_de_toque_e_contraste_no_css(client_equipe, relogio, cenario):
    from pathlib import Path

    from django.conf import settings
    css = (Path(settings.BASE_DIR) / "static/css/painel.css").read_text(encoding="utf-8")
    assert ".painel-aviso a {" in css and ".detalhe-tel {" in css
    for regra in (".painel-aviso a {", ".detalhe-tel {"):
        assert "min-height: 40px" in css.split(regra)[1].split("}")[0]
    assert "#25d366; color: #fff" not in css
    p = fazer(cenario)
    assert 'class="detalhe-tel"' in client_equipe.get(reverse("gerenciar:pedido", args=[p.pk])).content.decode()


def test_agendado_aguardando_aceite_conta_desde_que_foi_feito(client_equipe, relogio, cenario):
    """Na fila de aceite o que importa é há quanto tempo o cliente espera resposta."""
    p = fazer(cenario, "aguardando")
    Pedido.objects.filter(pk=p.pk).update(agendado_para=cenario.aberta + timedelta(days=2))
    relogio(minutes=15)
    cartao = client_equipe.get(PAINEL).content.decode().split(f'id="pedido-{p.pk}"')[1].split("</article>")[0]
    assert "15 min" in cartao
