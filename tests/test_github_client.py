"""Tests for reviewer.github_client module."""

from __future__ import annotations

from unittest.mock import MagicMock

from reviewer.github_client import (
    BOT_COMMENT_MARKER,
    GitHubClient,
    find_existing_bot_comment,
    post_or_update_comment,
)


class TestFindExistingBotComment:
    def test_returns_id_when_marker_found(self) -> None:
        github = MagicMock(spec=GitHubClient)
        github.list_issue_comments.return_value = [
            {"id": 1, "body": "random comment"},
            {"id": 42, "body": f"{BOT_COMMENT_MARKER}\nReview here"},
        ]

        result = find_existing_bot_comment(github, pr_number="10")

        assert result == 42

    def test_returns_none_when_no_marker(self) -> None:
        github = MagicMock(spec=GitHubClient)
        github.list_issue_comments.return_value = [
            {"id": 1, "body": "just a comment"},
        ]

        result = find_existing_bot_comment(github, pr_number="10")

        assert result is None

    def test_returns_none_for_empty_comments(self) -> None:
        github = MagicMock(spec=GitHubClient)
        github.list_issue_comments.return_value = []

        result = find_existing_bot_comment(github, pr_number="10")

        assert result is None


class TestPostOrUpdateComment:
    def test_creates_new_comment_when_none_exists(self) -> None:
        github = MagicMock(spec=GitHubClient)
        github.list_issue_comments.return_value = []

        post_or_update_comment(github, pr_number="10", review_body="Review")

        github.create_issue_comment.assert_called_once()
        body = github.create_issue_comment.call_args[1]["body"]
        assert BOT_COMMENT_MARKER in body
        assert "Review" in body

    def test_updates_existing_comment(self) -> None:
        github = MagicMock(spec=GitHubClient)
        github.list_issue_comments.return_value = [
            {"id": 99, "body": f"{BOT_COMMENT_MARKER}\nOld review"},
        ]

        post_or_update_comment(
            github,
            pr_number="10",
            review_body="New review",
        )

        github.update_issue_comment.assert_called_once()
        call_kwargs = github.update_issue_comment.call_args[1]
        assert call_kwargs["comment_id"] == 99
        assert "New review" in call_kwargs["body"]
        github.create_issue_comment.assert_not_called()
