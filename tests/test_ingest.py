from __future__ import annotations


def test_row_counts(conn):
    expected = {
        "products": 65,
        "categories": 9,
        "customers": 50,
        "orders": 20,
        "order_items": 22,
        "promotions": 25,
        "policy_sections": 26,
    }
    for table, count in expected.items():
        actual = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
        assert actual == count


def test_foreign_keys_resolve(conn):
    assert conn.execute(
        """
        SELECT COUNT(*) AS n FROM order_items oi
        LEFT JOIN orders o ON o.order_id = oi.order_id
        WHERE o.order_id IS NULL
        """
    ).fetchone()["n"] == 0
    assert conn.execute(
        """
        SELECT COUNT(*) AS n FROM orders o
        LEFT JOIN customers c ON c.customer_id = o.customer_id
        WHERE c.customer_id IS NULL
        """
    ).fetchone()["n"] == 0
    assert conn.execute(
        """
        SELECT COUNT(*) AS n FROM products p
        LEFT JOIN categories c ON c.category_id = p.category_id
        WHERE c.category_id IS NULL
        """
    ).fetchone()["n"] == 0


def test_money_is_stored_as_cents(conn):
    row = conn.execute("SELECT price_cents FROM products WHERE product_id = 81").fetchone()
    assert row["price_cents"] == 59990
    order = conn.execute("SELECT total_cents FROM orders WHERE order_id = 3").fetchone()
    assert order["total_cents"] == 345000


def test_status_counts(conn):
    products = {
        row["status"]: row["n"]
        for row in conn.execute("SELECT status, COUNT(*) AS n FROM products GROUP BY status")
    }
    assert products == {"active": 62, "discontinued": 2, "coming_soon": 1}
    orders = {
        row["status"]: row["n"]
        for row in conn.execute("SELECT status, COUNT(*) AS n FROM orders GROUP BY status")
    }
    assert orders == {
        "delivered": 7,
        "confirmed": 4,
        "pending": 4,
        "cancelled": 4,
        "shipped": 1,
    }


def test_active_promotions_only(conn):
    assert conn.execute("SELECT COUNT(*) AS n FROM promotions WHERE is_active = 1").fetchone()["n"] == 4
    assert conn.execute(
        "SELECT COUNT(*) AS n FROM promotions WHERE product_id IN (93, 96, 99) AND is_active = 1"
    ).fetchone()["n"] == 0


def test_data_quality_flags_known_anomalies(conn):
    codes = {
        row["code"] + ":" + row["entity_id"]
        for row in conn.execute("SELECT code, entity_id FROM data_quality_issues")
    }
    assert "order_total_mismatch:3" in codes
    assert "order_total_mismatch:20" in codes
    assert "discontinued_with_stock:136" in codes
    assert "active_without_stock:96" in codes
    assert "coming_soon_with_stock:130" in codes
    assert "empty_category:6" in codes
    assert "empty_category:7" in codes
    assert "empty_category:8" in codes
    assert "shipped_overdue:8" in codes


def test_policy_embeddings_were_stored(conn):
    assert conn.execute(
        "SELECT COUNT(*) AS n FROM policy_sections WHERE embedding IS NOT NULL"
    ).fetchone()["n"] == 26
