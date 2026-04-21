"""Tests for reviewer.config module."""

from __future__ import annotations

import pytest

from reviewer.config import Config, _parse_bounded_int
from reviewer.exceptions import ConfigError


class TestConfigFromEnv:
    """Config.from_env() reads and validates environment variables."""

    REQUIRED_ENV = {
        "LLM_PROVIDER": "groq",
        "LLM_API_KEY": "test-key-123",
        "GITHUB_TOKEN": "ghp_test",
        "PR_NUMBER": "42",
        "REPO_FULL_NAME": "owner/repo",
    }

    def test_minimal_config_uses_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for k, v in self.REQUIRED_ENV.items():
            monkeypatch.setenv(k, v)

        cfg = Config.from_env()

        assert cfg.llm_provider == "groq"
        assert cfg.llm_model == ""
        assert cfg.language == "english"
        assert cfg.max_files == 20
        assert cfg.pr_number == "42"
        assert cfg.pr_title == ""
        assert cfg.pr_body == ""

    def test_language_whitelist_rejects_unknown(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for k, v in self.REQUIRED_ENV.items():
            monkeypatch.setenv(k, v)
        monkeypatch.setenv("REVIEW_LANGUAGE", "klingon")

        cfg = Config.from_env()

        assert cfg.language == "english"

    def test_language_accepts_valid(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for k, v in self.REQUIRED_ENV.items():
            monkeypatch.setenv(k, v)
        monkeypatch.setenv("REVIEW_LANGUAGE", "Italian")

        cfg = Config.from_env()

        assert cfg.language == "italian"

    def test_ignore_patterns_parsed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for k, v in self.REQUIRED_ENV.items():
            monkeypatch.setenv(k, v)
        monkeypatch.setenv("IGNORE_PATTERNS", "*.lock, *.min.js ,")

        cfg = Config.from_env()

        assert cfg.ignore_patterns == ["*.lock", "*.min.js"]

    def test_max_files_capped_at_upper_bound(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for k, v in self.REQUIRED_ENV.items():
            monkeypatch.setenv(k, v)
        monkeypatch.setenv("MAX_FILES", "9999")

        cfg = Config.from_env()

        assert cfg.max_files == 100

    def test_missing_required_env_raises_config_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("LLM_PROVIDER", raising=False)

        with pytest.raises(ConfigError, match="LLM_PROVIDER"):
            Config.from_env()

    def test_non_numeric_pr_number_raises_config_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        for k, v in self.REQUIRED_ENV.items():
            monkeypatch.setenv(k, v)
        monkeypatch.setenv("PR_NUMBER", "not-a-number")

        with pytest.raises(ConfigError, match="positive integer"):
            Config.from_env()

    def test_provider_normalized_to_lowercase(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for k, v in self.REQUIRED_ENV.items():
            monkeypatch.setenv(k, v)
        monkeypatch.setenv("LLM_PROVIDER", "  GEMINI  ")

        cfg = Config.from_env()

        assert cfg.llm_provider == "gemini"

    def test_invalid_repo_format_raises_config_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        for k, v in self.REQUIRED_ENV.items():
            monkeypatch.setenv(k, v)
        monkeypatch.setenv("REPO_FULL_NAME", "owner/repo/../../../malicious")

        with pytest.raises(ConfigError, match="owner/repo"):
            Config.from_env()

    def test_valid_repo_format_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for k, v in self.REQUIRED_ENV.items():
            monkeypatch.setenv(k, v)
        monkeypatch.setenv("REPO_FULL_NAME", "my-org/my_repo.v2")

        cfg = Config.from_env()

        assert cfg.repo == "my-org/my_repo.v2"


class TestLlmModelValidation:
    REQUIRED_ENV = TestConfigFromEnv.REQUIRED_ENV

    def test_valid_model_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for k, v in self.REQUIRED_ENV.items():
            monkeypatch.setenv(k, v)
        monkeypatch.setenv("LLM_MODEL", "llama-3.1-8b")

        cfg = Config.from_env()

        assert cfg.llm_model == "llama-3.1-8b"

    def test_model_with_slashes_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for k, v in self.REQUIRED_ENV.items():
            monkeypatch.setenv(k, v)
        monkeypatch.setenv("LLM_MODEL", "meta/llama-3.1-8b:latest")

        cfg = Config.from_env()

        assert cfg.llm_model == "meta/llama-3.1-8b:latest"

    def test_empty_model_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for k, v in self.REQUIRED_ENV.items():
            monkeypatch.setenv(k, v)

        cfg = Config.from_env()

        assert cfg.llm_model == ""

    def test_malicious_model_raises_config_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for k, v in self.REQUIRED_ENV.items():
            monkeypatch.setenv(k, v)
        monkeypatch.setenv("LLM_MODEL", "../../../etc/passwd")

        with pytest.raises(ConfigError, match="invalid characters"):
            Config.from_env()

    def test_model_with_newline_raises_config_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for k, v in self.REQUIRED_ENV.items():
            monkeypatch.setenv(k, v)
        monkeypatch.setenv("LLM_MODEL", "model\nfake-log-line")

        with pytest.raises(ConfigError, match="invalid characters"):
            Config.from_env()


class TestConfigRepr:
    """Config.__repr__() redacts sensitive fields."""

    def test_repr_redacts_secrets(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for k, v in TestConfigFromEnv.REQUIRED_ENV.items():
            monkeypatch.setenv(k, v)

        cfg = Config.from_env()
        text = repr(cfg)

        assert "test-key-123" not in text
        assert "ghp_test" not in text
        assert "<REDACTED>" in text
        assert "groq" in text


class TestRequireEnvEdgeCases:
    """Edge cases for _require_env validation."""

    REQUIRED_ENV = TestConfigFromEnv.REQUIRED_ENV

    def test_whitespace_only_env_raises_config_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        for k, v in self.REQUIRED_ENV.items():
            monkeypatch.setenv(k, v)
        monkeypatch.setenv("LLM_API_KEY", "   ")

        with pytest.raises(ConfigError, match="LLM_API_KEY"):
            Config.from_env()

    def test_empty_string_env_raises_config_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        for k, v in self.REQUIRED_ENV.items():
            monkeypatch.setenv(k, v)
        monkeypatch.setenv("GITHUB_TOKEN", "")

        with pytest.raises(ConfigError, match="GITHUB_TOKEN"):
            Config.from_env()

    def test_unsupported_language_logs_warning_and_falls_back(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        for k, v in self.REQUIRED_ENV.items():
            monkeypatch.setenv(k, v)
        monkeypatch.setenv("REVIEW_LANGUAGE", "klingon")

        with caplog.at_level("WARNING"):
            cfg = Config.from_env()

        assert cfg.language == "english"
        assert "klingon" in caplog.text
        assert "Unsupported" in caplog.text


class TestParseBoundedInt:
    def test_within_range(self) -> None:
        assert _parse_bounded_int("10", label="X", upper=50) == 10

    def test_clamped_to_upper(self) -> None:
        assert _parse_bounded_int("200", label="X", upper=50) == 50

    def test_clamped_to_minimum_one(self) -> None:
        assert _parse_bounded_int("-5", label="X", upper=50) == 1

    def test_non_integer_raises_config_error(self) -> None:
        with pytest.raises(ConfigError, match="must be an integer"):
            _parse_bounded_int("abc", label="X", upper=50)
