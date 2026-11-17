"""Pedido, seus itens, o histórico de status e o contador do dia."""
import secrets
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


def gerar_codigo():
    """Código aleatório da URL de acompanhar (não dá para adivinhar o do vizinho)."""
    return secrets.token_urlsafe(9)


def dinheiro(**extra):
    """Campo de valor em reais, nunca negativo."""
    return models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(0)], **extra)


class Pedido(models.Model):
    """Um pedido feito no site ou no PDV. Nome, telefone e endereço são copiados na hora."""

    STATUS = [
        ("aguardando", "Aguardando aceite"),  # entrada manual: a loja ainda não aceitou
        ("agendado", "Agendado"),
        ("preparo", "Em preparo"),
        ("pronto", "Pronto"),
        ("saiu", "Saiu para entrega"),
        ("concluido", "Concluído"),
        ("cancelado", "Cancelado"),
    ]
    TIPOS = [("delivery", "Delivery"), ("retirada", "Retirada"), ("local", "No local")]
    ORIGENS = [("site", "Site"), ("pdv", "PDV")]

    codigo = models.CharField(max_length=20, unique=True, default=gerar_codigo, editable=False)
    chave = models.UUIDField(unique=True, help_text="Enviada pelo formulário: evita pedido duplicado.")
    numero = models.PositiveIntegerField("número do dia")
    dia = models.DateField(help_text="Data local (Recife) em que o pedido foi feito.")
    origem = models.CharField(max_length=10, choices=ORIGENS)
    tipo = models.CharField(max_length=10, choices=TIPOS)
    status = models.CharField(max_length=10, choices=STATUS, default="preparo")
    cliente = models.ForeignKey("clientes.Cliente", on_delete=models.PROTECT, related_name="pedidos")

    nome = models.CharField(max_length=80)
    telefone = models.CharField(max_length=11)
    bairro_nome = models.CharField("bairro", max_length=80, blank=True)
    rua = models.CharField(max_length=120, blank=True)
    numero_end = models.CharField("número (endereço)", max_length=20, blank=True)
    referencia = models.CharField("referência", max_length=200, blank=True)

    agendado_para = models.DateTimeField(null=True, blank=True)
    observacao = models.CharField("observação", max_length=500, blank=True)
    forma_pagamento_nome = models.CharField(max_length=60, blank=True)
    forma_pagamento_codigo = models.CharField(max_length=30, blank=True)
    troco_para = dinheiro(null=True, blank=True)

    subtotal = dinheiro()
    taxa_entrega = dinheiro(default=Decimal("0"))
    acrescimo = dinheiro(default=Decimal("0"))
    desconto = dinheiro(default=Decimal("0"))
    total = dinheiro()
    pago = models.BooleanField(default=False)
    criado_em = models.DateTimeField(auto_now_add=True)
    ip_hash = models.CharField(max_length=64, blank=True, default="", db_index=True, editable=False,
                               help_text="Código da rede de quem pediu pelo site (freio contra robô). Vazio no PDV.")
    visto_em = models.DateTimeField(null=True, blank=True, help_text="Quando a loja viu o pedido novo (apaga o destaque de 'novo').")
    motivo_cancelamento = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-criado_em"]
        constraints = [models.UniqueConstraint(fields=["dia", "numero"], name="pedido_numero_unico_no_dia")]

    def __str__(self):
        return f"Pedido {self.numero} de {self.dia:%d/%m/%Y}"

    @property
    def troco(self):
        """Quanto devolver ao cliente, ou None se ele não pediu troco."""
        if self.troco_para is None:
            return None
        return max(self.troco_para - self.total, Decimal("0"))


class ItemPedido(models.Model):
    """Linha do pedido. Nome e preço são copiados: mudar o cardápio não altera o passado."""

    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name="itens")
    produto = models.ForeignKey("cardapio.Produto", null=True, on_delete=models.SET_NULL)
    nome = models.CharField(max_length=120)
    preco_unitario = dinheiro(help_text="De 1 unidade, já com as opções.")
    quantidade = models.PositiveSmallIntegerField(default=1)
    opcoes = models.JSONField(default=list, blank=True, help_text='[{"grupo","nome","qtd","preco"}]')
    observacao = models.CharField("observação", max_length=300, blank=True)

    class Meta:
        ordering = ["id"]  # na ordem em que o cliente pediu
        verbose_name = "item do pedido"
        verbose_name_plural = "itens do pedido"

    def __str__(self):
        return f"{self.quantidade}x {self.nome}"

    @property
    def total(self):
        return self.preco_unitario * self.quantidade


class HistoricoStatus(models.Model):
    """Cada mudança de status do pedido, com a hora."""

    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name="historico")
    status = models.CharField(max_length=10, choices=Pedido.STATUS)
    em = models.DateTimeField(auto_now_add=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                help_text="Quem mudou o status (vazio quando foi o próprio sistema/cliente).")
    nota = models.CharField(max_length=200, blank=True, help_text='Ex.: "voltou", "pago", "recusado: motivo".')

    class Meta:
        ordering = ["em"]
        verbose_name = "histórico de status"
        verbose_name_plural = "histórico de status"


class ContadorDia(models.Model):
    """Último número usado em cada dia."""

    dia = models.DateField(unique=True)
    ultimo = models.PositiveIntegerField(default=0)
