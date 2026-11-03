from __future__ import annotations

import asyncio

from app.domain.policy import PolicyService
from app.llm.embeddings import FakeEmbeddingClient


def test_policy_sections_loaded(conn):
    service = PolicyService(conn, None)
    sections = service.list_sections()
    assert len(sections) == 26
    assert service.get_section("4.1")["title"].startswith("4.1 Direito de Arrependimento")
    assert "7 (sete) dias" in service.get_section("4.1")["text"]
    assert "R$ 80,00" in service.get_section("3.1")["text"]
    assert "90" in service.get_section("8.1")["text"]


def test_fts_only_search(conn):
    service = PolicyService(conn, None)
    results = asyncio.run(service.search("posso devolver compra online", 5))
    ids = [result["section_id"] for result in results]
    assert "4.1" in ids


def test_hybrid_search_relevant_sections(conn):
    service = PolicyService(conn, FakeEmbeddingClient(16))

    returns = asyncio.run(service.search("direito de arrependimento devolução", 5))
    assert "4.1" in [result["section_id"] for result in returns]

    pix = asyncio.run(service.search("desconto no PIX", 5))
    assert {"3", "3.1", "6.2"} & {result["section_id"] for result in pix}

    warranty = asyncio.run(service.search("prazo da garantia legal", 5))
    assert "8.1" in [result["section_id"] for result in warranty]

    shipping = asyncio.run(service.search("frete em Campo Grande", 5))
    assert "5.1" in [result["section_id"] for result in shipping]


def test_search_returns_sources(conn):
    service = PolicyService(conn, FakeEmbeddingClient(16))
    results = asyncio.run(service.search("troca por defeito", 3))
    assert results
    assert all(result["sources"] for result in results)
    assert all(result["text"] for result in results)
