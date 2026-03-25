from __future__ import annotations

import math
import re


class EmbeddingClient:
    """Deterministic lightweight embedding substitute.

    Keeps module pluggable until real embeddings are configured.
    """

    _token_re = re.compile(r"[a-zA-Z0-9_]+")

    def embed(self, text: str) -> dict[str, float]:
        tokens = [t.lower() for t in self._token_re.findall(text)]
        if not tokens:
            return {}
        counts: dict[str, float] = {}
        for token in tokens:
            counts[token] = counts.get(token, 0.0) + 1.0
        norm = math.sqrt(sum(v * v for v in counts.values()))
        if norm == 0:
            return counts
        return {k: v / norm for k, v in counts.items()}
