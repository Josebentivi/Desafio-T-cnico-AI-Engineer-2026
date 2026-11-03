from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal


def parse_brl_to_cents(value: str | int | float | Decimal) -> int:
    if isinstance(value, int):
        return value * 100
    if isinstance(value, float):
        value = str(value)
    if isinstance(value, Decimal):
        decimal_value = value
    else:
        text = str(value).strip().replace("R$", "").replace(" ", "")
        if "," in text:
            text = text.replace(".", "").replace(",", ".")
        elif re.fullmatch(r"\d{1,3}(?:\.\d{3})+", text):
            text = text.replace(".", "")
        decimal_value = Decimal(text)
    return int((decimal_value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def format_brl(cents: int) -> str:
    value = Decimal(cents) / Decimal(100)
    formatted = f"{value:,.2f}"
    return "R$ " + formatted.replace(",", "X").replace(".", ",").replace("X", ".")


def discount_cents(cents: int, percent: int | float) -> int:
    value = Decimal(cents) * (Decimal(100) - Decimal(str(percent))) / Decimal(100)
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def pix_cents(cents: int) -> int:
    return discount_cents(cents, 5)


def format_percent(value: int | float) -> str:
    return f"{value:g}%"
