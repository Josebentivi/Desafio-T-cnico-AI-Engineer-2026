from __future__ import annotations

import re
import sqlite3

from app.domain.money import discount_cents, format_brl, pix_cents
from app.domain.payments import payment_options
from app.domain.search_aliases import (
    expand_catalog_query,
    resolve_category_id,
    resolve_query_category_ids,
)

STATUS_LABELS = {
    "active": "Ativo",
    "discontinued": "Descontinuado",
    "coming_soon": "Em breve",
}

CATEGORY_LABELS_EN = {
    "Guitarras": "Electric guitars",
    "Baixos": "Basses",
    "Baterias e Percussão": "Drums & percussion",
    "Teclados e Pianos": "Keyboards & pianos",
    "Violões": "Acoustic guitars",
    "Instrumentos de Sopro (Madeiras)": "Woodwinds",
    "Instrumentos de Sopro (Metais)": "Brass",
    "Cordas Orquestrais": "Orchestral strings",
    "Ukuleles": "Ukuleles",
}


def availability(status: str, stock: int) -> str:
    if status == "discontinued":
        return "discontinued"
    if status == "coming_soon":
        return "coming_soon"
    if stock <= 0:
        return "out_of_stock"
    return "available"


def fts_query(text: str) -> str:
    terms = [
        term
        for term in re.findall(r"[0-9A-Za-zÀ-ÿ]+", text, flags=re.UNICODE)
        if len(term) >= 2
    ]
    if not terms:
        return ""
    return " OR ".join(f'"{term}"*' for term in terms)


def _product_payload(row: sqlite3.Row, *, full: bool = False) -> dict:
    discount = row["discount_percent"]
    price_cents = row["price_cents"]
    promo = None
    if discount:
        promo_cents = discount_cents(price_cents, discount)
        promo = {
            "discount_percent": discount,
            "price_cents": promo_cents,
            "price_brl": format_brl(promo_cents),
        }
    pix_value = None if promo else pix_cents(price_cents)
    payload = {
        "product_id": row["product_id"],
        "name": row["name"],
        "category_id": row["category_id"],
        "category": row["category_name"],
        "category_en": CATEGORY_LABELS_EN.get(row["category_name"], row["category_name"]),
        "price_cents": price_cents,
        "price_brl": format_brl(price_cents),
        "stock_quantity": row["stock_quantity"],
        "status": row["status"],
        "status_label": STATUS_LABELS.get(row["status"], row["status"]),
        "availability": availability(row["status"], row["stock_quantity"]),
        "promotion": promo,
        "pix_price_brl": format_brl(pix_value) if pix_value is not None else None,
        "pix_discount_percent": 5 if pix_value is not None else 0,
    }
    if full:
        import json

        payload["description"] = row["description"]
        payload["specs"] = json.loads(row["specs_json"] or "{}")
        effective_price = promo["price_cents"] if promo else price_cents
        payload["payment_options"] = payment_options(
            effective_price, allow_pix=promo is None
        )
    return payload


