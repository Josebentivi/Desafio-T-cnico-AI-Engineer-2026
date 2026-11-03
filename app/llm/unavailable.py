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
            "OPENAI_API_KEY não configurada. Copie .env.example para .env e preencha a chave."
        )
        yield StreamEvent(type="completed")
