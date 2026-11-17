"""Dados de teste reaproveitados em todos os testes (fixtures do pytest)."""
from datetime import time
from decimal import Decimal

import pytest


@pytest.fixture
def categoria(db):
    from cardapio.models import Categoria

    return Categoria.objects.create(nome="Burguers", ordem=1)


@pytest.fixture
def produto(categoria):
    from cardapio.models import Produto

    return Produto.objects.create(categoria=categoria, slug="le-premium", nome="Brasa Premium", preco=Decimal("20.00"))


@pytest.fixture
def grupo_unica(db):
    from cardapio.models import GrupoOpcao

    return GrupoOpcao.objects.create(codigo="ponto", nome="Escolha o ponto da carne", tipo="unica", minimo=1, maximo=1, obrigatorio=True)


@pytest.fixture
def grupo_varias(db):
    from cardapio.models import GrupoOpcao

    return GrupoOpcao.objects.create(codigo="adicionais", nome="Adicionais à parte", tipo="varias", minimo=0, maximo=30)


@pytest.fixture
def horarios(db):
    """Horário real da loja: qua–sáb 18:15–22:30, dom 18:00–22:30, seg e ter fechado."""
    from loja.models import Horario

    for dia in range(7):
        abre = time(18, 0) if dia == 6 else time(18, 15)
        Horario.objects.create(dia_semana=dia, abre=abre, fecha=time(22, 30), ativo=dia not in (0, 1))


@pytest.fixture
def burger(produto, grupo_unica, grupo_varias):
    from cardapio.models import ProdutoGrupo

    ProdutoGrupo.objects.create(produto=produto, grupo=grupo_unica, ordem=1)
    ProdutoGrupo.objects.create(produto=produto, grupo=grupo_varias, ordem=2)
    return produto


@pytest.fixture
def ponto(grupo_unica):
    from cardapio.models import Opcao

    return Opcao.objects.create(grupo=grupo_unica, nome="Ao ponto")


@pytest.fixture
def mal_passado(grupo_unica):
    from cardapio.models import Opcao

    return Opcao.objects.create(grupo=grupo_unica, nome="Mal passado")


@pytest.fixture
def bacon(grupo_varias):
    from cardapio.models import Opcao

    return Opcao.objects.create(grupo=grupo_varias, nome="Bacon", preco=Decimal("2.50"), qtd_maxima=3)


@pytest.fixture
def batata(categoria):
    """Produto com grupo próprio: suas opções não valem para o burger."""
    from cardapio.models import GrupoOpcao, Opcao, Produto, ProdutoGrupo

    p = Produto.objects.create(categoria=categoria, slug="batata", nome="Batata", preco=Decimal("10.00"))
    g = GrupoOpcao.objects.create(codigo="molho", nome="Molho", tipo="varias", maximo=2)
    ProdutoGrupo.objects.create(produto=p, grupo=g)
    p.molho = Opcao.objects.create(grupo=g, nome="Cheddar", preco=Decimal("3.00"))
    return p


@pytest.fixture
def bairro(db):
    from loja.models import Bairro

    return Bairro.objects.create(nome="Paratibe", taxa=Decimal("5"))


@pytest.fixture
def cenario(burger, ponto, bacon, horarios, bairro):
    """Loja pronta para receber pedido: burger com opções, horários, bairro e as 4 formas de pagamento.

    `cenario.dados(**mudar)` monta um pedido de delivery válido (2x burger ao ponto + 2 bacon,
    crédito). `cenario.aberta` / `cenario.fechada` são horários de Recife para passar em `agora`.
    """
    import uuid
    from datetime import datetime
    from types import SimpleNamespace
    from zoneinfo import ZoneInfo

    from loja.models import FormaPagamento

    formas = {}
    for i, (codigo, nome, pct) in enumerate([
        ("pix", "Pix", "0"), ("credito", "Cartão de crédito", "4"), ("debito", "Cartão de débito", "1"), ("dinheiro", "Dinheiro", "0"),
    ]):
        formas[codigo] = FormaPagamento.objects.create(codigo=codigo, nome=nome, acrescimo_pct=Decimal(pct), ordem=i)

    def dados(**mudar):
        base = {
            "chave": str(uuid.uuid4()), "tipo": "delivery", "nome": "Ana", "telefone": "(81) 98888-7777",
            "bairro_id": bairro.id, "rua": "Rua das Flores", "numero": "505", "referencia": "",
            "observacao": "", "pagamento": "credito", "troco_para": "", "agendar_para": "",
            "itens": [{"produto_id": burger.id, "quantidade": 2, "opcoes": {str(ponto.id): 1, str(bacon.id): 2}, "observacao": ""}],
        }
        base.update(mudar)
        return base

    recife = ZoneInfo("America/Recife")
    return SimpleNamespace(
        burger=burger, ponto=ponto, bacon=bacon, bairro=bairro, formas=formas, dados=dados,
        aberta=datetime(2026, 11, 11, 20, 0, tzinfo=recife),   # quarta, 18:15–22:30
        fechada=datetime(2026, 11, 16, 20, 0, tzinfo=recife),  # segunda (fechado) -> abre quarta 18/11
    )


def _usuario_no_grupo(username, grupo):
    from django.contrib.auth.models import Group, User

    usuario = User.objects.create_user(username, password="senha123")
    g, _ = Group.objects.get_or_create(name=grupo)
    usuario.groups.add(g)
    return usuario


@pytest.fixture
def usuario_dono(db):
    return _usuario_no_grupo("ana", "Dono")


@pytest.fixture
def usuario_equipe(db):
    return _usuario_no_grupo("atendente", "Equipe")
