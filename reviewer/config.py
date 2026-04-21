"""Runtime configuration loaded from environment variables."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass

from reviewer.exceptions import ConfigError

log = logging.getLogger("ai-pr-reviewer")

_REPO_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_MODEL_PATTERN = re.compile(r"^[a-zA-Z0-9._:/-]{1,100}$")

SUPPORTED_LANGUAGES = frozenset(
    {
        "english",
        "italian",
        "french",
        "spanish",
        "german",
    }
)
MAX_FILES_UPPER_BOUND = 100


@dataclass(frozen=True)
class Config:
    """Immutable runtime configuration."""

    llm_provider: str
    llm_api_key: str
    llm_model: str
    github_token: str
    language: str
    max_files: int
    ignore_patterns: list[str]
    pr_number: int
    repo: str
    pr_title: str
    pr_body: str

    def __repr__(self) -> str:
        return (
            f"Config(provider={self.llm_provider!r}, repo={self.repo!r}, "
            f"pr={self.pr_number}, language={self.language!r}, "
            f"max_files={self.max_files!r}, "
            f"llm_api_key=<REDACTED>, github_token=<REDACTED>)"
        )

    @classmethod
    def from_env(cls) -> Config:
        raw_patterns = os.environ.get("IGNORE_PATTERNS", "")
        patterns = [p.strip() for p in raw_patterns.split(",") if p.strip()]

        raw_lang = os.environ.get("REVIEW_LANGUAGE", "english").lower().strip()
        if raw_lang not in SUPPORTED_LANGUAGES:
            raise ConfigError(
                f"Unsupported REVIEW_LANGUAGE={raw_lang!r}. "
                f"Supported: {', '.join(sorted(SUPPORTED_LANGUAGES))}"
            )
        language = raw_lang

        max_files = _parse_bounded_int(
            os.environ.get("MAX_FILES", "20"),
            label="MAX_FILES",
            upper=MAX_FILES_UPPER_BOUND,
        )

        return cls(
            llm_provider=_require_env("LLM_PROVIDER").lower().strip(),
            llm_api_key=_require_env("LLM_API_KEY"),
            llm_model=_validate_optional_model(os.environ.get("LLM_MODEL", "").strip()),
            github_token=_require_env("GITHUB_TOKEN"),
            language=language,
            max_files=max_files,
            ignore_patterns=patterns,
            pr_number=_require_int_env("PR_NUMBER"),
            repo=_require_repo_env("REPO_FULL_NAME"),
            pr_title=os.environ.get("PR_TITLE", ""),
            pr_body=os.environ.get("PR_BODY", ""),
        )


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigError(f"Missing required environment variable: {name}")
    return value


def _require_int_env(name: str) -> int:
    value = _require_env(name)
    if not value.isdigit():
        raise ConfigError(f"Environment variable {name} must be a positive integer, got: {value!r}")
    return int(value)


def _require_repo_env(name: str) -> str:
    value = _require_env(name)
    if not _REPO_PATTERN.match(value):
        raise ConfigError(
            f"Environment variable {name} must be 'owner/repo' format, got: {value!r}"
        )
    return value


def _validate_optional_model(value: str) -> str:
    if not value:
        return value
    if not _MODEL_PATTERN.match(value) or ".." in value:
        raise ConfigError(
            f"LLM_MODEL contains invalid characters, got: {value!r}. "
            "Only alphanumerics, dots, dashes, underscores, colons and slashes allowed."
        )
    return value


def _parse_bounded_int(raw: str, *, label: str, upper: int) -> int:
    try:
        value = int(raw)
    except ValueError:
        raise ConfigError(f"{label} must be an integer, got: {raw!r}") from None
    return max(1, min(value, upper))
