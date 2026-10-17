"""Reusable money-display template filters.

Single source of truth for rendering monetary amounts. The output is
deliberately locale-independent (Western digits, ``,`` grouping, ``.`` decimal)
so it matches the ``amount-input`` fields (IMask, en-US) in both the English and
Arabic (RTL) layouts.

Usage::

    {% load money %}
    {{ operation.amount|money }}            {# E£ 1,234,567.89 #}
    {{ operation.amount|money_plain }}      {# 1,234,567.89 #}
    {{ delta|money_signed }}                {# +E£ 5.00 / -E£ 5.00 #}
    {{ value|money:'€' }}                   {# explicit symbol override #}

``None``/blank/invalid values render as ``E£ 0.00`` and negatives as ``-E£ 1.00``.
"""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django import template
from django.conf import settings

register = template.Library()

DEFAULT_SYMBOL = "E£"
_CENTS = Decimal("0.01")


def _symbol(symbol=None):
    """Resolve the currency symbol: explicit non-empty arg > ``settings.CURRENCY_SYMBOL``."""
    if symbol:
        return symbol
    return getattr(settings, "CURRENCY_SYMBOL", DEFAULT_SYMBOL) or DEFAULT_SYMBOL


def _to_decimal(value):
    """Coerce ``value`` to a finite :class:`~decimal.Decimal` (0 on bad input)."""
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        result = value
    else:
        try:
            result = Decimal(str(value).strip())
        except (InvalidOperation, ValueError, TypeError):
            return Decimal("0")
    if not result.is_finite():
        return Decimal("0")
    return result


def _magnitude(number):
    """Format ``abs(number)`` to 2 decimals with thousands grouping (half-up)."""
    return format(abs(number).quantize(_CENTS, rounding=ROUND_HALF_UP), ",.2f")


def _sign_and_magnitude(value):
    """Return ``(negative, "1,234.56")`` for ``value``."""
    number = _to_decimal(value)
    return number < 0, _magnitude(number)


@register.filter
def money(value, symbol=None):
    """Render ``value`` as ``$ 1,234.56`` (symbol + thousands grouping)."""
    negative, magnitude = _sign_and_magnitude(value)
    sign = "-" if negative else ""
    return f"{sign}{_symbol(symbol)} {magnitude}"


@register.filter
def money_plain(value, symbol=None):
    """Like :func:`money` but without the currency symbol."""
    negative, magnitude = _sign_and_magnitude(value)
    sign = "-" if negative else ""
    return f"{sign}{magnitude}"


@register.filter
def money_signed(value, symbol=None):
    """Render with an explicit leading sign: ``+$ 5.00`` / ``-$ 5.00``."""
    number = _to_decimal(value)
    sign = "-" if number < 0 else "+"
    return f"{sign}{_symbol(symbol)} {_magnitude(number)}"
