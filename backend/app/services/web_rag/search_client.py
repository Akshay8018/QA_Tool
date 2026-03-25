from __future__ import annotations

import httpx

from app.services.web_rag.models import SearchResult


class WebSearchClient:
    """Lightweight web search client using DuckDuckGo instant answer API."""

    async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        params = {"q": query, "format": "json", "no_redirect": "1", "no_html": "1"}
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get("https://api.duckduckgo.com/", params=params)
            response.raise_for_status()
            data = response.json()

        results: list[SearchResult] = []
        related = data.get("RelatedTopics", [])
        for item in related:
            if not isinstance(item, dict):
                continue
            if "Topics" in item and isinstance(item["Topics"], list):
                for nested in item["Topics"]:
                    if isinstance(nested, dict):
                        text = str(nested.get("Text", "")).strip()
                        url = str(nested.get("FirstURL", "")).strip()
                        if text and url:
                            results.append(SearchResult(title=text[:80], url=url, snippet=text))
            else:
                text = str(item.get("Text", "")).strip()
                url = str(item.get("FirstURL", "")).strip()
                if text and url:
                    results.append(SearchResult(title=text[:80], url=url, snippet=text))
            if len(results) >= max_results:
                break
        return results[:max_results]
