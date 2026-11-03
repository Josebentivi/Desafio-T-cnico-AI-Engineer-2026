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
            "Busca produtos do catálogo por texto, categoria, faixa de preço e disponibilidade. "
            "Retorna uma lista curta com id, nome, categoria, preço, status e promoção ativa."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    **_nullable("string"),
                    "description": "Texto livre para buscar no nome, descrição e especificações.",
                },
                "category": {
                    **_nullable("string"),
                    "description": "Nome ou id da categoria, por exemplo 'Violões' ou '5'.",
                },
                "min_price_brl": {
                    **_nullable("number"),
                    "description": "Preço mínimo em reais.",
                },
                "max_price_brl": {
                    **_nullable("number"),
                    "description": "Preço máximo em reais.",
                },
                "only_available": {
                    "type": "boolean",
                    "description": "Se verdadeiro, retorna apenas produtos ativos com estoque.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Quantidade máxima de resultados, entre 1 e 20.",
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
            "Retorna detalhes de um produto específico: preço, estoque, status, specs, "
            "promoção ativa e opções de pagamento."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "product_id": {"type": "integer", "description": "ID do produto."},
            },
            "required": ["product_id"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_active_promotions",
        "description": (
            "Lista promoções ativas. Se product_id for informado, filtra por produto. "
            "Retorna preço original, percentual e preço promocional."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "product_id": {
                    **_nullable("integer"),
                    "description": "ID do produto ou null para listar todas as promoções ativas.",
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
            "Consulta um pedido pelo ID. Exige também um dado do cliente (nome, telefone ou e-mail) "
            "para confirmar a identidade. Retorna status, itens, total, pagamento e rastreio."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {"type": "integer", "description": "Número do pedido."},
                "customer_verifier": {
                    "type": "string",
                    "description": "Nome, telefone ou e-mail do cliente usado no pedido.",
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
            "Busca seções do manual de políticas da loja. Use para trocas, devoluções, garantia, "
            "pagamento, frete, promoções, horários, privacidade e tom de voz."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Dúvida ou termos de busca, em português.",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Quantidade de seções a retornar, entre 1 e 5.",
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
            "Retorna o horário local da loja, se está aberta agora e quando ocorre o próximo atendimento."
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
            "Aplica a regra de frete para a cidade e o total do pedido. Para fora de Campo Grande, "
            "informa que é necessário o CEP para cotar PAC, SEDEX ou Jadlog."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "Cidade de entrega."},
                "total_brl": {"type": "number", "description": "Total do pedido em reais."},
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
                return {"found": False, "message": "Produto não encontrado no catálogo."}
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
