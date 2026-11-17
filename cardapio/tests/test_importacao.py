import json
import io
from decimal import Decimal
from pathlib import Path

import pytest

from cardapio.importacao import importar
from cardapio.models import Categoria, GrupoOpcao, Produto
from loja.models import Bairro, Configuracao, FormaPagamento, Horario

PASTA = Path(__file__).parent
REAL = PASTA.parents[1] / "dados" / "cardapio-portfolio.json"
MINI = PASTA / "fixtures" / "cardapio_mini.json"


def carregar(caminho):
    return json.loads(caminho.read_text(encoding="utf-8"))


@pytest.mark.skipif(not REAL.exists(), reason="arquivo do levantamento não encontrado")
def test_cardapio_real(db):
    importar(carregar(REAL))
    assert Produto.objects.count() == 69
    assert Categoria.objects.count() == 7
    assert GrupoOpcao.objects.count() == 8
    assert Bairro.objects.count() == 31
    assert Bairro.objects.filter(ativo=False).count() == 2
    assert Produto.objects.filter(destaque=True).count() == 4
    onion = Produto.objects.get(nome="Onion Ring + molho barbecue")
    primeiro = onion.produtogrupo_set.order_by("ordem").first().grupo
    assert primeiro.obrigatorio
    assert [o.nome for o in primeiro.opcoes.all()] == ["Barbecue", "Maionese artesanal"]
    assert GrupoOpcao.objects.get(nome="Cebola").tipo == "unica"
    retirar = GrupoOpcao.objects.get(nome="Quer tirar algum ingrediente?")
    assert [o.nome for o in retirar.opcoes.all()] == ["Sem alface", "Sem tomate"]
    assert Horario.objects.get(dia_semana=0).ativo is False  # segunda
    assert Horario.objects.get(dia_semana=6).abre.strftime("%H:%M") == "18:00"
    assert Produto.objects.filter(mais_pedido=True).count() == 4


def test_destaque_vira_marcacao_e_nao_categoria(db):
    importar(carregar(MINI))
    assert not Categoria.objects.filter(nome="Destaques").exists()
    assert Produto.objects.get(slug="le-premium").destaque is True
    assert Produto.objects.get(slug="cheddar-bacon").destaque is False


def test_cebola_vira_escolha_unica(db):
    importar(carregar(MINI))
    cebola = GrupoOpcao.objects.get(nome="Cebola")
    assert (cebola.tipo, cebola.minimo, cebola.maximo) == ("unica", 0, 1)
    assert [o.nome for o in cebola.opcoes.all()] == ["Cebola crua", "Cebola caramelizada", "Sem cebola"]


def test_retirar_ingrediente_sem_cebola_e_completo(db):
    importar(carregar(MINI))
    g = GrupoOpcao.objects.get(nome="Quer tirar algum ingrediente?")
    assert (g.tipo, g.maximo) == ("varias", 2)
    assert [o.nome for o in g.opcoes.all()] == ["Sem alface", "Sem tomate"]


def test_onion_ring_ganha_molho_obrigatorio_primeiro(db):
    importar(carregar(MINI))
    onion = Produto.objects.get(slug="onion-ring-molho-barbecue")
    grupos = [pg.grupo.codigo for pg in onion.produtogrupo_set.order_by("ordem")]
    assert grupos[0] == "molho-onion"


def test_grupo_opcional_fica_com_minimo_zero(db):
    importar(carregar(MINI))
    adicionais = GrupoOpcao.objects.get(codigo="78de8ac0-0c4d-11ee-8bab-350bee2c2279")
    assert adicionais.obrigatorio is False and adicionais.minimo == 0


def test_cria_loja_formas_de_pagamento_e_bairros(db):
    importar(carregar(MINI))
    cfg = Configuracao.atual()
    assert cfg.whatsapp == "5581990001234"
    assert cfg.pedido_minimo == Decimal("10")
    formas = {f.codigo: f for f in FormaPagamento.objects.all()}
    assert formas["credito"].acrescimo_pct == Decimal("4")
    assert formas["debito"].acrescimo_pct == Decimal("1")
    assert formas["dinheiro"].aceita_delivery is True
    assert Bairro.objects.get(nome="Paratibe").ativo is False


def test_reimportar_nao_duplica_e_preserva_edicoes_do_dono(db):
    dados = carregar(MINI)
    importar(dados)
    p = Produto.objects.get(slug="le-premium")
    p.visivel = False
    p.imagem.name = "produtos/minha.jpg"
    p.ordem = 99
    p.save()
    dados["categorias"][1]["produtos"][0]["variantes"][0]["preco"] = 27
    resumo = importar(dados)
    assert Produto.objects.count() == 3
    p.refresh_from_db()
    assert (p.visivel, p.imagem.name, p.ordem, p.preco) == (False, "produtos/minha.jpg", 99, Decimal("27"))
    assert resumo.atualizados == 3 and resumo.criados == 0
    assert GrupoOpcao.objects.count() == 5


def test_reimportar_nao_muda_config_editada(db):
    importar(carregar(MINI))
    cfg = Configuracao.atual()
    cfg.chave_pix = "nova"
    cfg.save()
    importar(carregar(MINI))
    assert Configuracao.atual().chave_pix == "nova"


