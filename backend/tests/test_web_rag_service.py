from __future__ import annotations

import unittest

from app.services.web_rag.cache import TTLCache
from app.services.web_rag.chunker import TextChunker
from app.services.web_rag.cleaner import TextCleaner
from app.services.web_rag.models import RAGDocument, SearchResult
from app.services.web_rag.service import WebRAGService


class _SearchClientStub:
    async def search(self, query: str, max_results: int = 5):
        _ = query
        _ = max_results
        return [SearchResult(title="Doc", url="https://example.com/doc", snippet="qa info")]


class _FetcherStub:
    async def fetch(self, url: str):
        _ = url
        return RAGDocument(
            source_url="https://example.com/doc",
            text="<html><body><h1>QA Testing</h1><script>ignored()</script><p>Use boundary value analysis.</p></body></html>",
        )


class WebRAGServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_cleaner_removes_html_and_script(self) -> None:
        cleaner = TextCleaner()
        text = cleaner.clean("<div>Hello</div><script>alert(1)</script><p>World</p>")
        self.assertIn("Hello", text)
        self.assertIn("World", text)
        self.assertNotIn("alert(1)", text)

    async def test_chunker_splits_text(self) -> None:
        chunker = TextChunker(chunk_size=120, overlap=20)
        chunks = chunker.chunk("x" * 260)
        self.assertGreaterEqual(len(chunks), 2)

    async def test_service_retrieves_and_caches(self) -> None:
        cache = TTLCache(ttl_seconds=60)
        service = WebRAGService(
            search_client=_SearchClientStub(),
            fetcher=_FetcherStub(),
            cache=cache,
        )
        first = await service.retrieve("qa login", top_k=3)
        self.assertGreaterEqual(first["indexed_documents"], 1)
        self.assertTrue(first["chunks"])
        second = await service.retrieve("qa login", top_k=3)
        self.assertEqual(first["chunks"], second["chunks"])


if __name__ == "__main__":
    unittest.main()
