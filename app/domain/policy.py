from __future__ import annotations

import sqlite3

import numpy as np

from app.domain.catalog import fts_query
from app.llm.embeddings import blob_to_vector, cosine_similarity


class PolicyService:
    def __init__(self, conn: sqlite3.Connection, embedding_client=None):
        self.conn = conn
        self.embedding_client = embedding_client

    def _fts_search(self, query: str, limit: int) -> list[dict]:
        fts = fts_query(query)
        if not fts:
            return []
        rows = self.conn.execute(
            """
            SELECT policy_fts.section_id, policy_fts.title, policy_fts.text, ps.page,
                   bm25(policy_fts) AS rank
            FROM policy_fts
            JOIN policy_sections ps ON ps.section_id = policy_fts.section_id
            WHERE policy_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (fts, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    async def _vector_search(self, query: str, limit: int) -> list[dict]:
        if self.embedding_client is None:
            return []
        rows = self.conn.execute(
            """
            SELECT section_id, title, text, page, embedding
            FROM policy_sections
            WHERE embedding IS NOT NULL
            """
        ).fetchall()
        if not rows:
            return []
        try:
            query_vector = np.asarray(
                (await self.embedding_client.embed_texts([query]))[0], dtype=np.float32
            )
        except Exception:
            return []
        vectors = []
        valid_rows = []
        for row in rows:
            vector = blob_to_vector(row["embedding"])
            if vector is None or vector.shape != query_vector.shape:
                continue
            vectors.append(vector)
            valid_rows.append(row)
        if not vectors:
            return []
        matrix = np.vstack(vectors)
        scores = cosine_similarity(query_vector, matrix)
        order = np.argsort(scores)[::-1][:limit]
        results = []
        for index in order:
            row = valid_rows[int(index)]
            results.append(
                {
                    "section_id": row["section_id"],
                    "title": row["title"],
                    "text": row["text"],
                    "page": row["page"],
                    "score": float(scores[int(index)]),
                }
            )
        return results

    async def search(self, query: str, top_k: int = 4) -> list[dict]:
        limit = max(1, min(int(top_k), 8))
        fts_results = self._fts_search(query, limit)
        vector_results = await self._vector_search(query, limit)
        merged: dict[str, dict] = {}
        for source, results in (("fts", fts_results), ("vector", vector_results)):
            for rank, result in enumerate(results):
                section_id = result["section_id"]
                entry = merged.setdefault(
                    section_id,
                    {
                        "section_id": section_id,
                        "title": result["title"],
                        "text": result["text"],
                        "page": result["page"],
                        "score": 0.0,
                        "sources": [],
                    },
                )
                entry["score"] += 1.0 / (60 + rank)
                entry["sources"].append(source)
        ordered = sorted(merged.values(), key=lambda item: item["score"], reverse=True)
        return ordered[:limit]

    def list_sections(self) -> list[dict]:
        return [
            dict(row)
            for row in self.conn.execute(
                """
                SELECT section_id, title, page,
                       CASE WHEN embedding IS NULL THEN 0 ELSE 1 END AS has_embedding
                FROM policy_sections
                ORDER BY CAST(section_id AS REAL), section_id
                """
            )
        ]

    def get_section(self, section_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT section_id, title, text, page FROM policy_sections WHERE section_id = ?",
            (str(section_id),),
        ).fetchone()
        return dict(row) if row else None
