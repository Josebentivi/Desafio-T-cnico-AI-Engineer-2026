from __future__ import annotations

from fastapi.testclient import TestClient

from app.llm.fake import FakeLLM, FakeTurn
from app.main import create_app


def make_client(conn, settings, turns=None):
    app = create_app(settings, conn=conn, llm=FakeLLM(turns or [FakeTurn(text="Olá!")]))
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
        assert "Atendimento Empório da Música" in response.text
        assert response.cookies.get("session_id")


def test_chat_stream(conn, settings):
    with make_client(conn, settings, [FakeTurn(text="Temos violões sim!")]) as client:
        page = client.get("/")
        session_id = page.cookies.get("session_id")
        response = client.post(
            "/chat/stream",
            data={"message": "Vocês têm violão?", "session_id": session_id},
        )
        assert response.status_code == 200
        assert "event: token" in response.text
        assert "event: done" in response.text
        assert "Temos violões sim!" in response.text
        assert conn.execute("SELECT COUNT(*) AS n FROM messages").fetchone()["n"] == 2
        assert conn.execute("SELECT COUNT(*) AS n FROM agent_runs").fetchone()["n"] == 1


def test_chat_non_streaming(conn, settings):
    with make_client(conn, settings, [FakeTurn(text="Resposta de teste.")]) as client:
        page = client.get("/")
        session_id = page.cookies.get("session_id")
        response = client.post(
            "/chat",
            data={"message": "Oi", "session_id": session_id},
        )
        assert response.status_code == 200
        assert "Resposta de teste." in response.text


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


def test_ops_detail_pages(conn, settings):
    with make_client(conn, settings) as client:
        product = client.get("/ops/catalog/81")
        assert product.status_code == 200
        assert "Yamaha C40" in product.text

        missing_product = client.get("/ops/catalog/9999")
        assert missing_product.status_code == 404

        order = client.get("/ops/orders/3")
        assert order.status_code == 200
        assert "Isabela Moreira Cunha" in order.text
        assert "***@" in order.text

        missing_order = client.get("/ops/orders/9999")
        assert missing_order.status_code == 404


def test_ops_policy_search(conn, settings):
    with make_client(conn, settings) as client:
        response = client.get("/ops/policy", params={"q": "devolução"})
        assert response.status_code == 200
        assert "Direito de Arrependimento" in response.text


def test_ops_catalog_filter(conn, settings):
    with make_client(conn, settings) as client:
        response = client.get("/ops/catalog", params={"q": "violão", "status": "active"})
        assert response.status_code == 200
        assert "Yamaha C40" in response.text
