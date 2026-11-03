from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return int(value)


@dataclass(frozen=True)
class Settings:
    openai_api_key: str = ""
    openai_base_url: str = ""
    chat_model: str = "gpt-6-luna"
    embedding_model: str = "text-embedding-3-large"
    embedding_dimensions: int = 3072
    reasoning_effort: str = "low"
    max_output_tokens: int = 4000
    max_tool_iterations: int = 6
    database_path: str = "data/app.db"
    app_timezone: str = "America/Campo_Grande"
    host: str = "127.0.0.1"
    port: int = 8000
    skip_embeddings: bool = False

    @property
    def database_file(self) -> Path:
        path = Path(self.database_path)
        if not path.is_absolute():
            path = ROOT_DIR / path
        return path

    @property
    def data_dir(self) -> Path:
        return ROOT_DIR / "data"

    @property
    def examples_dir(self) -> Path:
        return ROOT_DIR / "examples"

    @property
    def has_openai_key(self) -> bool:
        return bool(self.openai_api_key.strip())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        openai_base_url=os.getenv("OPENAI_BASE_URL", "").strip(),
        chat_model=os.getenv("CHAT_MODEL", "gpt-6-luna").strip() or "gpt-6-luna",
        embedding_model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-large").strip()
        or "text-embedding-3-large",
        embedding_dimensions=_env_int("EMBEDDING_DIMENSIONS", 3072),
        reasoning_effort=os.getenv("REASONING_EFFORT", "low").strip() or "low",
        max_output_tokens=_env_int("MAX_OUTPUT_TOKENS", 4000),
        max_tool_iterations=_env_int("MAX_TOOL_ITERATIONS", 6),
        database_path=os.getenv("DATABASE_PATH", "data/app.db").strip() or "data/app.db",
        app_timezone=os.getenv("APP_TIMEZONE", "America/Campo_Grande").strip()
        or "America/Campo_Grande",
        host=os.getenv("HOST", "127.0.0.1").strip() or "127.0.0.1",
        port=_env_int("PORT", 8000),
        skip_embeddings=_env_bool("SKIP_EMBEDDINGS", False),
    )
