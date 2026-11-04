from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.agent.guardrails import grounding_warnings, validate_user_message
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.tools import TOOL_SPECS, Toolbox, parse_arguments
from app.config import Settings
from app.llm.base import LLMClient, LLMError, normalize_api_item

INPUT_COST_PER_MTOK = 0.10
OUTPUT_COST_PER_MTOK = 0.50


@dataclass
class AgentResult:
    text: str
    run_id: int
    response_id: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    tool_calls: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _cost(input_tokens: int, output_tokens: int) -> float:
    return (
        input_tokens / 1_000_000 * INPUT_COST_PER_MTOK
        + output_tokens / 1_000_000 * OUTPUT_COST_PER_MTOK
    )


class Agent:
    def __init__(
        self,
        conn: sqlite3.Connection,
        llm: LLMClient,
        toolbox: Toolbox,
        settings: Settings,
    ):
        self.conn = conn
        self.llm = llm
        self.toolbox = toolbox
        self.settings = settings

    def _ensure_session(self, session_id: str, user_message: str) -> None:
        now = _now()
        self.conn.execute(
            """
            INSERT OR IGNORE INTO sessions (session_id, title, state_json, created_at, updated_at)
            VALUES (?, ?, '[]', ?, ?)
            """,
            (session_id, "Nova conversa", now, now),
        )
        self.conn.execute(
            "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
            (now, session_id),
        )
        row = self.conn.execute(
            "SELECT title FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if row and row["title"] in {"New conversation", "Nova conversa"}:
            title = " ".join(user_message.split())[:60]
            self.conn.execute(
                "UPDATE sessions SET title = ? WHERE session_id = ?", (title, session_id)
            )
        self.conn.execute(
            "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, 'user', ?, ?)",
            (session_id, user_message, now),
        )
        self.conn.commit()

    def _load_state(self, session_id: str) -> list[dict]:
        row = self.conn.execute(
            "SELECT state_json FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if not row or not row["state_json"]:
            return []
        try:
            value = json.loads(row["state_json"])
        except json.JSONDecodeError:
            return []
        if not isinstance(value, list):
            return []
        return [normalize_api_item(item) for item in value]

    def _save_state(self, session_id: str, state: list[dict]) -> None:
        cleaned = [normalize_api_item(item) for item in state]
        self.conn.execute(
            "UPDATE sessions SET state_json = ?, updated_at = ? WHERE session_id = ?",
            (json.dumps(cleaned, ensure_ascii=False, default=str), _now(), session_id),
        )
        self.conn.commit()

    async def run_stream(self, session_id: str, user_message: str) -> AsyncIterator[dict]:
        validation_error = validate_user_message(user_message)
        if validation_error:
            yield {"type": "error", "message": validation_error}
            return

        self._ensure_session(session_id, user_message)
        state = self._load_state(session_id)
        state.append({"role": "user", "content": user_message})

        cursor = self.conn.execute(
            """
            INSERT INTO agent_runs
                (session_id, model, reasoning_effort, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (session_id, self.settings.chat_model, self.settings.reasoning_effort, _now()),
        )
        run_id = int(cursor.lastrowid)
        self.conn.commit()

        started = time.perf_counter()
        input_tokens = 0
        output_tokens = 0
        response_id = ""
        final_text = ""
        tool_records: list[dict] = []
        tool_outputs: list[dict] = []
        warnings: list[str] = []
        error_message = ""

        try:
            for _ in range(max(1, self.settings.max_tool_iterations)):
                completed = None
                streamed_text = ""
                async for event in self.llm.stream_response(
                    instructions=SYSTEM_PROMPT,
                    input_items=state,
                    tools=TOOL_SPECS,
                ):
                    if event.type == "text_delta" and event.text:
                        streamed_text += event.text
                        yield {"type": "token", "text": event.text}
                    elif event.type == "completed" and event.response is not None:
                        completed = event.response
                if completed is None:
                    raise LLMError("O modelo não retornou uma resposta completa.")

                input_tokens += completed.input_tokens
                output_tokens += completed.output_tokens
                response_id = completed.response_id or response_id
                state.extend(completed.output_items)

                if not completed.function_calls:
                    final_text = completed.output_text or streamed_text
                    break

                for call in completed.function_calls:
                    arguments = parse_arguments(call.arguments)
                    yield {
                        "type": "tool_call",
                        "name": call.name,
                        "arguments": arguments,
                    }
                    tool_started = time.perf_counter()
                    tool_error = ""
                    try:
                        output = await self.toolbox.execute(call.name, arguments)
                    except Exception as exc:
                        output = {"error": str(exc)}
                        tool_error = str(exc)
                    tool_latency = int((time.perf_counter() - tool_started) * 1000)
                    output_json = json.dumps(output, ensure_ascii=False, default=str)
                    self.conn.execute(
                        """
                        INSERT INTO tool_calls
                            (run_id, name, arguments_json, output_json, latency_ms, error, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            run_id,
                            call.name,
                            json.dumps(arguments, ensure_ascii=False),
                            output_json,
                            tool_latency,
                            tool_error,
                            _now(),
                        ),
                    )
                    self.conn.commit()
                    state.append(
                        {
                            "type": "function_call_output",
                            "call_id": call.call_id,
                            "output": output_json,
                        }
                    )
                    tool_outputs.append(output)
                    tool_records.append(
                        {
                            "name": call.name,
                            "arguments": arguments,
                            "output": output,
                            "latency_ms": tool_latency,
                            "error": tool_error,
                        }
                    )
                    yield {
                        "type": "tool_result",
                        "name": call.name,
                        "output": output,
                        "latency_ms": tool_latency,
                        "error": tool_error,
                    }
            else:
                final_text = (
                    "Desculpe, não consegui concluir a consulta agora. "
                    "Tente novamente ou fale com a equipe da loja."
                )

            if not final_text:
                final_text = (
                    "Desculpe, não consegui concluir a consulta agora. "
                    "Tente novamente ou fale com a equipe da loja."
                )

            warnings = grounding_warnings(
                final_text, tool_outputs, len(tool_records), user_message
            )
        except LLMError as exc:
            error_message = str(exc)
            final_text = (
                "Desculpe, tive um problema ao consultar o sistema agora. "
                "Tente novamente em instantes."
            )
            yield {"type": "error", "message": final_text}
        except Exception as exc:
            error_message = str(exc)
            final_text = (
                "Desculpe, ocorreu um problema inesperado. "
                "Tente novamente ou fale com a equipe da loja."
            )
            yield {"type": "error", "message": final_text}

        latency_ms = int((time.perf_counter() - started) * 1000)
        self.conn.execute(
            """
            UPDATE agent_runs
            SET response_id = ?, input_tokens = ?, output_tokens = ?, latency_ms = ?,
                estimated_cost_usd = ?, error = ?, warnings_json = ?
            WHERE run_id = ?
            """,
            (
                response_id,
                input_tokens,
                output_tokens,
                latency_ms,
                _cost(input_tokens, output_tokens),
                error_message,
                json.dumps(warnings, ensure_ascii=False),
                run_id,
            ),
        )
        self.conn.execute(
            "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, 'assistant', ?, ?)",
            (session_id, final_text, _now()),
        )
        self._save_state(session_id, state)
        self.conn.commit()

        yield {
            "type": "done",
            "text": final_text,
            "run_id": run_id,
            "response_id": response_id,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "latency_ms": latency_ms,
            "tool_calls": [
                {
                    "name": record["name"],
                    "arguments": record["arguments"],
                    "latency_ms": record["latency_ms"],
                    "error": record["error"],
                }
                for record in tool_records
            ],
            "warnings": warnings,
        }

    async def run(self, session_id: str, user_message: str) -> AgentResult:
        result = AgentResult(text="", run_id=0)
        async for event in self.run_stream(session_id, user_message):
            if event["type"] == "done":
                result = AgentResult(
                    text=event["text"],
                    run_id=event["run_id"],
                    response_id=event["response_id"],
                    input_tokens=event["input_tokens"],
                    output_tokens=event["output_tokens"],
                    latency_ms=event["latency_ms"],
                    tool_calls=event["tool_calls"],
                    warnings=event["warnings"],
                )
            elif event["type"] == "error" and not result.text:
                result = AgentResult(text=event["message"], run_id=result.run_id)
        return result
