"""Telas do cliente para fechar o pedido: checkout e envio.

A tela do checkout vem pronta do servidor (bairros, formas de pagamento, horários, endereços
salvos neste aparelho e sugestões). Os itens vêm da sacola do navegador (localStorage) e o
checkout.js confere tudo em /sacola/validar/. Quem decide o preço final é sempre criar_pedido.
"""
import json

from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from cardapio.models import Produto
from clientes.servicos import COOKIE_DISPOSITIVO, dispositivo_do_token, formatar_telefone, gravar_cookie, lembrar
from gerenciar.permissoes import eh_dono
from loja.horario import status_loja
from loja.models import Bairro, Configuracao, FormaPagamento

from . import limite
from .agendamento import horarios_agendamento
from .servicos import ACEITA, PedidoInvalido, criar_pedido

MAX_SUGESTOES = 6
MAX_ENDERECOS = 5


def _valor(v):
    return f"{v:.2f}"


def _sugestoes(hoje):
    """Até 6 produtos marcados para o checkout, visíveis e não esgotados hoje."""
    return (
        Produto.objects.filter(sugerir_no_checkout=True, visivel=True, categoria__visivel=True)
        .exclude(esgotado_em=hoje)[:MAX_SUGESTOES]
    )


def _aparelho(request):
    """Nome, telefone e endereços salvos NESTE aparelho (só pelo cookie, nunca pelo telefone)."""
    disp = dispositivo_do_token(request.COOKIES.get(COOKIE_DISPOSITIVO))
    if disp is None:
        return None, []
    enderecos = list(disp.enderecos.filter(bairro__ativo=True).select_related("bairro")[:MAX_ENDERECOS])
    return disp, enderecos


@never_cache  # a página pode ter o endereço do cliente: nada de guardar em cache
@require_GET
def checkout(request):
    agora = timezone.now()
    status = status_loja(agora)
    horarios = horarios_agendamento(agora)
    disp, enderecos = _aparelho(request)
    formas = list(FormaPagamento.objects.all())
    for f in formas:  # tipos de pedido em que a forma é aceita (o JS esconde as outras)
        f.tipos = [t for t, campo in ACEITA.items() if getattr(f, campo)]
    bairros = list(Bairro.objects.filter(ativo=True).order_by("nome"))
    loja = Configuracao.atual()

    dados_js = {
        "bairros": {str(b.id): _valor(b.taxa) for b in bairros},
        "formas": {f.codigo: {"pct": _valor(f.acrescimo_pct), "tipos": f.tipos} for f in formas},
        "enderecos": [
            {"bairro_id": e.bairro_id, "rua": e.rua, "numero": e.numero, "referencia": e.referencia} for e in enderecos
        ],
        "aparelho": {"nome": disp.nome, "telefone": formatar_telefone(disp.telefone) if disp.telefone else ""} if disp else None,
        "pedido_minimo": _valor(loja.pedido_minimo),
    }
    return render(request, "pedidos/checkout.html", {
        "loja": loja,
        "status": status,
        "agendavel": bool(horarios),
        "horarios": [(h.isoformat(), h) for h in horarios],
        "fechada_sem_horario": not status.aberta and not horarios,
        "bairros": bairros,
        "formas": formas,
        "aparelho": disp,
        "enderecos": enderecos,
        "sugestoes": _sugestoes(timezone.localdate(agora)),
        "dados_js": dados_js,
    })


def _lembrar_aparelho(request, response, pedido):
    """'Lembrar de mim' marcado: guarda nome, telefone e endereço e grava o cookie."""
    bairro = Bairro.objects.filter(nome=pedido.bairro_nome).first() if pedido.tipo == "delivery" else None
    token = lembrar(
        request.COOKIES.get(COOKIE_DISPOSITIVO), pedido.nome, pedido.telefone, bairro,
        pedido.rua if bairro else "", pedido.numero_end if bairro else "", pedido.referencia if bairro else "",
    )
    gravar_cookie(response, token)


@require_POST
def enviar(request):
    """Recebe o pedido em JSON. 201 com a URL do pedido; 400 com o erro e o campo; 429 no limite."""
    try:
        dados = json.loads(request.body)
    except ValueError:
        dados = None
    if not isinstance(dados, dict):
        return JsonResponse({"erro": "Pedido inválido. Recarregue a página."}, status=400)

    # Freio contra robô por rede (IP). O Dono logado lançando pedidos não entra na conta.
    ip_hash = "" if eh_dono(request.user) else limite.codigo_ip(limite.ip_do_cliente(request))
    try:
        pedido = criar_pedido(dados, ip_hash=ip_hash)
    except limite.LimiteExcedido:
        return JsonResponse({"erro": limite.MENSAGEM}, status=429)
    except PedidoInvalido as e:
        return JsonResponse({"erro": str(e), "campo": e.campo}, status=400)

    resposta = JsonResponse({"codigo": pedido.codigo, "url": reverse("pedidos:acompanhar", args=[pedido.codigo])}, status=201)
    if dados.get("lembrar") is True:
        _lembrar_aparelho(request, resposta, pedido)
    return resposta
