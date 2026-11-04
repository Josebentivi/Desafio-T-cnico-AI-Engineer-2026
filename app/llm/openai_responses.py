from __future__ import annotations

from collections.abc import AsyncIterator

from openai import AsyncOpenAI

from app.config import Settings
from app.llm.base import (
    FunctionCall,
    LLMClient,
    LLMError,
    ModelResponse,
    StreamEvent,
    normalize_api_item,
)


def _dump(value):
    if hasattr(value, "model_dump"):
        return normalize_api_item(
            value.model_dump(mode="json", by_alias=True, exclude_none=True)
        )
    if isinstance(value, dict):
        return normalize_api_item(value)
    return value


def _as_dict(item) -> dict:
    dumped = _dump(item)
    return dumped if isinstance(dumped, dict) else {}


class OpenAIResponsesClient(LLMClient):
    def __init__(self, settings: Settings):
        if not settings.has_openai_key:
            raise ValueError("OPENAI_API_KEY is not configured")
        kwargs = {"api_key": settings.openai_api_key}
        if settings.openai_base_url:
            kwargs["base_url"] = settings.openai_base_url
        self.client = AsyncOpenAI(**kwargs)
        self.settings = settings

    def _to_model_response(self, response) -> ModelResponse:
        output = [_as_dict(item) for item in getattr(response, "output", []) or []]
        calls: list[FunctionCall] = []
        for item in output:
            if item.get("type") == "function_call":
                calls.append(
                    FunctionCall(
                        call_id=str(item.get("call_id", "")),
                        name=str(item.get("name", "")),
                        arguments=str(item.get("arguments", "{}")),
                    )
                )
        usage = getattr(response, "usage", None)
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        return ModelResponse(
            response_id=str(getattr(response, "id", "") or ""),
            output_text=str(getattr(response, "output_text", "") or ""),
            output_items=output,
            function_calls=calls,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    async def stream_response(
        self,
        *,
        instructions: str,
        input_items: list[dict],
        tools: list[dict],
    ) -> AsyncIterator[StreamEvent]:
        try:
            stream = await self.client.responses.create(
                model=self.settings.chat_model,
                instructions=instructions,
                input=input_items,
                tools=tools,
                reasoning={"effort": self.settings.reasoning_effort},
                max_output_tokens=self.settings.max_output_tokens,
                parallel_tool_calls=False,
                store=False,
                stream=True,
            )
            async for event in stream:
                event_type = getattr(event, "type", "")
                if event_type == "response.output_text.delta":
                    yield StreamEvent(type="text_delta", text=str(getattr(event, "delta", "")))
                elif event_type == "response.completed":
                    response = getattr(event, "response", None)
                    if response is None:
                        raise LLMError("The response completed without a response object")
                    yield StreamEvent(type="completed", response=self._to_model_response(response))
                elif event_type in {"response.failed", "error"}:
                    message = getattr(event, "message", "") or getattr(event, "error", "")
                    raise LLMError(str(message) or f"API failure: {event_type}")
        except LLMError:
            raise
        except Exception as exc:
            raise LLMError(f"OpenAI request failed: {exc}") from exc
