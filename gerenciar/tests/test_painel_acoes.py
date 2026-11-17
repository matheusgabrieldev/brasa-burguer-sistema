"""Detalhe do pedido e as ações dele: etapa, voltar, aceitar/recusar, pago, cancelar, WhatsApp."""
import json
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from loja.models import Configuracao
from pedidos.models import Pedido
from pedidos.servicos import criar_pedido


@pytest.fixture(autouse=True)
def relogio(monkeypatch, cenario):
    """As views usam "agora" = quarta 11/11 às 20:00 (loja aberta)."""
    monkeypatch.setattr(timezone, "now", lambda: cenario.aberta)


def fazer(cenario, status="preparo", tipo=None, **mudar):
    """Pedido de hoje com status (e tipo) forçados, sem passar por cada etapa."""
    if tipo in ("retirada", "local"):
        mudar.update(tipo="retirada", pagamento="pix")
    p = criar_pedido(cenario.dados(**mudar), agora=cenario.aberta)
    Pedido.objects.filter(pk=p.pk).update(status=status, tipo=tipo or p.tipo, criado_em=cenario.aberta)
    p.refresh_from_db()
    return p


def url(nome, p):
    return reverse(f"gerenciar:{nome}", args=[p.pk])


def gatilho(resposta):
    return json.loads(resposta["HX-Trigger"])


def test_abrir_detalhe_marca_visto(client_equipe, cenario):
    p = fazer(cenario, observacao="Tocar a campainha")
    assert p.visto_em is None
    r = client_equipe.get(url("pedido", p))
    assert r.status_code == 200
    html = r.content.decode()
    assert f"#{p.numero}" in html
    assert "2x" in html and p.itens.first().nome in html
    assert "Tocar a campainha" in html
    p.refresh_from_db()
    assert p.visto_em is not None


def test_detalhe_de_pedido_inexistente_404(client_equipe, db):
    assert client_equipe.get(reverse("gerenciar:pedido", args=[999999])).status_code == 404


def test_cartao_abre_o_detalhe(client_equipe, cenario):
    p = fazer(cenario)
    html = client_equipe.get(reverse("gerenciar:pedidos")).content.decode()
    assert f'hx-get="{url("pedido", p)}"' in html
    assert 'id="detalhe"' in html


def test_avancar_responde_detalhe_e_hx_trigger(client_equipe, cenario):
    p = fazer(cenario)
    r = client_equipe.post(url("pedido_avancar", p), {"de": "preparo"})
    assert r.status_code == 200
    assert b'class="detalhe' in r.content
    assert gatilho(r) == {"painel-mudou": True}  # delivery pronto: nada a avisar ainda
    p.refresh_from_db()
    assert p.status == "pronto"


def test_pronto_retirada_sugere_whatsapp(client_equipe, cenario):
    p = fazer(cenario, tipo="retirada")
    r = client_equipe.post(url("pedido_avancar", p), {"de": "preparo"})
    eventos = gatilho(r)
    assert eventos["painel-mudou"] is True
    assert eventos["avisar-whatsapp"]["url"].startswith("https://wa.me/5581988887777?text=")
    assert eventos["avisar-whatsapp"]["rotulo"] == "Pronto p/ retirada"


def test_pronto_no_local_nao_sugere(client_equipe, cenario):
    p = fazer(cenario, tipo="local")
    r = client_equipe.post(url("pedido_avancar", p), {"de": "preparo"})
    assert gatilho(r) == {"painel-mudou": True}


def test_saiu_sugere_whatsapp(client_equipe, cenario):
    p = fazer(cenario, status="pronto")
    r = client_equipe.post(url("pedido_avancar", p), {"de": "pronto"})
    assert gatilho(r)["avisar-whatsapp"]["rotulo"] == "Saiu p/ entrega"


def test_status_velho_nao_quebra(client_equipe, cenario):
    p = fazer(cenario, status="pronto", tipo="retirada")
    r = client_equipe.post(url("pedido_avancar", p), {"de": "preparo"})
    assert r.status_code == 200
    assert b'class="detalhe' in r.content
    assert gatilho(r) == {"painel-mudou": True}  # nada mudou: não sugere mensagem repetida
    p.refresh_from_db()
    assert p.status == "pronto"


