"""Identidade visual Brasa Burguer: fonte de títulos, cores e arquivos da marca."""
import re
from pathlib import Path

from django.conf import settings

STATIC = Path(settings.BASE_DIR) / "static"
BASE_CSS = (STATIC / "css" / "base.css").read_text(encoding="utf-8")


def test_fonte_dos_titulos_e_dela_gothic_one_local():
    m = re.search(r'@font-face\s*{[^}]*"Dela Gothic One"[^}]*url\("\.\./fonts/([^"]+)"\)', BASE_CSS)
    assert m, "base.css precisa declarar @font-face da Dela Gothic One"
    assert (STATIC / "fonts" / m.group(1)).is_file()
    assert re.search(r'--display:\s*"Dela Gothic One"', BASE_CSS)


def test_cores_da_marca():
    assert re.search(r"--creme:\s*#F6EAD7", BASE_CSS, re.I)
    assert re.search(r"--apoio:\s*#F2B705", BASE_CSS, re.I)
    assert re.search(r"--accent:\s*#111111", BASE_CSS, re.I)


def test_arquivos_da_marca_existem():
    for nome in ("logo.png", "favicon.png", "icon-192.png", "icon-512.png", "logo-horizontal.svg"):
        assert (STATIC / "img" / nome).is_file(), nome


def test_nenhum_titulo_usa_negrito_falso_na_dela():
    """Dela Gothic One só tem peso 400: títulos com var(--display) não podem pedir 700/800."""
    for css in ("cliente.css", "gerenciar.css"):
        texto = (STATIC / "css" / css).read_text(encoding="utf-8")
        for regra in re.findall(r"{[^}]*var\(--display\)[^}]*}", texto):
            assert not re.search(r"font-weight:\s*(6|7|8|9)00", regra), (css, regra)
