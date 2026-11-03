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
            "eta": "1 a 3 dias úteis",
            "note": "Entrega por motoboy próprio; o cliente é contactado antes da entrega.",
        }
    return {
        "region": "fora_campo_grande",
        "city": city,
        "requires_cep": True,
        "modalities": [
            {"name": "PAC (Correios)", "eta": "5 a 12 dias úteis"},
            {"name": "SEDEX (Correios)", "eta": "2 a 5 dias úteis"},
            {"name": "Jadlog (.package)", "eta": "3 a 8 dias úteis"},
        ],
        "note": (
            "O frete é calculado pelo CEP, peso e dimensões. "
            "Instrumentos de grande porte podem exigir cotação individual."
        ),
    }
