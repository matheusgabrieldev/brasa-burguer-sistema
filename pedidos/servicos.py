"""Criar pedido: todas as regras do checkout ficam aqui.

O navegador manda só o que o cliente escolheu (IDs, quantidades, textos). Preço, taxa,
acréscimo e total são SEMPRE recalculados com os dados do banco. Qualquer coisa fora das
regras vira `PedidoInvalido`, com a mensagem pronta para mostrar e o `campo` com problema.
"""
import re
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.utils import timezone

from cardapio.precos import PrecoInvalido, calcular_item, dinheiro
from cardapio.templatetags.brl import brl
from clientes.models import Cliente
from clientes.servicos import cliente_do_telefone, normalizar_telefone
from loja.horario import status_loja
from loja.models import Bairro, Configuracao, FormaPagamento

from . import limite
from .agendamento import horarios_agendamento
from .models import HistoricoStatus, ItemPedido, Pedido
from .numeracao import proximo_numero

MAX_ITENS = 50
TROCO_MAX = Decimal("99999.99")  # cabe no campo do banco; ninguém paga com mais que isso
MSG_FECHADA = "A loja está fechada no momento."
MSG_BLOQUEADO = "Não conseguimos receber seu pedido agora. Fale com a loja no WhatsApp."
ONDE = {"delivery": "na entrega", "retirada": "na retirada", "local": "no local"}
ACEITA = {"delivery": "aceita_delivery", "retirada": "aceita_retirada", "local": "aceita_local"}


class PedidoInvalido(Exception):
    """Pedido fora das regras. A mensagem é para o cliente; `campo` diz onde está o problema."""

    def __init__(self, mensagem, campo=None):
        super().__init__(mensagem)
        self.campo = campo


def _limite(nome_campo):
    """Tamanho máximo do campo no modelo (assim a regra acompanha o modelo)."""
    return Pedido._meta.get_field(nome_campo).max_length


def _texto(dados, chave):
    return str(dados.get(chave) or "").strip()


def ler_valor(texto):
    """Lê um valor digitado pelo cliente: '50', '50,00', 'R$ 50', '1.000,00' -> Decimal.

    Vazio devolve None. Texto que não é um valor positivo vira PedidoInvalido.
    """
    t = str(texto or "").replace("R$", "").replace(" ", "").strip()
    if not t:
        return None
    if "," in t:  # formato brasileiro: ponto é milhar, vírgula é decimal
        t = t.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", t):  # '1.000' = mil
        t = t.replace(".", "")
    try:
        v = Decimal(t)
    except InvalidOperation:
        v = None
    if v is None or not v.is_finite() or v <= 0 or v > TROCO_MAX:
        raise PedidoInvalido("Valor do troco inválido. Digite só o número, ex.: 50", campo="troco")
    return dinheiro(v)


def _pedido_da_chave(chave):
    """Pedido já criado com esta chave (o cliente tocou duas vezes em "Enviar")."""
    return Pedido.objects.filter(chave=chave).first()


def _ler_chave(dados):
    if not isinstance(dados, dict):  # JSON que não é um objeto {...}
        raise PedidoInvalido("Pedido inválido. Recarregue a página.")
    try:
        return uuid.UUID(str(dados.get("chave") or ""))
    except ValueError:
        raise PedidoInvalido("Pedido inválido. Recarregue a página.")


def _ler_horario(texto):
    """'2026-11-18T18:15:00-03:00' ou '2026-11-18T18:15' (hora de Recife) -> datetime com fuso."""
    try:
        quando = datetime.fromisoformat(texto)
    except ValueError:
        return None
    if timezone.is_naive(quando):
        quando = timezone.make_aware(quando)
    return quando


