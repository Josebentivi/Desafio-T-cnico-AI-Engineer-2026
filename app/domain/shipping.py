from __future__ import annotations

from app.domain.money import format_brl


def shipping_estimate(city: str, total_cents: int) -> dict:
    normalized = (city or "").strip().casefold()
    if normalized == "campo grande":
        free = total_cents >= 50000
        fee_cents = 0 if free else 3500
        return {
            "region": "campo_grande",
            "city": city,
            "free_shipping": free,
            "fee_cents": fee_cents,
            "fee_brl": format_brl(fee_cents),
            "eta": "1 to 3 business days",
            "note": "Delivered by the store's courier after contacting the customer.",
        }
    return {
        "region": "outside_campo_grande",
        "city": city,
        "requires_cep": True,
        "modalities": [
            {"name": "PAC (Correios)", "eta": "5 to 12 business days"},
            {"name": "SEDEX (Correios)", "eta": "2 to 5 business days"},
            {"name": "Jadlog (.package)", "eta": "3 to 8 business days"},
        ],
        "note": (
            "Shipping is calculated using the postal code, weight, and dimensions. "
            "Large instruments may require an individual quote."
        ),
    }
