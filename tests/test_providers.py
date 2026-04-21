"""Tests for reviewer.providers module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from reviewer.exceptions import LLMAPIError, LLMParseError, ProviderError
from reviewer.providers import (
    AnthropicProvider,
    GeminiProvider,
    GroqProvider,
    OpenAIProvider,
    call_llm_with_fallback,
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

    def test_empty_model_override_falls_back_to_class_default(self) -> None:
        provider = get_provider(name="groq", api_key="k", model="")
        assert provider.model == GroqProvider.MODEL


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


class TestOpenAIProviderCall:
    @patch("reviewer.providers.requests.post")
    def test_happy_path_returns_content(self, mock_post: MagicMock) -> None:
        mock_post.return_value = MagicMock(
            ok=True,
            json=lambda: {
                "choices": [{"message": {"content": "OpenAI review"}}],
            },
        )

        provider = OpenAIProvider(api_key="sk-test")
        result = provider.call(system="sys", user="usr")

        assert result == "OpenAI review"
        headers = mock_post.call_args[1]["headers"]
        assert headers["Authorization"] == "Bearer sk-test"

    @patch("reviewer.providers.requests.post")
    def test_http_error_raises_llm_api_error(self, mock_post: MagicMock) -> None:
        mock_post.return_value = MagicMock(ok=False, status_code=429)

        provider = OpenAIProvider(api_key="sk-test")

        with pytest.raises(LLMAPIError) as exc_info:
            provider.call(system="sys", user="usr")

        assert exc_info.value.status_code == 429


class TestPostJsonNonJsonResponse:
    @patch("reviewer.providers.requests.post")
    def test_non_json_response_raises_parse_error(self, mock_post: MagicMock) -> None:
        mock_resp = MagicMock(ok=True)
        mock_resp.json.side_effect = requests.exceptions.JSONDecodeError("", "", 0)
        mock_post.return_value = mock_resp

        provider = GroqProvider(api_key="k")

        with pytest.raises(LLMParseError):
            provider.call(system="s", user="u")


class TestPostJsonUnicodeError:
    @patch("reviewer.providers.requests.post")
    def test_unicode_decode_error_raises_parse_error(self, mock_post: MagicMock) -> None:
        mock_resp = MagicMock(ok=True)
        mock_resp.json.side_effect = UnicodeDecodeError("utf-8", b"", 0, 1, "invalid")
        mock_post.return_value = mock_resp

        provider = GroqProvider(api_key="k")

        with pytest.raises(LLMParseError):
            provider.call(system="s", user="u")

    @patch("reviewer.providers.requests.post")
    def test_value_error_raises_parse_error(self, mock_post: MagicMock) -> None:
        mock_resp = MagicMock(ok=True)
        mock_resp.json.side_effect = ValueError("No JSON object")
        mock_post.return_value = mock_resp

        provider = GroqProvider(api_key="k")

        with pytest.raises(LLMParseError):
            provider.call(system="s", user="u")


class TestGeminiProviderParseError:
    @patch("reviewer.providers.requests.post")
    def test_empty_candidates_raises_parse_error(self, mock_post: MagicMock) -> None:
        mock_post.return_value = MagicMock(
            ok=True,
            json=lambda: {"candidates": []},
        )

        with pytest.raises(LLMParseError):
            GeminiProvider(api_key="k").call("s", "u")

    @patch("reviewer.providers.requests.post")
    def test_missing_text_key_raises_parse_error(self, mock_post: MagicMock) -> None:
        mock_post.return_value = MagicMock(
            ok=True,
            json=lambda: {"candidates": [{"content": {"parts": [{"no_text": "x"}]}}]},
        )

        with pytest.raises(LLMParseError):
            GeminiProvider(api_key="k").call("s", "u")


class TestAnthropicProviderParseError:
    @patch("reviewer.providers.requests.post")
    def test_empty_content_raises_parse_error(self, mock_post: MagicMock) -> None:
        mock_post.return_value = MagicMock(
            ok=True,
            json=lambda: {"content": []},
        )

        with pytest.raises(LLMParseError):
            AnthropicProvider(api_key="k").call("s", "u")


class TestOpenAIProviderParseError:
    @patch("reviewer.providers.requests.post")
    def test_empty_choices_raises_parse_error(self, mock_post: MagicMock) -> None:
        mock_post.return_value = MagicMock(
            ok=True,
            json=lambda: {"choices": []},
        )

        with pytest.raises(LLMParseError):
            OpenAIProvider(api_key="k").call("s", "u")


class TestExtractNonStringValue:
    @patch("reviewer.providers.requests.post")
    def test_none_content_raises_parse_error(self, mock_post: MagicMock) -> None:
        mock_post.return_value = MagicMock(
            ok=True,
            json=lambda: {"choices": [{"message": {"content": None}}]},
        )

        provider = GroqProvider(api_key="k")

        with pytest.raises(LLMParseError):
            provider.call(system="s", user="u")

    @patch("reviewer.providers.requests.post")
    def test_integer_content_raises_parse_error(self, mock_post: MagicMock) -> None:
        mock_post.return_value = MagicMock(
            ok=True,
            json=lambda: {"choices": [{"message": {"content": 42}}]},
        )

        provider = GroqProvider(api_key="k")

        with pytest.raises(LLMParseError):
            provider.call(system="s", user="u")


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
    def test_retry_delay_uses_correct_value(self, mock_sleep: MagicMock) -> None:
        provider = MagicMock()
        provider.call.side_effect = [
            LLMAPIError(status_code=500, provider="T"),
            "Review OK",
        ]

        call_llm_with_retry(provider, system="s", user="u")

        mock_sleep.assert_called_once_with(2)

    @patch("reviewer.providers.time.sleep")
    def test_exhausts_exactly_max_attempts(self, mock_sleep: MagicMock) -> None:
        from reviewer.providers import LLM_MAX_ATTEMPTS

        provider = MagicMock()
        provider.call.side_effect = LLMAPIError(status_code=503, provider="T")

        with pytest.raises(ProviderError):
            call_llm_with_retry(provider, system="s", user="u")

        assert provider.call.call_count == LLM_MAX_ATTEMPTS

    @patch("reviewer.providers.time.sleep")
    def test_raises_provider_error_on_network_error(self, mock_sleep: MagicMock) -> None:
        provider = MagicMock()
        provider.call.side_effect = requests.ConnectionError("network down")

        with pytest.raises(ProviderError, match="failed after"):
            call_llm_with_retry(provider, system="s", user="u")

    @patch("reviewer.providers.time.sleep")
    def test_exponential_backoff_delays(self, mock_sleep: MagicMock) -> None:
        provider = MagicMock()
        provider.call.side_effect = [
            LLMAPIError(status_code=500, provider="T"),
            LLMAPIError(status_code=500, provider="T"),
            "Review OK",
        ]

        call_llm_with_retry(provider, system="s", user="u")

        delays = [c.args[0] for c in mock_sleep.call_args_list]
        assert delays == [2, 4]

    @patch("reviewer.providers.time.sleep")
    def test_retries_on_parse_error(self, mock_sleep: MagicMock) -> None:
        provider = MagicMock()
        provider.call.side_effect = [
            LLMParseError(provider="Test"),
            "Review OK",
        ]

        result = call_llm_with_retry(provider, system="s", user="u")

        assert result == "Review OK"


class TestCallLlmWithFallback:
    def test_single_provider_succeeds(self) -> None:
        provider = MagicMock()
        provider.call.return_value = "Review"

        result = call_llm_with_fallback([(provider, "sys")], user="u")

        assert result == "Review"

    def test_empty_chain_raises_provider_error(self) -> None:
        with pytest.raises(ProviderError, match="No LLM providers"):
            call_llm_with_fallback([], user="u")

    @patch("reviewer.providers.time.sleep")
    def test_falls_back_to_second_provider(self, mock_sleep: MagicMock) -> None:
        failing = MagicMock()
        failing.call.side_effect = LLMAPIError(status_code=429, provider="Groq")

        succeeding = MagicMock()
        succeeding.call.return_value = "Fallback review"

        result = call_llm_with_fallback(
            [(failing, "sys1"), (succeeding, "sys2")],
            user="u",
        )

        assert result == "Fallback review"
        succeeding.call.assert_called_once_with(system="sys2", user="u")

    @patch("reviewer.providers.time.sleep")
    def test_all_providers_fail_raises_provider_error(self, mock_sleep: MagicMock) -> None:
        p1 = MagicMock()
        p1.call.side_effect = LLMAPIError(status_code=429, provider="P1")
        p2 = MagicMock()
        p2.call.side_effect = LLMAPIError(status_code=500, provider="P2")

        with pytest.raises(ProviderError, match="All 2 provider"):
            call_llm_with_fallback(
                [(p1, "s1"), (p2, "s2")],
                user="u",
            )

    def test_first_provider_succeeds_skips_second(self) -> None:
        p1 = MagicMock()
        p1.call.return_value = "First"
        p2 = MagicMock()

        result = call_llm_with_fallback(
            [(p1, "s1"), (p2, "s2")],
            user="u",
        )

        assert result == "First"
        p2.call.assert_not_called()

    @patch("reviewer.providers.time.sleep")
    def test_uses_correct_system_prompt_per_provider(self, mock_sleep: MagicMock) -> None:
        p1 = MagicMock()
        p1.call.side_effect = LLMAPIError(status_code=429, provider="P1")
        p2 = MagicMock()
        p2.call.return_value = "OK"

        call_llm_with_fallback(
            [(p1, "groq-prompt"), (p2, "gemini-prompt")],
            user="u",
        )

        p1.call.assert_called_with(system="groq-prompt", user="u")
        p2.call.assert_called_with(system="gemini-prompt", user="u")

    @patch("reviewer.providers.time.sleep")
    def test_three_providers_third_succeeds(self, mock_sleep: MagicMock) -> None:
        p1 = MagicMock()
        p1.call.side_effect = LLMAPIError(status_code=429, provider="P1")
        p2 = MagicMock()
        p2.call.side_effect = LLMAPIError(status_code=500, provider="P2")
        p3 = MagicMock()
        p3.call.return_value = "Third wins"

        result = call_llm_with_fallback(
            [(p1, "s1"), (p2, "s2"), (p3, "s3")],
            user="u",
        )

        assert result == "Third wins"
