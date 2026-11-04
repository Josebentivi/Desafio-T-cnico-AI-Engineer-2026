from __future__ import annotations

import asyncio
import csv
import hashlib
import json
import sqlite3
import sys
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

from app.cli_parser import EnglishArgumentParser
from app.config import Settings, get_settings
from app.data.quality import run_quality_checks
from app.db import connect, init_db, reset_db
from app.domain.money import parse_brl_to_cents
from app.llm.embeddings import OpenAIEmbeddingClient, vector_to_blob

CSV_FILES = {
    "categories": "desafio_tecnico_ai_eng - categories.csv",
    "products": "desafio_tecnico_ai_eng - products.csv",
    "customers": "desafio_tecnico_ai_eng - customers.csv",
    "orders": "desafio_tecnico_ai_eng - orders.csv",
    "order_items": "desafio_tecnico_ai_eng - order_items.csv",
    "promotions": "desafio_tecnico_ai_eng - promotions.csv",
}

POLICY_PATH = "policy_sections.json"


def load_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def flatten_specs(value) -> str:
    parts: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            parts.append(str(key))
            parts.append(flatten_specs(item))
    elif isinstance(value, list):
        for item in value:
            parts.append(flatten_specs(item))
    elif value is not None:
        parts.append(str(value))
    return " ".join(part for part in parts if part)


def parse_date(value: str) -> str:
    if not value:
        return ""
    return date.fromisoformat(value).isoformat()


def clear_data(conn: sqlite3.Connection) -> None:
    for table in [
        "order_items",
        "orders",
        "promotions",
        "products",
        "customers",
        "categories",
        "policy_fts",
        "product_fts",
        "policy_sections",
        "data_quality_issues",
        "meta",
    ]:
        conn.execute(f"DELETE FROM {table}")


def insert_categories(conn: sqlite3.Connection, rows: list[dict]) -> None:
    conn.executemany(
        "INSERT INTO categories (category_id, name, description) VALUES (?, ?, ?)",
        [
            (int(row["category_id"]), row["name"], row.get("description", ""))
            for row in rows
        ],
    )


def insert_products(conn: sqlite3.Connection, rows: list[dict]) -> None:
    values = []
    fts_values = []
    for row in rows:
        specs = json.loads(row["specs"])
        specs_text = flatten_specs(specs)
        values.append(
            (
                int(row["product_id"]),
                row["name"],
                int(row["category_id"]),
                parse_brl_to_cents(row["price_brl"]),
                row.get("description", ""),
                int(row["stock_quantity"]),
                row["status"],
                json.dumps(specs, ensure_ascii=False),
                specs_text,
                row.get("created_at", ""),
            )
        )
        fts_values.append(
            (int(row["product_id"]), row["name"], row.get("description", ""), specs_text)
        )
    conn.executemany(
        """
        INSERT INTO products
            (product_id, name, category_id, price_cents, description, stock_quantity,
             status, specs_json, specs_text, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        values,
    )
    conn.executemany(
        "INSERT INTO product_fts (product_id, name, description, specs_text) VALUES (?, ?, ?, ?)",
        fts_values,
    )


def insert_customers(conn: sqlite3.Connection, rows: list[dict]) -> None:
    conn.executemany(
        "INSERT INTO customers (customer_id, name, phone, email, city) VALUES (?, ?, ?, ?, ?)",
        [
            (
                int(row["customer_id"]),
                row["name"],
                row["phone"],
                row["email"],
                row["city"],
            )
            for row in rows
        ],
    )


def insert_orders(conn: sqlite3.Connection, rows: list[dict]) -> None:
    conn.executemany(
        """
        INSERT INTO orders
            (order_id, customer_id, order_date, status, total_cents, payment_method,
             tracking_code, estimated_delivery, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                int(row["order_id"]),
                int(row["customer_id"]),
                parse_date(row["order_date"]),
                row["status"],
                parse_brl_to_cents(row["total_brl"]),
                row["payment_method"],
                row.get("tracking_code", ""),
                parse_date(row.get("estimated_delivery", "")),
                row.get("notes", ""),
            )
            for row in rows
        ],
    )


def insert_order_items(conn: sqlite3.Connection, rows: list[dict]) -> None:
    conn.executemany(
        "INSERT INTO order_items (order_id, product_id, quantity) VALUES (?, ?, ?)",
        [
            (int(row["order_id"]), int(row["product_id"]), int(row["quantity"]))
            for row in rows
        ],
    )


def insert_promotions(conn: sqlite3.Connection, rows: list[dict]) -> None:
    conn.executemany(
        """
        INSERT INTO promotions
            (promotion_id, product_id, discount_percent, description, is_active)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            (
                int(row["promotion_id"]),
                int(row["product_id"]),
                int(row["discount_percent"]),
                row["description"],
                int(row["is_active"]),
            )
            for row in rows
        ],
    )


def load_policy_sections(conn: sqlite3.Connection, path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    sections = payload["sections"] if isinstance(payload, dict) else payload
    conn.executemany(
        """
        INSERT INTO policy_sections
            (section_id, title, text, page, content_hash)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            (
                str(section["section_id"]),
                section["title"],
                section["text"],
                int(section.get("page", 0)),
                hashlib.sha256(
                    f"{section['title']}\n{section['text']}".encode()
                ).hexdigest(),
            )
            for section in sections
        ],
    )
    conn.executemany(
        "INSERT INTO policy_fts (section_id, title, text) VALUES (?, ?, ?)",
        [
            (str(section["section_id"]), section["title"], section["text"])
            for section in sections
        ],
    )
    return sections


