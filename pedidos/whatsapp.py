"""Mensagem de confirmação do cliente para o WhatsApp da loja."""
from decimal import Decimal
from urllib.parse import urlencode

from django.utils import timezone

from clientes.servicos import formatar_telefone
from loja.models import Configuracao


def reais(valor):
    return "R$ " + f"{valor:,.2f}".translate(str.maketrans(",.", ".,"))


def _mensagem(pedido, loja):
    linhas = [
        "Olá! Quero confirmar meu pedido 🍔",
        f"*Pedido #{pedido.numero}* · {pedido.codigo}",
    ]
    if pedido.agendado_para:
        horario = timezone.localtime(pedido.agendado_para)
        linhas.append(f"🗓️ {horario:%d/%m/%Y} ⏰ {horario:%H:%M}")

    linhas.extend([
        f"*Tipo de serviço: {pedido.get_tipo_display()}*",
        f"Nome: {pedido.nome}",
        f"Telefone: {formatar_telefone(pedido.telefone)}",
    ])
    if pedido.tipo == "delivery":
        linhas.append(f"Endereço: {pedido.rua}, {pedido.numero_end} — {pedido.bairro_nome}")
        if pedido.referencia:
            linhas.append(f"Referência: {pedido.referencia}")

    linhas.append("*📝 Produtos*")
    for item in pedido.itens.all():
        linhas.append(f"*{item.quantidade}x {item.nome}  {reais(item.total)}*")
        for opcao in item.opcoes:
            qtd = opcao["qtd"]
            extra = Decimal(opcao["preco"]) * qtd
            quantidade = f"{qtd}x " if qtd > 1 else ""
            preco = f" {reais(extra)}" if extra else ""
            linhas.append(f'    + {quantidade}{opcao["nome"]}{preco}')
        if item.observacao:
            linhas.append(f"    _Obs.: {item.observacao}_")

    linhas.append(f"Subtotal: {reais(pedido.subtotal)}")
    if pedido.tipo == "delivery":
        linhas.append(f"Entrega: {reais(pedido.taxa_entrega)}")
    if pedido.acrescimo:
        linhas.append(f"Acréscimo cartão: {reais(pedido.acrescimo)}")
    if pedido.desconto:
        linhas.append(f"Desconto: {reais(pedido.desconto)}")
    linhas.extend([f"*Total: {reais(pedido.total)}*", f"*💲 Pagamento:* {pedido.forma_pagamento_nome}"])

    if pedido.forma_pagamento_codigo == "dinheiro" and pedido.troco_para is not None:
        linhas.append(f"Troco para {reais(pedido.troco_para)} (troco de {reais(pedido.troco)})")
    if pedido.forma_pagamento_codigo == "pix" and loja.chave_pix:
        pix = [f"Chave Pix: {loja.chave_pix}"]
        if loja.pix_titular:
            pix.append(f"Titular: {loja.pix_titular}")
        if loja.pix_banco:
            pix.append(f"Banco: {loja.pix_banco}")
        linhas.append(" · ".join(pix))
    if pedido.observacao:
        linhas.append(f"Observação: {pedido.observacao}")
    return "\n".join(linhas)


def mensagem_pedido(pedido):
    return _mensagem(pedido, Configuracao.atual())


def link_whatsapp(pedido, loja=None):
    if loja is None:
        loja = Configuracao.atual()
    if not loja.whatsapp:
        return ""
    consulta = urlencode({"text": _mensagem(pedido, loja)})
    return f"https://wa.me/{loja.whatsapp}?{consulta}"
