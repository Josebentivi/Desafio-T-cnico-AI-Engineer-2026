from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from app.domain.money import format_brl, pix_cents


def payment_options(price_cents: int, *, allow_pix: bool = True) -> dict:
    options: dict = {
        "price_brl": format_brl(price_cents),
        "debit": {"available": True, "price_brl": format_brl(price_cents)},
        "boleto": {"available": True, "price_brl": format_brl(price_cents)},
        "pix": None,
        "credit": [],
    }
    if allow_pix:
        pix_value = pix_cents(price_cents)
        options["pix"] = {
            "available": True,
            "discount_percent": 5,
            "price_cents": pix_value,
            "price_brl": format_brl(pix_value),
        }

    if price_cents < 5000:
        max_installments = 1
    else:
        max_installments = 3
        if price_cents >= 8000:
            max_installments = max(max_installments, min(6, price_cents // 8000))
        if price_cents >= 10000:
            max_installments = max(max_installments, min(12, price_cents // 10000))

    for installments in range(1, max_installments + 1):
        installment_cents = int(
            (Decimal(price_cents) / Decimal(installments)).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            )
        )
        options["credit"].append(
            {
                "installments": installments,
                "installment_brl": format_brl(installment_cents),
                "total_brl": format_brl(installment_cents * installments),
                "interest_free": True,
            }
        )
    return options
