from datetime import date, timedelta
from decimal import Decimal

import pytest

from cardapio.precos import PrecoInvalido, calcular_item


def test_preco_com_adicionais_vezes_quantidade(burger, bacon, ponto):
    item = calcular_item(burger.id, 2, {bacon.id: 2, ponto.id: 1})
    assert item.preco_unitario == Decimal("25.00")
    assert item.total == Decimal("50.00")
    # saem na ordem dos grupos do produto: ponto (unica) antes dos adicionais
    assert [(o.grupo, o.nome, o.qtd, o.preco) for o in item.opcoes] == [
        ("Escolha o ponto da carne", "Ao ponto", 1, Decimal("0.00")),
        ("Adicionais à parte", "Bacon", 2, Decimal("2.50")),
    ]


def test_obrigatorio_faltando(burger, bacon, ponto):
    with pytest.raises(PrecoInvalido, match="escolha uma opção em 'Escolha o ponto da carne'"):
        calcular_item(burger.id, 1, {bacon.id: 1})


def test_opcao_de_outro_produto(burger, batata, ponto):
    with pytest.raises(PrecoInvalido, match="Opção inválida"):
        calcular_item(burger.id, 1, {ponto.id: 1, batata.molho.id: 1})


def test_opcao_inexistente(burger, ponto):
    with pytest.raises(PrecoInvalido, match="Opção inválida"):
        calcular_item(burger.id, 1, {ponto.id: 1, 99999: 1})


def test_opcao_esgotada_hoje(burger, bacon, ponto):
    hoje = date(2026, 11, 10)
    bacon.esgotado_em = hoje
    bacon.save()
    with pytest.raises(PrecoInvalido, match="Bacon está esgotado"):
        calcular_item(burger.id, 1, {ponto.id: 1, bacon.id: 1}, hoje=hoje)
    # no dia seguinte volta sozinho
    item = calcular_item(burger.id, 1, {ponto.id: 1, bacon.id: 1}, hoje=hoje + timedelta(days=1))
    assert item.preco_unitario == Decimal("22.50")


def test_produto_esgotado_ou_oculto(burger, ponto):
    hoje = date(2026, 11, 10)
    burger.esgotado_em = hoje
    burger.save()
    with pytest.raises(PrecoInvalido, match="não está mais disponível"):
        calcular_item(burger.id, 1, {ponto.id: 1}, hoje=hoje)
    burger.esgotado_em = None
    burger.visivel = False
    burger.save()
    with pytest.raises(PrecoInvalido, match="não está mais disponível"):
        calcular_item(burger.id, 1, {ponto.id: 1}, hoje=hoje)
    with pytest.raises(PrecoInvalido, match="não está mais disponível"):
        calcular_item(99999, 1, {})


def test_unica_com_duas_escolhas(burger, ponto, mal_passado):
    with pytest.raises(PrecoInvalido, match="só uma opção"):
        calcular_item(burger.id, 1, {ponto.id: 1, mal_passado.id: 1})


def test_unica_com_qtd_dois(burger, ponto):
    ponto.qtd_maxima = 5  # mesmo permitindo repetir, grupo único aceita 1 unidade só
    ponto.save()
    with pytest.raises(PrecoInvalido, match="só uma opção"):
        calcular_item(burger.id, 1, {ponto.id: 2})


def test_qtd_acima_do_maximo(burger, bacon, ponto):
    with pytest.raises(PrecoInvalido, match="Bacon"):
        calcular_item(burger.id, 1, {ponto.id: 1, bacon.id: 4})


def test_qtd_da_opcao_zero_ou_negativa(burger, bacon, ponto):
    with pytest.raises(PrecoInvalido):
        calcular_item(burger.id, 1, {ponto.id: 1, bacon.id: 0})


def test_varias_acima_do_maximo_do_grupo(burger, grupo_varias, bacon, ponto):
    grupo_varias.maximo = 2
    grupo_varias.save()
    with pytest.raises(PrecoInvalido, match="no máximo 2"):
        calcular_item(burger.id, 1, {ponto.id: 1, bacon.id: 3})


