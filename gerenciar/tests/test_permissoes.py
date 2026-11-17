"""Toda tela e ação de /gerenciar/ exige login; a maioria só para o Dono, o painel também para a Equipe."""
from types import SimpleNamespace

import pytest
from django.urls import URLResolver, get_resolver

from cardapio.models import Categoria, GrupoOpcao, Produto
from loja.models import Bairro

# (nome da URL, métodos, objeto que vai no endereço, quem acessa: "equipe" ou "dono")
ROTAS = [
    ("pedidos", ["get"], None, "equipe"),
    ("pedidos_colunas", ["get"], None, "equipe"),
    ("pedido_avancar", ["post"], "pedido", "equipe"),
    ("pedido", ["get"], "pedido", "equipe"),
    ("pedido_voltar", ["post"], "pedido", "equipe"),
    ("pedido_aceitar", ["post"], "pedido", "equipe"),
    ("pedido_recusar", ["post"], "pedido", "equipe"),
    ("pedido_comecar", ["post"], "pedido", "equipe"),
    ("pedido_pago", ["post"], "pedido", "equipe"),
    ("pedido_cancelar", ["post"], "pedido", "dono"),
    ("pedidos_finalizar", ["post"], None, "equipe"),
    ("lista", ["get"], None, "dono"),
    ("novo", ["get", "post"], None, "dono"),
    ("editar", ["get", "post"], "produto", "dono"),
    ("visivel", ["post"], "produto", "dono"),
    ("excluir", ["get", "post"], "produto", "dono"),
    ("mover", ["post"], "produto", "dono"),
    ("categorias", ["get", "post"], None, "dono"),
    ("categoria_renomear", ["post"], "categoria", "dono"),
    ("categoria_visivel", ["post"], "categoria", "dono"),
    ("categoria_mover", ["post"], "categoria", "dono"),
    ("categoria_excluir", ["post"], "categoria", "dono"),
    ("grupos", ["get"], None, "dono"),
    ("grupo_novo", ["get", "post"], None, "dono"),
    ("grupo_editar", ["get", "post"], "grupo", "dono"),
    ("grupo_excluir", ["get", "post"], "grupo", "dono"),
    ("loja", ["get", "post"], None, "dono"),
    ("horarios", ["get", "post"], None, "dono"),
    ("bairros", ["get", "post"], None, "dono"),
    ("bairro_editar", ["post"], "bairro", "dono"),
    ("bairro_excluir", ["get", "post"], "bairro", "dono"),
    ("pagamentos", ["get", "post"], None, "dono"),
]
CASOS = [(nome, m) for nome, metodos, _, _ in ROTAS for m in metodos]
CASOS_ACESSO = [(nome, m, acesso) for nome, metodos, _, acesso in ROTAS for m in metodos]


def nomes_das_rotas(resolver, prefixo=""):
    """Percorre includes para que uma nova rota também exija teste de acesso."""
    for rota in resolver.url_patterns:
        if isinstance(rota, URLResolver):
            namespace = f"{rota.namespace}:" if rota.namespace else ""
            yield from nomes_das_rotas(rota, prefixo + namespace)
        else:
            assert rota.name, f"Rota sem nome em gerenciar: {rota.pattern}"
            yield prefixo + rota.name


def test_todas_rotas_gerenciar_tem_cobertura():
    _, resolver = get_resolver().namespace_dict["gerenciar"]
    nomes = list(nomes_das_rotas(resolver))
    assert len(nomes) == len(set(nomes)), "Cada rota precisa de nome próprio para testar seu acesso."
    protegidas = {nome for nome, _, _, _ in ROTAS}
    assert set(nomes) == protegidas | {"entrar", "sair"}


@pytest.fixture
def url_de(db):
    from django.urls import reverse

    c = Categoria.objects.create(nome="C", ordem=1)
    objetos = {
        "produto": Produto.objects.create(categoria=c, slug="p", nome="P", preco=1),
        "categoria": c,
        "grupo": GrupoOpcao.objects.create(codigo="g", nome="G", tipo="varias", maximo=2),
        "bairro": Bairro.objects.create(nome="B", taxa=1),
        # pedido que não existe: o acesso é checado antes da busca, então 302/403 já vêm antes do 404
        "pedido": SimpleNamespace(pk=999999),
    }
    quem = {nome: alvo for nome, _, alvo, _ in ROTAS}

    def _url(nome):
        alvo = quem[nome]
        return reverse(f"gerenciar:{nome}", args=[objetos[alvo].pk] if alvo else [])
    return _url


@pytest.mark.parametrize("nome,metodo", CASOS)
def test_anonimo_vai_para_entrar(client, url_de, nome, metodo):
    r = getattr(client, metodo)(url_de(nome))
    assert r.status_code == 302 and r.url.startswith("/gerenciar/entrar/")


@pytest.mark.parametrize("nome,metodo", CASOS)
def test_usuario_comum_recebe_403(client, usuario_comum, url_de, nome, metodo):
    client.force_login(usuario_comum)
    assert getattr(client, metodo)(url_de(nome)).status_code == 403


@pytest.mark.parametrize("nome,metodo,acesso", CASOS_ACESSO)
def test_equipe_so_entra_nas_rotas_de_equipe(client_equipe, url_de, nome, metodo, acesso):
    status = getattr(client_equipe, metodo)(url_de(nome)).status_code
    if acesso == "dono":
        assert status == 403
    else:
        assert status != 403
