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
