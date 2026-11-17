"""Capacidade cadastrada e disponibilidade diária dos grupos de opções."""
from datetime import date
from collections.abc import Iterable

from .models import GrupoOpcao, Opcao


def capacidade_grupo(tipo: str, opcoes: Iterable[Opcao]) -> int:
    """Escolha única comporta uma unidade; várias somam as repetições permitidas."""
    if tipo == GrupoOpcao.UNICA:
        return int(any(True for _ in opcoes))
    return sum(opcao.qtd_maxima for opcao in opcoes)


def grupo_disponivel(grupo: GrupoOpcao, hoje: date) -> bool:
    minimo = max(grupo.minimo, 1) if grupo.obrigatorio else 0
    disponiveis = (opcao for opcao in grupo.opcoes.all() if not opcao.esta_esgotada(hoje))
    return capacidade_grupo(grupo.tipo, disponiveis) >= minimo
