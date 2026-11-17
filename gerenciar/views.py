"""Área do Dono (/gerenciar/): a Ana cuida de produtos e categorias pelo celular.

Para criar o login dela:  python manage.py createsuperuser
(superusuário já conta como Dono; outros usuários precisam estar no grupo "Dono").
"""
from django.contrib import messages
from django.db import transaction
from django.db.models import Max
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from cardapio.models import Categoria, GrupoOpcao, Produto, ProdutoGrupo

from .forms import CategoriaForm, ProdutoForm
from .permissoes import dono_obrigatorio


# ---------------------------------------------------------------------------
# Ajudantes
# ---------------------------------------------------------------------------
def mover(itens, alvo, direcao):
    """Troca a posição (`ordem`) de `alvo` com a do vizinho, dentro da lista `itens`.

    `itens` é um queryset já ordenado (ex.: produtos da mesma categoria). Antes de trocar,
    renumeramos tudo de 0 a n-1: assim itens com a mesma ordem (empate) não atrapalham.
    """
    lista = list(itens)
    for i, item in enumerate(lista):
        if item.ordem != i:
            item.ordem = i
            item.save(update_fields=["ordem"])
    posicao = next(i for i, item in enumerate(lista) if item.pk == alvo.pk)
    vizinho = posicao - 1 if direcao == "cima" else posicao + 1
    if 0 <= vizinho < len(lista):
        a, b = lista[posicao], lista[vizinho]
        a.ordem, b.ordem = b.ordem, a.ordem
        a.save(update_fields=["ordem"])
        b.save(update_fields=["ordem"])


def _direcao(request):
    d = request.POST.get("direcao")
    return d if d in ("cima", "baixo") else None


def _fim_da_categoria(categoria):
    return (categoria.produtos.aggregate(m=Max("ordem"))["m"] or 0) + 1


# ---------------------------------------------------------------------------
# Produtos
# ---------------------------------------------------------------------------
@dono_obrigatorio
def lista(request):
    """Todos os produtos agrupados por categoria, com busca pelo nome."""
    q = request.GET.get("q", "").strip()
    categorias = []
    for c in Categoria.objects.all():
        produtos = c.produtos.order_by("ordem", "id")
        if q:
            produtos = produtos.filter(nome__icontains=q)
        produtos = list(produtos)
        if produtos or not q:
            categorias.append({"categoria": c, "produtos": produtos})
    return render(request, "gerenciar/lista.html", {"categorias": categorias, "q": q})


def _numero(texto, padrao):
    """Lê um número inteiro digitado; se não for número (ex.: "1e2"), usa o padrão."""
    texto = str(texto or "")
    return int(texto) if texto.isdigit() else padrao


def _apagar_foto(nome, exceto_pk=None):
    """Apaga o arquivo da foto do disco, mas só se nenhum outro produto ainda usar o mesmo arquivo."""
    if nome and not Produto.objects.filter(imagem=nome).exclude(pk=exceto_pk).exists():
        Produto._meta.get_field("imagem").storage.delete(nome)


def _grupos_para_tela(produto, post=None):
    """Grupos de opção para marcar, com a ordem atual. Os do produto vêm primeiro, na ordem dele."""
    ligados = {}
    if post is not None:
        for i, gid in enumerate(post.getlist("grupos"), start=1):
            if gid.isdigit():
                ligados[int(gid)] = _numero(post.get(f"ordem_{gid}"), i)
    elif produto and produto.pk:
        ligados = {pg.grupo_id: pg.ordem for pg in produto.produtogrupo_set.all()}
    todos = list(GrupoOpcao.objects.prefetch_related("opcoes"))
    todos.sort(key=lambda g: (g.id not in ligados, ligados.get(g.id, 0), g.nome))
    return [{"grupo": g, "marcado": g.id in ligados, "ordem": ligados.get(g.id, "")} for g in todos]


def _salvar_grupos(produto, post):
    """Regrava a ligação produto <-> grupos. A ordem vem do número ao lado de cada grupo
    marcado (se faltar, vale a posição na tela)."""
    validos = set(GrupoOpcao.objects.values_list("id", flat=True))
    escolhidos = []
    for posicao, gid in enumerate(post.getlist("grupos")):
        if not gid.isdigit() or int(gid) not in validos or int(gid) in [g for g, _ in escolhidos]:
            continue
        escolhidos.append((int(gid), _numero(post.get(f"ordem_{gid}"), posicao + 1)))
    escolhidos.sort(key=lambda par: par[1])
    ProdutoGrupo.objects.filter(produto=produto).delete()
    for ordem, (gid, _) in enumerate(escolhidos, start=1):
        ProdutoGrupo.objects.create(produto=produto, grupo_id=gid, ordem=ordem)


