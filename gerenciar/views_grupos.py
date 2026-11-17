"""Área do Dono: grupos de opção (lista, criar/editar com as opções, excluir)."""
from django.contrib import messages
from django.db import transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render

from cardapio.models import GrupoOpcao

from .forms_grupos import GrupoForm, OpcaoFormSet
from .permissoes import dono_obrigatorio


@dono_obrigatorio
def grupos(request):
    """Lista os grupos, com quantos produtos usam cada um."""
    todos = GrupoOpcao.objects.annotate(
        n_produtos=Count("produtogrupo__produto", distinct=True),
        n_opcoes=Count("opcoes", distinct=True),
    )
    return render(request, "gerenciar/grupos.html", {"grupos": todos})


@dono_obrigatorio
def grupo_editar(request, pk=None):
    """Cria (sem pk) ou edita um grupo junto com as opções dele."""
    grupo = get_object_or_404(GrupoOpcao, pk=pk) if pk else None
    if request.method == "POST":
        form = GrupoForm(request.POST, instance=grupo)
        formset = OpcaoFormSet(request.POST, instance=grupo or GrupoOpcao(), prefix="opcoes")
        grupo_valido = form.is_valid()
        opcoes_validas = formset.is_valid()
        if grupo_valido and opcoes_validas and form.validar_capacidade(formset.opcoes_ativas()):
            with transaction.atomic():
                novo = grupo is None
                g = form.save()
                formset.instance = g
                formset.save()
            messages.success(request, f"Grupo “{g.nome}” {'criado' if novo else 'salvo'}!")
            return redirect("gerenciar:grupos")
    else:
        form = GrupoForm(instance=grupo)
        formset = OpcaoFormSet(instance=grupo or GrupoOpcao(), prefix="opcoes")
    return render(request, "gerenciar/grupo.html", {"form": form, "formset": formset, "grupo": grupo})


@dono_obrigatorio
def grupo_excluir(request, pk):
    """GET mostra os produtos afetados e pede confirmação; POST apaga o grupo (os produtos ficam)."""
    grupo = get_object_or_404(GrupoOpcao, pk=pk)
    if request.method == "POST":
        nome = grupo.nome
        grupo.delete()
        messages.success(request, f"Grupo “{nome}” excluído.")
        return redirect("gerenciar:grupos")
    ligacoes = grupo.produtogrupo_set.select_related("produto").order_by("produto__nome")
    return render(request, "gerenciar/grupo_excluir.html", {"grupo": grupo, "produtos": [pg.produto for pg in ligacoes]})
