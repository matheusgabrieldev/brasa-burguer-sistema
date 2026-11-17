"""Detalhe do pedido (abre ao tocar no cartão) e os botões dele.

Caminho: cartão → GET `pedido/<pk>/` → `_detalhe.html` dentro de `#detalhe` na tela do painel.
Cada botão do detalhe faz POST e recebe o detalhe atualizado, mais o cabeçalho `HX-Trigger`:
- "painel-mudou": as colunas recarregam na hora (sem esperar os 5 s);
- "avisar-whatsapp": só quando a mudança pede um aviso natural ao cliente (pronto p/ retirada,
  saiu, cancelado). A tela oferece o atalho; ninguém é avisado sozinho.

Os POST mandam `de` (a etapa que o aparelho viu). Se outro aparelho mexeu antes, a regra não
grava nada e a resposta é o detalhe como está agora, sem mensagem de erro na correria.
"""
import json

from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from clientes.servicos import formatar_telefone
from pedidos import painel as regras
from pedidos.mensagens_status import atalho_depois_de, link_cliente, mensagens_disponiveis
from pedidos.models import Pedido

from .permissoes import dono_obrigatorio, eh_dono, equipe_obrigatorio

ETAPAS = dict(Pedido.STATUS)
COM_RELOGIO = ("aguardando", "preparo", "pronto", "saiu")  # etapas em que o tempo de espera importa


def _quem(usuario):
    """Nome no histórico; "—" quando foi o sistema ou o cliente (sem usuário)."""
    if usuario is None:
        return "—"
    return usuario.get_full_name() or usuario.get_username()


def _detalhe(request, pk, erro=""):
    """Monta o `_detalhe.html` do pedido (404 se não existe). Devolve (resposta, pedido)."""
    pedido = get_object_or_404(Pedido.objects.prefetch_related("itens"), pk=pk)
    historico = list(pedido.historico.select_related("usuario").order_by("em", "id"))
    for h in historico:
        h.quem = _quem(h.usuario)
    anterior = regras.etapa_anterior(pedido)
    dono = eh_dono(request.user)
    contexto = {
        "p": pedido,
        "telefone": formatar_telefone(pedido.telefone),
        "etapa_rotulo": ETAPAS.get(pedido.status, pedido.status),
        "minutos": regras.minutos_de_espera(pedido, timezone.now()) if pedido.status in COM_RELOGIO else None,
        "etapa": regras.proxima_etapa(pedido),
        "anterior": ETAPAS[anterior] if anterior else None,
        "whatsapps": [(rotulo, link_cliente(pedido, chave)) for chave, rotulo in mensagens_disponiveis(pedido)],
        "historico": historico,
        # a Equipe não cancela: o formulário nem vai para o HTML dela
        "pode_cancelar": dono and pedido.status != "cancelado",
        "erro": erro,
    }
    return render(request, "gerenciar/pedidos/_detalhe.html", contexto), pedido


def _responder(request, pk, mudou, sugerir=False):
    """Detalhe atualizado + eventos do HX-Trigger, num objeto JSON só.

    `sugerir` = esta ação pode pedir aviso no WhatsApp. Só sugere quando a ação mudou mesmo
    o pedido: um toque atrasado (de velho) não oferece mandar a mesma mensagem de novo.
    """
    resposta, pedido = _detalhe(request, pk)
    eventos = {"painel-mudou": True}
    atalho = atalho_depois_de(pedido) if (mudou and sugerir) else None
    if atalho:
        chave, rotulo = atalho
        eventos["avisar-whatsapp"] = {"url": link_cliente(pedido, chave), "rotulo": rotulo}
    resposta["HX-Trigger"] = json.dumps(eventos)
    return resposta


def _fazer(acao, *args):
    """Roda uma regra de pedidos/painel.py; pedido inexistente vira 404."""
    try:
        return acao(*args)
    except Pedido.DoesNotExist:
        raise Http404


@never_cache
@equipe_obrigatorio
@require_GET
def pedido(request, pk):
    """Abre o detalhe. Abrir = "visto" (para o alarme e tira a borda amarela em todo aparelho)."""
    visto_agora = regras.marcar_visto(pk)
    resposta, _ = _detalhe(request, pk)
    if visto_agora:
        resposta["HX-Trigger"] = json.dumps({"painel-mudou": True})
    return resposta


@equipe_obrigatorio
@require_POST
def pedido_avancar(request, pk):
    """Próxima etapa (do cartão ou do detalhe). O cartão ignora o HTML e usa só os eventos."""
    mudou = _fazer(regras.avancar, pk, request.POST.get("de", ""), request.user)
    return _responder(request, pk, mudou, sugerir=True)


@equipe_obrigatorio
@require_POST
def pedido_voltar(request, pk):
    """Desfaz toque errado. Não sugere WhatsApp: o cliente já foi avisado (ou não) antes."""
    mudou = _fazer(regras.voltar, pk, request.POST.get("de", ""), request.user)
    return _responder(request, pk, mudou)


@equipe_obrigatorio
@require_POST
def pedido_aceitar(request, pk):
    mudou = _fazer(regras.aceitar, pk, request.user, timezone.now())
    return _responder(request, pk, mudou)


@equipe_obrigatorio
@require_POST
def pedido_recusar(request, pk):
    """Recusa um pedido aguardando aceite (motivo opcional). Sugere avisar o cliente."""
    mudou = _fazer(regras.recusar, pk, request.user, request.POST.get("motivo", ""))
    return _responder(request, pk, mudou, sugerir=True)


@equipe_obrigatorio
@require_POST
def pedido_comecar(request, pk):
    """Adianta um agendado para "Em preparo". Quem tocou já viu: para ele não é "novo" (os outros aparelhos
    recebem a mudança normalmente na próxima consulta)."""
    mudou = _fazer(regras.comecar_agora, pk, request.user)
    if mudou:
        regras.marcar_visto(pk)
    return _responder(request, pk, mudou)


@equipe_obrigatorio
@require_POST
def pedido_pago(request, pk):
    """Pago / não pago: só informativo, não trava nenhuma etapa."""
    mudou = _fazer(regras.marcar_pago, pk, request.POST.get("pago") == "1", request.user)
    return _responder(request, pk, mudou)


@dono_obrigatorio
@require_POST
def pedido_cancelar(request, pk):
    """Só o Dono cancela, e sempre com motivo (fica no histórico e na mensagem ao cliente)."""
    motivo = request.POST.get("motivo", "").strip()
    if not motivo:
        resposta, _ = _detalhe(request, pk, erro="Informe o motivo do cancelamento.")
        return resposta
    mudou = _fazer(regras.cancelar, pk, request.user, motivo)
    return _responder(request, pk, mudou, sugerir=True)


@equipe_obrigatorio
@require_POST
def pedidos_finalizar(request):
    """Fim da noite: tudo em preparo/pronto/saiu vai para Concluído. A tela já pediu confirmação."""
    regras.finalizar_todos(request.user)
    resposta = HttpResponse(status=204)
    resposta["HX-Trigger"] = json.dumps({"painel-mudou": True})
    return resposta
