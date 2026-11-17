from decimal import Decimal
from datetime import date

import pytest

from cardapio.models import GrupoOpcao, Opcao, Produto, ProdutoGrupo
from cardapio.precos import calcular_item


def post_grupo(opcoes=None, inicial=0, **extra):
    """Monta o POST do formulário de grupo + formset de opções (prefixo "opcoes")."""
    opcoes = opcoes if opcoes is not None else [{"nome": "Bacon", "preco": "2,50", "qtd_maxima": "3", "ordem": "1"}]
    dados = {"nome": "Adicionais", "tipo": "varias", "minimo": "0", "maximo": "3",
             "opcoes-TOTAL_FORMS": str(len(opcoes)), "opcoes-INITIAL_FORMS": str(inicial),
             "opcoes-MIN_NUM_FORMS": "0", "opcoes-MAX_NUM_FORMS": "1000"}
    for i, o in enumerate(opcoes):
        for campo, valor in o.items():
            dados[f"opcoes-{i}-{campo}"] = valor
    dados.update(extra)
    return dados


def linha_existente(op, **mudancas):
    d = {"id": str(op.id), "grupo": str(op.grupo_id), "nome": op.nome, "preco": str(op.preco).replace(".", ","),
         "qtd_maxima": str(op.qtd_maxima), "ordem": str(op.ordem)}
    d.update(mudancas)
    return d


def test_cria_grupo_com_opcoes(client_dono):
    r = client_dono.post("/gerenciar/grupo/novo/", post_grupo([
        {"nome": "Bacon", "preco": "2,50", "qtd_maxima": "3", "ordem": "1"},
        {"nome": "Cheddar", "preco": "3", "qtd_maxima": "1", "ordem": "2"},
    ]))
    assert r.status_code == 302
    g = GrupoOpcao.objects.get(nome="Adicionais")
    assert g.codigo == "adicionais"
    assert [(o.nome, o.preco, o.qtd_maxima) for o in g.opcoes.all()] == [
        ("Bacon", Decimal("2.50"), 3), ("Cheddar", Decimal("3.00"), 1)]


def test_codigo_repetido_ganha_sufixo(client_dono):
    for _ in range(2):
        client_dono.post("/gerenciar/grupo/novo/", post_grupo())
    assert sorted(GrupoOpcao.objects.values_list("codigo", flat=True)) == ["adicionais", "adicionais-2"]


def test_minimo_maior_que_maximo_da_erro(client_dono):
    r = client_dono.post("/gerenciar/grupo/novo/", post_grupo(minimo="4", maximo="2"))
    assert r.status_code == 200
    assert "mínimo não pode ser maior que o máximo" in r.content.decode()
    assert not GrupoOpcao.objects.exists()


def test_obrigatorio_exige_minimo_1(client_dono):
    r = client_dono.post("/gerenciar/grupo/novo/", post_grupo(obrigatorio="on", minimo="0"))
    assert r.status_code == 200
    assert "obrigatório precisa de mínimo" in r.content.decode()
    assert not GrupoOpcao.objects.exists()


def test_unica_forca_maximo_1(client_dono):
    client_dono.post("/gerenciar/grupo/novo/", post_grupo(tipo="unica", minimo="1", maximo="7"))
    g = GrupoOpcao.objects.get(nome="Adicionais")
    assert g.maximo == 1


def test_grupo_sem_opcao_e_recusado(client_dono):
    r = client_dono.post("/gerenciar/grupo/novo/", post_grupo([]))
    assert r.status_code == 200
    assert "pelo menos uma opção" in r.content.decode()
    assert not GrupoOpcao.objects.exists()


@pytest.mark.parametrize("campo,valor", [("preco", "abc"), ("preco", "-1"), ("qtd_maxima", "0"), ("nome", "")])
def test_opcao_invalida_e_recusada(client_dono, campo, valor):
    linha = {"nome": "Bacon", "preco": "2,50", "qtd_maxima": "3", "ordem": "1", campo: valor}
    r = client_dono.post("/gerenciar/grupo/novo/", post_grupo([linha]))
    assert r.status_code == 200
    assert not GrupoOpcao.objects.exists()


def test_editar_preco_da_opcao_reflete_no_calculo(client_dono, burger, bacon, ponto):
    g = bacon.grupo
    antes = calcular_item(burger.id, 1, {bacon.id: 1, ponto.id: 1}).total
    r = client_dono.post(f"/gerenciar/grupo/{g.id}/", post_grupo(
        [linha_existente(bacon, preco="3,00")], inicial=1, nome=g.nome, minimo="0", maximo="3"))
    assert r.status_code == 302
    bacon.refresh_from_db()
    assert bacon.preco == Decimal("3.00")
    assert calcular_item(burger.id, 1, {bacon.id: 1, ponto.id: 1}).total == antes + Decimal("0.50")