def test_equipe_nao_cancela(client_equipe, cenario):
    p = fazer(cenario)
    assert client_equipe.post(url("pedido_cancelar", p), {"de": "preparo", "motivo": "x"}).status_code == 403
    p.refresh_from_db()
    assert p.status == "preparo"
    # nem vê o botão
    assert url("pedido_cancelar", p).encode() not in client_equipe.get(url("pedido", p)).content


def test_dono_cancela_com_motivo(client_dono, cenario):
    p = fazer(cenario)
    assert url("pedido_cancelar", p).encode() in client_dono.get(url("pedido", p)).content
    r = client_dono.post(url("pedido_cancelar", p), {"de": "preparo", "motivo": "Cliente desistiu"})
    assert r.status_code == 200
    p.refresh_from_db()
    assert p.status == "cancelado" and p.motivo_cancelamento == "Cliente desistiu"
    assert gatilho(r)["avisar-whatsapp"]["rotulo"] == "Avisar cancelamento"
    assert "Cliente desistiu" in r.content.decode()


def test_cancelar_sem_motivo_mostra_erro(client_dono, cenario):
    p = fazer(cenario)
    r = client_dono.post(url("pedido_cancelar", p), {"de": "preparo", "motivo": "   "})
    assert r.status_code == 200
    assert "Informe o motivo do cancelamento." in r.content.decode()
    p.refresh_from_db()
    assert p.status == "preparo"
    assert not p.historico.filter(status="cancelado").exists()


def test_equipe_pode_recusar(client_equipe, cenario):
    cfg = Configuracao.atual()
    cfg.entrada_pedidos = "manual"
    cfg.save()
    p = criar_pedido(cenario.dados(), agora=cenario.aberta)
    assert p.status == "aguardando"
    html = client_equipe.get(url("pedido", p)).content.decode()
    assert url("pedido_aceitar", p) in html and url("pedido_recusar", p) in html
    r = client_equipe.post(url("pedido_recusar", p), {"de": "aguardando", "motivo": ""})
    assert r.status_code == 200
    p.refresh_from_db()
    assert p.status == "cancelado"


def test_aceitar_vai_para_preparo(client_equipe, cenario):
    p = fazer(cenario, status="aguardando")
    r = client_equipe.post(url("pedido_aceitar", p), {"de": "aguardando"})
    assert r.status_code == 200 and gatilho(r)["painel-mudou"] is True
    p.refresh_from_db()
    assert p.status == "preparo"


def test_comecar_agora_adianta_agendado(client_equipe, cenario):
    p = fazer(cenario, status="agendado", agendado_para=None)
    Pedido.objects.filter(pk=p.pk).update(agendado_para=cenario.aberta + timedelta(hours=2))
    assert url("pedido_comecar", p).encode() in client_equipe.get(url("pedido", p)).content
    client_equipe.post(url("pedido_comecar", p), {"de": "agendado"})
    p.refresh_from_db()
    assert p.status == "preparo"


def test_voltar_desfaz_e_link_mostra_etapa(client_equipe, cenario):
    p = fazer(cenario)
    r = client_equipe.post(url("pedido_avancar", p), {"de": "preparo"})
    assert "voltar para Em preparo" in r.content.decode()
    r = client_equipe.post(url("pedido_voltar", p), {"de": "pronto"})
    assert r.status_code == 200
    p.refresh_from_db()
    assert p.status == "preparo"
    assert "voltar para" not in r.content.decode()


def test_marcar_pago_e_nao_pago(client_equipe, cenario):
    p = fazer(cenario)
    r = client_equipe.post(url("pedido_pago", p), {"de": "preparo", "pago": "1"})
    p.refresh_from_db()
    assert p.pago is True and "Marcar como não pago" in r.content.decode()
    assert gatilho(r) == {"painel-mudou": True}
    client_equipe.post(url("pedido_pago", p), {"de": "preparo", "pago": "0"})
    p.refresh_from_db()
    assert p.pago is False


