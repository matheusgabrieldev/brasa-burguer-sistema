"""Formulários da área do Dono."""
import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django import forms
from django.conf import settings
from django.utils.text import slugify
from PIL import Image

from cardapio.fotos import otimizar_foto
from cardapio.models import Categoria, Produto


def ler_preco(texto):
    """Converte o que a Ana digitou em Decimal. Aceita "12,50", "12.5", "R$ 12,50", "1.234,50".

    Regras (na dúvida, recusa e pede de novo, para nunca errar o valor em silêncio):
    - vírgula separa os centavos (1 ou 2 dígitos): "12,5", "12,50";
    - ponto de milhar só no formato certo: "1.234", "1.234.567,89";
    - um ponto só com 1 ou 2 dígitos depois é separador de centavos: "12.50";
    - o resto ("1,234", "0.500", "1.2.3", "1,234.50") é recusado.
    """
    t = re.sub(r"(?i)r\$|\s", "", texto or "")
    if not t:
        raise ValueError("vazio")
    milhar = r"[1-9]\d{0,2}(?:\.\d{3})+"
    if re.fullmatch(rf"(?:{milhar}|\d+),\d{{1,2}}", t):
        t = t.replace(".", "").replace(",", ".")
    elif re.fullmatch(milhar, t):
        t = t.replace(".", "")
    elif not re.fullmatch(r"\d+(?:\.\d{1,2})?", t):
        raise ValueError("formato")
    try:
        valor = Decimal(t)
    except InvalidOperation:
        raise ValueError("formato")
    return valor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class FotoProdutoField(forms.ImageField):
    def to_python(self, data):
        if getattr(data, "size", 0) > settings.MAX_FOTO_BYTES:
            raise forms.ValidationError("A foto deve ter no máximo 10 MiB.", code="foto_grande")
        return super().to_python(data)


class ProdutoForm(forms.ModelForm):
    preco = forms.CharField(
        label="Preço (R$)",
        widget=forms.TextInput(attrs={"class": "input", "inputmode": "decimal", "placeholder": "Ex.: 29,90"}),
    )
    imagem = FotoProdutoField(
        label="Foto", required=False,
        error_messages={"invalid_image": "Esse arquivo não é uma foto. Envie uma imagem (JPG ou PNG)."},
    )
    remover_foto = forms.BooleanField(label="Remover foto", required=False)

    class Meta:
        model = Produto
        fields = ["nome", "descricao", "preco", "categoria", "destaque", "mais_pedido", "sugerir_no_checkout", "visivel"]
        labels = {
            "nome": "Nome do produto",
            "descricao": "Descrição",
            "categoria": "Categoria",
            "destaque": "Mostrar nos destaques (topo do cardápio)",
            "mais_pedido": 'Selo "Mais pedido"',
            "sugerir_no_checkout": 'Sugerir no checkout ("Complemente seu pedido")',
            "visivel": "Aparece no cardápio",
        }
        widgets = {
            "nome": forms.TextInput(attrs={"class": "input", "placeholder": "Ex.: X-Bacon Duplo"}),
            "descricao": forms.Textarea(attrs={"class": "input", "rows": 3, "placeholder": "Ex.: Pão brioche, 2 carnes de 90g, cheddar e bacon"}),
            "categoria": forms.Select(attrs={"class": "input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["categoria"].empty_label = "Escolha a categoria"
        if self.instance.pk:  # mostra o preço no formato brasileiro
            self.initial["preco"] = f"{self.instance.preco:.2f}".replace(".", ",")

    def clean_preco(self):
        try:
            valor = ler_preco(self.cleaned_data["preco"])
        except ValueError:
            raise forms.ValidationError("Digite o preço em reais, por exemplo 12,50.")
        if valor <= 0:
            raise forms.ValidationError("O preço precisa ser maior que zero.")
        if valor >= Decimal("100000"):
            raise forms.ValidationError("Esse preço é alto demais. Confira o valor.")
        return valor

    def _slug_livre(self, nome):
        """Gera o endereço do produto a partir do nome; se já existe, acrescenta -2, -3..."""
        base = slugify(nome)[:110] or "produto"
        slug, n = base, 2
        while Produto.objects.filter(slug=slug).exists():
            slug = f"{base}-{n}"
            n += 1
        return slug

    def clean_imagem(self):
        imagem = self.cleaned_data.get("imagem")
        if not imagem:
            return imagem
        try:
            return otimizar_foto(imagem)
        except (OSError, ValueError, SyntaxError, Image.DecompressionBombError) as exc:
            raise forms.ValidationError(
                "Não foi possível preparar essa foto. Envie outra imagem (JPG ou PNG).",
                code="invalid_image",
            ) from exc

    def save(self, commit=True):
        produto = super().save(commit=False)
        if not produto.slug:  # só produto novo: ao editar o endereço não muda
            produto.slug = self._slug_livre(produto.nome)
        if self.cleaned_data.get("imagem"):
            produto.imagem = self.cleaned_data["imagem"]
        elif self.cleaned_data.get("remover_foto"):
            produto.imagem = ""
        if commit:
            produto.save()
        return produto


class CategoriaForm(forms.ModelForm):
    class Meta:
        model = Categoria
        fields = ["nome"]
        widgets = {"nome": forms.TextInput(attrs={"class": "input", "placeholder": "Ex.: Sobremesas"})}
