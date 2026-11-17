import os
import io
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from PIL import Image

from cardapio.models import Categoria, Produto, ProdutoGrupo


def dados(categoria, **extra):
    base = {"nome": "X Teste", "descricao": "Bom", "preco": "12,50", "categoria": categoria.id}
    base.update(extra)
    return base


def test_sem_login_vai_para_entrar(client):
    r = client.get(reverse("gerenciar:lista"))
    assert r.status_code == 302 and r.url.startswith("/gerenciar/entrar/")


def test_usuario_sem_grupo_dono_recebe_403(client, usuario_comum):
    client.force_login(usuario_comum)
    assert client.get(reverse("gerenciar:lista")).status_code == 403


def test_superusuario_entra(client, db):
    client.force_login(User.objects.create_superuser("admin", password="x"))
    assert client.get(reverse("gerenciar:lista")).status_code == 200


def test_grupo_dono_existe(db):
    assert Group.objects.filter(name="Dono").exists()


def test_tela_de_entrar_abre(client, db):
    assert client.get("/gerenciar/entrar/").status_code == 200


def test_dono_ve_lista_e_busca(client_dono, produto):
    assert b"Brasa Premium" in client_dono.get(reverse("gerenciar:lista")).content
    assert b"Brasa Premium" not in client_dono.get(reverse("gerenciar:lista") + "?q=zzz").content
    assert b"Brasa Premium" in client_dono.get(reverse("gerenciar:lista") + "?q=premium").content


def test_dono_cria_produto_com_preco_em_reais(client_dono, categoria):
    r = client_dono.post("/gerenciar/produto/novo/", dados(categoria))
    assert r.status_code == 302
    assert Produto.objects.get(nome="X Teste").preco == Decimal("12.50")


@pytest.mark.parametrize("texto,esperado", [
    ("12,50", "12.50"), ("12.50", "12.50"), ("R$ 12,50", "12.50"),
    ("1.234,50", "1234.50"), ("15", "15.00"),
])
def test_formatos_de_preco(client_dono, categoria, texto, esperado):
    client_dono.post("/gerenciar/produto/novo/", dados(categoria, preco=texto))
    assert Produto.objects.get(nome="X Teste").preco == Decimal(esperado)


@pytest.mark.parametrize("texto", ["0", "-5", "abc", "", "0,00"])
def test_preco_invalido_e_recusado(client_dono, categoria, texto):
    r = client_dono.post("/gerenciar/produto/novo/", dados(categoria, preco=texto))
    assert r.status_code == 200
    assert not Produto.objects.filter(nome="X Teste").exists()


def test_slug_repetido_ganha_sufixo(client_dono, categoria):
    for _ in range(3):
        client_dono.post("/gerenciar/produto/novo/", dados(categoria))
    assert sorted(Produto.objects.values_list("slug", flat=True)) == ["x-teste", "x-teste-2", "x-teste-3"]


def test_marcar_sugerir_no_checkout(client_dono, produto):
    html = client_dono.get(f"/gerenciar/produto/{produto.pk}/").content.decode()
    assert 'name="sugerir_no_checkout"' in html
    client_dono.post(f"/gerenciar/produto/{produto.pk}/", dados(produto.categoria, visivel="on", sugerir_no_checkout="on"))
    produto.refresh_from_db()
    assert produto.sugerir_no_checkout is True


def test_editar_mantem_slug(client_dono, produto):
    client_dono.post(f"/gerenciar/produto/{produto.id}/", dados(produto.categoria, nome="Outro Nome"))
    produto.refresh_from_db()
    assert produto.nome == "Outro Nome" and produto.slug == "le-premium"


def test_grupos_ligados_com_ordem(client_dono, categoria, grupo_unica, grupo_varias):
    client_dono.post("/gerenciar/produto/novo/", dados(
        categoria, grupos=[grupo_unica.id, grupo_varias.id],
        **{f"ordem_{grupo_unica.id}": "2", f"ordem_{grupo_varias.id}": "1"}))
    p = Produto.objects.get(nome="X Teste")
    ordem = list(ProdutoGrupo.objects.filter(produto=p).order_by("ordem").values_list("grupo_id", flat=True))
    assert ordem == [grupo_varias.id, grupo_unica.id]


def test_ocultar_tira_do_cardapio(client_dono, produto):
    r = client_dono.post(f"/gerenciar/produto/{produto.id}/visivel/")
    assert r.status_code in (200, 302)
    produto.refresh_from_db()
    assert produto.visivel is False
    assert b"Brasa Premium" not in Client().get("/").content


def test_ocultar_via_htmx_devolve_trecho(client_dono, produto):
    r = client_dono.post(f"/gerenciar/produto/{produto.id}/visivel/", HTTP_HX_REQUEST="true")
    assert r.status_code == 200 and b"<html" not in r.content


def test_excluir_pede_confirmacao_e_apaga(client_dono, produto):
    assert client_dono.get(f"/gerenciar/produto/{produto.id}/excluir/").status_code == 200
    assert Produto.objects.filter(pk=produto.pk).exists()
    client_dono.post(f"/gerenciar/produto/{produto.id}/excluir/")
    assert not Produto.objects.filter(pk=produto.pk).exists()