def _conferir_horario(dados, agora):
    """Loja aberta: pedido é para agora. Fechada: precisa de um horário da lista. Devolve o horário ou None."""
    texto = _texto(dados, "agendar_para")
    if status_loja(agora).aberta:
        if texto:
            raise PedidoInvalido("A loja abriu: o pedido agora é para já. Recarregue a página.", campo="horario")
        return None
    horarios = horarios_agendamento(agora)
    if not horarios:  # forçada a fechar ou sem abertura prevista: não há horário para escolher
        raise PedidoInvalido(MSG_FECHADA, campo="horario")
    if not texto:
        raise PedidoInvalido("A loja está fechada. Escolha um horário para agendar.", campo="horario")
    quando = _ler_horario(texto)
    if quando is None or quando not in horarios:
        raise PedidoInvalido("Esse horário não está disponível. Escolha outro.", campo="horario")
    return quando


def _calcular_itens(itens, hoje):
    """Recalcula cada item pelo banco (`calcular_item`). Erro de item vira PedidoInvalido."""
    calculados = []
    for item in itens:
        if not isinstance(item, dict):
            raise PedidoInvalido("Pedido inválido. Confira a sacola.", campo="itens")
        try:
            calculados.append(calcular_item(
                item.get("produto_id"), item.get("quantidade", 1), item.get("opcoes"), item.get("observacao") or "", hoje=hoje,
            ))
        except PrecoInvalido as e:
            raise PedidoInvalido(str(e), campo="itens")
    return calculados


def _conferir_entrega(dados, subtotal):
    """Delivery: bairro ativo, rua, número e pedido mínimo. Devolve (bairro, rua, número)."""
    try:
        bairro = Bairro.objects.get(pk=int(dados.get("bairro_id")))
    except (Bairro.DoesNotExist, TypeError, ValueError, OverflowError):
        raise PedidoInvalido("Escolha o bairro de entrega.", campo="bairro")
    if not bairro.ativo:
        raise PedidoInvalido(f"No momento não entregamos em {bairro.nome}.", campo="bairro")

    rua, numero = _texto(dados, "rua"), _texto(dados, "numero")
    # Rua e número grandes demais são recusados (não cortados): endereço cortado = entrega errada.
    if not rua:
        raise PedidoInvalido("Informe a rua.", campo="rua")
    if len(rua) > _limite("rua"):
        raise PedidoInvalido(f"A rua pode ter até {_limite('rua')} caracteres.", campo="rua")
    if not numero:
        raise PedidoInvalido("Informe o número.", campo="numero")
    if len(numero) > _limite("numero_end"):
        raise PedidoInvalido(f"O número pode ter até {_limite('numero_end')} caracteres.", campo="numero")

    minimo = Configuracao.atual().pedido_minimo
    if subtotal < minimo:
        raise PedidoInvalido(f"Pedido mínimo para entrega: {brl(minimo)}.", campo="itens")
    return bairro, rua, numero


def _conferir_pagamento(dados, tipo):
    try:
        forma = FormaPagamento.objects.get(codigo=_texto(dados, "pagamento"))
    except FormaPagamento.DoesNotExist:
        raise PedidoInvalido("Escolha a forma de pagamento.", campo="pagamento")
    if not getattr(forma, ACEITA[tipo]):
        raise PedidoInvalido(f"{forma.nome} não é aceito {ONDE[tipo]}.", campo="pagamento")
    return forma


