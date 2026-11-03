from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

UI_LABELS = {
    "active": "Ativo",
    "discontinued": "Descontinuado",
    "coming_soon": "Em breve",
    "available": "Disponível",
    "out_of_stock": "Sem estoque",
    "delivered": "Entregue",
    "confirmed": "Confirmado",
    "pending": "Pendente",
    "cancelled": "Cancelado",
    "shipped": "Enviado",
    "user": "Cliente",
    "assistant": "Assistente",
    "warning": "Atenção",
    "info": "Informação",
    "error": "Erro",
    "product": "Produto",
    "order": "Pedido",
    "category": "Categoria",
    "low": "Baixo",
    "medium": "Médio",
    "high": "Alto",
    "minimal": "Mínimo",
    "none": "Nenhum",
    "search_products": "Busca no catálogo",
    "get_product": "Detalhes do instrumento",
    "get_active_promotions": "Promoções ativas",
    "get_order": "Consulta de pedido",
    "search_policy": "Consulta às políticas",
    "get_store_status": "Horário da loja",
    "get_shipping_estimate": "Estimativa de frete",
    "top": "Tampo",
    "back_sides": "Fundo e laterais",
    "neck": "Braço",
    "strings": "Cordas",
    "scale": "Escala",
    "electronics": "Eletrônica",
    "color": "Cor",
    "body": "Corpo",
    "fretboard": "Escala",
    "frets": "Trastes",
    "pickups": "Captadores",
    "bridge": "Ponte",
    "finish": "Acabamento",
    "keys": "Teclas",
    "voices": "Timbres",
    "polyphony": "Polifonia",
    "rhythms": "Ritmos",
    "speakers": "Alto-falantes",
    "pedals": "Pedais",
    "weight": "Peso",
    "size": "Tamanho",
    "type": "Tipo",
    "pieces": "Peças",
    "material": "Material",
    "cymbals": "Pratos",
    "hardware": "Ferragens",
    "shells": "Cascos",
    "pads": "Pads",
    "sounds": "Sons",
    "connectivity": "Conectividade",
    "outputs": "Saídas",
    "inputs": "Entradas",
    "power": "Alimentação",
    "no": "Não",
    "yes": "Sim",
    "true": "Sim",
    "false": "Não",
    "steel": "Aço",
    "passive": "Passiva",
    "included": "Incluído",
    "synthesizer": "Sintetizador",
    "red": "Vermelho",
    "black": "Preto",
    "blue": "Azul",
    "wine red": "Vermelho vinho",
    "discontinued_with_stock": "Descontinuado com estoque",
    "active_without_stock": "Ativo sem estoque",
    "coming_soon_with_stock": "Lançamento com estoque",
    "empty_category": "Categoria sem produtos",
    "order_total_mismatch": "Divergência no total",
    "non_active_product_in_order": "Produto não ativo no pedido",
    "shipped_overdue": "Previsão de entrega vencida",
    "duplicate_active_promotion": "Promoções ativas duplicadas",
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
    return parsed.strftime("%d/%m/%Y às %H:%M")


def issue_message(value: str) -> str:
    """Localize quality messages from databases ingested before the PT-BR UI."""
    replacements = [
        (r"(.+) is discontinued but has stock (\d+)\.", r"\1 foi descontinuado, mas possui \2 unidades em estoque."),
        (r"(.+) is active but has no stock\.", r"\1 está ativo, mas não possui estoque."),
        (r"(.+) is coming_soon but has stock (\d+)\.", r"\1 está em pré-lançamento, mas possui \2 unidades em estoque."),
        (r"Category '(.+)' has no products in the CSV\.", r"A categoria '\1' não possui produtos no CSV."),
        (r"Order (\d+): total (.+) differs from the line-item sum by (.+)\.", r"Pedido \1: o total de \2 difere da soma dos itens em \3."),
        (r"Order (\d+) contains (.+) \((.+)\)\.", r"O pedido \1 contém \2 (\3)."),
        (r"Order (\d+) is marked shipped but the estimated delivery date has passed\.", r"O pedido \1 está marcado como enviado, mas a previsão de entrega já passou."),
        (r"Product (\d+) has (\d+) active promotions\.", r"O produto \1 possui \2 promoções ativas."),
    ]
    for pattern, replacement in replacements:
        if re.fullmatch(pattern, value):
            translated = re.sub(pattern, replacement, value)
            for source, target in {"Woodwinds": "Instrumentos de Sopro (Madeiras)", "Brass": "Instrumentos de Sopro (Metais)", "Orchestral strings": "Cordas Orquestrais", "coming_soon": "em breve", "discontinued": "descontinuado"}.items():
                translated = translated.replace(source, target)
            return translated
    return value
