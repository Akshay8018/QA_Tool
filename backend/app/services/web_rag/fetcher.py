from __future__ import annotations

import httpx

from app.services.web_rag.models import RAGDocument


class WebContentFetcher:
    async def fetch(self, url: str) -> RAGDocument:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            return RAGDocument(source_url=url, text=response.text)
