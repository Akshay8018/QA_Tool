from __future__ import annotations

from app.services.web_rag.models import RAGChunk


class InMemoryVectorStore:
    def __init__(self) -> None:
        self._items: list[tuple[RAGChunk, dict[str, float]]] = []

    def add(self, chunk: RAGChunk, vector: dict[str, float]) -> None:
        self._items.append((chunk, vector))

    def search(self, query_vector: dict[str, float], top_k: int = 5) -> list[RAGChunk]:
        scored: list[RAGChunk] = []
        for chunk, vector in self._items:
            score = 0.0
            for token, qv in query_vector.items():
                score += qv * vector.get(token, 0.0)
            scored.append(RAGChunk(source_url=chunk.source_url, text=chunk.text, score=score))
        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:top_k]
