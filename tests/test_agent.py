from __future__ import annotations

import asyncio
import json
from dataclasses import replace

from app.agent.orchestrator import Agent
from app.agent.tools import Toolbox
from app.llm.embeddings import FakeEmbeddingClient
from app.llm.fake import FakeLLM, FakeTurn, function_call


def make_agent(conn, settings, turns):
    llm = FakeLLM(turns)
    toolbox = Toolbox(conn, embedding_client=FakeEmbeddingClient(16))
    return Agent(conn, llm, toolbox, settings), llm


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
                            "query": "violão",
                            "category": None,
                            "min_price_brl": None,
                            "max_price_brl": 1000.0,
                            "only_available": True,
                            "limit": 3,
                        },
                    )
                ]
            ),
            FakeTurn(text="Encontrei três violões disponíveis até R$ 1.000."),
        ],
    )
    result = asyncio.run(agent.run("s1", "Quais violões até 1000?"))
    assert result.text.startswith("Encontrei três")
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
            FakeTurn(text="Seu pedido está entregue."),
        ],
    )
    result = asyncio.run(agent.run("s2", "Qual o status do pedido 3?"))
    assert result.text == "Seu pedido está entregue."
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
            FakeTurn(text="Não encontrei esse pedido com os dados informados."),
        ],
    )
    result = asyncio.run(agent.run("s3", "Pedido 3, sou Pedro."))
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
                    function_call("search_policy", {"query": "devolução", "top_k": 2})
                ]
            ),
            FakeTurn(text="Conforme a política 4.1, você pode devolver em até 7 dias."),
        ],
    )
    result = asyncio.run(agent.run("s4", "Posso devolver?"))
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
    result = asyncio.run(agent.run("s5", "Que horas vocês abrem?"))
    assert "não consegui concluir" in result.text
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
                            "query": "violão",
                            "category": None,
                            "min_price_brl": None,
                            "max_price_brl": None,
                            "only_available": False,
                            "limit": 1,
                        },
                    )
                ]
            ),
            FakeTurn(text="O preço é R$ 9.999,99."),
        ],
    )
    result = asyncio.run(agent.run("s6", "Quanto custa?"))
    assert result.warnings
    assert "9.999,99" in result.warnings[0]


def test_agent_stream_events(conn, settings):
    agent, _ = make_agent(conn, settings, [FakeTurn(text="Olá, tudo bem?")])

    async def collect():
        return [event async for event in agent.run_stream("s7", "Oi")]

    events = asyncio.run(collect())
    types = [event["type"] for event in events]
    assert "token" in types
    assert types[-1] == "done"
    assert events[-1]["text"] == "Olá, tudo bem?"
