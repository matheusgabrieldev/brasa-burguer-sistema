"""Importa o cardápio levantado do OlaClick (dados/cardapio-AAAA-MM-DD.json) para o banco.

Pode rodar de novo (perto da entrega, por exemplo) sem duplicar nada:
- produto é procurado pelo `slug`; grupo pelo `codigo` (o id do OlaClick).
- o que o Dono edita no sistema (foto enviada, visível, ordem, esgotado) NÃO é sobrescrito.
- produto que está no banco e não está no arquivo NÃO é apagado: só aparece em `ausentes`.
- loja, horários, bairros e formas de pagamento só são criados se ainda não existirem.

Também aplica as correções combinadas no PRD (seção 5) em relação ao OlaClick.
"""
from dataclasses import dataclass, field
from datetime import time
from decimal import Decimal

from django.db import transaction

from loja.models import Bairro, Configuracao, FormaPagamento, Horario

from .models import Categoria, GrupoOpcao, Opcao, Produto, ProdutoGrupo

# ---- Correções em relação ao OlaClick (PRD seção 5) ----------------------------
GRUPO_CEBOLA = "9e5f41ff-d180-443f-a22e-c1a68821fb41"
GRUPO_RETIRAR = "9e5b6281-d1e9-4f0d-9655-b85c8650d01a"
CORRECOES_GRUPOS = {
    GRUPO_CEBOLA: {
        "nome": "Cebola", "tipo": GrupoOpcao.UNICA, "minimo": 0, "maximo": 1, "obrigatorio": False,
        "opcoes": [("Cebola crua", 0, 1), ("Cebola caramelizada", 0, 1), ("Sem cebola", 0, 1)],
    },
    GRUPO_RETIRAR: {
        "nome": "Quer tirar algum ingrediente?", "tipo": GrupoOpcao.VARIAS, "minimo": 0, "maximo": 2, "obrigatorio": False,
        "opcoes": [("Sem alface", 0, 1), ("Sem tomate", 0, 1)],
    },
}
GRUPO_MOLHO_ONION = {
    "codigo": "molho-onion", "nome": "Escolha o molho", "tipo": GrupoOpcao.UNICA, "minimo": 1, "maximo": 1,
    "obrigatorio": True, "opcoes": [("Barbecue", 0, 1), ("Maionese artesanal", 0, 1)],
}
PRODUTO_ONION = "Onion Ring + molho barbecue"

# Selo "Mais pedido" (escolha inicial, igual ao protótipo; o Dono ajusta depois)
MAIS_PEDIDOS = {"Brasa Premium", "Combo Brasa Premium", "Cheddar Bacon", "Coalho Nordestino em dobro"}

LOJA = {
    "nome": "Brasa Burguer",
    "slogan": "O hambúrguer na brasa do bairro",
    "endereco": "Rua das Flores, 120 - Centro, Recife - PE",
    "whatsapp": "5581990001234",
    "instagram": "brasa.burguer",
    "prazo": "15 - 80 min",
    "pedido_minimo": Decimal("10"),
    "chave_pix": "81990001234",
}
# Dinheiro no delivery: aceito, como no OlaClick hoje (PENDENTE confirmar com a Ana — é só desmarcar).
FORMAS = [
    ("pix", "Pix", Decimal("0")),
    ("credito", "Cartão de crédito", Decimal("4")),
    ("debito", "Cartão de débito", Decimal("1")),
    ("dinheiro", "Dinheiro", Decimal("0")),
]
DIAS_OLACLICK = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


@dataclass
class ResumoImportacao:
    criados: int = 0
    atualizados: int = 0
    ausentes: list = field(default_factory=list)


def _salvar_grupo(codigo, nome, tipo, minimo, maximo, obrigatorio, opcoes):
    """Cria ou atualiza o grupo; opções são procuradas pelo nome (para não perder 'esgotado')."""
    grupo, _ = GrupoOpcao.objects.update_or_create(
        codigo=codigo,
        defaults={"nome": nome, "tipo": tipo, "minimo": minimo, "maximo": maximo, "obrigatorio": obrigatorio},
    )
    nomes = []
    for i, (nome_op, preco, qmax) in enumerate(opcoes):
        Opcao.objects.update_or_create(
            grupo=grupo, nome=nome_op, defaults={"preco": Decimal(str(preco)), "qtd_maxima": qmax, "ordem": i}
        )
        nomes.append(nome_op)
    grupo.opcoes.exclude(nome__in=nomes).delete()
    return grupo


