"""Testes de clientes e do 'Lembrar de mim'."""
import pytest

from clientes import servicos
from clientes.models import Cliente, Dispositivo, EnderecoSalvo


@pytest.mark.parametrize(
    "entrada, saida",
    [("(81) 9 8888-7777", "81988887777"), ("+55 81 98888-7777", "81988887777"), ("8133334444", "8133334444")],
)
def test_normalizar_telefone(entrada, saida):
    assert servicos.normalizar_telefone(entrada) == saida


@pytest.mark.parametrize("entrada", ["", "98888-7777", "123", None])
def test_telefone_sem_ddd_da_erro(entrada):
    with pytest.raises(ValueError, match="Informe o WhatsApp com DDD"):
        servicos.normalizar_telefone(entrada)


def test_formatar_telefone():
    assert servicos.formatar_telefone("81988887777") == "(81) 98888-7777"
    assert servicos.formatar_telefone("8133334444") == "(81) 3333-4444"


def test_cliente_existente_nao_troca_nome(db):
    a = servicos.cliente_do_telefone("(81) 98888-7777", "Maria")
    b = servicos.cliente_do_telefone("81988887777", "Outro Nome")
    assert a.pk == b.pk and b.nome == "Maria"
    assert Cliente.objects.count() == 1


def test_lembrar_cria_token_e_nao_duplica_endereco(db, bairro):
    token = servicos.lembrar(None, "Maria", "81988887777", bairro, "Rua A", "10", "perto da padaria")
    assert token
    mesmo = servicos.lembrar(token, "Maria S.", "81988887777", bairro, "  rua a ", "10", "portão azul")
    assert mesmo == token
    assert Dispositivo.objects.count() == 1
    assert EnderecoSalvo.objects.count() == 1
    end = EnderecoSalvo.objects.get()
    assert end.referencia == "portão azul"
    assert servicos.dispositivo_do_token(token).nome == "Maria S."
    servicos.lembrar(token, "Maria S.", "81988887777", bairro, "Rua B", "5", "")
    assert EnderecoSalvo.objects.count() == 2


def test_token_desconhecido_cria_novo_dispositivo(db, bairro):
    token = servicos.lembrar("token-falso", "Ana", "81988887777", bairro, "Rua A", "1", "")
    assert token != "token-falso"
    assert Dispositivo.objects.count() == 1


def test_token_errado_nao_acha_dispositivo(db):
    assert servicos.dispositivo_do_token("nada") is None
    assert servicos.dispositivo_do_token(None) is None
    assert servicos.dispositivo_do_token("") is None


def test_token_guardado_so_como_hash(db, bairro):
    token = servicos.lembrar(None, "Maria", "81988887777", bairro, "Rua A", "10", "")
    disp = Dispositivo.objects.get()
    assert disp.token_hash != token
    assert len(disp.token_hash) == 64
    assert servicos.dispositivo_do_token(token) == disp


def test_telefone_nao_acha_dispositivo(db, bairro):
    """Saber o telefone de alguém não revela o endereço dela."""
    servicos.lembrar(None, "Maria", "81988887777", bairro, "Rua A", "10", "")
    assert servicos.dispositivo_do_token("81988887777") is None


def test_lembrar_atualiza_usado_em(db, bairro):
    token = servicos.lembrar(None, "Maria", "81988887777", bairro, "Rua A", "10", "")
    antes = Dispositivo.objects.get().usado_em
    servicos.lembrar(token, "Maria", "81988887777", bairro, "Rua A", "10", "")
    assert Dispositivo.objects.get().usado_em >= antes


def test_lembrar_sem_endereco_guarda_so_nome_e_telefone(db):
    """Retirada / no local: lembra quem é, sem criar endereço vazio."""
    token = servicos.lembrar(None, "Maria", "81988887777", None, "", "", "")
    disp = servicos.dispositivo_do_token(token)
    assert disp.nome == "Maria" and not disp.enderecos.exists()


def test_gravar_cookie_seguro_fora_do_debug(settings):
    from django.http import HttpResponse

    settings.DEBUG = False
    r = HttpResponse()
    servicos.gravar_cookie(r, "abc")
    c = r.cookies[servicos.COOKIE_DISPOSITIVO]
    assert c.value == "abc" and c["httponly"] and c["secure"] and c["samesite"] == "Lax"
    assert c["max-age"] == servicos.COOKIE_MAX_AGE
    settings.DEBUG = True
    r = HttpResponse()
    servicos.gravar_cookie(r, "abc")
    assert not r.cookies[servicos.COOKIE_DISPOSITIVO]["secure"]
