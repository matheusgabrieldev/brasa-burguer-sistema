from django.http import HttpResponse


def saude(request):
    """O servidor (Railway) chama esta página para saber se o sistema está de pé."""
    return HttpResponse("ok", content_type="text/plain")
