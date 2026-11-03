from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from app.llm.base import FunctionCall, LLMClient, ModelResponse, StreamEvent


@dataclass
class FakeTurn:
    text: str = ""
    function_calls: list[FunctionCall] = field(default_factory=list)
    input_tokens: int = 10
    output_tokens: int = 5


class FakeLLM(LLMClient):
    def __init__(self, turns: list[FakeTurn]):
        self.turns = list(turns)
        self.calls: list[list[dict]] = []

    async def stream_response(
        self,
        *,
        instructions: str,
        input_items: list[dict],
        tools: list[dict],
    ) -> AsyncIterator[StreamEvent]:
        self.calls.append(list(input_items))
        if not self.turns:
            turn = FakeTurn(text="Não tenho mais nada a responder.")
        else:
            turn = self.turns.pop(0)

        output_items: list[dict] = []
        for call in turn.function_calls:
            output_items.append(
                {
                    "type": "function_call",
                    "call_id": call.call_id,
                    "name": call.name,
                    "arguments": call.arguments,
                }
            )
        if turn.text:
            output_items.append(
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": turn.text}],
                }
            )
            for start in range(0, len(turn.text), 24):
                yield StreamEvent(type="text_delta", text=turn.text[start : start + 24])

        yield StreamEvent(
            type="completed",
            response=ModelResponse(
                response_id=f"fake-{len(self.calls)}",
                output_text=turn.text,
                output_items=output_items,
                function_calls=turn.function_calls,
                input_tokens=turn.input_tokens,
                output_tokens=turn.output_tokens,
            ),
        )


def function_call(name: str, arguments: dict, call_id: str = "call_1") -> FunctionCall:
    return FunctionCall(call_id=call_id, name=name, arguments=json.dumps(arguments))