def test_historico_mostra_hora_etapa_e_usuario(client_equipe, usuario_equipe, cenario):
    usuario_equipe.first_name, usuario_equipe.last_name = "Caio", "Silva"
    usuario_equipe.save()
    p = fazer(cenario)
    html = client_equipe.post(url("pedido_avancar", p), {"de": "preparo"}).content.decode()
    historico = html.split('class="detalhe-hist"')[1]
    assert "20:00" in historico  # hora de Recife
    assert "Pronto" in historico and "Caio Silva" in historico
    assert "—" in historico  # a entrada criada pelo sistema não tem usuário


def test_finalizar_todos_pela_tela(client_equipe, cenario):
    a, b = fazer(cenario), fazer(cenario, status="saiu")
    espera = fazer(cenario, status="aguardando")
    html = client_equipe.get(reverse("gerenciar:pedidos")).content.decode()
    assert 'hx-confirm="Finalizar 2 pedidos?"' in html
    r = client_equipe.post(reverse("gerenciar:pedidos_finalizar"))
    assert r.status_code == 204
    assert gatilho(r) == {"painel-mudou": True}
    assert set(Pedido.objects.filter(status="concluido").values_list("pk", flat=True)) == {a.pk, b.pk}
    espera.refresh_from_db()
    assert espera.status == "aguardando"
    # a contagem do botão anda junto com a atualização das colunas
    assert b'hx-confirm="Finalizar 0 pedidos?"' not in client_equipe.get(reverse("gerenciar:pedidos_colunas")).content
    assert b'id="finalizar-todos"' in client_equipe.get(reverse("gerenciar:pedidos_colunas")).content


def test_detalhe_local_so_tem_falar_com_cliente(client_equipe, cenario):
    p = fazer(cenario, tipo="local")
    html = client_equipe.get(url("pedido", p)).content.decode()
    assert "Falar com o cliente" in html
    for rotulo in ("Pedido aceito", "Pronto p/ retirada", "Saiu p/ entrega"):
        assert rotulo not in html
    assert 'target="_blank" rel="noopener"' in html


def test_detalhe_delivery_tem_mensagens_de_entrega(client_equipe, cenario):
    p = fazer(cenario, referencia="Portão azul")
    html = client_equipe.get(url("pedido", p)).content.decode()
    assert "Pedido aceito" in html and "Saiu p/ entrega" in html and "Falar com o cliente" in html
    assert "Portão azul" in html and "Rua das Flores" in html


def test_painel_carrega_o_js_e_o_detalhe_tem_ganchos(client_equipe, cenario):
    """Fiação do painel.js: o script na página, a URL do detalhe (para recarregar quando o
    painel muda), o botão de fechar e o Espaço abrindo o cartão (acessibilidade)."""
    p = fazer(cenario)
    pagina = client_equipe.get(reverse("gerenciar:pedidos")).content.decode()
    assert "js/painel.js" in pagina
    assert 'id="faixa-som"' in pagina and "Toque para ativar o som dos pedidos" in pagina
    assert "key==' '" in pagina  # Espaço também abre o cartão focado
    # aba visível: a cada 5 s; aba escondida: a cada 15 s (o alarme não para em outra aba)
    assert "every 5s [document.visibilityState=='visible']" in pagina
    assert "every 15s [document.visibilityState=='hidden']" in pagina
    detalhe = client_equipe.get(url("pedido", p)).content.decode()
    assert f'data-url="{url("pedido", p)}"' in detalhe and f'data-pk="{p.pk}"' in detalhe
    assert "data-fechar" in detalhe and "← Voltar" in detalhe


def test_comecar_agora_marca_visto_para_quem_tocou(client_equipe, cenario):
    """Quem tocou em "Começar agora" já viu o pedido: não vira "novo" nem toca o alarme."""
    from pedidos.painel_consultas import montar_painel
    p = fazer(cenario, status="agendado", agendado_para=None)
    Pedido.objects.filter(pk=p.pk).update(agendado_para=cenario.aberta + timedelta(hours=2))
    client_equipe.post(url("pedido_comecar", p), {"de": "agendado"})
    p.refresh_from_db()
    assert p.status == "preparo" and p.visto_em is not None
    assert montar_painel(timezone.localdate(cenario.aberta)).novos == 0
