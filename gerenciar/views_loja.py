"""Área do Dono: configuração da loja (modo, dados, horários, bairros e formas de pagamento)."""
from datetime import time

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from loja.horario import status_loja
from loja.models import Bairro, Configuracao, FormaPagamento, Horario

from .forms_loja import BairroForm, HorarioFormSet, LojaForm, PagamentoFormSet
from .permissoes import dono_obrigatorio


@dono_obrigatorio
@require_http_methods(["GET", "POST"])
def loja(request):
    """Dados da loja. Os 3 botões de modo mandam só `modo`; o resto vem do formulário."""
    cfg = Configuracao.atual()
    if request.method == "POST" and "modo" in request.POST:
        modo = request.POST["modo"]
        if modo in dict(Configuracao.MODOS):
            cfg.modo_loja = modo
            cfg.save(update_fields=["modo_loja"])
            messages.success(request, f"Loja: {dict(Configuracao.MODOS)[modo].lower()}.")
        else:
            messages.error(request, "Modo da loja inválido.")
        return redirect("gerenciar:loja")
    form = LojaForm(request.POST or None, instance=cfg)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Dados da loja salvos!")
        return redirect("gerenciar:loja")
    contexto = {"form": form, "cfg": cfg, "status": status_loja(), "modos": Configuracao.MODOS}
    return render(request, "gerenciar/loja.html", contexto)


@dono_obrigatorio
@require_http_methods(["GET", "POST"])
def horarios(request):
    """Os 7 dias da semana: abre neste dia?, hora de abrir e de fechar."""
    for dia in range(7):  # garante uma linha por dia (loja nova ainda sem horários)
        Horario.objects.get_or_create(dia_semana=dia, defaults={"abre": time(18, 0), "fecha": time(22, 30), "ativo": False})
    fila = Horario.objects.order_by("dia_semana")
    formset = HorarioFormSet(request.POST or None, queryset=fila)
    if request.method == "POST" and formset.is_valid():
        formset.save()
        messages.success(request, "Horários salvos!")
        return redirect("gerenciar:horarios")
    return render(request, "gerenciar/horarios.html", {"formset": formset})


def _form_novo():
    """Formulário vazio de "novo bairro" (já marcado como ativo)."""
    return BairroForm(auto_id="novo_%s", initial={"ativo": True})


def _pagina_bairros(request, novo, editado=None):
    """Monta a página com um formulário pequeno por bairro. `editado` = (pk, form com erro)."""
    linhas = []
    for b in Bairro.objects.all():
        form = editado[1] if editado and editado[0] == b.pk else BairroForm(instance=b, auto_id=f"b{b.pk}_%s")
        linhas.append((b, form))
    return render(request, "gerenciar/bairros.html", {"linhas": linhas, "novo": novo})


@dono_obrigatorio
@require_http_methods(["GET", "POST"])
def bairros(request):
    """Lista os bairros e cria um novo (POST)."""
    if request.method == "POST":
        novo = BairroForm(request.POST, auto_id="novo_%s")
        if novo.is_valid():
            b = novo.save()
            messages.success(request, f"Bairro “{b.nome}” criado!")
            return redirect("gerenciar:bairros")
        return _pagina_bairros(request, novo)
    return _pagina_bairros(request, _form_novo())


@dono_obrigatorio
@require_http_methods(["POST"])
def bairro_editar(request, pk):
    """Salva nome, taxa e ativo de um bairro (um formulário pequeno por linha)."""
    bairro = get_object_or_404(Bairro, pk=pk)
    form = BairroForm(request.POST, instance=bairro, auto_id=f"b{pk}_%s")
    if form.is_valid():
        form.save()
        messages.success(request, f"Bairro “{bairro.nome}” salvo!")
        return redirect("gerenciar:bairros")
    return _pagina_bairros(request, _form_novo(), editado=(pk, form))


@dono_obrigatorio
def bairro_excluir(request, pk):
    """GET pede confirmação; POST apaga. Pedidos antigos guardam nome e taxa copiados."""
    bairro = get_object_or_404(Bairro, pk=pk)
    if request.method == "POST":
        nome = bairro.nome
        bairro.delete()
        messages.success(request, f"Bairro “{nome}” excluído.")
        return redirect("gerenciar:bairros")
    return render(request, "gerenciar/bairro_excluir.html", {"bairro": bairro})


@dono_obrigatorio
@require_http_methods(["GET", "POST"])
def pagamentos(request):
    """Edita as formas de pagamento que já existem: acréscimo % e onde cada uma vale."""
    formset = PagamentoFormSet(request.POST or None, queryset=FormaPagamento.objects.order_by("ordem"))
    if request.method == "POST" and formset.is_valid():
        formset.save()
        messages.success(request, "Formas de pagamento salvas!")
        return redirect("gerenciar:pagamentos")
    return render(request, "gerenciar/pagamentos.html", {"formset": formset})
