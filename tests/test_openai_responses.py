from __future__ import annotations

import json
from types import SimpleNamespace

from openai.types.responses import ResponseFunctionToolCall, ResponseReasoningItem

from app.agent.orchestrator import Agent
from app.agent.tools import Toolbox
from app.config import Settings
from app.llm.base import normalize_api_item
from app.llm.fake import FakeLLM
from app.llm.openai_responses import OpenAIResponsesClient


def test_sdk_items_use_api_aliases_and_omit_sdk_only_null_fields():
    client = OpenAIResponsesClient(Settings(openai_api_key="test-key"))
    response = SimpleNamespace(
        id="resp_1",
        output_text="",
        output=[
            ResponseFunctionToolCall(
                arguments="{}",
                call_id="call_1",
                name="get_store_status",
                type="function_call",
                id="fc_1",
                async_=None,
                caller=None,
                namespace=None,
                status=None,
            ),
            ResponseReasoningItem(
                id="rs_1",
                type="reasoning",
                summary=[],
                encrypted_content="encrypted-reasoning",
                status="completed",
            ),
        ],
        usage=SimpleNamespace(input_tokens=10, output_tokens=5),
    )

    result = client._to_model_response(response)

    assert result.function_calls[0].call_id == "call_1"
    assert result.function_calls[0].name == "get_store_status"
    assert result.output_items[0] == {
        "arguments": "{}",
        "call_id": "call_1",
        "name": "get_store_status",
        "type": "function_call",
        "id": "fc_1",
    }
    assert result.output_items[1]["encrypted_content"] == "encrypted-reasoning"
    assert "async_" not in json.dumps(result.output_items)


def test_normalize_api_item_recursively_removes_null_and_sdk_aliases():
    value = {
        "type": "function_call",
        "async_": True,
        "caller": None,
        "content": [{"type": "output_text", "text": "ok", "annotations": None}],
    }
    assert normalize_api_item(value) == {
        "type": "function_call",
        "async": True,
        "content": [{"type": "output_text", "text": "ok"}],
    }


def test_legacy_session_state_is_cleaned_before_reuse(conn, settings):
    legacy_state = [
        {"role": "user", "content": "Olá"},
        {
            "type": "function_call",
            "arguments": "{}",
            "call_id": "call_legacy",
            "name": "get_store_status",
            "async_": None,
            "caller": None,
            "namespace": None,
            "status": None,
        },
        {
            "type": "function_call_output",
            "call_id": "call_legacy",
            "output": "{}",
        },
    ]
    conn.execute(
        "INSERT INTO sessions (session_id, title, state_json, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("legacy", "Conversa antiga", json.dumps(legacy_state), "2026-01-01", "2026-01-01"),
    )
    conn.commit()

    agent = Agent(conn, FakeLLM([]), Toolbox(conn), settings)

    assert agent._load_state("legacy") == [
        {"role": "user", "content": "Olá"},
        {
            "type": "function_call",
            "arguments": "{}",
            "call_id": "call_legacy",
            "name": "get_store_status",
        },
        {
            "type": "function_call_output",
            "call_id": "call_legacy",
            "output": "{}",
        },
    ]
