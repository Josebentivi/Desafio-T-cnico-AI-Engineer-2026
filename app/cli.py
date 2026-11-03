from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from dataclasses import replace

from app.agent.orchestrator import Agent
from app.agent.tools import Toolbox
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
            print(f"\n[consulta: {event['name']}]", file=sys.stderr)
        elif event["type"] == "done":
            print()
        elif event["type"] == "error":
            print(f"\n{event['message']}", file=sys.stderr)


async def _chat(agent: Agent, session_id: str) -> None:
    print("Empório da Música — atendimento. Digite 'sair' para encerrar.")
    while True:
        try:
            message = input("\nVocê: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if message.casefold() in {"sair", "exit", "quit"}:
            break
        if not message:
            continue
        print("Assistente: ", end="", flush=True)
        await _ask(agent, session_id, message)


async def _main(args) -> int:
    settings, conn, agent = await _build_runtime(args.db, args.skip_embeddings)
    try:
        if args.command == "ask":
            await _ask(agent, args.session or uuid.uuid4().hex, args.message)
        elif args.command == "chat":
            await _chat(agent, args.session or uuid.uuid4().hex)
        elif args.command == "status":
            print(f"Banco: {settings.database_file}")
            print(f"Modelo: {settings.chat_model}")
            print(f"OpenAI configurada: {settings.has_openai_key}")
            for table in ["products", "orders", "customers", "policy_sections", "agent_runs"]:
                count = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
                print(f"{table}: {count}")
    finally:
        conn.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="CLI do agente da Empório da Música.")
    parser.add_argument("--db", default=None, help="Caminho alternativo do SQLite.")
    parser.add_argument("--session", default=None, help="ID de sessão para continuar uma conversa.")
    parser.add_argument("--skip-embeddings", action="store_true", help="Não usa embeddings.")
    sub = parser.add_subparsers(dest="command", required=True)
    ask = sub.add_parser("ask", help="Envia uma mensagem única.")
    ask.add_argument("message")
    sub.add_parser("chat", help="Abre um chat interativo no terminal.")
    sub.add_parser("status", help="Mostra o estado do banco e do modelo.")
    args = parser.parse_args()
    return asyncio.run(_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
