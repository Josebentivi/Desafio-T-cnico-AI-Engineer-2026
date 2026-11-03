from __future__ import annotations

import asyncio

import pytest

from app.agent.guardrails import validate_user_message
from app.agent.orchestrator import Agent
from app.agent.tools import Toolbox
from app.cli import main as cli_main
from app.data.ingest import main as ingest_main
from app.llm.unavailable import UnavailableLLM
from app.web.presentation import format_datetime


def test_missing_provider_returns_portuguese_and_persists_reply(conn, settings):
    agent = Agent(conn, UnavailableLLM(), Toolbox(conn), settings)
    result = asyncio.run(agent.run("pt-fallback", "Quais violões vocês têm?"))
    assert "Desculpe, tive um problema ao consultar o sistema" in result.text
    stored = conn.execute(
        "SELECT content FROM messages WHERE session_id = ? AND role = 'assistant'",
        ("pt-fallback",),
    ).fetchone()
    assert stored["content"] == result.text
    run = conn.execute("SELECT error FROM agent_runs WHERE run_id = ?", (result.run_id,)).fetchone()
    assert "OPENAI_API_KEY não configurada" in run["error"]


def test_message_validation_is_portuguese_and_preserves_limit():
    assert validate_user_message("  ") == "A mensagem está vazia."
    assert "máximo de 4000 caracteres" in validate_user_message("a" * 4001)
    assert validate_user_message("á" * 4000) is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-11-03T20:30:00+00:00", "03/11/2026 às 16:30"),
        ("2026-11-04T01:00:00Z", "03/11/2026 às 21:00"),
        ("2026-11-03T09:30:00-04:00", "03/11/2026 às 09:30"),
    ],
)
def test_timestamps_use_brazilian_format_and_store_timezone(value, expected):
    assert format_datetime(value) == expected


def test_cli_help_uses_portuguese(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["emporio", "--help"])
    with pytest.raises(SystemExit) as exc:
        cli_main()
    assert exc.value.code == 0
    output = capsys.readouterr().out
    assert "uso:" in output
    assert "Enviar uma única mensagem" in output
    assert "Abrir uma conversa interativa" in output


def test_ingestion_help_uses_portuguese(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["ingest", "--help"])
    with pytest.raises(SystemExit) as exc:
        ingest_main()
    assert exc.value.code == 0
    output = capsys.readouterr().out
    assert "uso:" in output
    assert "Importar os arquivos CSV" in output


def test_cli_missing_command_error_uses_portuguese(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["emporio"])
    with pytest.raises(SystemExit) as exc:
        cli_main()
    assert exc.value.code == 2
    assert "os seguintes argumentos são obrigatórios" in capsys.readouterr().err