def test_acoes_exigem_post(client_dono, produto):
    assert client_dono.get(f"/gerenciar/produto/{produto.id}/visivel/").status_code == 405
    assert client_dono.get(f"/gerenciar/produto/{produto.id}/mover/").status_code == 405


def test_mover_troca_com_vizinho(client_dono, categoria):
    a = Produto.objects.create(categoria=categoria, slug="a", nome="A", preco=1, ordem=0)
    Produto.objects.create(categoria=categoria, slug="b", nome="B", preco=1, ordem=0)  # empate
    c = Produto.objects.create(categoria=categoria, slug="c", nome="C", preco=1, ordem=0)
    client_dono.post(f"/gerenciar/produto/{c.id}/mover/", {"direcao": "cima"})
    assert [p.nome for p in Produto.objects.filter(categoria=categoria)] == ["A", "C", "B"]
    client_dono.post(f"/gerenciar/produto/{c.id}/mover/", {"direcao": "baixo"})
    assert [p.nome for p in Produto.objects.filter(categoria=categoria)] == ["A", "B", "C"]
    client_dono.post(f"/gerenciar/produto/{a.id}/mover/", {"direcao": "cima"})  # já é o primeiro
    assert [p.nome for p in Produto.objects.filter(categoria=categoria)] == ["A", "B", "C"]


def test_nao_exclui_categoria_com_produto(client_dono, produto):
    r = client_dono.post(f"/gerenciar/categorias/{produto.categoria_id}/excluir/", follow=True)
    assert Categoria.objects.filter(pk=produto.categoria_id).exists()
    assert "Mova ou exclua os produtos antes" in r.content.decode()


def test_exclui_categoria_vazia(client_dono, categoria):
    client_dono.post(f"/gerenciar/categorias/{categoria.id}/excluir/")
    assert not Categoria.objects.filter(pk=categoria.pk).exists()


def test_categorias_criar_renomear_ocultar_mover(client_dono, categoria):
    client_dono.post("/gerenciar/categorias/", {"nome": "Bebidas"})
    nova = Categoria.objects.get(nome="Bebidas")
    assert nova.ordem > categoria.ordem
    client_dono.post(f"/gerenciar/categorias/{nova.id}/renomear/", {"nome": "Bebidas Geladas"})
    client_dono.post(f"/gerenciar/categorias/{nova.id}/visivel/")
    nova.refresh_from_db()
    assert nova.nome == "Bebidas Geladas" and nova.visivel is False
    client_dono.post(f"/gerenciar/categorias/{nova.id}/mover/", {"direcao": "cima"})
    assert [c.nome for c in Categoria.objects.all()] == ["Bebidas Geladas", "Burguers"]


def _png(w, h, modo="RGB"):
    buf = io.BytesIO()
    cor = (200, 30, 30, 0) if modo == "RGBA" else (200, 30, 30)
    Image.new(modo, (w, h), cor).save(buf, "PNG")
    return SimpleUploadedFile("foto.png", buf.getvalue(), content_type="image/png")


