from __future__ import annotations

import html
import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from markupsafe import Markup

from app.agent.orchestrator import Agent
from app.domain.catalog import CatalogService
from app.domain.money import format_brl
from app.domain.orders import OrderService, format_date_br

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
templates.env.globals["format_brl"] = format_brl
templates.env.globals["format_date_br"] = format_date_br


def render_message(text: str) -> Markup:
    escaped = html.escape(text or "")
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    return Markup(escaped.replace("\n", "<br>"))


templates.env.filters["render_message"] = render_message


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _conn(request: Request):
    return request.app.state.conn


def _settings(request: Request):
    return request.app.state.settings


def _agent(request: Request) -> Agent:
    return Agent(
        _conn(request),
        request.app.state.llm,
        request.app.state.toolbox,
        _settings(request),
    )


def _ensure_session(request: Request, session_id: str | None = None) -> str:
    conn = _conn(request)
    sid = (session_id or request.cookies.get("session_id") or uuid.uuid4().hex).strip()
    row = conn.execute("SELECT session_id FROM sessions WHERE session_id = ?", (sid,)).fetchone()
    if row is None:
        now = _now()
        conn.execute(
            """
            INSERT INTO sessions (session_id, title, state_json, created_at, updated_at)
            VALUES (?, 'Nova conversa', '[]', ?, ?)
            """,
            (sid, now, now),
        )
        conn.commit()
    return sid


def _messages(request: Request, session_id: str) -> list[dict]:
    return [
        dict(row)
        for row in _conn(request).execute(
            "SELECT role, content, created_at FROM messages WHERE session_id = ? ORDER BY message_id",
            (session_id,),
        )
    ]


def _sessions(request: Request) -> list[dict]:
    return [
        dict(row)
        for row in _conn(request).execute(
            "SELECT session_id, title, updated_at FROM sessions ORDER BY updated_at DESC LIMIT 20"
        )
    ]


def _chat_context(request: Request, session_id: str) -> dict:
    return {
        "request": request,
        "active_nav": "chat",
        "session_id": session_id,
        "messages": _messages(request, session_id),
        "sessions": _sessions(request),
        "model": _settings(request).chat_model,
    }


def _set_session_cookie(response, session_id: str):
    response.set_cookie(
        "session_id",
        session_id,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 30,
    )
    return response


def _sse(event: dict) -> str:
    event_type = event.get("type", "message")
    data = json.dumps(event, ensure_ascii=False)
    return f"event: {event_type}\ndata: {data}\n\n"


@router.get("/", response_class=HTMLResponse)
async def chat_page(request: Request, session_id: str | None = None):
    sid = _ensure_session(request, session_id)
    response = templates.TemplateResponse("chat.html", _chat_context(request, sid))
    return _set_session_cookie(response, sid)


@router.get("/sessions/{session_id}")
async def select_session(request: Request, session_id: str):
    sid = _ensure_session(request, session_id)
    response = RedirectResponse("/", status_code=303)
    return _set_session_cookie(response, sid)


@router.post("/sessions/new")
async def new_session(request: Request):
    sid = _ensure_session(request, uuid.uuid4().hex)
    response = RedirectResponse("/", status_code=303)
    return _set_session_cookie(response, sid)


@router.post("/chat/stream")
async def chat_stream(
    request: Request,
    message: str = Form(...),
    session_id: str = Form(...),
):
    sid = _ensure_session(request, session_id)
    agent = _agent(request)

    async def generate():
        async for event in agent.run_stream(sid, message):
            yield _sse(event)

    response = StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
    return _set_session_cookie(response, sid)


@router.post("/chat", response_class=HTMLResponse)
async def chat_once(
    request: Request,
    message: str = Form(...),
    session_id: str = Form(...),
):
    sid = _ensure_session(request, session_id)
    result = await _agent(request).run(sid, message)
    return templates.TemplateResponse(
        "partials/chat_exchange.html",
        {
            "request": request,
            "message": message,
            "answer": result.text,
            "warnings": result.warnings,
        },
    )


@router.get("/health")
async def health(request: Request):
    conn = _conn(request)
    return JSONResponse(
        {
            "status": "ok",
            "model": _settings(request).chat_model,
            "products": conn.execute("SELECT COUNT(*) AS n FROM products").fetchone()["n"],
            "orders": conn.execute("SELECT COUNT(*) AS n FROM orders").fetchone()["n"],
            "policy_sections": conn.execute(
                "SELECT COUNT(*) AS n FROM policy_sections"
            ).fetchone()["n"],
            "openai_configured": _settings(request).has_openai_key,
        }
    )


def _ops_context(request: Request, active_nav: str, **kwargs) -> dict:
    context = {"request": request, "active_nav": active_nav}
    context.update(kwargs)
    return context


