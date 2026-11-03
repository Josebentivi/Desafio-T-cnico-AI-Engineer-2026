from __future__ import annotations

import asyncio
import json
from dataclasses import replace

from app.agent.guardrails import grounding_warnings
from app.agent.orchestrator import Agent
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.tools import Toolbox
from app.llm.embeddings import FakeEmbeddingClient
from app.llm.fake import FakeLLM, FakeTurn, function_call


def make_agent(conn, settings, turns):
    llm = FakeLLM(turns)
    toolbox = Toolbox(conn, embedding_client=FakeEmbeddingClient(16))
    return Agent(conn, llm, toolbox, settings), llm


def test_system_prompt_requires_brazilian_portuguese():
    assert "Always answer in Brazilian Portuguese (pt-BR)" in SYSTEM_PROMPT


def test_grounding_accepts_both_currency_formats():
    outputs = [{"total_cents": 1149900, "total_brl": "R$ 11.499,00"}]
    assert grounding_warnings("The total is R$ 11,499.00", outputs, 1) == []
    assert grounding_warnings("The total is R$ 11.499,00", outputs, 1) == []


def test_agent_executes_tool_and_persists(conn, settings):
    agent, _ = make_agent(
        conn,
        settings,
        [
            FakeTurn(
                function_calls=[
                    function_call(
                        "search_products",
                        {
                            "query": "acoustic guitar",
                            "category": None,
                            "min_price_brl": None,
                            "max_price_brl": 1000.0,
                            "only_available": True,
                            "limit": 3,
                        },
                    )
                ]
            ),
            FakeTurn(text="I found three acoustic guitars available under R$ 1,000."),
        ],
    )
    result = asyncio.run(agent.run("s1", "Which acoustic guitars are under R$ 1,000?"))
    assert result.text.startswith("I found three")
    assert result.tool_calls[0]["name"] == "search_products"
    assert conn.execute("SELECT COUNT(*) AS n FROM messages").fetchone()["n"] == 2
    assert conn.execute("SELECT COUNT(*) AS n FROM tool_calls").fetchone()["n"] == 1
    run = conn.execute("SELECT * FROM agent_runs WHERE run_id = ?", (result.run_id,)).fetchone()
    assert run["model"] == settings.chat_model
    assert run["input_tokens"] == 20
    assert run["output_tokens"] == 10
    state = json.loads(
        conn.execute("SELECT state_json FROM sessions WHERE session_id = 's1'").fetchone()[
            "state_json"
        ]
    )
    assert any(item.get("type") == "function_call_output" for item in state)


def test_agent_order_verification_found(conn, settings):
    agent, _ = make_agent(
        conn,
        settings,
        [
            FakeTurn(
                function_calls=[
                    function_call(
                        "get_order",
                        {"order_id": 3, "customer_verifier": "Isabela Moreira Cunha"},
                    )
                ]
            ),
            FakeTurn(text="Your order has been delivered."),
        ],
    )
    result = asyncio.run(agent.run("s2", "What is the status of order 3?"))
    assert result.text == "Your order has been delivered."
    output = json.loads(
        conn.execute("SELECT output_json FROM tool_calls WHERE run_id = ?", (result.run_id,))
        .fetchone()["output_json"]
    )
    assert output["found"] is True
    assert output["status"] == "delivered"


def test_agent_order_verification_rejects_wrong_customer(conn, settings):
    agent, _ = make_agent(
        conn,
        settings,
        [
            FakeTurn(
                function_calls=[
                    function_call(
                        "get_order",
                        {"order_id": 3, "customer_verifier": "Pedro Henrique Oliveira"},
                    )
                ]
            ),
            FakeTurn(text="I could not find that order with the details provided."),
        ],
    )
    result = asyncio.run(agent.run("s3", "Order 3, I am Pedro."))
    output = json.loads(
        conn.execute("SELECT output_json FROM tool_calls WHERE run_id = ?", (result.run_id,))
        .fetchone()["output_json"]
    )
    assert output["found"] is False


def test_agent_policy_tool(conn, settings):
    agent, _ = make_agent(
        conn,
        settings,
        [
            FakeTurn(
                function_calls=[
                    function_call("search_policy", {"query": "return policy", "top_k": 2})
                ]
            ),
            FakeTurn(text="Under policy 4.1, you can return it within 7 days."),
        ],
    )
    result = asyncio.run(agent.run("s4", "Can I return it?"))
    output = json.loads(
        conn.execute("SELECT output_json FROM tool_calls WHERE run_id = ?", (result.run_id,))
        .fetchone()["output_json"]
    )
    assert output["sections"]
    assert any(section["section_id"] == "4.1" for section in output["sections"])


def test_agent_stops_after_max_iterations(conn, settings):
    limited = replace(settings, max_tool_iterations=2)
    turns = [
        FakeTurn(function_calls=[function_call("get_store_status", {}, call_id=f"c{i}")])
        for i in range(5)
    ]
    agent, _ = make_agent(conn, limited, turns)
    result = asyncio.run(agent.run("s5", "What time do you open?"))
    assert "não consegui concluir a consulta" in result.text
    assert conn.execute("SELECT COUNT(*) AS n FROM tool_calls").fetchone()["n"] == 2


def test_agent_grounding_warning(conn, settings):
    agent, _ = make_agent(
        conn,
        settings,
        [
            FakeTurn(
                function_calls=[
                    function_call(
                        "search_products",
                        {
                            "query": "acoustic guitar",
                            "category": None,
                            "min_price_brl": None,
                            "max_price_brl": None,
                            "only_available": False,
                            "limit": 1,
                        },
                    )
                ]
            ),
            FakeTurn(text="The price is R$ 9.999,99."),
        ],
    )
    result = asyncio.run(agent.run("s6", "How much is it?"))
    assert result.warnings
    assert "9.999,99" in result.warnings[0]


def test_agent_stream_events(conn, settings):
    agent, _ = make_agent(conn, settings, [FakeTurn(text="Hello, how are you?")])

    async def collect():
        return [event async for event in agent.run_stream("s7", "Hi")]

    events = asyncio.run(collect())
    types = [event["type"] for event in events]
    assert "token" in types
    assert types[-1] == "done"
    assert events[-1]["text"] == "Hello, how are you?"
