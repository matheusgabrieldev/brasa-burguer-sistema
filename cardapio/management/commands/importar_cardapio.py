"""Importa o cardápio do OlaClick para o banco.

Uso:
    python manage.py importar_cardapio                      # usa dados/cardapio-portfolio.json
    python manage.py importar_cardapio caminho/arquivo.json
    python manage.py importar_cardapio --baixar-fotos       # também salva as fotos em media/produtos

Pode rodar de novo: não duplica e não apaga o que o Dono editou (ver cardapio/importacao.py).
"""
import json
import urllib.request
from pathlib import Path
from tempfile import SpooledTemporaryFile
from urllib.parse import urlsplit

from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.files import File
from django.core.files.storage import default_storage

from cardapio.importacao import importar
from cardapio.models import Produto

PADRAO = Path(settings.BASE_DIR) / "dados" / "cardapio-portfolio.json"


class Command(BaseCommand):
    help = "Importa o cardápio levantado do OlaClick"

    def add_arguments(self, parser):
        parser.add_argument("caminho", nargs="?", default=str(PADRAO))
        parser.add_argument("--baixar-fotos", action="store_true", help="Salva as fotos do OlaClick no Storage configurado")

    def handle(self, caminho, baixar_fotos, **opts):
        dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
        r = importar(dados)
        self.stdout.write(self.style.SUCCESS(f"Cardápio importado: {r.criados} criados, {r.atualizados} atualizados."))
        if r.ausentes:
            self.stdout.write(self.style.WARNING("No banco mas não no arquivo (não foram apagados): " + ", ".join(r.ausentes)))
        if baixar_fotos:
            ok, falhas = self.baixar_fotos()
            self.stdout.write(self.style.SUCCESS(f"Fotos: {ok} salvas" + (f", {falhas} continuam online" if falhas else "")))

    def baixar_fotos(self):
        """Só para produtos que ainda não têm foto enviada. Sem internet: avisa e segue usando a foto online."""
        ok = falhas = 0
        for p in Produto.objects.exclude(foto_url="").filter(imagem=""):
            nome = "produtos/" + Path(urlsplit(p.foto_url).path).name
            try:
                if not default_storage.exists(nome):
                    req = urllib.request.Request(p.foto_url, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req, timeout=20) as resp, SpooledTemporaryFile(max_size=1048576) as foto:
                        while bloco := resp.read(65536):
                            foto.write(bloco)
                        foto.seek(0)
                        nome = default_storage.save(nome, File(foto))
            except Exception:
                falhas += 1
                self.stdout.write(self.style.WARNING(f"  não baixou {p.nome}; a foto online foi preservada."))
                continue
            p.imagem.name = nome
            p.save(update_fields=["imagem"])
            ok += 1
        return ok, falhas
