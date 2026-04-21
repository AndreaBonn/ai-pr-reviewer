"""Tests for reviewer.providers module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from reviewer.exceptions import ProviderError
from reviewer.providers import (
    AnthropicProvider,
    GeminiProvider,
    GroqProvider,
    LLMAPIError,
    LLMParseError,
    OpenAIProvider,
    call_llm_with_retry,
    get_provider,
)


class TestGetProvider:
    def test_returns_groq_provider(self) -> None:
        provider = get_provider(name="groq", api_key="k")
        assert isinstance(provider, GroqProvider)

    def test_returns_gemini_provider(self) -> None:
        provider = get_provider(name="gemini", api_key="k")
        assert isinstance(provider, GeminiProvider)

    def test_returns_anthropic_provider(self) -> None:
        provider = get_provider(name="anthropic", api_key="k")
        assert isinstance(provider, AnthropicProvider)

    def test_returns_openai_provider(self) -> None:
        provider = get_provider(name="openai", api_key="k")
        assert isinstance(provider, OpenAIProvider)

    def test_unknown_provider_raises_provider_error(self) -> None:
        with pytest.raises(ProviderError, match="unknown"):
            get_provider(name="unknown", api_key="k")

    def test_model_override_applied(self) -> None:
        provider = get_provider(name="groq", api_key="k", model="llama-3.1-8b")
        assert provider.model == "llama-3.1-8b"

    def test_default_model_when_no_override(self) -> None:
        provider = get_provider(name="groq", api_key="k")
        assert provider.model == "llama-3.3-70b-versatile"


class TestLLMAPIError:
    def test_message_contains_status_and_provider(self) -> None:
        err = LLMAPIError(status_code=401, provider="GroqProvider")

        assert "401" in str(err)
        assert "GroqProvider" in str(err)

    def test_does_not_leak_api_key(self) -> None:
        err = LLMAPIError(status_code=403, provider="TestProvider")

        assert "sk-" not in str(err)
        assert "key" not in str(err).lower()


class TestGroqProviderCall:
    @patch("reviewer.providers.requests.post")
    def test_happy_path_returns_content(self, mock_post: MagicMock) -> None:
        mock_post.return_value = MagicMock(
            ok=True,
            json=lambda: {
                "choices": [{"message": {"content": "Review text"}}],
            },
        )

        provider = GroqProvider(api_key="test-key")
        result = provider.call(system="sys", user="usr")

        assert result == "Review text"
        call_kwargs = mock_post.call_args
        assert "Bearer test-key" in str(call_kwargs)

    @patch("reviewer.providers.requests.post")
    def test_http_error_raises_llm_api_error(self, mock_post: MagicMock) -> None:
        mock_post.return_value = MagicMock(ok=False, status_code=500)

        provider = GroqProvider(api_key="test-key")

        with pytest.raises(LLMAPIError) as exc_info:
            provider.call(system="sys", user="usr")

        assert exc_info.value.status_code == 500


class TestGroqProviderParseError:
    @patch("reviewer.providers.requests.post")
    def test_malformed_response_raises_parse_error(self, mock_post: MagicMock) -> None:
        mock_post.return_value = MagicMock(
            ok=True,
            json=lambda: {"choices": []},
        )

        provider = GroqProvider(api_key="k")

        with pytest.raises(LLMParseError):
            provider.call(system="sys", user="usr")


class TestGeminiProviderCall:
    @patch("reviewer.providers.requests.post")
    def test_uses_header_not_url_for_api_key(self, mock_post: MagicMock) -> None:
        mock_post.return_value = MagicMock(
            ok=True,
            json=lambda: {
                "candidates": [{"content": {"parts": [{"text": "OK"}]}}],
            },
        )

        provider = GeminiProvider(api_key="secret-key")
        provider.call(system="sys", user="usr")

        call_args = mock_post.call_args
        url = call_args[0][0]
        headers = call_args[1]["headers"]

        assert "secret-key" not in url
        assert headers["x-goog-api-key"] == "secret-key"

    @patch("reviewer.providers.requests.post")
    def test_uses_native_system_instruction(self, mock_post: MagicMock) -> None:
        mock_post.return_value = MagicMock(
            ok=True,
            json=lambda: {
                "candidates": [{"content": {"parts": [{"text": "OK"}]}}],
            },
        )

        provider = GeminiProvider(api_key="k")
        provider.call(system="Be helpful", user="Review this")

        payload = mock_post.call_args[1]["json"]
        assert "systemInstruction" in payload
        assert payload["systemInstruction"]["parts"][0]["text"] == "Be helpful"
        assert payload["contents"][0]["parts"][0]["text"] == "Review this"


class TestAnthropicProviderCall:
    @patch("reviewer.providers.requests.post")
    def test_uses_x_api_key_header(self, mock_post: MagicMock) -> None:
        mock_post.return_value = MagicMock(
            ok=True,
            json=lambda: {
                "content": [{"text": "Claude review"}],
            },
        )

        provider = AnthropicProvider(api_key="ant-key")
        result = provider.call(system="sys", user="usr")

        assert result == "Claude review"
        headers = mock_post.call_args[1]["headers"]
        assert headers["x-api-key"] == "ant-key"
        assert "anthropic-version" in headers


class TestCallLlmWithRetry:
    def test_returns_on_first_success(self) -> None:
        provider = MagicMock()
        provider.call.return_value = "Review"

        result = call_llm_with_retry(provider, system="s", user="u")

        assert result == "Review"
        assert provider.call.call_count == 1

    @patch("reviewer.providers.time.sleep")
    def test_retries_on_failure_then_succeeds(
        self,
        mock_sleep: MagicMock,
    ) -> None:
        provider = MagicMock()
        provider.call.side_effect = [
            requests.ConnectionError("timeout"),
            "Review after retry",
        ]

        result = call_llm_with_retry(provider, system="s", user="u")

        assert result == "Review after retry"
        assert provider.call.call_count == 2
        mock_sleep.assert_called_once()

    @patch("reviewer.providers.time.sleep")
    def test_raises_provider_error_after_max_retries(self, mock_sleep: MagicMock) -> None:
        provider = MagicMock()
        provider.call.side_effect = LLMAPIError(
            status_code=500,
            provider="Test",
        )

        with pytest.raises(ProviderError, match="failed after"):
            call_llm_with_retry(provider, system="s", user="u")

    @patch("reviewer.providers.time.sleep")
    def test_retries_on_parse_error(self, mock_sleep: MagicMock) -> None:
        provider = MagicMock()
        provider.call.side_effect = [
            LLMParseError(provider="Test"),
            "Review OK",
        ]

        result = call_llm_with_retry(provider, system="s", user="u")

        assert result == "Review OK"
