from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


URL_PATTERN = re.compile(r"https?://[^\s\]\)\}\"']+", re.IGNORECASE)
JSON_BLOCK_PATTERN = re.compile(r"\{[\s\S]*\}")
KV_PATTERN = re.compile(r"^\s*([A-Za-z_ ][A-Za-z0-9_ ]{1,40})\s*:\s*(.+?)\s*$")


@dataclass
class ParsedPrompt:
    target_url: str | None
    test_data: dict[str, Any]


class PromptParser:
    _alias_map = {
        "url": "url",
        "target url": "url",
        "website": "url",
        "username": "username",
        "user name": "username",
        "email": "email",
        "password": "password",
        "passwaord": "password",
        "passwrod": "password",
    }

    def parse(self, instruction: str) -> ParsedPrompt:
        url_match = URL_PATTERN.search(instruction)
        target_url = url_match.group(0) if url_match else None

        parsed_data: dict[str, Any] = {}
        json_match = JSON_BLOCK_PATTERN.search(instruction)
        if json_match:
            candidate = json_match.group(0)
            try:
                value = json.loads(candidate)
                if isinstance(value, dict):
                    parsed_data = value
            except json.JSONDecodeError:
                parsed_data = {}

        for line in instruction.splitlines():
            kv_match = KV_PATTERN.match(line)
            if not kv_match:
                continue
            key_raw = kv_match.group(1).strip().lower()
            value = kv_match.group(2).strip()
            if key_raw in {"http", "https"}:
                continue
            canonical = self._alias_map.get(key_raw, key_raw.replace(" ", "_"))
            parsed_data[canonical] = value

        if not target_url:
            target_url = parsed_data.get("url")

        has_creds = any(parsed_data.get(k) for k in ("username", "email")) and bool(parsed_data.get("password"))
        asks_matrix = ("valid" in instruction.lower()) or ("invalid" in instruction.lower())
        if has_creds and asks_matrix:
            parsed_data["login_case_matrix"] = True

        return ParsedPrompt(target_url=target_url, test_data=parsed_data)
