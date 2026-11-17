import hashlib
import io
import json

import pytest
from django.core.files.base import File
from django.core.files.storage import Storage
from django.core.management import call_command, CommandError


class StorageMemoria(Storage):
    """Storage sem path(), lendo os arquivos apenas em blocos."""

    def __init__(self, arquivos=None):
        self.arquivos = dict(arquivos or {})
        self.gravados = []

    def exists(self, nome):
        return nome in self.arquivos

    def _open(self, nome, mode="rb"):
        class Blocos(io.BytesIO):
            def read(self, tamanho=-1):
                assert 0 < tamanho <= 65536, "hash deve ler em blocos"
                return super().read(tamanho)
        return File(Blocos(self.arquivos[nome]), name=nome)

    def _save(self, nome, conteudo):
        assert nome not in self.arquivos, "nao deve sobrescrever"
        self.arquivos[nome] = b"".join(conteudo.chunks(chunk_size=65536))
        self.gravados.append(nome)
        return nome


def preparar(produto, tmp_path, monkeypatch, arquivos=None):
    from cardapio.management.commands import transferir_fotos

    storage = StorageMemoria(arquivos)
    monkeypatch.setattr(transferir_fotos, "default_storage", storage)
    produto.imagem.name = "produtos/burger.jpg"
    produto.save()
    pasta = tmp_path / "media"
    (pasta / "produtos").mkdir(parents=True)
    return storage, pasta, tmp_path / "manifesto.json"


def test_transferencia_preserva_nome_hash_e_repete_sem_duplicar(produto, tmp_path, monkeypatch):
    storage, pasta, manifesto = preparar(produto, tmp_path, monkeypatch)
    conteudo = b"foto-publica" * 20000
    (pasta / "produtos/burger.jpg").write_bytes(conteudo)
    for _ in range(2):
        call_command("transferir_fotos", origem=str(pasta), manifesto=str(manifesto))
    assert storage.arquivos == {"produtos/burger.jpg": conteudo}
    assert storage.gravados == ["produtos/burger.jpg"]
    assert json.loads(manifesto.read_text(encoding="utf-8")) == {"arquivos": [{
        "nome": "produtos/burger.jpg", "tamanho": len(conteudo),
        "sha256": hashlib.sha256(conteudo).hexdigest(),
    }]}


def test_arquivo_ausente_recusa_sem_enviar(produto, tmp_path, monkeypatch):
    storage, pasta, manifesto = preparar(produto, tmp_path, monkeypatch)
    with pytest.raises(CommandError, match="ausente"):
        call_command("transferir_fotos", origem=str(pasta), manifesto=str(manifesto))
    assert storage.arquivos == {}


def test_objeto_diferente_recusa_sem_sobrescrever(produto, tmp_path, monkeypatch):
    storage, pasta, manifesto = preparar(produto, tmp_path, monkeypatch, {"produtos/burger.jpg": b"destino"})
    (pasta / "produtos/burger.jpg").write_bytes(b"origem")
    with pytest.raises(CommandError, match="Conflito"):
        call_command("transferir_fotos", origem=str(pasta), manifesto=str(manifesto))
    assert storage.arquivos["produtos/burger.jpg"] == b"destino"
    assert storage.gravados == []


def test_manifesto_impede_retomada_com_foto_local_alterada(produto, tmp_path, monkeypatch):
    storage, pasta, manifesto = preparar(produto, tmp_path, monkeypatch)
    (pasta / "produtos/burger.jpg").write_bytes(b"original")
    call_command("transferir_fotos", origem=str(pasta), manifesto=str(manifesto))
    (pasta / "produtos/burger.jpg").write_bytes(b"alterada")
    with pytest.raises(CommandError, match="manifesto"):
        call_command("transferir_fotos", origem=str(pasta), manifesto=str(manifesto))
    assert storage.arquivos["produtos/burger.jpg"] == b"original"


def test_hash_de_destino_e_verificado_apos_envio(produto, tmp_path, monkeypatch):
    storage, pasta, manifesto = preparar(produto, tmp_path, monkeypatch)
    (pasta / "produtos/burger.jpg").write_bytes(b"original")
    salvar = storage._save

    def corromper(nome, conteudo):
        salvo = salvar(nome, conteudo)
        storage.arquivos[salvo] = b"corrompida"
        return salvo

    monkeypatch.setattr(storage, "_save", corromper)
    with pytest.raises(CommandError, match="verificação"):
        call_command("transferir_fotos", origem=str(pasta), manifesto=str(manifesto))


def test_transferencia_recusa_nome_renomeado_pelo_storage(produto, tmp_path, monkeypatch):
    storage, pasta, manifesto = preparar(produto, tmp_path, monkeypatch)
    (pasta / "produtos/burger.jpg").write_bytes(b"foto")
    monkeypatch.setattr(storage, "get_available_name", lambda nome, max_length=None: "produtos/outro.jpg")
    with pytest.raises(CommandError, match="renomeou"):
        call_command("transferir_fotos", origem=str(pasta), manifesto=str(manifesto))
    assert "produtos/burger.jpg" not in storage.arquivos


def test_recusa_backend_com_sobrescrita_ativada(produto, tmp_path, monkeypatch):
    storage, pasta, manifesto = preparar(produto, tmp_path, monkeypatch)
    storage.file_overwrite = True
    (pasta / "produtos/burger.jpg").write_bytes(b"foto")
    with pytest.raises(CommandError, match="sobrescrita"):
        call_command("transferir_fotos", origem=str(pasta), manifesto=str(manifesto))
    assert storage.arquivos == {}
    assert not manifesto.exists()


@pytest.mark.parametrize("nome", ["../fora.jpg", "produtos/../../fora.jpg", "outra/foto.jpg"])
def test_recusa_nome_fora_de_produtos(produto, tmp_path, monkeypatch, nome):
    storage, pasta, manifesto = preparar(produto, tmp_path, monkeypatch)
    produto.imagem.name = nome
    produto.save()
    with pytest.raises(CommandError, match="Nome de foto inválido"):
        call_command("transferir_fotos", origem=str(pasta), manifesto=str(manifesto))
    assert storage.arquivos == {}