def test_foto_enviada_vira_jpeg_de_ate_1000px(client_dono, produto, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    client_dono.post(f"/gerenciar/produto/{produto.id}/", dados(produto.categoria, imagem=_png(3000, 2000)))
    produto.refresh_from_db()
    assert produto.imagem.name.endswith(".jpg")
    img = Image.open(produto.imagem.path)
    assert img.format == "JPEG" and img.size == (1000, 667)


def test_png_transparente_ganha_fundo_branco(client_dono, produto, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    client_dono.post(f"/gerenciar/produto/{produto.id}/", dados(produto.categoria, imagem=_png(50, 50, "RGBA")))
    produto.refresh_from_db()
    assert Image.open(produto.imagem.path).getpixel((5, 5))[0] > 240


def test_arquivo_que_nao_e_imagem_e_recusado(client_dono, produto, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    falso = SimpleUploadedFile("x.png", b"isso nao e imagem", content_type="image/png")
    r = client_dono.post(f"/gerenciar/produto/{produto.id}/", dados(produto.categoria, imagem=falso, nome="Mudou"))
    assert r.status_code == 200
    assert "imagem" in r.context["form"].errors
    produto.refresh_from_db()
    assert produto.nome != "Mudou" and not produto.imagem
    assert not list(tmp_path.rglob("*"))


@pytest.mark.parametrize("tamanho,aceita", [
    (10 * 1024 * 1024 - 1, True),
    (10 * 1024 * 1024, True),
    (10 * 1024 * 1024 + 1, False),
])
def test_limite_da_foto(client_dono, categoria, settings, tmp_path, tamanho, aceita):
    settings.MEDIA_ROOT = tmp_path
    conteudo = _png(20, 20).read()
    foto = SimpleUploadedFile("foto.png", conteudo + b"\0" * (tamanho - len(conteudo)), content_type="image/png")
    r = client_dono.post("/gerenciar/produto/novo/", dados(categoria, imagem=foto))
    assert r.status_code == (302 if aceita else 200)
    assert Produto.objects.filter(nome="X Teste").exists() is aceita
    if aceita:
        produto = Produto.objects.get(nome="X Teste")
        assert Image.open(produto.imagem.path).format == "JPEG"
    else:
        assert "10 MiB" in r.context["form"].errors["imagem"][0]
        assert not list(tmp_path.rglob("*"))


@pytest.mark.parametrize("editar", [False, True])
@pytest.mark.parametrize("erro", [OSError, ValueError, SyntaxError, Image.DecompressionBombError])
def test_falha_ao_otimizar_vira_erro_de_campo_sem_gravar(
    client_dono, produto, settings, tmp_path, monkeypatch, editar, erro,
):
    settings.MEDIA_ROOT = tmp_path
    produto.imagem.save("anterior.png", _png(10, 10), save=True)
    nome_anterior = produto.imagem.name
    arquivos_antes = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*") if p.is_file())
    foto = _png(20, 20)

    def falhar(imagem):
        raise erro("Falha de decodificação")

    monkeypatch.setattr("PIL.ImageOps.exif_transpose", falhar)
    url = f"/gerenciar/produto/{produto.pk}/" if editar else "/gerenciar/produto/novo/"
    r = client_dono.post(url, dados(produto.categoria, imagem=foto, nome="Mudou"))
    assert r.status_code == 200
    assert "imagem" in r.context["form"].errors
    assert not Produto.objects.filter(nome="Mudou").exists()
    produto.refresh_from_db()
    assert produto.imagem.name == nome_anterior
    assert sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*") if p.is_file()) == arquivos_antes


# --- correções da revisão da Task 8 ---------------------------------------
def test_ordem_nao_numerica_com_preco_invalido_nao_da_500(client_dono, categoria, grupo_unica):
    r = client_dono.post("/gerenciar/produto/novo/", dados(
        categoria, preco="abc", grupos=[grupo_unica.id], **{f"ordem_{grupo_unica.id}": "1e2"}))
    assert r.status_code == 200
    assert "Digite o preço em reais" in r.content.decode()


@pytest.mark.parametrize("texto", ["1,234.50", "1,5.50", "1.234,50,10"])
def test_preco_ambiguo_estilo_americano_e_recusado(client_dono, categoria, texto):
    r = client_dono.post("/gerenciar/produto/novo/", dados(categoria, preco=texto))
    assert r.status_code == 200
    assert "Digite o preço em reais" in r.content.decode()
    assert not Produto.objects.filter(nome="X Teste").exists()


def test_trocar_foto_apaga_arquivo_antigo(client_dono, produto, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    produto.imagem.save("velha.png", _png(10, 10), save=True)
    antigo = produto.imagem.path
    client_dono.post(f"/gerenciar/produto/{produto.id}/", dados(produto.categoria, imagem=_png(20, 20)))
    produto.refresh_from_db()
    assert produto.imagem.path != antigo
    assert not os.path.exists(antigo) and os.path.exists(produto.imagem.path)


def test_remover_foto_apaga_arquivo(client_dono, produto, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    produto.imagem.save("velha.png", _png(10, 10), save=True)
    antigo = produto.imagem.path
    client_dono.post(f"/gerenciar/produto/{produto.id}/", dados(produto.categoria, remover_foto="on"))
    produto.refresh_from_db()
    assert not produto.imagem and not os.path.exists(antigo)


def test_excluir_produto_apaga_foto(client_dono, produto, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    produto.imagem.save("velha.png", _png(10, 10), save=True)
    caminho = produto.imagem.path
    client_dono.post(f"/gerenciar/produto/{produto.id}/excluir/")
    assert not os.path.exists(caminho)


def test_nao_apaga_foto_usada_por_outro_produto(client_dono, produto, categoria, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    produto.imagem.save("compartilhada.png", _png(10, 10), save=True)
    outro = Produto.objects.create(categoria=categoria, slug="outro", nome="Outro", preco=1, imagem=produto.imagem.name)
    caminho = produto.imagem.path
    client_dono.post(f"/gerenciar/produto/{produto.id}/", dados(categoria, remover_foto="on"))
    assert os.path.exists(caminho)
    client_dono.post(f"/gerenciar/produto/{produto.id}/excluir/")
    assert os.path.exists(caminho)
    client_dono.post(f"/gerenciar/produto/{outro.id}/excluir/")
    assert not os.path.exists(caminho)


@pytest.mark.parametrize("texto,esperado", [
    ("12,5", "12.50"), ("12.5", "12.50"), ("1.234.567,89", "1234567.89"),
    ("1.234", "1234.00"), ("10", "10.00"), ("0,50", "0.50"), ("1.234,5", "1234.50"),
])
def test_ler_preco_aceita(texto, esperado):
    from gerenciar.forms import ler_preco
    assert ler_preco(texto) == Decimal(esperado)


@pytest.mark.parametrize("texto", ["1,234", "0.500", "1.2.3", "1,234.50", "12.345.6", "1.23.456", "12,345,67", "1234.567"])
def test_ler_preco_recusa_ambiguos(texto):
    from gerenciar.forms import ler_preco
    with pytest.raises(ValueError):
        ler_preco(texto)
