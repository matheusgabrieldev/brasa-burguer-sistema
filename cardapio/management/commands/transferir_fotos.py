"""Copia fotos referenciadas no banco, com manifesto de origem e verificação do destino."""
import hashlib
import json
from pathlib import Path, PurePosixPath

from django.core.files import File
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError

from cardapio.models import Produto

BLOCO = 65536


def assinatura(arquivo):
    tamanho = 0
    hash_foto = hashlib.sha256()
    while bloco := arquivo.read(BLOCO):
        tamanho += len(bloco)
        hash_foto.update(bloco)
    return {"tamanho": tamanho, "sha256": hash_foto.hexdigest()}


class Command(BaseCommand):
    help = "Transfere produtos/* da pasta local para o Storage; cria ou confere o manifesto."

    def add_arguments(self, parser):
        parser.add_argument("--origem", required=True, help="Pasta media que contém produtos/")
        parser.add_argument("--manifesto", required=True, help="JSON criado na primeira execução e conferido nas retomadas")

    def handle(self, origem, manifesto, **opts):
        try:
            self.transferir(Path(origem).resolve(), Path(manifesto))
        except CommandError:
            raise
        except Exception:
            # Falhas de backend podem conter URLs assinadas/credenciais: não as imprimir.
            raise CommandError("Falha na transferência; confira origem, manifesto e acesso ao Storage.") from None

    def transferir(self, origem, manifesto):
        if getattr(default_storage, "file_overwrite", False):
            raise CommandError("O Storage está com sobrescrita ativada; desative-a antes da transferência.")
        nomes = sorted(set(Produto.objects.exclude(imagem="").values_list("imagem", flat=True)))
        arquivos, caminhos = [], {}
        for nome in nomes:
            partes = PurePosixPath(nome).parts
            if (not nome.startswith("produtos/") or "\\" in nome or ":" in nome or
                    ".." in partes or PurePosixPath(nome).is_absolute()):
                raise CommandError("Nome de foto inválido; use apenas caminhos relativos produtos/*.")
            caminho = (origem / nome).resolve()
            if not caminho.is_relative_to(origem):
                raise CommandError("Nome de foto inválido: caminho fora da origem.")
            if not caminho.is_file():
                raise CommandError(f"Arquivo ausente na origem: {nome}")
            with caminho.open("rb") as foto:
                arquivos.append({"nome": nome, **assinatura(foto)})
            caminhos[nome] = caminho

        esperado = {"arquivos": arquivos}
        if manifesto.exists():
            if json.loads(manifesto.read_text(encoding="utf-8")) != esperado:
                raise CommandError("A origem ou as referências do banco mudaram em relação ao manifesto; revise o conjunto.")
        else:
            # O manifesto descreve a origem inteira, nunca sinaliza progresso parcial.
            with manifesto.open("x", encoding="utf-8") as arquivo:
                json.dump(esperado, arquivo, ensure_ascii=False, indent=2)
                arquivo.write("\n")

        enviados = 0
        for registro in arquivos:
            nome = registro["nome"]
            hash_esperado = {chave: registro[chave] for chave in ("tamanho", "sha256")}
            if default_storage.exists(nome):
                with default_storage.open(nome, "rb") as foto:
                    if assinatura(foto) != hash_esperado:
                        raise CommandError(f"Conflito no destino: {nome}. Nenhum objeto existente foi sobrescrito.")
            else:
                with caminhos[nome].open("rb") as foto:
                    salvo = default_storage.save(nome, File(foto))
                if salvo != nome:
                    raise CommandError(f"O Storage renomeou {nome}; revise o destino antes de retomar.")
                with default_storage.open(nome, "rb") as foto:
                    if assinatura(foto) != hash_esperado:
                        raise CommandError(f"Falha de verificação após envio: {nome}.")
                enviados += 1
        self.stdout.write(self.style.SUCCESS(f"Fotos verificadas: {len(arquivos)}; enviadas nesta execução: {enviados}."))
