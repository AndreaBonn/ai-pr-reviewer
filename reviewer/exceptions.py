"""Custom exception hierarchy for the AI PR Reviewer."""

from __future__ import annotations


class ReviewerError(Exception):
    """Base exception for all reviewer errors."""

    def __init__(self, message: str, code: str = "INTERNAL_ERROR") -> None:
        self.message = message
        self.code = code
        super().__init__(message)


class ConfigError(ReviewerError):
    """Raised when configuration is missing or invalid."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="CONFIG_ERROR")


class ProviderError(ReviewerError):
    """Raised when an LLM provider fails irrecoverably."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="PROVIDER_ERROR")


class GitHubAPIError(ReviewerError):
    """Raised when GitHub API returns an unrecoverable error."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="GITHUB_API_ERROR")


class LLMAPIError(ReviewerError):
    """Safe error that never leaks response body or API keys in its repr."""

    def __init__(self, status_code: int, provider: str) -> None:
        self.status_code = status_code
        self.provider = provider
        super().__init__(
            f"{provider} API returned HTTP {status_code}",
            code="LLM_API_ERROR",
        )


class LLMParseError(ReviewerError):
    """Raised when the LLM response has an unexpected structure."""

    def __init__(self, provider: str) -> None:
        self.provider = provider
        super().__init__(
            f"{provider} returned an unexpected response structure",
            code="LLM_PARSE_ERROR",
        )
