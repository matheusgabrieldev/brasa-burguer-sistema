"""Cardápio: Categoria -> Produto, com Grupos de opção (reutilizáveis) e suas Opções.

"Esgotado" guarda a DATA em que foi marcado. Assim o produto volta sozinho no dia seguinte,
sem precisar de nenhuma tarefa agendada. Para desmarcar na mão: esgotado_em = None.
"""
from django.core.validators import MinValueValidator
from django.db import models


class Categoria(models.Model):
    nome = models.CharField(max_length=80)
    ordem = models.PositiveIntegerField(default=0)
    visivel = models.BooleanField(default=True)

    class Meta:
        ordering = ["ordem", "id"]

    def __str__(self):
        return self.nome


class GrupoOpcao(models.Model):
    """Ex.: 'Escolha o ponto da carne'. 'unica' = uma opção só; 'varias' = pode marcar várias."""

    UNICA, VARIAS = "unica", "varias"
    TIPOS = [(UNICA, "Escolha única"), (VARIAS, "Várias")]

    codigo = models.CharField(max_length=60, unique=True)
    nome = models.CharField(max_length=80)
    tipo = models.CharField(max_length=10, choices=TIPOS)
    minimo = models.PositiveSmallIntegerField("mínimo", default=0)
    maximo = models.PositiveSmallIntegerField("máximo", default=1)
    obrigatorio = models.BooleanField("obrigatório", default=False)

    class Meta:
        ordering = ["nome"]
        verbose_name = "grupo de opção"
        verbose_name_plural = "grupos de opção"

    def __str__(self):
        return self.nome


class Opcao(models.Model):
    grupo = models.ForeignKey(GrupoOpcao, related_name="opcoes", on_delete=models.CASCADE)
    nome = models.CharField(max_length=80)
    preco = models.DecimalField("preço", max_digits=7, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    qtd_maxima = models.PositiveSmallIntegerField("qtd. máxima", default=1, help_text="Quantas vezes pode repetir (ex.: bacon x3)")
    ordem = models.PositiveIntegerField(default=0)
    esgotado_em = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["ordem", "id"]
        verbose_name = "opção"
        verbose_name_plural = "opções"

    def __str__(self):
        return f"{self.grupo.nome}: {self.nome}"

    def esta_esgotada(self, hoje):
        return self.esgotado_em == hoje


class Produto(models.Model):
    categoria = models.ForeignKey(Categoria, related_name="produtos", on_delete=models.PROTECT)
    slug = models.SlugField(max_length=120, unique=True)
    nome = models.CharField(max_length=100)
    descricao = models.TextField("descrição", blank=True)
    preco = models.DecimalField("preço", max_digits=7, decimal_places=2, validators=[MinValueValidator(0)])
    foto_url = models.URLField(blank=True, help_text="Foto original (OlaClick)")
    imagem = models.ImageField(upload_to="produtos/", max_length=200, blank=True)
    destaque = models.BooleanField(default=False)
    mais_pedido = models.BooleanField(default=False)
    sugerir_no_checkout = models.BooleanField(default=False, help_text='Aparece em "Complemente seu pedido" no checkout.')
    visivel = models.BooleanField("visível", default=True)
    ordem = models.PositiveIntegerField(default=0)
    esgotado_em = models.DateField(null=True, blank=True)
    grupos = models.ManyToManyField(GrupoOpcao, through="ProdutoGrupo", blank=True)

    class Meta:
        ordering = ["categoria__ordem", "ordem", "id"]

    def __str__(self):
        return self.nome

    @property
    def foto(self):
        """A foto enviada pela loja; se não tiver, a do OlaClick."""
        if self.imagem:
            return self.imagem.url
        return self.foto_url

    def esta_esgotado(self, hoje):
        return self.esgotado_em == hoje


class ProdutoGrupo(models.Model):
    """Liga produto e grupo, guardando a ordem em que o grupo aparece naquele produto."""

    produto = models.ForeignKey(Produto, on_delete=models.CASCADE)
    grupo = models.ForeignKey(GrupoOpcao, on_delete=models.CASCADE)
    ordem = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["ordem", "id"]
        constraints = [models.UniqueConstraint(fields=["produto", "grupo"], name="produto_grupo_unico")]
