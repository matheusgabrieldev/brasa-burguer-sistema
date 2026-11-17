from django.contrib import admin

from .models import Bairro, Configuracao, FormaPagamento, Horario


@admin.register(Configuracao)
class ConfiguracaoAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not Configuracao.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Horario)
class HorarioAdmin(admin.ModelAdmin):
    list_display = ["dia_semana", "abre", "fecha", "ativo"]
    list_editable = ["abre", "fecha", "ativo"]


@admin.register(Bairro)
class BairroAdmin(admin.ModelAdmin):
    list_display = ["nome", "taxa", "ativo"]
    list_editable = ["taxa", "ativo"]
    search_fields = ["nome"]


@admin.register(FormaPagamento)
class FormaPagamentoAdmin(admin.ModelAdmin):
    list_display = ["nome", "acrescimo_pct", "aceita_delivery", "aceita_retirada", "aceita_local", "ordem"]
    list_editable = ["acrescimo_pct", "aceita_delivery", "aceita_retirada", "aceita_local", "ordem"]
