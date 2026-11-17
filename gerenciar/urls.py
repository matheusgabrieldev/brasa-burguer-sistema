from django.contrib.auth import views as auth_views
from django.urls import path

from . import views, views_grupos, views_loja, views_pedido_acoes, views_pedidos

app_name = "gerenciar"

urlpatterns = [
    path("entrar/", auth_views.LoginView.as_view(template_name="gerenciar/entrar.html", redirect_authenticated_user=True), name="entrar"),
    path("sair/", auth_views.LogoutView.as_view(), name="sair"),  # só aceita POST
    path("", views_pedidos.painel, name="pedidos"),  # primeira tela depois de entrar (Dono e Equipe)
    path("pedidos/colunas/", views_pedidos.colunas, name="pedidos_colunas"),
    path("pedidos/finalizar/", views_pedido_acoes.pedidos_finalizar, name="pedidos_finalizar"),
    path("pedido/<int:pk>/", views_pedido_acoes.pedido, name="pedido"),
    path("pedido/<int:pk>/avancar/", views_pedido_acoes.pedido_avancar, name="pedido_avancar"),
    path("pedido/<int:pk>/voltar/", views_pedido_acoes.pedido_voltar, name="pedido_voltar"),
    path("pedido/<int:pk>/aceitar/", views_pedido_acoes.pedido_aceitar, name="pedido_aceitar"),
    path("pedido/<int:pk>/recusar/", views_pedido_acoes.pedido_recusar, name="pedido_recusar"),
    path("pedido/<int:pk>/comecar/", views_pedido_acoes.pedido_comecar, name="pedido_comecar"),
    path("pedido/<int:pk>/pago/", views_pedido_acoes.pedido_pago, name="pedido_pago"),
    path("pedido/<int:pk>/cancelar/", views_pedido_acoes.pedido_cancelar, name="pedido_cancelar"),
    path("produtos/", views.lista, name="lista"),
    path("produto/novo/", views.editar, name="novo"),
    path("produto/<int:pk>/", views.editar, name="editar"),
    path("produto/<int:pk>/visivel/", views.alternar_visivel, name="visivel"),
    path("produto/<int:pk>/excluir/", views.excluir, name="excluir"),
    path("produto/<int:pk>/mover/", views.mover_produto, name="mover"),
    path("categorias/", views.categorias, name="categorias"),
    path("categorias/<int:pk>/renomear/", views.categoria_renomear, name="categoria_renomear"),
    path("categorias/<int:pk>/visivel/", views.categoria_visivel, name="categoria_visivel"),
    path("categorias/<int:pk>/mover/", views.categoria_mover, name="categoria_mover"),
    path("categorias/<int:pk>/excluir/", views.categoria_excluir, name="categoria_excluir"),
    path("grupos/", views_grupos.grupos, name="grupos"),
    path("grupo/novo/", views_grupos.grupo_editar, name="grupo_novo"),
    path("grupo/<int:pk>/", views_grupos.grupo_editar, name="grupo_editar"),
    path("grupo/<int:pk>/excluir/", views_grupos.grupo_excluir, name="grupo_excluir"),
    path("loja/", views_loja.loja, name="loja"),
    path("loja/horarios/", views_loja.horarios, name="horarios"),
    path("loja/bairros/", views_loja.bairros, name="bairros"),
    path("loja/bairros/<int:pk>/", views_loja.bairro_editar, name="bairro_editar"),
    path("loja/bairros/<int:pk>/excluir/", views_loja.bairro_excluir, name="bairro_excluir"),
    path("loja/pagamentos/", views_loja.pagamentos, name="pagamentos"),
]
