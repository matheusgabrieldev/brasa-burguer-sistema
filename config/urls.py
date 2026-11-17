from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from loja.views import saude

urlpatterns = [
    path("admin/", admin.site.urls),
    path("saude/", saude),
    path("gerenciar/", include("gerenciar.urls")),
    path("", include("pedidos.urls")),
    path("", include("cardapio.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
