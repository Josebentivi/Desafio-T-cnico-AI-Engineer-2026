from __future__ import annotations

import asyncio
import sys
import uuid
from dataclasses import replace

from app.agent.orchestrator import Agent
from app.agent.tools import Toolbox
from app.cli_parser import EnglishArgumentParser
from app.config import get_settings
from app.data.ingest import ingest_all
from app.db import connect, init_db
from app.llm.embeddings import OpenAIEmbeddingClient
from app.llm.openai_responses import OpenAIResponsesClient
from app.llm.unavailable import UnavailableLLM


async def _build_runtime(db_path: str | None, skip_embeddings: bool):
    settings = get_settings()
    if db_path:
        settings = replace(settings, database_path=db_path)
    conn = connect(settings.database_file)
    init_db(conn)
    if conn.execute("SELECT COUNT(*) AS n FROM products").fetchone()["n"] == 0:
        await ingest_all(conn, settings, skip_embeddings=True)
    embedding_client = None
    if not skip_embeddings and settings.has_openai_key and not settings.skip_embeddings:
        embedding_client = OpenAIEmbeddingClient(settings)
    llm = OpenAIResponsesClient(settings) if settings.has_openai_key else UnavailableLLM()
    toolbox = Toolbox(
        conn,
        timezone_name=settings.app_timezone,
        embedding_client=embedding_client,
    )
    return settings, conn, Agent(conn, llm, toolbox, settings)


async def _ask(agent: Agent, session_id: str, message: str) -> None:
    async for event in agent.run_stream(session_id, message):
        if event["type"] == "token":
            print(event["text"], end="", flush=True)
        elif event["type"] == "tool_call":
            print(f"\n[lookup: {event['name']}]", file=sys.stderr)
        elif event["type"] == "done":
            print()
        elif event["type"] == "error":
            print(f"\n{event['message']}", file=sys.stderr)


async def _chat(agent: Agent, session_id: str) -> None:
    print("Empório da Música support. Type 'exit' to quit.")
    while True:
        try:
            message = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if message.casefold() in {"sair", "exit", "quit"}:
            break
        if not message:
            continue
        print("Assistant: ", end="", flush=True)
        await _ask(agent, session_id, message)


async def _main(args) -> int:
    settings, conn, agent = await _build_runtime(args.db, args.skip_embeddings)
    try:
        if args.command == "ask":
            await _ask(agent, args.session or uuid.uuid4().hex, args.message)
        elif args.command == "chat":
            await _chat(agent, args.session or uuid.uuid4().hex)
        elif args.command == "status":
            print(f"Database: {settings.database_file}")
            print(f"Model: {settings.chat_model}")
            print(f"OpenAI configured: {'Yes' if settings.has_openai_key else 'No'}")
            for table, label in {
                "products": "Instruments", "orders": "Orders", "customers": "Customers",
                "policy_sections": "Manual sections", "agent_runs": "Interactions",
            }.items():
                count = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
                print(f"{label}: {count}")
    finally:
        conn.close()
    return 0


def main() -> int:
    parser = EnglishArgumentParser(description="Empório da Música terminal support.")
    parser.add_argument("--db", default=None, help="Alternative SQLite database path.")
    parser.add_argument("--session", default=None, help="Session ID to continue a conversation.")
    parser.add_argument("--skip-embeddings", action="store_true", help="Use text search only.")
    sub = parser.add_subparsers(dest="command", required=True)
    ask = sub.add_parser("ask", help="Send a single message.")
    ask.add_argument("message")
    sub.add_parser("chat", help="Open an interactive terminal chat.")
    sub.add_parser("status", help="Show database and model status.")
    args = parser.parse_args()
    return asyncio.run(_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
