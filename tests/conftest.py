from __future__ import annotations

import asyncio

import pytest

from app.config import Settings
from app.data.ingest import ingest_all
from app.db import connect, init_db
from app.llm.embeddings import FakeEmbeddingClient


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        database_path=str(tmp_path / "test.db"),
        chat_model="gpt-6-luna",
        embedding_model="fake-embedding",
        embedding_dimensions=16,
        reasoning_effort="low",
        skip_embeddings=False,
    )


@pytest.fixture
def conn(settings):
    connection = connect(settings.database_file)
    init_db(connection)
    asyncio.run(
        ingest_all(
            connection,
            settings,
            reset=True,
            embedding_client=FakeEmbeddingClient(16),
            skip_embeddings=False,
        )
    )
    yield connection
    connection.close()
