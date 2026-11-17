from django.urls import path

from . import views

urlpatterns = [
    path("", views.cardapio, name="cardapio"),
    path("produto/<slug:slug>/", views.produto_modal, name="produto_modal"),
    path("sacola/validar/", views.validar_sacola, name="validar_sacola"),
]
