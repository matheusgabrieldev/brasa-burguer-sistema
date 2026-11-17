"""Clientes (lado da loja) e aparelhos que lembram dados (lado do cliente).

Regra de privacidade: o endereço salvo NUNCA é achado pelo telefone, só pelo
token secreto guardado no cookie do aparelho.
"""
from django.db import models


class Cliente(models.Model):
    """Quem já pediu, identificado pelo telefone. Serve para histórico e bloqueio."""

    telefone = models.CharField(max_length=11, unique=True, help_text="Só dígitos, com DDD.")
    nome = models.CharField(max_length=80)
    bloqueado = models.BooleanField(default=False)
    motivo_bloqueio = models.CharField("motivo do bloqueio", max_length=200, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nome"]

    def __str__(self):
        return f"{self.nome} ({self.telefone})"


class Dispositivo(models.Model):
    """Um navegador que escolheu 'lembrar de mim'. Guarda só o hash do token."""

    token_hash = models.CharField(max_length=64, unique=True)
    nome = models.CharField(max_length=80, blank=True)
    telefone = models.CharField(max_length=11, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    usado_em = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Aparelho de {self.nome or 'sem nome'}"


class EnderecoSalvo(models.Model):
    """Endereço lembrado por um aparelho."""

    dispositivo = models.ForeignKey(Dispositivo, on_delete=models.CASCADE, related_name="enderecos")
    bairro = models.ForeignKey("loja.Bairro", null=True, on_delete=models.SET_NULL)
    rua = models.CharField(max_length=120)
    numero = models.CharField("número", max_length=20)
    referencia = models.CharField("referência", max_length=200, blank=True)
    usado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-usado_em"]
        verbose_name = "endereço salvo"
        verbose_name_plural = "endereços salvos"

    def __str__(self):
        return f"{self.rua}, {self.numero}"