def test_produto_fora_do_json_vai_para_ausentes_e_nao_e_apagado(db):
    importar(carregar(MINI))
    Produto.objects.create(categoria=Categoria.objects.first(), slug="sorvete", nome="Sorvete", preco=5)
    resumo = importar(carregar(MINI))
    assert resumo.ausentes == ["Sorvete"]
    assert Produto.objects.filter(slug="sorvete").exists()


def test_reimportar_preserva_destaque_mais_pedido_e_categoria_renomeada(db):
    dados = carregar(MINI)
    importar(dados)
    premium = Produto.objects.get(slug="le-premium")
    premium.destaque = False  # dono tirou dos destaques
    premium.mais_pedido = True  # e marcou o selo
    premium.save()
    outro = Produto.objects.get(slug="cheddar-bacon")
    outro.destaque = True
    outro.save()
    cat = premium.categoria
    nome_antigo = cat.nome
    cat.nome = "Nome novo do dono"
    cat.save()
    total_cats = Categoria.objects.count()
    importar(dados)
    premium.refresh_from_db()
    outro.refresh_from_db()
    assert premium.destaque is False and premium.mais_pedido is True
    assert outro.destaque is True
    assert premium.categoria_id == cat.pk
    assert not Categoria.objects.filter(nome=nome_antigo).exists()
    assert Categoria.objects.count() == total_cats


def test_importar_com_configuracao_em_branco_preenche_contato(db):
    Configuracao.atual()  # uma visita qualquer cria a linha em branco
    importar(carregar(MINI))
    cfg = Configuracao.atual()
    assert cfg.whatsapp == "5581990001234"
    assert cfg.chave_pix == "81990001234"
    assert cfg.endereco and cfg.slogan and cfg.instagram


def test_baixar_fotos_usa_storage_sem_caminho_local(produto, monkeypatch, settings, tmp_path):
    from cardapio.management.commands import importar_cardapio as comando
    from cardapio.tests.test_transferir_fotos import StorageMemoria

    storage = StorageMemoria()
    monkeypatch.setattr(comando, "default_storage", storage, raising=False)
    settings.MEDIA_ROOT = tmp_path / "nao-criar"
    produto.foto_url = "https://fotos.example/burger.jpg"
    produto.save()
    dados = b"foto" * 20000

    class Download(io.BytesIO):
        def read(self, tamanho=-1):
            assert 0 < tamanho <= 65536, "download deve ler em blocos"
            return super().read(tamanho)

    monkeypatch.setattr(comando.urllib.request, "urlopen", lambda *a, **kw: Download(dados))
    comando.Command().baixar_fotos()
    produto.refresh_from_db()
    assert produto.imagem.name == "produtos/burger.jpg"
    assert storage.arquivos[produto.imagem.name] == dados
    assert not settings.MEDIA_ROOT.exists()
    assert comando.Command().baixar_fotos() == (0, 0)


def test_baixar_fotos_reutiliza_objeto_existente_e_preserva_foto_editada(produto, monkeypatch, settings, tmp_path):
    from cardapio.management.commands import importar_cardapio as comando
    from cardapio.tests.test_transferir_fotos import StorageMemoria

    storage = StorageMemoria({"produtos/burger.jpg": b"ja salvo"})
    settings.MEDIA_ROOT = tmp_path / "nao-criar"
    monkeypatch.setattr(comando, "default_storage", storage, raising=False)
    produto.foto_url = "https://fotos.example/burger.jpg"
    produto.save()
    monkeypatch.setattr(comando.urllib.request, "urlopen", lambda *a, **kw: pytest.fail("nao deve baixar foto existente"))
    assert comando.Command().baixar_fotos() == (1, 0)
    produto.refresh_from_db()
    assert produto.imagem.name == "produtos/burger.jpg"
    produto.imagem.name = "produtos/editada.jpg"
    produto.save()
    assert comando.Command().baixar_fotos() == (0, 0)
    produto.refresh_from_db()
    assert produto.imagem.name == "produtos/editada.jpg"


def test_baixar_fotos_grava_nome_real_devolvido_pelo_storage(produto, monkeypatch, settings, tmp_path):
    from cardapio.management.commands import importar_cardapio as comando
    from cardapio.tests.test_transferir_fotos import StorageMemoria

    storage = StorageMemoria()
    settings.MEDIA_ROOT = tmp_path / "nao-criar"
    monkeypatch.setattr(storage, "get_available_name", lambda nome, max_length=None: "produtos/renomeada.jpg")
    monkeypatch.setattr(comando, "default_storage", storage, raising=False)
    monkeypatch.setattr(comando.urllib.request, "urlopen", lambda *a, **kw: io.BytesIO(b"foto"))
    produto.foto_url = "https://fotos.example/burger.jpg"
    produto.save()
    assert comando.Command().baixar_fotos() == (1, 0)
    produto.refresh_from_db()
    assert produto.imagem.name == "produtos/renomeada.jpg"
    assert storage.arquivos[produto.imagem.name] == b"foto"