def test_editar_nao_muda_codigo_e_remove_linha(client_dono, bacon):
    g = bacon.grupo
    codigo = g.codigo
    extra = Opcao.objects.create(grupo=g, nome="Ovo", preco=1)
    client_dono.post(f"/gerenciar/grupo/{g.id}/", post_grupo(
        [linha_existente(bacon), linha_existente(extra, DELETE="on")], inicial=2, nome="Outro nome", maximo="3"))
    g.refresh_from_db()
    assert g.codigo == codigo and g.nome == "Outro nome"
    assert list(g.opcoes.values_list("nome", flat=True)) == ["Bacon"]


def test_remover_todas_as_opcoes_e_recusado(client_dono, bacon):
    g = bacon.grupo
    r = client_dono.post(f"/gerenciar/grupo/{g.id}/", post_grupo(
        [linha_existente(bacon, DELETE="on")], inicial=1, nome=g.nome, maximo="30"))
    assert r.status_code == 200 and g.opcoes.count() == 1


def test_lista_mostra_quantos_produtos_usam(client_dono, burger, grupo_unica):
    html = client_dono.get("/gerenciar/grupos/").content.decode()
    assert grupo_unica.nome in html and "1 produto" in html


def test_pagina_de_edicao_abre(client_dono, bacon):
    r = client_dono.get(f"/gerenciar/grupo/{bacon.grupo_id}/")
    assert r.status_code == 200 and "Bacon" in r.content.decode()
    assert client_dono.get("/gerenciar/grupo/novo/").status_code == 200


def test_excluir_mostra_produtos_afetados_e_apaga(client_dono, burger, grupo_unica):
    r = client_dono.get(f"/gerenciar/grupo/{grupo_unica.id}/excluir/")
    assert r.status_code == 200 and "Brasa Premium" in r.content.decode()
    assert GrupoOpcao.objects.filter(pk=grupo_unica.pk).exists()
    client_dono.post(f"/gerenciar/grupo/{grupo_unica.id}/excluir/")
    assert not GrupoOpcao.objects.filter(pk=grupo_unica.pk).exists()
    assert Produto.objects.filter(pk=burger.pk).exists()
    assert ProdutoGrupo.objects.filter(produto=burger).count() == 1


def test_grupo_opcional_forca_minimo_zero(client_dono):
    client_dono.post("/gerenciar/grupo/novo/", post_grupo(minimo="2", maximo="3"))
    g = GrupoOpcao.objects.get(nome="Adicionais")
    assert g.obrigatorio is False and g.minimo == 0


@pytest.mark.parametrize("minimo,maximo,obrigatorio,campo", [
    ("3", "3", "on", "minimo"),
    ("0", "4", "", "maximo"),
])
def test_limites_nao_podem_exceder_capacidade(client_dono, minimo, maximo, obrigatorio, campo):
    r = client_dono.post("/gerenciar/grupo/novo/", post_grupo(
        [{"nome": "Bacon", "preco": "0", "qtd_maxima": "2"}],
        minimo=minimo, maximo=maximo, obrigatorio=obrigatorio))
    assert r.status_code == 200
    assert campo in r.context["form"].errors
    assert not GrupoOpcao.objects.exists()


def test_capacidade_igual_aos_limites_e_aceita(client_dono):
    r = client_dono.post("/gerenciar/grupo/novo/", post_grupo(
        [{"nome": "Bacon", "preco": "0", "qtd_maxima": "2"}],
        minimo="2", maximo="2", obrigatorio="on"))
    assert r.status_code == 302
    assert GrupoOpcao.objects.get().minimo == 2


def test_opcao_removida_nao_conta_na_capacidade(client_dono, bacon):
    g = bacon.grupo
    extra = Opcao.objects.create(grupo=g, nome="Ovo", qtd_maxima=2)
    r = client_dono.post(f"/gerenciar/grupo/{g.pk}/", post_grupo(
        [linha_existente(bacon), linha_existente(extra, DELETE="on")], inicial=2,
        nome="Nome alterado", maximo="5"))
    assert r.status_code == 200
    assert "maximo" in r.context["form"].errors
    g.refresh_from_db()
    assert g.nome == "Adicionais à parte"
    assert g.opcoes.count() == 2


def test_formset_invalido_nao_salva_alteracoes_parciais(client_dono, bacon):
    g = bacon.grupo
    r = client_dono.post(f"/gerenciar/grupo/{g.pk}/", post_grupo(
        [linha_existente(bacon, preco="invalido")], inicial=1, nome="Nome alterado", maximo="3"))
    assert r.status_code == 200
    g.refresh_from_db()
    bacon.refresh_from_db()
    assert g.nome == "Adicionais à parte"
    assert bacon.preco == Decimal("2.50")


def test_capacidade_cadastrada_inclui_opcoes_esgotadas(client_dono, bacon):
    bacon.esgotado_em = date(2026, 11, 10)
    bacon.save()
    r = client_dono.post(f"/gerenciar/grupo/{bacon.grupo_id}/", post_grupo(
        [linha_existente(bacon)], inicial=1, nome=bacon.grupo.nome,
        minimo="3", maximo="3", obrigatorio="on"))
    assert r.status_code == 302
