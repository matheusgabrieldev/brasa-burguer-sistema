from urllib.parse import parse_qs, urlparse

from pedidos.mensagens_status import (
    MENSAGENS,
    atalho_depois_de,
    link_cliente,
    mensagem_status,
    mensagens_disponiveis,
)
from pedidos.models import Pedido


def _pedido(tipo="delivery", status="preparo", motivo=""):
    return Pedido(
        nome="Ana", numero=7, telefone="81988887777",
        tipo=tipo, status=status, motivo_cancelamento=motivo,
    )


def test_textos_exatos():
    p = _pedido(motivo="Sem estoque")
    assert mensagem_status(p, "aceito") == "✅ Oi Ana, seu pedido Nº 7 foi aceito. Estamos preparando tudo."
    assert mensagem_status(p, "saiu") == "🛵 Seu pedido Nº 7 já está a caminho, Ana."
    assert mensagem_status(p, "pronto") == "🛍️ Seu pedido Nº 7 está pronto, Ana. Pode vir buscar!"
    assert mensagem_status(p, "falar") == "Olá, Ana! Aqui é da Brasa Burguer, sobre o seu pedido Nº 7: "
    assert mensagem_status(p, "cancelado") == "🚫 Lamentamos informar que o pedido Nº 7 foi cancelado. Motivo: Sem estoque."
    assert set(MENSAGENS) == {"aceito", "pronto", "saiu", "falar", "cancelado"}


def test_cancelado_sem_motivo():
    assert mensagem_status(_pedido(), "cancelado") == "🚫 Lamentamos informar que o pedido Nº 7 foi cancelado."


def test_link_tem_55_e_texto_codificado():
    p = _pedido()
    link = link_cliente(p, "saiu")
    assert link.startswith("https://wa.me/5581988887777?text=")
    assert " " not in link
    assert parse_qs(urlparse(link).query)["text"] == [mensagem_status(p, "saiu")]


def _chaves(p):
    return [c for c, _ in mensagens_disponiveis(p)]


def test_disponiveis_por_tipo():
    assert _chaves(_pedido("delivery")) == ["aceito", "saiu", "falar"]
    assert _chaves(_pedido("retirada")) == ["aceito", "pronto", "falar"]
    assert _chaves(_pedido("local")) == ["falar"]
    assert _chaves(_pedido("delivery", "cancelado")) == ["falar", "cancelado"]
    assert _chaves(_pedido("retirada", "cancelado")) == ["falar", "cancelado"]
    assert _chaves(_pedido("local", "cancelado")) == ["falar"]
    assert dict(mensagens_disponiveis(_pedido("retirada")))["pronto"] == "Pronto p/ retirada"
    assert dict(mensagens_disponiveis(_pedido("delivery")))["saiu"] == "Saiu p/ entrega"


def test_atalho_depois_de():
    assert atalho_depois_de(_pedido("retirada", "pronto")) == ("pronto", "Pronto p/ retirada")
    assert atalho_depois_de(_pedido("delivery", "pronto")) is None
    assert atalho_depois_de(_pedido("delivery", "saiu"))[0] == "saiu"
    assert atalho_depois_de(_pedido("retirada", "cancelado"))[0] == "cancelado"
    assert atalho_depois_de(_pedido("local", "cancelado")) is None
    assert atalho_depois_de(_pedido("delivery", "preparo")) is None
