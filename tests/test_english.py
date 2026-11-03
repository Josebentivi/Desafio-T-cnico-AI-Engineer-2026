from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_runtime_strings_are_english():
    files = [
        "app/web/static/chat.js",
        "app/cli.py",
        "app/llm/openai_responses.py",
        "app/llm/unavailable.py",
        "app/agent/orchestrator.py",
    ]
    forbidden = [
        "Falha",
        "Ocorreu",
        "[consulta",
        "não configurada",
        "Desculpe",
        "Servidor",
    ]
    for relative in files:
        text = (ROOT / relative).read_text(encoding="utf-8")
        for marker in forbidden:
            assert marker not in text, f"{relative} still contains {marker!r}"
