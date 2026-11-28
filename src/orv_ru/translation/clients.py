"""LLM client utilities and official `google-genai` SDK adapter."""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any

from orv_ru.translation.exceptions import LLMClientError

_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL | re.IGNORECASE)
_TRANSIENT_KEYWORDS = ("429", "503", "rate limit", "resource_exhausted", "unavailable", "timeout")


def extract_json_object(raw_text: str) -> dict[str, Any]:
    """Parse a JSON dictionary from raw model text, stripping optional code fences."""
    cleaned = raw_text.strip()
    fence_match = _CODE_FENCE_RE.match(cleaned)
    if fence_match:
        cleaned = fence_match.group(1).strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end <= start:
            raise LLMClientError("Model response does not contain a valid JSON object.") from exc
        try:
            parsed = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as inner_exc:
            raise LLMClientError(f"Failed to parse JSON from model response: {inner_exc}") from inner_exc

    if not isinstance(parsed, dict):
        raise LLMClientError(f"Expected JSON object at top level, got {type(parsed).__name__}.")
    return parsed


class GeminiLLMClient:
    """Current-SDK (`google-genai`) adapter implementing `LLMClient` with lazy import."""

    def __init__(
        self,
        *,
        model: str = "gemini-2.5-pro",
        api_key: str | None = None,
        temperature: float = 0.3,
        max_retries: int = 3,
        base_backoff_seconds: float = 2.0,
    ) -> None:
        self._model = model
        self._api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self._temperature = temperature
        self._max_retries = max_retries
        self._base_backoff_seconds = base_backoff_seconds
        self._client: Any = None
        self._types: Any = None

    def _ensure_client(self) -> None:
        if self._client is not None:
            return
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise LLMClientError(
                "Optional dependency 'google-genai' is not installed. "
                "Install it with `pip install google-genai` (or `pip install -e .[gemini]`)."
            ) from exc

        if not self._api_key:
            raise LLMClientError(
                "Missing Gemini API key. Set GEMINI_API_KEY (or GOOGLE_API_KEY) environment variable."
            )

        self._client = genai.Client(api_key=self._api_key)
        self._types = types

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        """Generate structured JSON text using `client.models.generate_content`."""
        self._ensure_client()
        config = self._types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            temperature=self._temperature,
        )

        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.models.generate_content(
                    model=self._model,
                    contents=user_prompt,
                    config=config,
                )
                text = getattr(response, "text", None)
                if not isinstance(text, str) or not text.strip():
                    raise LLMClientError("Gemini returned an empty response.")
                return text
            except LLMClientError:
                raise
            except Exception as exc:
                last_exc = exc
                msg = str(exc).lower()
                is_transient = any(kw in msg for kw in _TRANSIENT_KEYWORDS)
                if not is_transient or attempt >= self._max_retries:
                    break
                time.sleep(self._base_backoff_seconds * (2**attempt))

        raise LLMClientError(f"Gemini API request failed: {last_exc}") from last_exc


class OpenAICompatibleLLMClient:
    """OpenAI-compatible `LLMClient` adapter (ZCode / GLM-5.3-Flash / GLM-5.4 / DeepSeek / Ollama)."""

    def __init__(
        self,
        *,
        model: str = "GLM-5.3-Flash",
        base_url: str | None = None,
        api_key: str | None = None,
        api_key_env: str = "OPENAI_API_KEY",
        temperature: float = 0.3,
        reasoning_effort: str | None = None,
        max_retries: int = 3,
        base_backoff_seconds: float = 2.0,
        timeout: float = 180.0,
    ) -> None:
        self._model = model
        self._base_url = base_url or os.getenv("OPENAI_BASE_URL")
        self._api_key = api_key or os.getenv(api_key_env)
        self._api_key_env = api_key_env
        self._temperature = temperature
        self._reasoning_effort = reasoning_effort
        self._max_retries = max_retries
        self._base_backoff_seconds = base_backoff_seconds
        self._timeout = timeout
        self._client: Any = None

    def _ensure_client(self) -> None:
        if self._client is not None:
            return
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise LLMClientError(
                "Optional dependency 'openai' is not installed. "
                "Install it with `pip install openai` (or `pip install -e .[openai]`)."
            ) from exc

        if not self._api_key:
            raise LLMClientError(
                f"Missing API key. Set {self._api_key_env} environment variable."
            )

        self._client = OpenAI(
            api_key=self._api_key,
            base_url=self._base_url,
            timeout=self._timeout,
        )

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        """Generate structured JSON text using Chat Completions API."""
        self._ensure_client()
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self._temperature,
            "response_format": {"type": "json_object"},
        }
        if self._reasoning_effort:
            kwargs["reasoning_effort"] = self._reasoning_effort

        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.chat.completions.create(**kwargs)
                choices = getattr(response, "choices", None) or []
                content = getattr(choices[0].message, "content", None) if choices else None
                if not isinstance(content, str) or not content.strip():
                    raise LLMClientError("OpenAI-compatible endpoint returned an empty response.")
                return content
            except LLMClientError:
                raise
            except Exception as exc:
                last_exc = exc
                msg = str(exc).lower()
                if "response_format" in msg and "response_format" in kwargs:
                    kwargs.pop("response_format", None)
                    continue
                if "reasoning_effort" in msg and "reasoning_effort" in kwargs:
                    kwargs.pop("reasoning_effort", None)
                    continue
                is_transient = any(kw in msg for kw in _TRANSIENT_KEYWORDS)
                if not is_transient or attempt >= self._max_retries:
                    break
                time.sleep(self._base_backoff_seconds * (2**attempt))

        raise LLMClientError(f"OpenAI-compatible API request failed: {last_exc}") from last_exc
