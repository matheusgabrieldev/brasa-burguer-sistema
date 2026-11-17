from django.contrib import admin

from .models import Cliente


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ("nome", "telefone", "bloqueado", "criado_em")
    list_filter = ("bloqueado",)
    search_fields = ("telefone", "nome")
