from __future__ import annotations

import re
from typing import Any

from app.domain.money import format_brl, parse_brl_to_cents

BRL_RE = re.compile(
    r"R\$\s*\d{1,3}(?:\.\d{3})+(?:,\d{2})?"
    r"|R\$\s*\d+\.\d{1,2}"
    r"|R\$\s*\d+(?:,\d{2})?"
)
MAX_USER_MESSAGE_CHARS = 4000


def extract_brl_cents(text: str) -> set[int]:
    values: set[int] = set()
    for match in BRL_RE.findall(text or ""):
        try:
            values.add(parse_brl_to_cents(match))
        except Exception:
            continue
    return values


def _collect_tool_values(value: Any, values: set[int]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key.endswith("_cents") and isinstance(item, (int, float)):
                values.add(int(item))
            _collect_tool_values(item, values)
    elif isinstance(value, list):
        for item in value:
            _collect_tool_values(item, values)
    elif isinstance(value, str):
        values.update(extract_brl_cents(value))


def grounding_warnings(
    text: str,
    tool_outputs: list[Any],
    tool_call_count: int,
    user_message: str = "",
) -> list[str]:
    text_values = extract_brl_cents(text)
    if not text_values:
        return []
    if tool_call_count == 0:
        return ["The answer mentions BRL values without any tool lookup."]
    allowed: set[int] = set()
    for output in tool_outputs:
        _collect_tool_values(output, allowed)
    allowed.update(extract_brl_cents(user_message))
    missing = sorted(text_values - allowed)
    if missing:
        return [
            "BRL values in the answer do not appear in tool results: "
            + ", ".join(format_brl(value) for value in missing)
        ]
    return []


def validate_user_message(text: str) -> str | None:
    if not text or not text.strip():
        return "Message is empty."
    if len(text) > MAX_USER_MESSAGE_CHARS:
        return f"Message is too long (maximum {MAX_USER_MESSAGE_CHARS} characters)."
    return None
