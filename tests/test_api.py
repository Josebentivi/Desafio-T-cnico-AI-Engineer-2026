from __future__ import annotations

from fastapi.testclient import TestClient

from app.llm.fake import FakeLLM, FakeTurn
from app.main import create_app


def make_client(conn, settings, turns=None):
    app = create_app(settings, conn=conn, llm=FakeLLM(turns or [FakeTurn(text="Hello!")]))
    return TestClient(app)


def test_health(conn, settings):
    with make_client(conn, settings) as client:
        response = client.get("/health")
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ok"
        assert payload["products"] == 65
        assert payload["orders"] == 20
        assert payload["openai_configured"] is False


def test_chat_page_sets_session_cookie(conn, settings):
    with make_client(conn, settings) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert "Empório da Música Support" in response.text
        assert response.cookies.get("session_id")


def test_chat_stream(conn, settings):
    with make_client(conn, settings, [FakeTurn(text="Yes, we have acoustic guitars!")]) as client:
        page = client.get("/")
        session_id = page.cookies.get("session_id")
        response = client.post(
            "/chat/stream",
            data={"message": "Do you have acoustic guitars?", "session_id": session_id},
        )
        assert response.status_code == 200
        assert "event: token" in response.text
        assert "event: done" in response.text
        assert "Yes, we have acoustic guitars!" in response.text
        assert conn.execute("SELECT COUNT(*) AS n FROM messages").fetchone()["n"] == 2
        assert conn.execute("SELECT COUNT(*) AS n FROM agent_runs").fetchone()["n"] == 1


def test_chat_non_streaming(conn, settings):
    with make_client(conn, settings, [FakeTurn(text="This is a test response.")]) as client:
        page = client.get("/")
        session_id = page.cookies.get("session_id")
        response = client.post(
            "/chat",
            data={"message": "Hi", "session_id": session_id},
        )
        assert response.status_code == 200
        assert "This is a test response." in response.text


def test_new_session(conn, settings):
    with make_client(conn, settings) as client:
        response = client.post("/sessions/new", follow_redirects=False)
        assert response.status_code == 303
        assert response.cookies.get("session_id")


def test_ops_pages(conn, settings):
    with make_client(conn, settings) as client:
        for path in [
            "/ops",
            "/ops/catalog",
            "/ops/orders",
            "/ops/traces",
            "/ops/policy",
            "/ops/quality",
        ]:
            response = client.get(path)
            assert response.status_code == 200, path


def test_ops_ui_is_english(conn, settings):
    with make_client(conn, settings) as client:
        dashboard = client.get("/ops")
        assert "Operational dashboard" in dashboard.text
        assert "Recent runs" in dashboard.text

        catalog = client.get("/ops/catalog")
        assert "Availability" in catalog.text
        assert "Promotion" in catalog.text
        assert "Acoustic guitars" in catalog.text

        orders = client.get("/ops/orders")
        assert "Tracking" in orders.text
        assert "No orders found." not in orders.text

        policy = client.get("/ops/policy")
        assert "Manual sections" in policy.text


def test_ops_detail_pages(conn, settings):
    with make_client(conn, settings) as client:
        product = client.get("/ops/catalog/81")
        assert product.status_code == 200
        assert "Yamaha C40" in product.text
        assert "Payment methods" in product.text

        missing_product = client.get("/ops/catalog/9999")
        assert missing_product.status_code == 404
        assert "Product not found." in missing_product.text

        order = client.get("/ops/orders/3")
        assert order.status_code == 200
        assert "Isabela Moreira Cunha" in order.text
        assert "***@" in order.text

        missing_order = client.get("/ops/orders/9999")
        assert missing_order.status_code == 404
        assert "Order not found." in missing_order.text


def test_ops_policy_search(conn, settings):
    with make_client(conn, settings) as client:
        response = client.get("/ops/policy", params={"q": "return policy"})
        assert response.status_code == 200
        assert "Direito de Arrependimento" in response.text


def test_ops_catalog_filter(conn, settings):
    with make_client(conn, settings) as client:
        response = client.get(
            "/ops/catalog", params={"q": "acoustic guitar", "status": "active"}
        )
        assert response.status_code == 200
        assert "Yamaha C40" in response.text
