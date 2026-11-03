from __future__ import annotations

from collections.abc import AsyncIterator

from app.llm.base import LLMClient, LLMError, StreamEvent


class UnavailableLLM(LLMClient):
    async def stream_response(
        self,
        *,
        instructions: str,
        input_items: list[dict],
        tools: list[dict],
    ) -> AsyncIterator[StreamEvent]:
        raise LLMError(
            "OPENAI_API_KEY is not configured. Copy .env.example to .env and fill in the key."
        )
        yield StreamEvent(type="completed")
