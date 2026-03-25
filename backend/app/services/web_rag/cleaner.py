from __future__ import annotations

import re


class TextCleaner:
    _script_style = re.compile(r"(?is)<(script|style).*?>.*?</\1>")
    _tags = re.compile(r"(?is)<[^>]+>")
    _spaces = re.compile(r"\s+")

    def clean(self, html_or_text: str) -> str:
        text = self._script_style.sub(" ", html_or_text)
        text = self._tags.sub(" ", text)
        text = text.replace("&nbsp;", " ").replace("&amp;", "&")
        text = self._spaces.sub(" ", text).strip()
        return text