class CatalogService:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def search(
        self,
        *,
        query: str | None = None,
        category: str | None = None,
        min_price_brl: float | None = None,
        max_price_brl: float | None = None,
        only_available: bool = False,
        limit: int = 10,
    ) -> list[dict]:
        sql = """
            SELECT p.*, c.name AS category_name,
                   (SELECT pr.discount_percent
                    FROM promotions pr
                    WHERE pr.product_id = p.product_id AND pr.is_active = 1
                    ORDER BY pr.discount_percent DESC
                    LIMIT 1) AS discount_percent
            FROM products p
            JOIN categories c ON c.category_id = p.category_id
        """
        params: list = []
        where: list[str] = []
        query_category_ids = resolve_query_category_ids(query or "") if query else None
        fts = fts_query(expand_catalog_query(query or ""))
        if fts:
            sql += " JOIN product_fts ON product_fts.product_id = p.product_id "
            where.append("product_fts MATCH ?")
            params.append(fts)
        if category:
            category_id = resolve_category_id(category)
            if category_id is not None:
                where.append("p.category_id = ?")
                params.append(category_id)
            elif category.strip().isdigit():
                where.append("p.category_id = ?")
                params.append(int(category))
            else:
                where.append("c.name LIKE ?")
                params.append(f"%{category.strip()}%")
        elif query_category_ids:
            placeholders = ", ".join("?" for _ in query_category_ids)
            where.append(f"p.category_id IN ({placeholders})")
            params.extend(sorted(query_category_ids))
        if min_price_brl is not None:
            where.append("p.price_cents >= ?")
            params.append(round(min_price_brl * 100))
        if max_price_brl is not None:
            where.append("p.price_cents <= ?")
            params.append(round(max_price_brl * 100))
        if only_available:
            where.append("p.status = 'active' AND p.stock_quantity > 0")
        if where:
            sql += " WHERE " + " AND ".join(where)
        if fts:
            sql += " ORDER BY bm25(product_fts), p.price_cents"
        else:
            sql += " ORDER BY p.price_cents, p.name"
        limit = max(1, min(int(limit), 200))
        diversify = bool(query_category_ids and not category and len(query_category_ids) > 1)
        sql_limit = max(limit, 50) if diversify else limit
        sql += " LIMIT ?"
        params.append(sql_limit)
        rows = list(self.conn.execute(sql, params))

        if diversify and rows:
            grouped: dict[int, list] = {}
            for row in rows:
                grouped.setdefault(row["category_id"], []).append(row)

            first = rows[0]
            ordered = [first]
            grouped[first["category_id"]].pop(0)

            if len(ordered) < limit:
                for category_id in sorted(grouped):
                    if category_id == first["category_id"] or not grouped[category_id]:
                        continue
                    ordered.append(grouped[category_id].pop(0))
                    if len(ordered) >= limit:
                        break

            while len(ordered) < limit:
                added = False
                for category_id in sorted(grouped):
                    if grouped[category_id]:
                        ordered.append(grouped[category_id].pop(0))
                        added = True
                        if len(ordered) >= limit:
                            break
                if not added:
                    break
            rows = ordered

        return [_product_payload(row) for row in rows]

    def get_product(self, product_id: int) -> dict | None:
        row = self.conn.execute(
            """
            SELECT p.*, c.name AS category_name,
                   (SELECT pr.discount_percent
                    FROM promotions pr
                    WHERE pr.product_id = p.product_id AND pr.is_active = 1
                    ORDER BY pr.discount_percent DESC
                    LIMIT 1) AS discount_percent
            FROM products p
            JOIN categories c ON c.category_id = p.category_id
            WHERE p.product_id = ?
            """,
            (int(product_id),),
        ).fetchone()
        if row is None:
            return None
        return _product_payload(row, full=True)

    def list_categories(self) -> list[dict]:
        categories = []
        for row in self.conn.execute(
            """
            SELECT c.category_id, c.name, COUNT(p.product_id) AS product_count
            FROM categories c
            LEFT JOIN products p ON p.category_id = c.category_id
            GROUP BY c.category_id
            ORDER BY c.category_id
            """
        ):
            category = dict(row)
            category["name_en"] = CATEGORY_LABELS_EN.get(
                category["name"], category["name"]
            )
            categories.append(category)
        return categories

    def active_promotions(self, product_id: int | None = None) -> list[dict]:
        sql = """
            SELECT pr.*, p.name, p.price_cents, p.status, p.stock_quantity
            FROM promotions pr
            JOIN products p ON p.product_id = pr.product_id
            WHERE pr.is_active = 1
        """
        params: list = []
        if product_id is not None:
            sql += " AND pr.product_id = ?"
            params.append(int(product_id))
        sql += " ORDER BY pr.discount_percent DESC, p.name"
        results = []
        for row in self.conn.execute(sql, params):
            promo_cents = discount_cents(row["price_cents"], row["discount_percent"])
            results.append(
                {
                    "product_id": row["product_id"],
                    "product_name": row["name"],
                    "discount_percent": row["discount_percent"],
                    "original_price_brl": format_brl(row["price_cents"]),
                    "promo_price_brl": format_brl(promo_cents),
                    "description": row["description"],
                    "availability": availability(row["status"], row["stock_quantity"]),
                }
            )
        return results
