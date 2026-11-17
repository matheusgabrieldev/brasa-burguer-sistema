"""Gera os arquivos da marca Brasa Burguer usados pelo sistema.

Uso (na raiz do projeto, com o .venv ativo):
    pip install pillow fonttools
    python docs/marca/gerar_marca.py

Saída em static/img: logo.png, icon-512.png, icon-192.png, favicon.png e logo-horizontal.svg.
Fontes (OFL) em docs/marca/fontes.
"""
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from PIL import Image, ImageDraw, ImageFont

RAIZ = Path(__file__).resolve().parents[2]
FONTES = Path(__file__).resolve().parent / "fontes"
SAIDA = RAIZ / "static" / "img"
DELA = FONTES / "DelaGothicOne-Latin.ttf"
SPACE = FONTES / "SpaceGrotesk-wght.ttf"

PRETO = "#111111"
AMARELO = "#F2B705"
CREME = "#F6EAD7"


def _traco(d, a, b, largura, cor):
    """Linha com pontas arredondadas."""
    d.line([a, b], fill=cor, width=largura)
    r = largura / 2
    for x, y in (a, b):
        d.ellipse([x - r, y - r, x + r, y + r], fill=cor)


def _estalo(d, x, y, u, cor):
    """Os três traços do estalo; (x, y) é o canto de baixo à esquerda, u é a unidade."""
    w = round(u * 0.9)
    _traco(d, (x, y - 4.2 * u), (x, y - 1.6 * u), w, cor)
    _traco(d, (x + 1.3 * u, y - 0.4 * u), (x + 3.3 * u, y - 2.4 * u), w, cor)
    _traco(d, (x + 1.9 * u, y + 1.3 * u), (x + 4.6 * u, y + 1.3 * u), w, cor)


def _b_vazado(d, cx, cy, tamanho):
    """'B' amarelo com vão preto e contorno creme deslocado (sombra vazada)."""
    fonte = ImageFont.truetype(str(DELA), tamanho)
    desloc = round(tamanho * 0.045)
    contorno = max(2, round(tamanho * 0.018))
    vao = max(3, round(tamanho * 0.03))
    d.text((cx + desloc, cy + desloc), "B", font=fonte, fill=PRETO, anchor="mm",
           stroke_width=contorno, stroke_fill=CREME)
    d.text((cx, cy), "B", font=fonte, fill=AMARELO, anchor="mm",
           stroke_width=vao, stroke_fill=PRETO)


def emblema(lado, redondo):
    """Fundo preto (círculo ou quadrado), B vazado e estalo. Desenha em 2x e reduz."""
    s = lado * 2
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if redondo:
        d.ellipse([0, 0, s - 1, s - 1], fill=PRETO)
    else:
        d.rectangle([0, 0, s, s], fill=PRETO)
    _b_vazado(d, s * 0.483, s * 0.442, round(s * 0.56))
    return img.resize((lado, lado), Image.LANCZOS)


def favicon(lado=64):
    """B preto chapado em círculo amarelo: legível a 16 px."""
    s = lado * 4
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([0, 0, s - 1, s - 1], fill=AMARELO)
    d.text((s * 0.5, s * 0.53), "B", font=ImageFont.truetype(str(DELA), round(s * 0.62)),
           fill=PRETO, anchor="mm")
    return img.resize((lado, lado), Image.LANCZOS)


def _caminho(fonte, texto, espaco_extra=0):
    """Contorno do texto em SVG (unidades da fonte, y para cima) e largura total."""
    glifos = fonte.getGlyphSet()
    cmap = fonte.getBestCmap()
    partes, x = [], 0
    for ch in texto:
        nome = cmap[ord(ch)]
        pen = SVGPathPen(glifos)
        glifos[nome].draw(pen)
        partes.append(f'<path transform="translate({x} 0)" d="{pen.getCommands()}"/>')
        x += glifos[nome].width + espaco_extra
    return "".join(partes), x - espaco_extra


def logo_horizontal_svg():
    dela = TTFont(str(DELA))
    space = instantiateVariableFont(TTFont(str(SPACE)), {"wght": 700})
    upm_d, upm_s = dela["head"].unitsPerEm, space["head"].unitsPerEm

    brasa, larg_b = _caminho(dela, "BRASA", espaco_extra=-20)
    burguer, larg_g = _caminho(space, "BURGUER", espaco_extra=round(upm_s * 0.55))

    esc_b = 110 / upm_d            # BRASA com ~110 px de altura de corpo
    esc_g = 22 / upm_s
    w_b, w_g = larg_b * esc_b, larg_g * esc_g
    W, H = 700, 300
    xb = (W - w_b) / 2
    xg = (W - w_g) / 2
    desloc, contorno, vao = 7, 3.5 / esc_b, 9 / esc_b

    def bloco(x, y, extra):
        return f'<g transform="translate({x} {y}) scale({esc_b} {-esc_b})" {extra}>{brasa}</g>'

    sombra = bloco(xb + desloc, 190 + desloc, f'fill="none" stroke="{CREME}" stroke-width="{contorno:.1f}"')
    frente = bloco(xb, 190, f'fill="{AMARELO}" stroke="{PRETO}" stroke-width="{vao:.1f}" '
                            'stroke-linejoin="round" paint-order="stroke"')
    sub = f'<g transform="translate({xg} 252) scale({esc_g} {-esc_g})" fill="{CREME}">{burguer}</g>'
    xe = xb + w_b - 16
    estalo = (f'<g stroke="{CREME}" stroke-width="7" stroke-linecap="round">'
              f'<line x1="{xe}" y1="66" x2="{xe}" y2="88"/>'
              f'<line x1="{xe + 12}" y1="99" x2="{xe + 30}" y2="81"/>'
              f'<line x1="{xe + 17}" y1="113" x2="{xe + 41}" y2="113"/></g>')
    linhas = (f'<g stroke="{CREME}" stroke-width="5" stroke-linecap="round">'
              f'<line x1="{xb}" y1="244" x2="{xg - 24}" y2="244"/>'
              f'<line x1="{xg + w_g + 24}" y1="244" x2="{xb + w_b}" y2="244"/></g>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" role="img" '
            f'aria-label="Brasa Burguer"><rect width="{W}" height="{H}" fill="{PRETO}"/>'
            f'{sombra}{frente}{linhas}{sub}</svg>\n')


def main():
    emblema(512, redondo=True).save(SAIDA / "logo.png", optimize=True)
    app = emblema(512, redondo=False)
    app.save(SAIDA / "icon-512.png", optimize=True)
    app.resize((192, 192), Image.LANCZOS).save(SAIDA / "icon-192.png", optimize=True)
    favicon().save(SAIDA / "favicon.png", optimize=True)
    (SAIDA / "logo-horizontal.svg").write_text(logo_horizontal_svg(), encoding="utf-8")
    print("Marca gerada em", SAIDA)


if __name__ == "__main__":
    main()
