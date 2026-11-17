"""Consultas do painel de pedidos: o que aparece em cada coluna, filtros, busca, total e versão.

Só lê (exceto `promover_agendados`). As telas chamam `montar_painel` e recebem tudo pronto,
sem fazer consulta no template.
"""
import re
from dataclasses import dataclass, field
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db import transaction
from django.db.models import Count, Max, Q, Sum
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone

from loja.models import Configuracao
from pedidos.models import HistoricoStatus, Pedido
from pedidos.painel import ANTECEDENCIA_AGENDADO, _mudar, _trancar

RECIFE = ZoneInfo("America/Recife")
ABERTOS = ("aguardando", "preparo", "pronto", "saiu")
LIMITE_CONCLUIDOS = 20
TITULOS = {
    "aguardando": "Aguardando aceite", "preparo": "Em preparo", "pronto": "Pronto",
    "saiu": "Saiu para entrega", "concluido": "Concluído", "resultado": "Resultado",
}


@dataclass
class Coluna:
    status: str
    titulo: str
    pedidos: list
    total_itens: int


@dataclass
class Painel:
    colunas: list = field(default_factory=list)
    agendados: list = field(default_factory=list)
    contagem_tipo: dict = field(default_factory=dict)
    novos: int = 0


def com_dia_efetivo(qs):
    """Anota o dia em que o pedido conta: o da entrega (se agendado) ou o dia em que foi feito."""
    return qs.annotate(dia_efetivo=Coalesce(TruncDate("agendado_para", tzinfo=RECIFE), "dia"))


def promover_agendados(agora):
    """Agendados que faltam 30 min ou menos viram 'em preparo' (entram no painel como novos)."""
    limite = agora + ANTECEDENCIA_AGENDADO
    with transaction.atomic():
        ids = list(Pedido.objects.filter(status="agendado", agendado_para__lte=limite).values_list("pk", flat=True))
        for pk in ids:
            pedido = _trancar(pk)
            if pedido.status != "agendado":
                continue
            _mudar(pedido, "preparo", None, nota="agendado: começou", visto_em=None)
    return len(ids)


def _base():
    return com_dia_efetivo(Pedido.objects.prefetch_related("itens"))


def _coluna(status, pedidos, titulo=None):
    pedidos = list(pedidos)
    itens = sum(i.quantidade for p in pedidos for i in p.itens.all())
    return Coluna(status, titulo or TITULOS[status], pedidos, itens)


def _filtrar_busca(qs, busca):
    digitos = re.sub(r"\D", "", busca)
    if digitos:
        return qs.filter(numero=int(digitos)) if len(digitos) <= 3 else qs.filter(telefone__contains=digitos)
    return qs.filter(nome__icontains=busca.strip())


def montar_painel(hoje, tipo="", busca="", todos_concluidos=False):
    base = _base()
    abertos = base.filter(status__in=ABERTOS)
    contagem = {"tudo": 0, "delivery": 0, "retirada": 0, "local": 0}
    for linha in abertos.values("tipo").annotate(n=Count("id")):
        contagem[linha["tipo"]] = linha["n"]
        contagem["tudo"] += linha["n"]
    contagem["agendados"] = base.filter(status="agendado").count()
    novos = Pedido.objects.filter(status__in=("aguardando", "preparo"), visto_em__isnull=True).count()
    painel = Painel(contagem_tipo=contagem, novos=novos)

    if tipo == "agendados" and not busca:
        painel.agendados = list(base.filter(status="agendado").order_by("agendado_para", "id"))
        return painel

    filtro_tipo = Q(tipo=tipo) if tipo in ("delivery", "retirada", "local") else Q()

    if busca.strip():
        universo = base.filter(Q(status__in=ABERTOS) | Q(dia_efetivo=hoje)).filter(filtro_tipo)
        achados = _filtrar_busca(universo, busca).order_by("criado_em", "id")
        painel.colunas = [_coluna("resultado", achados)]
        return painel

    painel.agendados = list(base.filter(status="agendado").filter(filtro_tipo).order_by("agendado_para", "id"))
    existe_aguardando = abertos.filter(status="aguardando").exists()
    status_colunas = ["preparo", "pronto", "saiu"]
    if Configuracao.atual().entrada_pedidos == "manual" or existe_aguardando:
        status_colunas.insert(0, "aguardando")
    for status in status_colunas:
        qs = abertos.filter(status=status).filter(filtro_tipo).order_by("criado_em", "id")
        painel.colunas.append(_coluna(status, qs))

    concluidos = (base.filter(status__in=("concluido", "cancelado"), dia_efetivo=hoje).filter(filtro_tipo)
                  .order_by("-criado_em", "-id"))
    painel.colunas.append(_coluna("concluido", concluidos if todos_concluidos else concluidos[:LIMITE_CONCLUIDOS]))
    return painel


def total_do_dia(hoje):
    """(quantidade, soma) dos pedidos do dia: sem cancelados e sem os que a loja ainda não aceitou."""
    qs = com_dia_efetivo(Pedido.objects).filter(dia_efetivo=hoje).exclude(status__in=("cancelado", "aguardando"))
    r = qs.aggregate(n=Count("id"), soma=Sum("total"))
    return r["n"], r["soma"] or Decimal("0")


def versao_painel(agora):
    """Texto que muda quando algo do painel mudou (histórico novo, pedido visto, virada do dia)
    ou quando vira o minuto (para os "12 min" do cartão e o vermelho dos 40 min andarem sozinhos).

    O aparelho compara com a última versão e só recarrega as colunas se for diferente:
    no máximo um redesenho por minuto quando nada acontece.
    """
    local = timezone.localtime(agora, RECIFE)
    # máximo E contagem: no Postgres o id é reservado no INSERT, não no commit; um id menor pode
    # aparecer depois do maior, e só o máximo não mudaria (pedido escondido até outra mudança)
    hist = HistoricoStatus.objects.aggregate(m=Max("id"), n=Count("id"))
    vistos = Pedido.objects.filter(visto_em__isnull=False).aggregate(m=Max("visto_em"), n=Count("id"))
    return f"{local:%Y-%m-%d %H%M}:{hist['m'] or 0}.{hist['n']}:{vistos['m']}:{vistos['n']}"