@dono_obrigatorio
def editar(request, pk=None):
    """Cria (sem pk) ou edita um produto."""
    produto = get_object_or_404(Produto, pk=pk) if pk else None
    categoria_antiga = produto.categoria_id if produto else None
    foto_antiga = produto.imagem.name if produto else ""
    if request.method == "POST":
        form = ProdutoForm(request.POST, request.FILES, instance=produto)
        if form.is_valid():
            with transaction.atomic():
                novo = produto is None
                p = form.save(commit=False)
                if novo or p.categoria_id != categoria_antiga:  # vai para o fim da categoria
                    p.ordem = _fim_da_categoria(p.categoria)
                p.save()
                _salvar_grupos(p, request.POST)
            if foto_antiga and p.imagem.name != foto_antiga:  # foto trocada ou removida
                _apagar_foto(foto_antiga, exceto_pk=p.pk)
            messages.success(request, f"“{p.nome}” {'adicionado' if novo else 'salvo'}!")
            return redirect("gerenciar:lista")
        grupos = _grupos_para_tela(produto, request.POST)
    else:
        form = ProdutoForm(instance=produto)
        grupos = _grupos_para_tela(produto)
    return render(request, "gerenciar/produto.html", {"form": form, "produto": produto, "grupos": grupos})


@dono_obrigatorio
@require_POST
def alternar_visivel(request, pk):
    """Esconde ou mostra o produto no cardápio (ex.: acabou o pão). Com HTMX troca só a linha."""
    p = get_object_or_404(Produto, pk=pk)
    p.visivel = not p.visivel
    p.save(update_fields=["visivel"])
    if request.headers.get("HX-Request"):
        ids = list(Produto.objects.filter(categoria_id=p.categoria_id).order_by("ordem", "id").values_list("id", flat=True))
        return render(request, "gerenciar/_produto_linha.html", {"p": p, "primeiro": ids[0] == p.pk, "ultimo": ids[-1] == p.pk})
    messages.success(request, f"“{p.nome}” {'voltou ao cardápio' if p.visivel else 'foi escondido do cardápio'}.")
    return redirect(reverse("gerenciar:lista") + f"#p{p.pk}")


@dono_obrigatorio
def excluir(request, pk):
    """GET mostra a tela "tem certeza?"; POST apaga de verdade."""
    p = get_object_or_404(Produto, pk=pk)
    if request.method == "POST":
        nome, foto = p.nome, p.imagem.name
        p.delete()
        _apagar_foto(foto)  # pedidos antigos continuam: o item do pedido guarda nome e preço
        messages.success(request, f"“{nome}” foi excluído.")
        return redirect("gerenciar:lista")
    return render(request, "gerenciar/confirmar_exclusao.html", {"produto": p})


@dono_obrigatorio
@require_POST
def mover_produto(request, pk):
    p = get_object_or_404(Produto, pk=pk)
    direcao = _direcao(request)
    if direcao:
        mover(Produto.objects.filter(categoria_id=p.categoria_id).order_by("ordem", "id"), p, direcao)
    return redirect(reverse("gerenciar:lista") + f"#p{p.pk}")


# ---------------------------------------------------------------------------
# Categorias
# ---------------------------------------------------------------------------
@dono_obrigatorio
def categorias(request):
    """Lista as categorias e cria uma nova (POST)."""
    if request.method == "POST":
        form = CategoriaForm(request.POST)
        if form.is_valid():
            c = form.save(commit=False)
            c.ordem = (Categoria.objects.aggregate(m=Max("ordem"))["m"] or 0) + 1
            c.save()
            messages.success(request, f"Categoria “{c.nome}” criada.")
            return redirect("gerenciar:categorias")
    else:
        form = CategoriaForm()
    lista_cats = Categoria.objects.prefetch_related("produtos")
    return render(request, "gerenciar/categorias.html", {"categorias": lista_cats, "form": form})


@dono_obrigatorio
@require_POST
def categoria_renomear(request, pk):
    c = get_object_or_404(Categoria, pk=pk)
    form = CategoriaForm(request.POST, instance=c)
    if form.is_valid():
        form.save()
        messages.success(request, "Nome alterado.")
    else:
        messages.error(request, "Digite um nome para a categoria.")
    return redirect("gerenciar:categorias")


@dono_obrigatorio
@require_POST
def categoria_visivel(request, pk):
    c = get_object_or_404(Categoria, pk=pk)
    c.visivel = not c.visivel
    c.save(update_fields=["visivel"])
    messages.success(request, f"“{c.nome}” {'voltou ao cardápio' if c.visivel else 'foi escondida do cardápio'}.")
    return redirect("gerenciar:categorias")


@dono_obrigatorio
@require_POST
def categoria_mover(request, pk):
    c = get_object_or_404(Categoria, pk=pk)
    direcao = _direcao(request)
    if direcao:
        mover(Categoria.objects.order_by("ordem", "id"), c, direcao)
    return redirect("gerenciar:categorias")


@dono_obrigatorio
@require_POST
def categoria_excluir(request, pk):
    """Só exclui categoria vazia (os produtos têm que ser movidos ou excluídos antes)."""
    c = get_object_or_404(Categoria, pk=pk)
    if c.produtos.exists():
        messages.error(request, "Mova ou exclua os produtos antes de excluir a categoria.")
    else:
        c.delete()
        messages.success(request, f"Categoria “{c.nome}” excluída.")
    return redirect("gerenciar:categorias")
