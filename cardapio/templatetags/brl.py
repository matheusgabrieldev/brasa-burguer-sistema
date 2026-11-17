from decimal import Decimal

from django import template

register = template.Library()


@register.filter
def brl(valor):
    """12.5 -> 'R$ 12,50'"""
    try:
        v = Decimal(str(valor or 0))
    except Exception:
        return valor
    txt = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {txt}"
