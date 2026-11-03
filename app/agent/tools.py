from __future__ import annotations

import json
import sqlite3
from typing import Any

from app.domain.catalog import CatalogService
from app.domain.money import parse_brl_to_cents
from app.domain.orders import OrderService
from app.domain.policy import PolicyService
from app.domain.shipping import shipping_estimate
from app.domain.store import store_status


def _nullable(kind: str) -> dict:
    return {"type": [kind, "null"]}


TOOL_SPECS: list[dict] = [
    {
        "type": "function",
        "name": "search_products",
        "description": (
            "Search the catalog by text, category, price range, and availability. "
            "Returns a short list with id, name, category, price, status, and active promotion."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    **_nullable("string"),
                    "description": "Free-text search over product name, description, and specifications.",
                },
                "category": {
                    **_nullable("string"),
                    "description": "Category name or id, for example 'Acoustic guitars' or '5'.",
                },
                "min_price_brl": {
                    **_nullable("number"),
                    "description": "Minimum price in Brazilian reais.",
                },
                "max_price_brl": {
                    **_nullable("number"),
                    "description": "Maximum price in Brazilian reais.",
                },
                "only_available": {
                    "type": "boolean",
                    "description": "If true, return only active products with stock.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results, between 1 and 20.",
                },
            },
            "required": [
                "query",
                "category",
                "min_price_brl",
                "max_price_brl",
                "only_available",
                "limit",
            ],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_product",
        "description": (
            "Return details for a specific product: price, stock, status, specs, active promotion, "
            "and payment options."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "product_id": {"type": "integer", "description": "Product ID."},
            },
            "required": ["product_id"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_active_promotions",
        "description": (
            "List active promotions. If product_id is provided, filter by product. "
            "Returns original price, discount percentage, and promotional price."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "product_id": {
                    **_nullable("integer"),
                    "description": "Product ID, or null to list all active promotions.",
                },
            },
            "required": ["product_id"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_order",
        "description": (
            "Look up an order by ID. Also requires a customer identifier (name, phone, or email) "
            "to verify identity. Returns status, items, total, payment, and tracking."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {"type": "integer", "description": "Order number."},
                "customer_verifier": {
                    "type": "string",
                    "description": "Customer name, phone, or email used on the order.",
                },
            },
            "required": ["order_id", "customer_verifier"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "search_policy",
        "description": (
            "Search the store policy manual. Use it for returns, exchanges, warranty, payment, "
            "shipping, promotions, hours, privacy, and tone of voice."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Question or search terms, in English or Portuguese.",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of sections to return, between 1 and 5.",
                },
            },
            "required": ["query", "top_k"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_store_status",
        "description": (
            "Return the store's local time, whether it is open now, and when the next opening is."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_shipping_estimate",
        "description": (
            "Apply the shipping rule for a city and order total. Outside Campo Grande, explain that "
            "the postal code (CEP) is required to quote PAC, SEDEX, or Jadlog."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "Delivery city."},
                "total_brl": {"type": "number", "description": "Order total in Brazilian reais."},
            },
            "required": ["city", "total_brl"],
            "additionalProperties": False,
        },
    },
]


class Toolbox:
    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        timezone_name: str = "America/Campo_Grande",
        embedding_client=None,
    ):
        self.conn = conn
        self.catalog = CatalogService(conn)
        self.orders = OrderService(conn)
        self.policy = PolicyService(conn, embedding_client)
        self.timezone_name = timezone_name

    async def execute(self, name: str, arguments: dict[str, Any]) -> dict:
        if name == "search_products":
            results = self.catalog.search(
                query=arguments.get("query"),
                category=arguments.get("category"),
                min_price_brl=arguments.get("min_price_brl"),
                max_price_brl=arguments.get("max_price_brl"),
                only_available=bool(arguments.get("only_available", False)),
                limit=int(arguments.get("limit", 10)),
            )
            return {"count": len(results), "results": results}
        if name == "get_product":
            product = self.catalog.get_product(int(arguments["product_id"]))
            if product is None:
                return {"found": False, "message": "Instrumento não encontrado no catálogo."}
            return {"found": True, "product": product}
        if name == "get_active_promotions":
            product_id = arguments.get("product_id")
            return {
                "promotions": self.catalog.active_promotions(
                    int(product_id) if product_id is not None else None
                )
            }
        if name == "get_order":
            return self.orders.get_order(
                int(arguments["order_id"]), str(arguments["customer_verifier"])
            )
        if name == "search_policy":
            sections = await self.policy.search(
                str(arguments["query"]), int(arguments.get("top_k", 4))
            )
            return {"sections": sections}
        if name == "get_store_status":
            return store_status(self.timezone_name)
        if name == "get_shipping_estimate":
            return shipping_estimate(
                str(arguments["city"]), parse_brl_to_cents(arguments["total_brl"])
            )
        return {"error": f"Ferramenta desconhecida: {name}"}


def parse_arguments(raw: str) -> dict:
    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}
