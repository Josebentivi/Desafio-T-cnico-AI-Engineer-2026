from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime

from app.domain.catalog import CATEGORY_LABELS_EN
from app.domain.money import format_brl


def _issue(
    conn: sqlite3.Connection,
    severity: str,
    code: str,
    entity_type: str,
    entity_id: str | int,
    message: str,
) -> None:
    conn.execute(
        """
        INSERT INTO data_quality_issues
            (severity, code, entity_type, entity_id, message, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (severity, code, entity_type, str(entity_id), message, datetime.now(UTC).isoformat()),
    )


def run_quality_checks(conn: sqlite3.Connection, today: date | None = None) -> list[dict]:
    conn.execute("DELETE FROM data_quality_issues")
    today = today or date.today()

    products = {row["product_id"]: row for row in conn.execute("SELECT * FROM products")}

    for product in products.values():
        stock = product["stock_quantity"]
        status = product["status"]
        if status == "discontinued" and stock > 0:
            _issue(
                conn,
                "warning",
                "discontinued_with_stock",
                "product",
                product["product_id"],
                f"{product['name']} is discontinued but has stock {stock}.",
            )
        if status == "active" and stock == 0:
            _issue(
                conn,
                "warning",
                "active_without_stock",
                "product",
                product["product_id"],
                f"{product['name']} is active but has no stock.",
            )
        if status == "coming_soon" and stock > 0:
            _issue(
                conn,
                "info",
                "coming_soon_with_stock",
                "product",
                product["product_id"],
                f"{product['name']} is coming_soon but has stock {stock}.",
            )

    for row in conn.execute(
        """
        SELECT c.category_id, c.name, COUNT(p.product_id) AS total
        FROM categories c
        LEFT JOIN products p ON p.category_id = c.category_id
        GROUP BY c.category_id
        HAVING total = 0
        """
    ):
        _issue(
            conn,
            "info",
            "empty_category",
            "category",
            row["category_id"],
            "Category '{}' has no products in the CSV.".format(
                CATEGORY_LABELS_EN.get(row["name"], row["name"])
            ),
        )

    for row in conn.execute(
        """
        SELECT o.order_id, o.total_cents,
               COALESCE(SUM(oi.quantity * p.price_cents), 0) AS calculated_cents
        FROM orders o
        LEFT JOIN order_items oi ON oi.order_id = o.order_id
        LEFT JOIN products p ON p.product_id = oi.product_id
        GROUP BY o.order_id
        """
    ):
        diff = row["total_cents"] - row["calculated_cents"]
        if diff != 0:
            _issue(
                conn,
                "warning",
                "order_total_mismatch",
                "order",
                row["order_id"],
                (
                    f"Order {row['order_id']}: total {format_brl(row['total_cents'])} "
                    f"differs from the line-item sum by {format_brl(abs(diff))}."
                ),
            )

    for row in conn.execute(
        """
        SELECT oi.order_id, p.product_id, p.name, p.status
        FROM order_items oi
        JOIN products p ON p.product_id = oi.product_id
        WHERE p.status != 'active'
        ORDER BY oi.order_id, p.product_id
        """
    ):
        _issue(
            conn,
            "warning",
            "non_active_product_in_order",
            "order",
            row["order_id"],
            f"Order {row['order_id']} contains {row['name']} ({row['status']}).",
        )

    for row in conn.execute(
        """
        SELECT order_id, estimated_delivery
        FROM orders
        WHERE status = 'shipped' AND estimated_delivery != ''
        """
    ):
        try:
            estimated = date.fromisoformat(row["estimated_delivery"])
        except ValueError:
            continue
        if estimated < today:
            _issue(
                conn,
                "warning",
                "shipped_overdue",
                "order",
                row["order_id"],
                f"Order {row['order_id']} is marked shipped but the estimated delivery date has passed.",
            )

    for row in conn.execute(
        """
        SELECT product_id, COUNT(*) AS total
        FROM promotions
        WHERE is_active = 1
        GROUP BY product_id
        HAVING total > 1
        """
    ):
        _issue(
            conn,
            "warning",
            "duplicate_active_promotion",
            "product",
            row["product_id"],
            f"Product {row['product_id']} has {row['total']} active promotions.",
        )

    conn.commit()
    return [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM data_quality_issues ORDER BY issue_id"
        )
    ]
