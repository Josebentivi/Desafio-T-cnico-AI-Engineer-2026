from __future__ import annotations

import hashlib

import numpy as np
from openai import AsyncOpenAI

from app.config import Settings


class OpenAIEmbeddingClient:
    def __init__(self, settings: Settings):
        if not settings.has_openai_key:
            raise ValueError("OPENAI_API_KEY is not configured")
        kwargs = {"api_key": settings.openai_api_key}
        if settings.openai_base_url:
            kwargs["base_url"] = settings.openai_base_url
        self.client = AsyncOpenAI(**kwargs)
        self.model = settings.embedding_model
        self.dimensions = settings.embedding_dimensions

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = await self.client.embeddings.create(
            model=self.model,
            input=texts,
            dimensions=self.dimensions,
            encoding_format="float",
        )
        return [item.embedding for item in response.data]


class FakeEmbeddingClient:
    def __init__(self, dimensions: int = 16):
        self.dimensions = dimensions

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            seed = int.from_bytes(digest[:8], "big")
            rng = np.random.default_rng(seed)
            vector = rng.normal(size=self.dimensions)
            norm = np.linalg.norm(vector)
            vectors.append((vector / norm).astype(float).tolist())
        return vectors


def vector_to_blob(vector: list[float]) -> bytes:
    return np.asarray(vector, dtype=np.float32).tobytes()


def blob_to_vector(blob: bytes | None) -> np.ndarray | None:
    if not blob:
        return None
    return np.frombuffer(blob, dtype=np.float32)


def cosine_similarity(query: np.ndarray, vectors: np.ndarray) -> np.ndarray:
    query_norm = np.linalg.norm(query)
    vector_norms = np.linalg.norm(vectors, axis=1)
    denominator = np.maximum(query_norm * vector_norms, 1e-12)
    return (vectors @ query) / denominator
