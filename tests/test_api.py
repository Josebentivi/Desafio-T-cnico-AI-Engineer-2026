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
        assert "Let's talk music" in response.text
        assert '<html lang="en">' in response.text
        assert 'for="chat-input">Your message</label>' in response.text
        assert response.cookies.get("session_id")


def test_chat_stream(conn, settings):
    with make_client(conn, settings, [FakeTurn(text="Sim, temos violões!")]) as client:
        page = client.get("/")
        session_id = page.cookies.get("session_id")
        response = client.post(
            "/chat/stream",
            data={"message": "Vocês têm violões?", "session_id": session_id},
        )
        assert response.status_code == 200
        assert "event: token" in response.text
        assert response.headers["cache-control"] == "no-cache"
        assert response.headers["content-type"].startswith("text/event-stream")
        assert "event: done" in response.text
        assert "Sim, temos violões!" in response.text
        assert conn.execute("SELECT COUNT(*) AS n FROM messages").fetchone()["n"] == 2
        assert conn.execute("SELECT COUNT(*) AS n FROM agent_runs").fetchone()["n"] == 1


def test_chat_non_streaming(conn, settings):
    with make_client(conn, settings, [FakeTurn(text="Esta é uma resposta de teste.")]) as client:
        page = client.get("/")
        session_id = page.cookies.get("session_id")
        response = client.post(
            "/chat",
            data={"message": "Oi", "session_id": session_id},
        )
        assert response.status_code == 200
        assert "Esta é uma resposta de teste." in response.text


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
        assert "Overview" in dashboard.text
        assert "Recent interactions" in dashboard.text

        catalog = client.get("/ops/catalog")
        assert "Availability" in catalog.text
        assert "Promotion" in catalog.text
        assert "Acoustic guitars" in catalog.text

        orders = client.get("/ops/orders")
        assert "Tracking" in orders.text
        assert "No orders found." not in orders.text
        assert "Delivered" in orders.text

        policy = client.get("/ops/policy")
        assert "Manual sections" in policy.text


def test_ops_detail_pages(conn, settings):
    with make_client(conn, settings) as client:
        product = client.get("/ops/catalog/81")
        assert product.status_code == 200
        assert "Yamaha C40" in product.text
        assert "Payment methods" in product.text
        assert "Top" in product.text
        assert "No" in product.text

        missing_product = client.get("/ops/catalog/9999")
        assert missing_product.status_code == 404
        assert "Instrument not found." in missing_product.text

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


def test_catalog_htmx_response_contains_updated_count_and_filters(conn, settings):
    with make_client(conn, settings) as client:
        response = client.get(
            "/ops/catalog", params={"q": "violão", "status": "discontinued"},
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        partial = response.text.split('<div id="ops-content">', 1)[1]
        assert "1 instrument found" in partial
        assert 'value="discontinued" selected' in partial
        assert "Shelby SN-7C" in partial
        assert "Yamaha C40" not in partial


def test_chat_history_renders_after_stream_and_switches_sessions(conn, settings):
    with make_client(conn, settings, [FakeTurn(text="Olá! Como posso ajudar?")]) as client:
        first = client.get("/").cookies["session_id"]
        client.post("/chat", data={"message": "Preciso de um violão", "session_id": first})
        page = client.get("/")
        assert "Preciso de um violão" in page.text
        assert "Olá! Como posso ajudar?" in page.text
        assert "You" in page.text
        assert " at " in page.text
        second = client.post("/sessions/new", follow_redirects=False).cookies["session_id"]
        assert first != second
        assert "New conversation" in client.get("/").text
        client.get(f"/sessions/{first}")
        assert "Olá! Como posso ajudar?" in client.get("/").text


def test_legacy_quality_messages_display_in_english(conn, settings):
    conn.execute(
        "UPDATE data_quality_issues SET message = ? WHERE code = 'empty_category'",
        ("A categoria 'Instrumentos de Sopro (Metais)' não possui produtos no CSV.",),
    )
    conn.commit()
    with make_client(conn, settings) as client:
        page = client.get("/ops/quality")
        assert "Instrumentos de Sopro (Metais)" in page.text
        assert "has no products in the CSV" in page.text
        assert "não possui produtos" not in page.text


def test_message_rendering_escapes_html_and_keeps_supported_emphasis(conn, settings):
    with make_client(conn, settings, [FakeTurn(text='**Olá** <script>alert("teste")</script>')]) as client:
        sid = client.get("/").cookies["session_id"]
        response = client.post("/chat", data={"message": "<img src=x>", "session_id": sid})
        assert "<strong>Olá</strong>" in response.text
        assert "&lt;script&gt;" in response.text
        assert "<script>" not in response.text
        assert "&lt;img src=x&gt;" in response.text