@router.get("/ops", response_class=HTMLResponse)
async def ops_dashboard(request: Request):
    conn = _conn(request)
    counts = {
        "products": conn.execute("SELECT COUNT(*) AS n FROM products").fetchone()["n"],
        "orders": conn.execute("SELECT COUNT(*) AS n FROM orders").fetchone()["n"],
        "customers": conn.execute("SELECT COUNT(*) AS n FROM customers").fetchone()["n"],
        "promotions": conn.execute(
            "SELECT COUNT(*) AS n FROM promotions WHERE is_active = 1"
        ).fetchone()["n"],
        "issues": conn.execute("SELECT COUNT(*) AS n FROM data_quality_issues").fetchone()["n"],
        "runs": conn.execute("SELECT COUNT(*) AS n FROM agent_runs").fetchone()["n"],
    }
    recent_runs = [
        dict(row)
        for row in conn.execute(
            """
            SELECT r.*, s.title
            FROM agent_runs r
            JOIN sessions s ON s.session_id = r.session_id
            ORDER BY r.run_id DESC
            LIMIT 8
            """
        )
    ]
    issues = [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM data_quality_issues ORDER BY issue_id DESC LIMIT 8"
        )
    ]
    return templates.TemplateResponse(
        "ops_dashboard.html",
        _ops_context(
            request,
            "dashboard",
            counts=counts,
            recent_runs=recent_runs,
            issues=issues,
        ),
    )


@router.get("/ops/catalog", response_class=HTMLResponse)
async def ops_catalog(
    request: Request,
    q: str = "",
    category: str = "",
    status: str = "",
    only_available: bool = False,
):
    catalog = CatalogService(_conn(request))
    products = catalog.search(
        query=q or None,
        category=category or None,
        only_available=only_available,
        limit=200,
    )
    if status:
        products = [product for product in products if product["status"] == status]
    return templates.TemplateResponse(
        "ops_catalog.html",
        _ops_context(
            request,
            "catalog",
            products=products,
            categories=catalog.list_categories(),
            q=q,
            category=category,
            status=status,
            only_available=only_available,
        ),
    )


@router.get("/ops/catalog/{product_id}", response_class=HTMLResponse)
async def ops_product(request: Request, product_id: int):
    product = CatalogService(_conn(request)).get_product(product_id)
    return templates.TemplateResponse(
        "ops_product.html",
        _ops_context(request, "catalog", product=product),
        status_code=200 if product else 404,
    )


@router.get("/ops/orders", response_class=HTMLResponse)
async def ops_orders(request: Request, status: str = "", q: str = ""):
    orders = OrderService(_conn(request)).list_orders(status=status or None, search=q or None)
    return templates.TemplateResponse(
        "ops_orders.html",
        _ops_context(request, "orders", orders=orders, status=status, q=q),
    )


@router.get("/ops/orders/{order_id}", response_class=HTMLResponse)
async def ops_order(request: Request, order_id: int):
    order = OrderService(_conn(request)).get_order_for_ops(order_id)
    return templates.TemplateResponse(
        "ops_order.html",
        _ops_context(request, "orders", order=order),
        status_code=200 if order else 404,
    )


@router.get("/ops/traces", response_class=HTMLResponse)
async def ops_traces(request: Request):
    runs = [
        dict(row)
        for row in _conn(request).execute(
            """
            SELECT r.*, s.title,
                   (SELECT COUNT(*) FROM tool_calls t WHERE t.run_id = r.run_id) AS tool_count
            FROM agent_runs r
            JOIN sessions s ON s.session_id = r.session_id
            ORDER BY r.run_id DESC
            LIMIT 100
            """
        )
    ]
    return templates.TemplateResponse(
        "ops_traces.html",
        _ops_context(request, "traces", runs=runs),
    )


@router.get("/ops/traces/{run_id}", response_class=HTMLResponse)
async def ops_trace(request: Request, run_id: int):
    conn = _conn(request)
    run = conn.execute(
        """
        SELECT r.*, s.title
        FROM agent_runs r
        JOIN sessions s ON s.session_id = r.session_id
        WHERE r.run_id = ?
        """,
        (run_id,),
    ).fetchone()
    tool_calls = [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM tool_calls WHERE run_id = ? ORDER BY tool_call_id", (run_id,)
        )
    ]
    messages = []
    if run:
        messages = [
            dict(row)
            for row in conn.execute(
                "SELECT role, content, created_at FROM messages WHERE session_id = ? ORDER BY message_id",
                (run["session_id"],),
            )
        ]
    return templates.TemplateResponse(
        "ops_trace.html",
        _ops_context(
            request,
            "traces",
            run=dict(run) if run else None,
            tool_calls=tool_calls,
            messages=messages,
        ),
        status_code=200 if run else 404,
    )


@router.get("/ops/policy", response_class=HTMLResponse)
async def ops_policy(request: Request, q: str = ""):
    policy = request.app.state.toolbox.policy
    results = await policy.search(q, 5) if q.strip() else []
    return templates.TemplateResponse(
        "ops_policy.html",
        _ops_context(
            request,
            "policy",
            sections=policy.list_sections(),
            results=results,
            q=q,
        ),
    )


@router.get("/ops/quality", response_class=HTMLResponse)
async def ops_quality(request: Request):
    issues = [
        dict(row)
        for row in _conn(request).execute(
            "SELECT * FROM data_quality_issues ORDER BY issue_id DESC"
        )
    ]
    return templates.TemplateResponse(
        "ops_quality.html",
        _ops_context(request, "quality", issues=issues),
    )