async def embed_policy_sections(
    conn: sqlite3.Connection,
    sections: list[dict],
    embedding_client,
    embedding_model: str,
) -> int:
    existing = {
        row["section_id"]: row
        for row in conn.execute(
            "SELECT section_id, content_hash, embedding, embedding_model FROM policy_sections"
        )
    }
    pending: list[dict] = []
    for section in sections:
        section_id = str(section["section_id"])
        current = existing.get(section_id)
        if (
            current
            and current["content_hash"]
            == hashlib.sha256(
                f"{section['title']}\n{section['text']}".encode()
            ).hexdigest()
            and current["embedding"]
            and current["embedding_model"] == embedding_model
        ):
            continue
        pending.append(section)

    if not pending:
        return 0

    texts = [f"{section['title']}\n{section['text']}" for section in pending]
    vectors = await embedding_client.embed_texts(texts)
    embedded_at = datetime.now(UTC).isoformat()
    for section, vector in zip(pending, vectors, strict=True):
        conn.execute(
            """
            UPDATE policy_sections
            SET embedding = ?, embedding_model = ?, embedded_at = ?
            WHERE section_id = ?
            """,
            (
                vector_to_blob(vector),
                embedding_model,
                embedded_at,
                str(section["section_id"]),
            ),
        )
    conn.commit()
    return len(pending)


async def ingest_all(
    conn: sqlite3.Connection,
    settings: Settings,
    *,
    reset: bool = False,
    embedding_client=None,
    skip_embeddings: bool = False,
) -> dict:
    if reset:
        reset_db(conn)
    else:
        init_db(conn)
        clear_data(conn)
        conn.commit()

    data = {
        name: load_csv(settings.data_dir / filename)
        for name, filename in CSV_FILES.items()
    }
    insert_categories(conn, data["categories"])
    insert_products(conn, data["products"])
    insert_customers(conn, data["customers"])
    insert_orders(conn, data["orders"])
    insert_order_items(conn, data["order_items"])
    insert_promotions(conn, data["promotions"])
    conn.commit()

    sections = load_policy_sections(conn, settings.data_dir / POLICY_PATH)
    conn.commit()

    embedded = 0
    if not skip_embeddings and embedding_client is not None:
        try:
            embedded = await embed_policy_sections(
                conn,
                sections,
                embedding_client,
                f"{settings.embedding_model}:{settings.embedding_dimensions}",
            )
        except Exception as exc:
            print(f"Warning: embeddings could not be generated ({exc}). Using FTS5 text search.", file=sys.stderr)
            conn.rollback()

    issues = run_quality_checks(conn)
    counts = {
        name: len(rows)
        for name, rows in data.items()
    }
    counts["policy_sections"] = len(sections)
    conn.execute(
        "INSERT INTO meta (key, value) VALUES (?, ?)",
        ("ingested_at", datetime.now(UTC).isoformat()),
    )
    conn.execute(
        "INSERT INTO meta (key, value) VALUES (?, ?)",
        ("counts", json.dumps(counts, ensure_ascii=False)),
    )
    conn.commit()
    return {"counts": counts, "issues": issues, "embedded": embedded}


def main() -> int:
    parser = EnglishArgumentParser(
        description="Import CSV files and policy sections into SQLite."
    )
    parser.add_argument("--db", default=None, help="SQLite database path.")
    parser.add_argument("--reset", action="store_true", help="Recreate the database from scratch.")
    parser.add_argument(
        "--skip-embeddings",
        action="store_true",
        help="Use FTS5 text search without calling the embeddings API.",
    )
    args = parser.parse_args()

    settings = get_settings()
    if args.db:
        settings = replace(settings, database_path=args.db)

    embedding_client = None
    if not args.skip_embeddings and settings.has_openai_key and not settings.skip_embeddings:
        embedding_client = OpenAIEmbeddingClient(settings)

    conn = connect(settings.database_file)
    try:
        summary = asyncio.run(
            ingest_all(
                conn,
                settings,
                reset=args.reset,
                embedding_client=embedding_client,
                skip_embeddings=args.skip_embeddings or settings.skip_embeddings,
            )
        )
    finally:
        conn.close()

    print("Import complete.")
    labels = {
        "categories": "Categories", "products": "Instruments", "customers": "Customers",
        "orders": "Orders", "order_items": "Order items", "promotions": "Promotions",
        "policy_sections": "Manual sections",
    }
    for name, count in summary["counts"].items():
        print(f"{labels.get(name, name)}: {count}")
    print(f"Embeddings generated: {summary['embedded']}")
    print(f"Data issues recorded: {len(summary['issues'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
