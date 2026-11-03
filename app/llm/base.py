from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class FunctionCall:
    call_id: str
    name: str
    arguments: str


@dataclass
class ModelResponse:
    response_id: str = ""
    output_text: str = ""
    output_items: list[dict] = field(default_factory=list)
    function_calls: list[FunctionCall] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class StreamEvent:
    type: str
    text: str = ""
    response: ModelResponse | None = None


class LLMError(RuntimeError):
    pass


class LLMClient(Protocol):
    async def stream_response(
        self,
        *,
        instructions: str,
        input_items: list[dict],
        tools: list[dict],
    ) -> AsyncIterator[StreamEvent]:
        ...


class EmbeddingClient(Protocol):
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        ...
