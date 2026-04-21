"""Integration tests for review.py::main() orchestrator."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from review import main
from reviewer.exceptions import ConfigError, GitHubAPIError, ProviderError


class TestMain:
    """Tests for the main() orchestration function."""

    REQUIRED_ENV = {
        "LLM_PROVIDER": "groq",
        "LLM_API_KEY": "test-key",
        "GITHUB_TOKEN": "ghp_test",
        "PR_NUMBER": "42",
        "REPO_FULL_NAME": "owner/repo",
    }

    @patch("review.post_or_update_comment")
    @patch("review.call_llm_with_retry", return_value="## Review")
    @patch("review.get_provider")
    @patch("review.GitHubClient")
    def test_happy_path_posts_review(
        self,
        mock_github_cls: MagicMock,
        mock_get_provider: MagicMock,
        mock_call_llm: MagicMock,
        mock_post_comment: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        for k, v in self.REQUIRED_ENV.items():
            monkeypatch.setenv(k, v)

        mock_github = mock_github_cls.return_value
        mock_github.get_pr_files.return_value = [
            {"filename": "app.py", "patch": "+new", "additions": 1, "deletions": 0},
        ]

        main()

        mock_call_llm.assert_called_once()
        mock_post_comment.assert_called_once()
        body = mock_post_comment.call_args[1]["review_body"]
        assert "Review" in body

    @patch("review.post_or_update_comment")
    @patch("review.GitHubClient")
    def test_no_files_posts_nothing_to_review(
        self,
        mock_github_cls: MagicMock,
        mock_post_comment: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        for k, v in self.REQUIRED_ENV.items():
            monkeypatch.setenv(k, v)

        mock_github = mock_github_cls.return_value
        mock_github.get_pr_files.return_value = []

        main()

        mock_post_comment.assert_called_once()
        body = mock_post_comment.call_args[1]["review_body"]
        assert "Nothing to review" in body

    @patch("review.post_or_update_comment")
    @patch("review.GitHubClient")
    def test_all_binary_files_posts_nothing_to_review(
        self,
        mock_github_cls: MagicMock,
        mock_post_comment: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        for k, v in self.REQUIRED_ENV.items():
            monkeypatch.setenv(k, v)

        mock_github = mock_github_cls.return_value
        mock_github.get_pr_files.return_value = [
            {"filename": "image.png", "status": "added", "additions": 0, "deletions": 0},
        ]

        main()

        mock_post_comment.assert_called_once()
        body = mock_post_comment.call_args[1]["review_body"]
        assert "Nothing to review" in body

    def test_missing_env_raises_config_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("LLM_PROVIDER", raising=False)
        monkeypatch.delenv("LLM_API_KEY", raising=False)

        with pytest.raises(ConfigError):
            main()

    @patch("review.call_llm_with_retry")
    @patch("review.get_provider")
    @patch("review.GitHubClient")
    def test_provider_error_propagates(
        self,
        mock_github_cls: MagicMock,
        mock_get_provider: MagicMock,
        mock_call_llm: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        for k, v in self.REQUIRED_ENV.items():
            monkeypatch.setenv(k, v)

        mock_github = mock_github_cls.return_value
        mock_github.get_pr_files.return_value = [
            {"filename": "app.py", "patch": "+new", "additions": 1, "deletions": 0},
        ]
        mock_call_llm.side_effect = ProviderError("LLM failed")

        with pytest.raises(ProviderError):
            main()

    @patch("review.GitHubClient")
    def test_github_api_error_propagates(
        self,
        mock_github_cls: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        for k, v in self.REQUIRED_ENV.items():
            monkeypatch.setenv(k, v)

        mock_github = mock_github_cls.return_value
        mock_github.get_pr_files.side_effect = GitHubAPIError("rate limit hit")

        with pytest.raises(GitHubAPIError):
            main()
