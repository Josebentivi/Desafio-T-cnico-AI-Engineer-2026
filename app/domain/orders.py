from __future__ import annotations

import re
import sqlite3
import unicodedata
from datetime import date

from app.domain.money import format_brl

STATUS_LABELS = {
    "delivered": "Delivered",
    "confirmed": "Confirmed",
    "pending": "Pending",
    "cancelled": "Cancelled",
    "shipped": "Shipped",
}

PAYMENT_LABELS = {
    "pix": "PIX",
    "debit": "Debit card",
    "boleto": "Boleto",
    "credit_3x": "Credit card (3x)",
    "credit_6x": "Credit card (6x)",
    "credit_12x": "Credit card (12x)",
}


def normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(char for char in decomposed if not unicodedata.combining(char)).casefold().strip()


def only_digits(text: str) -> str:
    return re.sub(r"\D", "", text or "")


def format_date_br(value: str) -> str:
    if not value:
        return ""
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return value
    return parsed.strftime("%d/%m/%Y")


def mask_email(value: str) -> str:
    if not value or "@" not in value:
        return value
    local, domain = value.split("@", 1)
    visible = local[:2] if len(local) > 2 else local[:1]
    return f"{visible}***@{domain}"


def mask_phone(value: str) -> str:
    digits = only_digits(value)
    if len(digits) < 4:
        return "***"
    return f"({digits[:2]}) *****-{digits[-4:]}"


def _matches_verifier(row: sqlite3.Row, verifier: str) -> bool:
    needle = normalize(verifier)
    if not needle:
        return False
    if needle in normalize(row["customer_name"]):
        return True
    if needle in normalize(row["email"]):
        return True
    verifier_digits = only_digits(verifier)
    if verifier_digits and verifier_digits in only_digits(row["phone"]):
        return True
    return False


def _order_payload(row: sqlite3.Row, items: list[dict]) -> dict:
    items_sum = sum(item["line_total_cents"] for item in items)
    payload = {
        "order_id": row["order_id"],
        "status": row["status"],
        "status_label": STATUS_LABELS.get(row["status"], row["status"]),
        "order_date": row["order_date"],
        "order_date_br": format_date_br(row["order_date"]),
        "total_cents": row["total_cents"],
        "total_brl": format_brl(row["total_cents"]),
        "items_sum_brl": format_brl(items_sum),
        "payment_method": row["payment_method"],
        "payment_method_label": PAYMENT_LABELS.get(row["payment_method"], row["payment_method"]),
        "customer": {
            "name": row["customer_name"],
            "city": row["city"],
        },
        "items": items,
    }
    if row["tracking_code"]:
        payload["tracking_code"] = row["tracking_code"]
    if row["estimated_delivery"]:
        payload["estimated_delivery"] = row["estimated_delivery"]
        payload["estimated_delivery_br"] = format_date_br(row["estimated_delivery"])
    if row["notes"]:
        payload["notes"] = row["notes"]
    return payload


class OrderService:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def get_order(self, order_id: int, verifier: str) -> dict:
        row = self.conn.execute(
            """
            SELECT o.*, c.name AS customer_name, c.phone, c.email, c.city
            FROM orders o
            JOIN customers c ON c.customer_id = o.customer_id
            WHERE o.order_id = ?
            """,
            (int(order_id),),
        ).fetchone()
        if row is None or not _matches_verifier(row, verifier):
            return {
                "found": False,
                "message": "Order not found or customer details do not match.",
            }
        items = []
        for item in self.conn.execute(
            """
            SELECT oi.quantity, p.product_id, p.name, p.price_cents
            FROM order_items oi
            JOIN products p ON p.product_id = oi.product_id
            WHERE oi.order_id = ?
            ORDER BY p.name
            """,
            (int(order_id),),
        ):
            line_total = item["price_cents"] * item["quantity"]
            items.append(
                {
                    "product_id": item["product_id"],
                    "name": item["name"],
                    "quantity": item["quantity"],
                    "unit_price_brl": format_brl(item["price_cents"]),
                    "line_total_brl": format_brl(line_total),
                    "line_total_cents": line_total,
                }
            )
        payload = _order_payload(row, items)
        payload["found"] = True
        return payload

    def list_orders(self, *, status: str | None = None, search: str | None = None) -> list[dict]:
        sql = """
            SELECT o.*, c.name AS customer_name, c.phone, c.email, c.city,
                   (SELECT COUNT(*) FROM order_items oi WHERE oi.order_id = o.order_id) AS item_count
            FROM orders o
            JOIN customers c ON c.customer_id = o.customer_id
        """
        where: list[str] = []
        params: list = []
        if status:
            where.append("o.status = ?")
            params.append(status)
        if search:
            where.append("(CAST(o.order_id AS TEXT) LIKE ? OR c.name LIKE ?)")
            params.extend([f"%{search}%", f"%{search}%"])
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY o.order_id"
        return [
            {
                "order_id": row["order_id"],
                "customer_name": row["customer_name"],
                "customer_phone_masked": mask_phone(row["phone"]),
                "customer_email_masked": mask_email(row["email"]),
                "city": row["city"],
                "order_date_br": format_date_br(row["order_date"]),
                "status": row["status"],
                "status_label": STATUS_LABELS.get(row["status"], row["status"]),
                "total_brl": format_brl(row["total_cents"]),
                "payment_method_label": PAYMENT_LABELS.get(
                    row["payment_method"], row["payment_method"]
                ),
                "item_count": row["item_count"],
                "tracking_code": row["tracking_code"],
            }
            for row in self.conn.execute(sql, params)
        ]

    def get_order_for_ops(self, order_id: int) -> dict | None:
        row = self.conn.execute(
            """
            SELECT o.*, c.name AS customer_name, c.phone, c.email, c.city
            FROM orders o
            JOIN customers c ON c.customer_id = o.customer_id
            WHERE o.order_id = ?
            """,
            (int(order_id),),
        ).fetchone()
        if row is None:
            return None
        items = []
        for item in self.conn.execute(
            """
            SELECT oi.quantity, p.product_id, p.name, p.price_cents, p.status
            FROM order_items oi
            JOIN products p ON p.product_id = oi.product_id
            WHERE oi.order_id = ?
            ORDER BY p.name
            """,
            (int(order_id),),
        ):
            line_total = item["price_cents"] * item["quantity"]
            items.append(
                {
                    "product_id": item["product_id"],
                    "name": item["name"],
                    "quantity": item["quantity"],
                    "unit_price_brl": format_brl(item["price_cents"]),
                    "line_total_brl": format_brl(line_total),
                    "line_total_cents": line_total,
                    "product_status": item["status"],
                }
            )
        payload = _order_payload(row, items)
        payload["customer"]["phone_masked"] = mask_phone(row["phone"])
        payload["customer"]["email_masked"] = mask_email(row["email"])
        return payload
