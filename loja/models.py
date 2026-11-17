"""Dados da loja: configuração geral, horário, bairros de entrega e formas de pagamento."""
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models


class Configuracao(models.Model):
    """Uma linha só (pk=1). Use sempre Configuracao.atual()."""

    MODO_AUTO, MODO_ABERTA, MODO_FECHADA = "auto", "aberta", "fechada"
    MODOS = [(MODO_AUTO, "Pelo horário"), (MODO_ABERTA, "Forçar aberta"), (MODO_FECHADA, "Forçar fechada")]
    ENTRADAS = [("auto", "Automática: o pedido do site entra direto em preparo"),
                ("manual", "Manual: o pedido do site espera você revisar e aceitar")]

    modo_loja = models.CharField("modo da loja", max_length=10, choices=MODOS, default=MODO_AUTO)
    nome = models.CharField(max_length=80, default="Brasa Burguer")
    slogan = models.CharField(max_length=120, blank=True)
    endereco = models.CharField("endereço", max_length=200, blank=True)
    whatsapp = models.CharField(max_length=20, blank=True, help_text="Só números, com 55 e DDD. Ex.: 5581990001234")
    instagram = models.CharField(max_length=60, blank=True)
    chave_pix = models.CharField("chave Pix", max_length=120, blank=True)
    pix_titular = models.CharField("titular do Pix", max_length=80, blank=True)
    pix_banco = models.CharField("banco do Pix", max_length=60, blank=True)
    prazo = models.CharField(max_length=30, default="15 - 80 min")
    pedido_minimo = models.DecimalField("pedido mínimo (delivery)", max_digits=7, decimal_places=2, default=Decimal("10"), validators=[MinValueValidator(0)])
    vias_padrao = models.PositiveSmallIntegerField("vias da comanda", default=1)
    entrada_pedidos = models.CharField("entrada dos pedidos do site", max_length=10, choices=ENTRADAS, default="auto")

    class Meta:
        verbose_name = "configuração"
        verbose_name_plural = "configuração"

    def __str__(self):
        return "Configuração da loja"

    def save(self, *args, **kwargs):
        self.pk = 1  # garante que só existe uma linha
        super().save(*args, **kwargs)

    @classmethod
    def atual(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class Horario(models.Model):
    DIAS = [(0, "Segunda"), (1, "Terça"), (2, "Quarta"), (3, "Quinta"), (4, "Sexta"), (5, "Sábado"), (6, "Domingo")]

    dia_semana = models.PositiveSmallIntegerField("dia", choices=DIAS, unique=True)
    abre = models.TimeField()
    fecha = models.TimeField()
    ativo = models.BooleanField("abre neste dia", default=True)

    class Meta:
        ordering = ["dia_semana"]
        verbose_name = "horário"

    def __str__(self):
        if not self.ativo:
            return f"{self.get_dia_semana_display()}: fechado"
        return f"{self.get_dia_semana_display()}: {self.abre:%H:%M}–{self.fecha:%H:%M}"


class Bairro(models.Model):
    nome = models.CharField(max_length=80, unique=True)
    taxa = models.DecimalField(max_digits=6, decimal_places=2, validators=[MinValueValidator(0)])
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nome"]

    def __str__(self):
        return f"{self.nome} (R$ {self.taxa})"


class FormaPagamento(models.Model):
    codigo = models.SlugField(unique=True)
    nome = models.CharField(max_length=40)
    acrescimo_pct = models.DecimalField("acréscimo %", max_digits=5, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    aceita_delivery = models.BooleanField(default=True)
    aceita_retirada = models.BooleanField(default=True)
    aceita_local = models.BooleanField("aceita no local", default=True)
    ordem = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["ordem"]
        verbose_name = "forma de pagamento"
        verbose_name_plural = "formas de pagamento"

    def __str__(self):
        return self.nome
