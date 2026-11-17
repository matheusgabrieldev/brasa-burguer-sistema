"""Cálculo de preço no servidor.

O navegador manda só IDs e quantidades. O preço NUNCA vem do cliente: aqui recalculamos tudo
a partir do banco, e validamos as regras do cardápio (esgotado, grupo obrigatório, limites).
Quem usa (o checkout) só precisa chamar `calcular_item` e tratar `PrecoInvalido`.
"""
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone

from .models import GrupoOpcao, Opcao, Produto
from .disponibilidade import grupo_disponivel

QTD_MIN, QTD_MAX = 1, 50
OBSERVACAO_MAX = 140


class PrecoInvalido(Exception):
    """Pedido fora das regras. A mensagem já está pronta para mostrar ao cliente."""


@dataclass
class OpcaoEscolhida:
    grupo: str
    nome: str
    qtd: int
    preco: Decimal  # preço de UMA unidade da opção


@dataclass
class ItemCalculado:
    produto: Produto
    nome: str
    preco_unitario: Decimal  # produto + opções, para 1 unidade do item
    quantidade: int
    opcoes: list[OpcaoEscolhida]
    observacao: str

    @property
    def total(self) -> Decimal:
        return dinheiro(self.preco_unitario * self.quantidade)


def dinheiro(valor: Decimal) -> Decimal:
    """Arredonda para centavos (0,005 sobe), como se espera em reais."""
    return Decimal(valor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calcular_item(
    produto_id: int,
    quantidade: int,
    opcoes: dict[int, int],
    observacao: str = "",
    hoje: date | None = None,
) -> ItemCalculado:
    """Valida um item da sacola e calcula o preço. `opcoes` = {opcao_id: quantidade}.

    `hoje` existe para os testes poderem simular outro dia (esgotado vale só no dia marcado).
    """
    hoje = hoje or timezone.localdate()

    # O navegador manda texto/JSON: normaliza tudo de uma vez. Qualquer lixo (letras, null,
    # número gigante) vira erro amigável em vez de erro 500. Chaves "12" (texto) funcionam.
    try:
        produto_id = int(produto_id)
        quantidade = max(QTD_MIN, min(int(quantidade), QTD_MAX))
        opcoes = {int(k): int(v) for k, v in dict(opcoes or {}).items()}
        produto = Produto.objects.select_related("categoria").prefetch_related("produtogrupo_set__grupo__opcoes").get(pk=produto_id)
    except Produto.DoesNotExist:
        raise PrecoInvalido("Um dos produtos não está mais disponível. Confira a sacola.")
    except (TypeError, ValueError, OverflowError):
        raise PrecoInvalido("Pedido inválido. Confira a sacola.")
    if not produto.visivel or not produto.categoria.visivel or produto.esta_esgotado(hoje):
        raise PrecoInvalido(f"{produto.nome} não está mais disponível. Confira a sacola.")

    # Só aceitamos opções que pertencem a um grupo DESTE produto (senão dava para
    # pedir uma opção barata/grátis de outro produto).
    grupos = [pg.grupo for pg in produto.produtogrupo_set.all()]
    ids_grupos = {g.id for g in grupos}
    opcoes_db = {o.id: o for o in Opcao.objects.filter(pk__in=opcoes.keys())}
    for opcao_id in opcoes:
        opcao = opcoes_db.get(opcao_id)
        if opcao is None or opcao.grupo_id not in ids_grupos:
            raise PrecoInvalido(f"Opção inválida para {produto.nome}. Confira a sacola.")

    preco = produto.preco
    escolhidas: list[OpcaoEscolhida] = []
    for grupo in grupos:  # a ordem dos grupos do produto vira a ordem das opções no pedido
        if not grupo_disponivel(grupo, hoje):
            raise PrecoInvalido(f"Indisponível no momento: {produto.nome}, grupo '{grupo.nome}'.")
        do_grupo = [(opcoes_db[i], q) for i, q in opcoes.items() if opcoes_db[i].grupo_id == grupo.id]

        for opcao, qtd in do_grupo:
            if qtd < 1:
                raise PrecoInvalido(f"Quantidade inválida para {opcao.nome}.")
            if opcao.esta_esgotada(hoje):
                raise PrecoInvalido(f"{opcao.nome} está esgotado. Escolha outra opção.")
            if qtd > opcao.qtd_maxima:
                raise PrecoInvalido(f"{opcao.nome}: máximo de {opcao.qtd_maxima} por item.")

        total_no_grupo = sum(q for _, q in do_grupo)
        if grupo.tipo == GrupoOpcao.UNICA:
            if len(do_grupo) > 1 or total_no_grupo > 1:
                raise PrecoInvalido(f"'{grupo.nome}' aceita só uma opção.")
        elif total_no_grupo > grupo.maximo:
            raise PrecoInvalido(f"'{grupo.nome}': escolha no máximo {grupo.maximo}.")

        if grupo.obrigatorio and total_no_grupo < max(grupo.minimo, 1):
            raise PrecoInvalido(f"{produto.nome}: escolha uma opção em '{grupo.nome}'.")

        for opcao, qtd in do_grupo:
            preco += opcao.preco * qtd
            escolhidas.append(OpcaoEscolhida(grupo.nome, opcao.nome, qtd, dinheiro(opcao.preco)))

    return ItemCalculado(
        produto=produto,
        nome=produto.nome,
        preco_unitario=dinheiro(preco),
        quantidade=quantidade,
        opcoes=escolhidas,
        observacao=(observacao or "").strip()[:OBSERVACAO_MAX],
    )
