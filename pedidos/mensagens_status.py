"""Textos de WhatsApp que o painel oferece para avisar o cliente de cada etapa."""
from urllib.parse import urlencode

MENSAGENS = {
    "aceito": "✅ Oi {nome}, seu pedido Nº {n} foi aceito. Estamos preparando tudo.",
    "pronto": "🛍️ Seu pedido Nº {n} está pronto, {nome}. Pode vir buscar!",
    "saiu": "🛵 Seu pedido Nº {n} já está a caminho, {nome}.",
    "falar": "Olá, {nome}! Aqui é da Brasa Burguer, sobre o seu pedido Nº {n}: ",
    "cancelado": "🚫 Lamentamos informar que o pedido Nº {n} foi cancelado.{motivo}",
}

ROTULOS = {
    "aceito": "Pedido aceito",
    "pronto": "Pronto p/ retirada",
    "saiu": "Saiu p/ entrega",
    "falar": "Falar com o cliente",
    "cancelado": "Avisar cancelamento",
}


def mensagem_status(pedido, chave):
    # O motivo só entra na frase quando existe, para não sobrar "Motivo: ."
    motivo = f" Motivo: {pedido.motivo_cancelamento}." if pedido.motivo_cancelamento else ""
    return MENSAGENS[chave].format(nome=pedido.nome, n=pedido.numero, motivo=motivo)


def link_cliente(pedido, chave):
    consulta = urlencode({"text": mensagem_status(pedido, chave)})
    return f"https://wa.me/55{pedido.telefone}?{consulta}"


def mensagens_disponiveis(pedido):
    """Botões do pedido como (chave, rótulo); pedido no local só conversa."""
    cancelado = pedido.status == "cancelado"
    entrega_ou_retirada = pedido.tipo in ("delivery", "retirada")
    chaves = []
    if entrega_ou_retirada and not cancelado:
        chaves.append("aceito")
    # Pedido cancelado nunca recebe "pronto"/"saiu": evitaria um aviso contraditório
    if pedido.tipo == "retirada" and not cancelado:
        chaves.append("pronto")
    if pedido.tipo == "delivery" and not cancelado:
        chaves.append("saiu")
    chaves.append("falar")
    if cancelado and entrega_ou_retirada:
        chaves.append("cancelado")
    return [(c, ROTULOS[c]) for c in chaves]


def atalho_depois_de(pedido):
    """Mensagem sugerida logo após a mudança de status, se houver uma natural."""
    chave = None
    if pedido.status == "pronto" and pedido.tipo == "retirada":
        chave = "pronto"
    elif pedido.status == "saiu":
        chave = "saiu"
    elif pedido.status == "cancelado" and pedido.tipo in ("delivery", "retirada"):
        chave = "cancelado"
    return (chave, ROTULOS[chave]) if chave else None
