"""Tratamento das fotos enviadas pela loja."""
import io
import uuid

from django.core.files.base import ContentFile


def otimizar_foto(arquivo, lado_max=1000):
    """Diminui a foto enviada (foto de celular tem 3-5 MB) para no máximo 1000px e salva em JPEG.

    Assim o cardápio continua rápido no 4G. Usa a biblioteca Pillow.
    """
    from PIL import Image, ImageOps

    img = Image.open(arquivo)
    img = ImageOps.exif_transpose(img)  # respeita a foto tirada "deitada" no celular
    if img.mode != "RGB":
        rgba = img.convert("RGBA")
        fundo = Image.new("RGB", rgba.size, (255, 255, 255))  # PNG transparente ganha fundo branco
        fundo.paste(rgba, mask=rgba.split()[-1])
        img = fundo
    img.thumbnail((lado_max, lado_max))
    saida = io.BytesIO()
    img.save(saida, "JPEG", quality=82, optimize=True)
    return ContentFile(saida.getvalue(), name=f"{uuid.uuid4()}.jpg")
