from loja.models import Configuracao


def test_configuracao_e_linha_unica(db):
    assert Configuracao.atual().pk == Configuracao.atual().pk == 1
    assert Configuracao.objects.count() == 1


def test_configuracao_padrao_pelo_horario(db):
    assert Configuracao.atual().modo_loja == "auto"
