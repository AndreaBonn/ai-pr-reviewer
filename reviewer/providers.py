"""LLM provider implementations (Strategy pattern)."""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod

import requests

from reviewer.exceptions import ProviderError

log = logging.getLogger("ai-pr-reviewer")

LLM_MAX_RETRIES = 2
LLM_RETRY_BASE_DELAY = 5


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class LLMAPIError(Exception):
    """Safe error that never leaks response body or API keys in its repr."""

    def __init__(self, status_code: int, provider: str) -> None:
        self.status_code = status_code
        self.provider = provider
        super().__init__(f"{provider} API returned HTTP {status_code}")


class LLMParseError(Exception):
    """Raised when the LLM response has an unexpected structure."""

    def __init__(self, provider: str) -> None:
        self.provider = provider
        super().__init__(f"{provider} returned an unexpected response structure")


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------


class LLMProvider(ABC):
    """Base class for LLM API providers."""

    MODEL: str = ""

    def __init__(self, api_key: str, model: str = "") -> None:
        self._api_key = api_key
        self._model_override = model

    @property
    def model(self) -> str:
        """Return the model override if set, otherwise the class default."""
        return self._model_override or self.MODEL

    @abstractmethod
    def call(self, system: str, user: str) -> str:
        """Send a prompt to the LLM and return the response text."""

    def _post_json(
        self,
        url: str,
        *,
        headers: dict[str, str],
        payload: dict,
        timeout: int = 120,
    ) -> dict:
        resp = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=timeout,
        )
        if not resp.ok:
            raise LLMAPIError(resp.status_code, type(self).__name__)
        return resp.json()

    def _extract(self, data: dict, *keys: str | int) -> str:
        """Traverse nested dict/list by keys, raise LLMParseError on miss."""
        current = data
        for key in keys:
            try:
                current = current[key]
            except (KeyError, IndexError, TypeError):
                raise LLMParseError(type(self).__name__) from None
        if not isinstance(current, str):
            raise LLMParseError(type(self).__name__)
        return current


# ---------------------------------------------------------------------------
# Concrete providers
# ---------------------------------------------------------------------------


class GroqProvider(LLMProvider):
    """Groq — OpenAI-compatible endpoint with Llama models."""

    URL = "https://api.groq.com/openai/v1/chat/completions"
    MODEL = "llama-3.3-70b-versatile"

    def call(self, system: str, user: str) -> str:
        data = self._post_json(
            self.URL,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            payload={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "max_tokens": 2000,
                "temperature": 0.3,
            },
        )
        return self._extract(data, "choices", 0, "message", "content")


class GeminiProvider(LLMProvider):
    """Google Gemini — REST API with native systemInstruction support."""

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
    MODEL = "gemini-2.0-flash"

    def call(self, system: str, user: str) -> str:
        url = f"{self.BASE_URL}/{self.model}:generateContent"
        data = self._post_json(
            url,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self._api_key,
            },
            payload={
                "systemInstruction": {
                    "parts": [{"text": system}],
                },
                "contents": [{"parts": [{"text": user}]}],
                "generationConfig": {
                    "maxOutputTokens": 2000,
                    "temperature": 0.3,
                },
            },
        )
        return self._extract(
            data,
            "candidates",
            0,
            "content",
            "parts",
            0,
            "text",
        )


class AnthropicProvider(LLMProvider):
    """Anthropic Claude — uses x-api-key header (not Bearer)."""

    URL = "https://api.anthropic.com/v1/messages"
    MODEL = "claude-sonnet-4-5-20250514"

    def call(self, system: str, user: str) -> str:
        data = self._post_json(
            self.URL,
            headers={
                "x-api-key": self._api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            payload={
                "model": self.model,
                "max_tokens": 2000,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
        )
        return self._extract(data, "content", 0, "text")


class OpenAIProvider(LLMProvider):
    """OpenAI — standard chat completions endpoint."""

    URL = "https://api.openai.com/v1/chat/completions"
    MODEL = "gpt-4o-mini"

    def call(self, system: str, user: str) -> str:
        data = self._post_json(
            self.URL,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            payload={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "max_tokens": 2000,
                "temperature": 0.3,
            },
        )
        return self._extract(data, "choices", 0, "message", "content")


# ---------------------------------------------------------------------------
# Provider registry & retry logic
# ---------------------------------------------------------------------------

_PROVIDERS: dict[str, type[LLMProvider]] = {
    "groq": GroqProvider,
    "gemini": GeminiProvider,
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
}


def get_provider(name: str, api_key: str, model: str = "") -> LLMProvider:
    cls = _PROVIDERS.get(name)
    if cls is None:
        supported = ", ".join(sorted(_PROVIDERS))
        raise ProviderError(f"Unknown LLM provider: '{name}'. Supported: {supported}")
    return cls(api_key=api_key, model=model)


def call_llm_with_retry(
    provider: LLMProvider,
    system: str,
    user: str,
) -> str:
    """Call the LLM provider with exponential backoff retry."""
    last_error: Exception | None = None
    for attempt in range(1, LLM_MAX_RETRIES + 1):
        try:
            return provider.call(system=system, user=user)
        except (requests.RequestException, LLMAPIError, LLMParseError) as exc:
            last_error = exc
            if attempt < LLM_MAX_RETRIES:
                delay = LLM_RETRY_BASE_DELAY * attempt
                log.warning(
                    "LLM call failed (attempt %d/%d): %s — retrying in %ds",
                    attempt,
                    LLM_MAX_RETRIES,
                    exc,
                    delay,
                )
                time.sleep(delay)

    raise ProviderError(f"LLM call failed after {LLM_MAX_RETRIES} attempts: {last_error}")
