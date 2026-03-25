from __future__ import annotations

import logging
from dataclasses import asdict

from app.core.config import settings
from app.services.web_rag.cache import TTLCache
from app.services.web_rag.chunker import TextChunker
from app.services.web_rag.cleaner import TextCleaner
from app.services.web_rag.embedding_client import EmbeddingClient
from app.services.web_rag.fetcher import WebContentFetcher
from app.services.web_rag.models import RAGChunk, SearchResult
from app.services.web_rag.search_client import WebSearchClient
from app.services.web_rag.vector_store import InMemoryVectorStore

logger = logging.getLogger(__name__)


class WebRAGService:
    def __init__(
        self,
        search_client: WebSearchClient | None = None,
        fetcher: WebContentFetcher | None = None,
        cleaner: TextCleaner | None = None,
        chunker: TextChunker | None = None,
        embedding_client: EmbeddingClient | None = None,
        vector_store: InMemoryVectorStore | None = None,
        cache: TTLCache[dict] | None = None,
    ) -> None:
        self.search_client = search_client or WebSearchClient()
        self.fetcher = fetcher or WebContentFetcher()
        self.cleaner = cleaner or TextCleaner()
        self.chunker = chunker or TextChunker(
            chunk_size=settings.web_rag_chunk_size,
            overlap=settings.web_rag_chunk_overlap,
        )
        self.embedding_client = embedding_client or EmbeddingClient()
        self.vector_store = vector_store or InMemoryVectorStore()
        self.cache = cache or TTLCache(ttl_seconds=settings.web_rag_cache_ttl_seconds)

    async def retrieve(self, query: str, top_k: int = 5) -> dict:
        cache_key = f"rag:{query}:{top_k}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            search_results = await self.search_client.search(query, max_results=settings.web_rag_search_max_results)
            docs_indexed = await self._index_results(search_results)
            query_vector = self.embedding_client.embed(query)
            chunks = self.vector_store.search(query_vector, top_k=top_k)
            payload = {
                "query": query,
                "sources": [asdict(r) for r in search_results],
                "chunks": [asdict(c) for c in chunks],
                "indexed_documents": docs_indexed,
            }
            self.cache.set(cache_key, payload)
            return payload
        except Exception as exc:
            logger.warning("WebRAG retrieve failed query=%s error=%s", query, exc)
            return {"query": query, "sources": [], "chunks": [], "indexed_documents": 0}

    async def _index_results(self, search_results: list[SearchResult]) -> int:
        indexed = 0
        for result in search_results:
            try:
                doc = await self.fetcher.fetch(result.url)
                clean_text = self.cleaner.clean(doc.text)
                for chunk_text in self.chunker.chunk(clean_text):
                    vector = self.embedding_client.embed(chunk_text)
                    chunk = RAGChunk(source_url=result.url, text=chunk_text)
                    self.vector_store.add(chunk, vector)
                indexed += 1
            except Exception as exc:
                logger.debug("WebRAG skip source url=%s error=%s", result.url, exc)
        return indexed