def _importar_grupos(dados):
    grupos = {}
    for codigo, g in dados["grupos"].items():
        if codigo in CORRECOES_GRUPOS:
            c = CORRECOES_GRUPOS[codigo]
            grupos[codigo] = _salvar_grupo(codigo, c["nome"], c["tipo"], c["minimo"], c["maximo"], c["obrigatorio"], c["opcoes"])
            continue
        obrigatorio = bool(g["obrigatorio"])
        tipo = GrupoOpcao.UNICA if g["tipo"] == "one" else GrupoOpcao.VARIAS
        opcoes = [(o["nome"], o["preco"], o["max"]) for o in g["opcoes"] if o.get("visivel", True)]
        # OlaClick grava min=1 mesmo em grupo opcional; aqui opcional = mínimo 0.
        minimo = g["min"] if obrigatorio else 0
        grupos[codigo] = _salvar_grupo(codigo, g["nome"], tipo, minimo, g["max"], obrigatorio, opcoes)
    m = GRUPO_MOLHO_ONION
    molho = _salvar_grupo(m["codigo"], m["nome"], m["tipo"], m["minimo"], m["maximo"], m["obrigatorio"], m["opcoes"])
    return grupos, molho


def _importar_loja(dados):
    cfg = Configuracao.atual()
    for campo in ("nome", "slogan", "endereco", "whatsapp", "instagram", "chave_pix"):
        if not getattr(cfg, campo):  # só preenche o que está em branco; prazo e mínimo já vêm do padrão do modelo
            setattr(cfg, campo, LOJA[campo])
    cfg.save()
    for dia, chave in enumerate(DIAS_OLACLICK):
        h = dados.get("horarios", {}).get(chave)
        if not h or Horario.objects.filter(dia_semana=dia).exists():
            continue
        faixa = h["hours"][0]
        Horario.objects.create(
            dia_semana=dia, abre=time.fromisoformat(faixa["open"]), fecha=time.fromisoformat(faixa["close"]), ativo=h["is_active"]
        )
    for b in dados.get("bairros", []):
        Bairro.objects.get_or_create(nome=b["nome"], defaults={"taxa": Decimal(str(b["taxa"])), "ativo": b["ativo"]})
    for i, (codigo, nome, pct) in enumerate(FORMAS):
        FormaPagamento.objects.get_or_create(codigo=codigo, defaults={"nome": nome, "acrescimo_pct": pct, "ordem": i})


def _categoria(cat, ordem):
    """Acha a categoria pelo nome ou cria. Só é usada para produto novo."""
    categoria = Categoria.objects.filter(nome=cat["nome"]).first()
    if categoria is None:
        categoria = Categoria.objects.create(nome=cat["nome"], ordem=ordem, visivel=cat.get("visivel", True))
    return categoria


@transaction.atomic
def importar(dados):
    resumo = ResumoImportacao()
    _importar_loja(dados)
    grupos, molho = _importar_grupos(dados)

    destaques = {p["slug"] for c in dados["categorias"] if c["tipo"] != "NORMAL" for p in c["produtos"]}
    vistos = set()
    normais = [c for c in dados["categorias"] if c["tipo"] == "NORMAL"]
    for ci, cat in enumerate(normais):
        for pi, p in enumerate(cat["produtos"]):
            campos = {
                "nome": p["nome"],
                "descricao": p.get("descricao") or "",
                "preco": Decimal(str(p["variantes"][0]["preco"])),
                "foto_url": p.get("foto") or "",
            }
            produto = Produto.objects.filter(slug=p["slug"]).first()
            if produto:  # edições do dono (categoria, destaque, selo) não são mexidas
                for k, v in campos.items():
                    setattr(produto, k, v)
                produto.save()
                resumo.atualizados += 1
            else:
                produto = Produto.objects.create(
                    slug=p["slug"], ordem=pi, visivel=p.get("visivel", True), categoria=_categoria(cat, ci),
                    destaque=p["slug"] in destaques, mais_pedido=p["nome"] in MAIS_PEDIDOS, **campos,
                )
                resumo.criados += 1
            vistos.add(produto.pk)

            codigos = [g for g in p.get("grupos", []) if g in grupos]
            ligados = [grupos[g] for g in dict.fromkeys(codigos)]
            if p["nome"] == PRODUTO_ONION:
                ligados = [molho] + ligados
            ProdutoGrupo.objects.filter(produto=produto).delete()
            ProdutoGrupo.objects.bulk_create(
                ProdutoGrupo(produto=produto, grupo=g, ordem=i) for i, g in enumerate(ligados)
            )

    resumo.ausentes = list(Produto.objects.exclude(pk__in=vistos).order_by("nome").values_list("nome", flat=True))
    return resumo