def test_quantidade_limitada_de_1_a_50(burger, ponto):
    assert calcular_item(burger.id, 0, {ponto.id: 1}).quantidade == 1
    assert calcular_item(burger.id, 500, {ponto.id: 1}).quantidade == 50


def test_observacao_cortada_em_140(burger, ponto):
    item = calcular_item(burger.id, 1, {ponto.id: 1}, observacao="  " + "x" * 200)
    assert item.observacao == "x" * 140


@pytest.mark.parametrize("quantidade", ["abc", None])
def test_quantidade_malformada(burger, ponto, quantidade):
    with pytest.raises(PrecoInvalido, match="Pedido inválido"):
        calcular_item(burger.id, quantidade, {ponto.id: 1})


def test_chave_de_opcao_nao_numerica(burger):
    with pytest.raises(PrecoInvalido, match="Pedido inválido"):
        calcular_item(burger.id, 1, {"x": 1})


def test_valor_de_opcao_nulo(burger, ponto):
    with pytest.raises(PrecoInvalido, match="Pedido inválido"):
        calcular_item(burger.id, 1, {ponto.id: None})


def test_opcoes_none_cai_na_regra_do_obrigatorio(burger, ponto):
    with pytest.raises(PrecoInvalido, match="escolha uma opção em"):
        calcular_item(burger.id, 1, None)


def test_produto_id_malformado_ou_gigante(burger):
    for ruim in ("abc", None, 10**30):
        with pytest.raises(PrecoInvalido):
            calcular_item(ruim, 1, {})


def test_chaves_de_opcao_como_texto_numerico(burger, bacon, ponto):
    # o JSON do navegador manda as chaves como texto
    item = calcular_item(str(burger.id), "2", {str(ponto.id): "1", str(bacon.id): 1})
    assert item.preco_unitario == Decimal("22.50")
    assert item.quantidade == 2


def test_categoria_oculta(burger, categoria, ponto):
    categoria.visivel = False
    categoria.save()
    with pytest.raises(PrecoInvalido, match="não está mais disponível"):
        calcular_item(burger.id, 1, {ponto.id: 1})


def test_grupo_obrigatorio_esgotado_informa_indisponibilidade_e_recupera(burger, ponto):
    hoje = date(2026, 11, 10)
    ponto.esgotado_em = hoje
    ponto.save()
    with pytest.raises(PrecoInvalido, match="Indisponível no momento.*Escolha o ponto da carne"):
        calcular_item(burger.pk, 1, {}, hoje=hoje)
    assert calcular_item(burger.pk, 1, {ponto.pk: 1}, hoje=hoje + timedelta(days=1)).total == Decimal("20.00")


def test_capacidade_disponivel_abaixo_do_minimo_recusa_pedido(burger, grupo_varias, bacon, ponto):
    from cardapio.models import Opcao

    hoje = date(2026, 11, 10)
    grupo_varias.obrigatorio = True
    grupo_varias.minimo = grupo_varias.maximo = 4
    grupo_varias.save()
    ovo = Opcao.objects.create(grupo=grupo_varias, nome="Ovo", qtd_maxima=1, esgotado_em=hoje)
    with pytest.raises(PrecoInvalido, match="Indisponível no momento.*Adicionais"):
        calcular_item(burger.pk, 1, {ponto.pk: 1, bacon.pk: 3}, hoje=hoje)
    assert calcular_item(burger.pk, 1, {ponto.pk: 1, bacon.pk: 3, ovo.pk: 1}, hoje=hoje + timedelta(days=1)).total == Decimal("27.50")


def test_grupo_opcional_esgotado_permite_produto(burger, bacon, ponto):
    hoje = date(2026, 11, 10)
    bacon.esgotado_em = hoje
    bacon.save()
    assert calcular_item(burger.pk, 1, {ponto.pk: 1}, hoje=hoje).total == Decimal("20.00")
