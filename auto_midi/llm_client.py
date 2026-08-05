"""Small OpenAI-compatible JSON client for the internal model gateway."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class LLMError(RuntimeError):
    """Raised when the model gateway cannot return valid JSON."""


class OpenAICompatibleClient:
    def __init__(self, base_url: str, api_key: str, model: str, timeout: float = 90.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def complete_json(self, system_prompt: str, user_prompt: str, seed: int) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.25,
            "seed": seed,
            "response_format": {"type": "json_object"},
        }
        request = Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw_response = response.read().decode("utf-8")
        except HTTPError as exc:
            raise LLMError(f"LLM gateway HTTP {exc.code}") from exc
        except URLError as exc:
            raise LLMError(f"LLM gateway unavailable: {exc.reason}") from exc
        except TimeoutError as exc:
            raise LLMError("LLM gateway timed out") from exc

        try:
            envelope = json.loads(raw_response)
            content = envelope["choices"][0]["message"]["content"]
            if isinstance(content, list):
                content = "".join(str(item.get("text", "")) for item in content if isinstance(item, dict))
            if not isinstance(content, str):
                raise TypeError("message content is not text")
            return _parse_json_content(content)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError, ValueError) as exc:
            raise LLMError("LLM gateway returned an invalid JSON response") from exc


def _parse_json_content(content: str) -> dict[str, Any]:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    payload = json.loads(cleaned)
    if not isinstance(payload, dict):
        raise ValueError("LLM JSON root must be an object")
    return payload
