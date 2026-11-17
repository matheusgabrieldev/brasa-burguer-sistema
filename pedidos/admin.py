"""Admin do pedido: só leitura (quem muda status é o painel da loja)."""
from django.contrib import admin

from .models import HistoricoStatus, ItemPedido, Pedido


class SomenteLeitura:
    """Mistura que tira os botões de adicionar, alterar e apagar."""

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class ItemInline(SomenteLeitura, admin.TabularInline):
    model = ItemPedido
    extra = 0


class HistoricoInline(SomenteLeitura, admin.TabularInline):
    model = HistoricoStatus
    extra = 0


@admin.register(Pedido)
class PedidoAdmin(SomenteLeitura, admin.ModelAdmin):
    list_display = ("numero", "dia", "nome", "tipo", "status", "total")
    list_filter = ("status", "tipo", "origem")
    search_fields = ("nome", "telefone", "codigo")
    inlines = [ItemInline, HistoricoInline]

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields]
