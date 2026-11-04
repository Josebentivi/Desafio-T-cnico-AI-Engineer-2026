from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

UI_LABELS = {
    "active": "Active", "discontinued": "Discontinued", "coming_soon": "Coming soon",
    "available": "Available", "out_of_stock": "Out of stock", "delivered": "Delivered",
    "confirmed": "Confirmed", "pending": "Pending", "cancelled": "Cancelled",
    "shipped": "Shipped", "user": "Customer", "assistant": "Assistant",
    "warning": "Warning", "info": "Information", "error": "Error",
    "product": "Product", "order": "Order", "category": "Category",
    "low": "Low", "medium": "Medium", "high": "High", "minimal": "Minimal", "none": "None",
    "search_products": "Catalog search", "get_product": "Instrument details",
    "get_active_promotions": "Active promotions", "get_order": "Order lookup",
    "search_policy": "Policy lookup", "get_store_status": "Store hours",
    "get_shipping_estimate": "Shipping estimate", "top": "Top", "back_sides": "Back and sides",
    "neck": "Neck", "strings": "Strings", "scale": "Scale", "electronics": "Electronics",
    "color": "Color", "body": "Body", "fretboard": "Fretboard", "frets": "Frets",
    "pickups": "Pickups", "bridge": "Bridge", "finish": "Finish", "keys": "Keys",
    "voices": "Voices", "polyphony": "Polyphony", "rhythms": "Rhythms", "speakers": "Speakers",
    "pedals": "Pedals", "weight": "Weight", "size": "Size", "type": "Type",
    "pieces": "Pieces", "material": "Material", "cymbals": "Cymbals", "hardware": "Hardware",
    "shells": "Shells", "pads": "Pads", "sounds": "Sounds", "connectivity": "Connectivity",
    "outputs": "Outputs", "inputs": "Inputs", "power": "Power", "no": "No", "yes": "Yes",
    "true": "Yes", "false": "No", "steel": "Steel", "passive": "Passive",
    "included": "Included", "synthesizer": "Synthesizer", "red": "Red", "black": "Black",
    "blue": "Blue", "wine red": "Wine red",
    "discontinued_with_stock": "Discontinued with stock", "active_without_stock": "Active without stock",
    "coming_soon_with_stock": "Coming soon with stock", "empty_category": "Empty category",
    "order_total_mismatch": "Order total mismatch", "non_active_product_in_order": "Inactive product in order",
    "shipped_overdue": "Delivery estimate passed", "duplicate_active_promotion": "Duplicate active promotions",
}


def ui_label(value) -> str:
    return UI_LABELS.get(str(value), str(value))


def spec_value(value) -> str:
    if isinstance(value, dict):
        return "; ".join(f"{ui_label(key)}: {spec_value(item)}" for key, item in value.items())
    if isinstance(value, list):
        return ", ".join(spec_value(item) for item in value)
    return ui_label(str(value).lower()) if str(value).lower() in UI_LABELS else str(value)


def format_datetime(value: str, timezone_name: str = "America/Campo_Grande") -> str:
    if not value:
        return "—"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(ZoneInfo(timezone_name))
    return parsed.strftime("%d/%m/%Y at %H:%M")


def issue_message(value: str) -> str:
    """Translate quality messages stored by earlier Portuguese-language ingestions."""
    replacements = [
        (r"(.+) foi descontinuado, mas possui (\d+) unidades em estoque\.", r"\1 is discontinued but has \2 units in stock."),
        (r"(.+) está ativo, mas não possui estoque\.", r"\1 is active but has no stock."),
        (r"(.+) está em pré-lançamento, mas possui (\d+) unidades em estoque\.", r"\1 is coming soon but has \2 units in stock."),
        (r"A categoria '(.+)' não possui produtos no CSV\.", r"Category '\1' has no products in the CSV."),
        (r"Pedido (\d+): o total de (.+) difere da soma dos itens em (.+)\.", r"Order \1: total \2 differs from the item sum by \3."),
        (r"O pedido (\d+) contém (.+) \((.+)\)\.", r"Order \1 contains \2 (\3)."),
        (r"O pedido (\d+) está marcado como enviado, mas a previsão de entrega já passou\.", r"Order \1 is marked as shipped, but its estimated delivery date has passed."),
        (r"O produto (\d+) possui (\d+) promoções ativas\.", r"Product \1 has \2 active promotions."),
    ]
    for pattern, replacement in replacements:
        if re.fullmatch(pattern, value):
            translated = re.sub(pattern, replacement, value)
            return translated.replace("(Em breve)", "(Coming soon)").replace("(Descontinuado)", "(Discontinued)")
    return value
