"""Telas do cardápio online: página inicial, modal do produto e validação da sacola."""
import json

from django.db.models import Prefetch
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from loja.horario import DIAS, status_loja
from loja.models import Bairro, Configuracao

from pedidos.agendamento import horarios_agendamento

from .models import Categoria, Produto
from .disponibilidade import grupo_disponivel
from .precos import PrecoInvalido, calcular_item

MAX_ITENS_SACOLA = 50


def _agendamento():
    """Loja fechada mas com abertura prevista: o cliente pode montar um pedido agendado.
    Devolve (agendavel, texto da barra da sacola)."""
    horarios = horarios_agendamento()
    if not horarios:
        return False, ""
    primeiro = horarios[0]
    dias = (primeiro.date() - timezone.localtime().date()).days
    dia = "hoje" if dias == 0 else "amanhã" if dias == 1 else DIAS[primeiro.weekday()]
    return True, f"Pedido agendado para {dia}, a partir de {primeiro:%H:%M}"


def cardapio(request):
    """Página principal: só categorias e produtos visíveis."""
    hoje = timezone.localdate()
    visiveis = Produto.objects.filter(visivel=True)
    categorias = (
        Categoria.objects.filter(visivel=True)
        .prefetch_related(Prefetch("produtos", queryset=visiveis, to_attr="produtos_visiveis"))
    )
    categorias = [c for c in categorias if c.produtos_visiveis]
    destaques = list(visiveis.filter(destaque=True, categoria__visivel=True))
    # Banner só com fotos de burgers: as artes de promoção têm texto e logo próprios.
    banner = [p for p in visiveis.filter(categoria__visivel=True).exclude(categoria__nome__icontains="promo") if p.foto][:3]
    agendavel, agendamento_texto = _agendamento()
    return render(
        request,
        "cardapio/cardapio.html",
        {
            "agendavel": agendavel,
            "agendamento_texto": agendamento_texto,
            "loja": Configuracao.atual(),
            "status": status_loja(),
            "categorias": categorias,
            "destaques": destaques,
            "banner": banner,
            "bairros": Bairro.objects.filter(ativo=True).order_by("taxa", "nome"),
            "hoje": hoje,
        },
    )


def produto_modal(request, slug):
    """Fragmento HTML do modal (carregado pelo HTMX). Produto oculto dá 404."""
    produto = get_object_or_404(Produto, slug=slug, visivel=True, categoria__visivel=True)
    grupos = [pg.grupo for pg in produto.produtogrupo_set.select_related("grupo").prefetch_related("grupo__opcoes")]
    hoje = timezone.localdate()
    for g in grupos:  # textos prontos para o template
        g.disponivel = grupo_disponivel(g, hoje)
        g.limite = 1 if g.tipo == "unica" else g.maximo
        if g.tipo == "unica":
            g.subtitulo = "Escolha 1 opção"
        elif g.maximo <= 1:
            g.subtitulo = "Opcional"
        elif g.obrigatorio:
            g.subtitulo = f"Escolha de {max(g.minimo, 1)} até {g.maximo}"
        else:
            g.subtitulo = f"Escolha até {g.maximo}"
    return render(
        request,
        "cardapio/_produto_modal.html",
        {"produto": produto, "grupos": grupos, "status": status_loja(), "agendavel": _agendamento()[0],
         "hoje": hoje, "grupos_disponiveis": all(g.disponivel for g in grupos)},
    )


def _texto(valor):
    return f"{valor:.2f}"


@require_POST
def validar_sacola(request):
    """Recalcula a sacola no servidor: preço sempre do banco; item inválido vai para `removidos`."""
    try:
        corpo = json.loads(request.body)
        itens = corpo["itens"]
        if not isinstance(itens, list):
            raise ValueError
    except (ValueError, KeyError, TypeError):
        return JsonResponse({"erro": "Pedido inválido: envie a lista de itens."}, status=400)
    if len(itens) > MAX_ITENS_SACOLA:
        return JsonResponse({"erro": f"A sacola aceita no máximo {MAX_ITENS_SACOLA} itens."}, status=400)

    hoje = timezone.localdate()
    validos, removidos, subtotal = [], [], 0
    for indice, bruto in enumerate(itens):
        try:
            if not isinstance(bruto, dict):
                raise PrecoInvalido("Item inválido. Confira a sacola.")
            item = calcular_item(
                bruto.get("produto_id"), bruto.get("quantidade", 1), bruto.get("opcoes"), str(bruto.get("observacao") or ""), hoje
            )
        except PrecoInvalido as e:
            removidos.append({"indice": indice, "motivo": str(e)})
            continue
        subtotal += item.total
        validos.append(
            {
                "indice": indice,
                "nome": item.nome,
                "preco_unitario": _texto(item.preco_unitario),
                "total": _texto(item.total),
                "opcoes": [{"grupo": o.grupo, "nome": o.nome, "qtd": o.qtd, "preco": _texto(o.preco)} for o in item.opcoes],
            }
        )
    return JsonResponse({"itens": validos, "removidos": removidos, "subtotal": _texto(subtotal)})