def criar_pedido(dados: dict, agora: datetime | None = None, ip_hash: str = "") -> Pedido:
    """Confere tudo, recalcula os valores e grava o pedido. `agora` existe para os testes.

    As regras seguem a ordem do plano; a primeira que falhar levanta PedidoInvalido.
    `ip_hash` (vazio para o Dono) liga o freio contra robô; passando dele levanta limite.LimiteExcedido.
    """
    agora = agora or timezone.now()
    chave = _ler_chave(dados)
    existente = _pedido_da_chave(chave)
    if existente:
        return existente  # duplo toque: devolve o mesmo pedido, sem criar outro

    itens = dados.get("itens")
    if not isinstance(itens, list) or not itens:
        raise PedidoInvalido("A sacola está vazia.", campo="itens")
    if len(itens) > MAX_ITENS:
        raise PedidoInvalido(f"A sacola pode ter até {MAX_ITENS} itens.", campo="itens")

    nome = _texto(dados, "nome")
    if not nome:
        raise PedidoInvalido("Informe seu nome.", campo="nome")
    if len(nome) > _limite("nome"):
        raise PedidoInvalido(f"O nome pode ter até {_limite('nome')} letras.", campo="nome")
    try:
        telefone = normalizar_telefone(dados.get("telefone"))
    except ValueError as e:
        raise PedidoInvalido(str(e), campo="telefone")
    # Só consulta: o cliente é criado lá embaixo, junto com o pedido (se tudo der certo).
    if Cliente.objects.filter(telefone=telefone, bloqueado=True).exists():
        raise PedidoInvalido(MSG_BLOQUEADO)

    tipo = _texto(dados, "tipo")
    if tipo not in dict(Pedido.TIPOS):
        raise PedidoInvalido("Escolha entrega, retirada ou no local.", campo="tipo")
    agendado_para = _conferir_horario(dados, agora)

    calculados = _calcular_itens(itens, hoje=timezone.localdate(agora))
    subtotal = dinheiro(sum((c.total for c in calculados), Decimal("0")))

    bairro, rua, numero, taxa = None, "", "", Decimal("0")
    if tipo == "delivery":
        bairro, rua, numero = _conferir_entrega(dados, subtotal)
        taxa = dinheiro(bairro.taxa)

    forma = _conferir_pagamento(dados, tipo)
    acrescimo = dinheiro((subtotal + taxa) * forma.acrescimo_pct / 100)
    total = dinheiro(subtotal + taxa + acrescimo)
    troco_para = ler_valor(dados.get("troco_para")) if forma.codigo == "dinheiro" else None
    if troco_para is not None and troco_para < total:
        raise PedidoInvalido(f"O troco precisa ser para um valor igual ou maior que o total ({brl(total)}).", campo="troco")

    if Configuracao.atual().entrada_pedidos == "manual":
        status = "aguardando"  # a loja revisa e aceita no painel (o horário agendado continua guardado)
    else:
        status = "agendado" if agendado_para else "preparo"
    dia = timezone.localdate(agora)  # dia de Recife, não o dia em UTC
    try:
        # Tudo ou nada: se algo falhar, nem o cliente, nem o número do dia, nem os itens ficam gravados.
        with transaction.atomic():
            numero_dia = proximo_numero(dia)  # trava o contador do dia até o fim: a conta abaixo não tem corrida
            limite.conferir(ip_hash)
            pedido = Pedido.objects.create(
                chave=chave, numero=numero_dia, ip_hash=ip_hash, dia=dia, origem="site", tipo=tipo, status=status,
                cliente=cliente_do_telefone(telefone, nome), nome=nome, telefone=telefone,
                bairro_nome=bairro.nome if bairro else "", rua=rua, numero_end=numero,
                referencia=_texto(dados, "referencia")[:_limite("referencia")] if bairro else "",
                agendado_para=agendado_para, observacao=_texto(dados, "observacao")[:_limite("observacao")],
                forma_pagamento_nome=forma.nome, forma_pagamento_codigo=forma.codigo, troco_para=troco_para,
                subtotal=subtotal, taxa_entrega=taxa, acrescimo=acrescimo, total=total,
            )
            ItemPedido.objects.bulk_create([
                ItemPedido(
                    pedido=pedido, produto=c.produto, nome=c.nome, preco_unitario=c.preco_unitario,
                    quantidade=c.quantidade, observacao=c.observacao,
                    opcoes=[{"grupo": o.grupo, "nome": o.nome, "qtd": o.qtd, "preco": str(o.preco)} for o in c.opcoes],
                )
                for c in calculados
            ])
            HistoricoStatus.objects.create(pedido=pedido, status=status)
    except IntegrityError:
        # Dois envios com a mesma chave ao mesmo tempo: o segundo bate no "unique" e devolve o primeiro.
        existente = Pedido.objects.filter(chave=chave).first()
        if existente is None:
            raise
        return existente
    return pedido
