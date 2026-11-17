from django.urls import path

from . import views_acompanhar, views_checkout

app_name = "pedidos"

urlpatterns = [
    path("checkout/", views_checkout.checkout, name="checkout"),
    path("checkout/enviar/", views_checkout.enviar, name="enviar"),
    path("pedido/<str:codigo>/", views_acompanhar.acompanhar, name="acompanhar"),
    path("pedido/<str:codigo>/status/", views_acompanhar.status, name="status"),
]
