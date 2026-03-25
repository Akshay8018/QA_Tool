from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str


@dataclass
class RAGDocument:
    source_url: str
    text: str


@dataclass
class RAGChunk:
    source_url: str
    text: str
    score: float = 0.0
