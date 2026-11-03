from __future__ import annotations

import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.agent.tools import Toolbox
from app.config import Settings, get_settings
from app.data.ingest import ingest_all
from app.db import connect, init_db
from app.llm.embeddings import OpenAIEmbeddingClient
from app.llm.openai_responses import OpenAIResponsesClient
from app.llm.unavailable import UnavailableLLM
from app.web.assets import RevalidateBrowserCache
from app.web.routes import router

STATIC_DIR = Path(__file__).resolve().parent / "web" / "static"


def create_app(
    settings: Settings | None = None,
    conn: sqlite3.Connection | None = None,
    llm=None,
    embedding_client=None,
) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        own_conn = conn is None
        db_conn = conn or connect(settings.database_file)
        init_db(db_conn)

        product_count = db_conn.execute("SELECT COUNT(*) AS n FROM products").fetchone()["n"]
        if product_count == 0:
            await ingest_all(
                db_conn,
                settings,
                reset=False,
                embedding_client=None,
                skip_embeddings=True,
            )

        active_embedding_client = embedding_client
        if active_embedding_client is None and settings.has_openai_key and not settings.skip_embeddings:
            active_embedding_client = OpenAIEmbeddingClient(settings)

        active_llm = llm
        if active_llm is None:
            active_llm = (
                OpenAIResponsesClient(settings) if settings.has_openai_key else UnavailableLLM()
            )

        app.state.settings = settings
        app.state.conn = db_conn
        app.state.embedding_client = active_embedding_client
        app.state.llm = active_llm
        app.state.toolbox = Toolbox(
            db_conn,
            timezone_name=settings.app_timezone,
            embedding_client=active_embedding_client,
        )
        yield
        if own_conn:
            db_conn.close()

    app = FastAPI(title="Empório da Música", lifespan=lifespan)
    app.state.static_dir = STATIC_DIR
    app.add_middleware(RevalidateBrowserCache)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.include_router(router)
    return app


app = create_app()


if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=True)
