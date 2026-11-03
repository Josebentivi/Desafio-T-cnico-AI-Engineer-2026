from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.domain.catalog import CatalogService, availability
from app.domain.money import format_brl, parse_brl_to_cents
from app.domain.orders import OrderService
from app.domain.shipping import shipping_estimate
from app.domain.store import store_status


def test_money_helpers():
    assert parse_brl_to_cents("R$ 1.299,90") == 129990
    assert parse_brl_to_cents("R$ 1.000") == 100000
    assert parse_brl_to_cents("599.9") == 59990
    assert format_brl(129990) == "R$ 1.299,90"


def test_availability_prefers_status():
    assert availability("discontinued", 13) == "discontinued"
    assert availability("coming_soon", 2) == "coming_soon"
    assert availability("active", 0) == "out_of_stock"
    assert availability("active", 1) == "available"


def test_catalog_search_filters_and_availability(conn):
    catalog = CatalogService(conn)
    results = catalog.search(query="violão", max_price_brl=1000, only_available=True, limit=20)
    assert results
    for product in results:
        assert product["price_cents"] <= 100000
        assert product["status"] == "active"
        assert product["stock_quantity"] > 0
        assert product["availability"] == "available"


def test_catalog_english_query_and_category_aliases(conn):
    catalog = CatalogService(conn)

    acoustic = catalog.search(query="acoustic guitar", only_available=True, limit=20)
    assert any(product["category"] == "Violões" for product in acoustic)

    ukuleles = catalog.search(query="ukulele", only_available=True, limit=20)
    assert any(product["category"] == "Ukuleles" for product in ukuleles)

    category = catalog.search(category="Acoustic guitars", only_available=True, limit=20)
    assert category
    assert all(product["category"] == "Violões" for product in category)
    assert all(product["category_en"] == "Acoustic guitars" for product in category)

    categories = catalog.list_categories()
    assert any(category["name_en"] == "Acoustic guitars" for category in categories)

    basses = catalog.search(category="basses", only_available=True, limit=20)
    assert basses
    assert all(product["category"] == "Baixos" for product in basses)


def test_catalog_status_traps(conn):
    catalog = CatalogService(conn)
    discontinued = catalog.get_product(136)
    assert discontinued["status"] == "discontinued"
    assert discontinued["availability"] == "discontinued"
    assert discontinued["stock_quantity"] == 13

    no_stock = catalog.get_product(96)
    assert no_stock["availability"] == "out_of_stock"

    coming_soon = catalog.get_product(130)
    assert coming_soon["availability"] == "coming_soon"


def test_active_promotion_price_and_pix_rules(conn):
    catalog = CatalogService(conn)
    product = catalog.get_product(94)
    assert product["promotion"]["discount_percent"] == 8
    assert product["promotion"]["price_brl"] == "R$ 5.519,08"
    assert product["pix_price_brl"] is None
    assert product["payment_options"]["pix"] is None
    assert product["payment_options"]["price_brl"] == "R$ 5.519,08"

    regular = catalog.get_product(81)
    assert regular["promotion"] is None
    assert regular["pix_price_brl"] == "R$ 569,91"
    assert regular["status_label"] == "active"


def test_order_verification(conn):
    orders = OrderService(conn)
    found = orders.get_order(3, "Isabela Moreira Cunha")
    assert found["found"] is True
    assert found["total_brl"] == "R$ 3.450,00"
    assert found["items_sum_brl"] == "R$ 3.498,00"
    assert found["status"] == "delivered"
    assert found["items"][0]["product_id"] == 130

    missing = orders.get_order(3, "Another Person")
    assert missing["found"] is False
    assert "not found" in missing["message"]


def test_order_masks_pii_in_list(conn):
    orders = OrderService(conn).list_orders()
    assert len(orders) == 20
    assert all("*" in order["customer_email_masked"] for order in orders)
    assert all("*" in order["customer_phone_masked"] for order in orders)


def test_shipping_rules():
    free = shipping_estimate("Campo Grande", 50000)
    assert free["free_shipping"] is True
    assert free["fee_cents"] == 0

    paid = shipping_estimate("Campo Grande", 49999)
    assert paid["free_shipping"] is False
    assert paid["fee_cents"] == 3500

    outside = shipping_estimate("Dourados", 80000)
    assert outside["region"] == "outside_campo_grande"
    assert outside["requires_cep"] is True
    assert len(outside["modalities"]) == 3


def test_store_status_weekday_and_sunday():
    tz = ZoneInfo("America/Campo_Grande")
    monday_open = store_status(now=datetime(2026, 11, 2, 10, 0, tzinfo=tz))
    assert monday_open["is_open"] is True

    monday_early = store_status(now=datetime(2026, 11, 2, 8, 0, tzinfo=tz))
    assert monday_early["is_open"] is False
    assert monday_early["next_opening"].startswith("2026-11-02T09:00")

    sunday = store_status(now=datetime(2026, 11, 8, 10, 0, tzinfo=tz))
    assert sunday["is_open"] is False
    assert sunday["next_opening"].startswith("2026-11-09T09:00")

    saturday_after = store_status(now=datetime(2026, 11, 7, 14, 0, tzinfo=tz))
    assert saturday_after["is_open"] is False
    assert saturday_after["next_opening"].startswith("2026-11-09T09:00")
