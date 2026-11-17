from django.contrib import admin

from .models import Categoria, GrupoOpcao, Opcao, Produto, ProdutoGrupo


class ProdutoGrupoInline(admin.TabularInline):
    model = ProdutoGrupo
    extra = 0


class OpcaoInline(admin.TabularInline):
    model = Opcao
    extra = 0


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ["nome", "ordem", "visivel"]
    list_editable = ["ordem", "visivel"]


@admin.register(Produto)
class ProdutoAdmin(admin.ModelAdmin):
    list_display = ["nome", "categoria", "preco", "visivel", "destaque", "mais_pedido", "esgotado_em"]
    list_filter = ["categoria", "visivel", "destaque"]
    list_editable = ["preco", "visivel"]
    search_fields = ["nome"]
    prepopulated_fields = {"slug": ["nome"]}
    inlines = [ProdutoGrupoInline]


@admin.register(GrupoOpcao)
class GrupoOpcaoAdmin(admin.ModelAdmin):
    list_display = ["nome", "tipo", "minimo", "maximo", "obrigatorio"]
    inlines = [OpcaoInline]
