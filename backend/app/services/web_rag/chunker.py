from __future__ import annotations


class TextChunker:
    def __init__(self, chunk_size: int = 700, overlap: int = 120) -> None:
        self.chunk_size = max(100, chunk_size)
        self.overlap = max(0, min(overlap, self.chunk_size // 2))

    def chunk(self, text: str) -> list[str]:
        if not text.strip():
            return []
        chunks: list[str] = []
        start = 0
        size = len(text)
        while start < size:
            end = min(size, start + self.chunk_size)
            chunks.append(text[start:end].strip())
            if end >= size:
                break
            start = max(0, end - self.overlap)
        return [c for c in chunks if c]
