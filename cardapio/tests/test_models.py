from datetime import date, timedelta

from cardapio.models import Opcao


def test_produto_esgotado_volta_no_dia_seguinte(produto):
    hoje = date(2026, 11, 14)
    produto.esgotado_em = hoje
    assert produto.esta_esgotado(hoje) is True
    assert produto.esta_esgotado(hoje + timedelta(days=1)) is False


def test_produto_sem_esgotado_nao_esta_esgotado(produto):
    assert produto.esta_esgotado(date(2026, 11, 14)) is False


def test_opcao_esgotada_volta_no_dia_seguinte(grupo_varias):
    hoje = date(2026, 11, 14)
    bacon = Opcao.objects.create(grupo=grupo_varias, nome="Bacon", esgotado_em=hoje)
    assert bacon.esta_esgotada(hoje) is True
    assert bacon.esta_esgotada(hoje + timedelta(days=1)) is False


def test_foto_usa_url_do_olaclick_quando_sem_imagem(produto):
    produto.foto_url = "https://x/a.jpg"
    assert produto.foto == "https://x/a.jpg"


def test_foto_prefere_imagem_enviada(produto):
    produto.foto_url = "https://x/a.jpg"
    produto.imagem.name = "produtos/b.jpg"
    assert produto.foto.endswith("/media/produtos/b.jpg")
