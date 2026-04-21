"""Tests for reviewer.github_client module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from reviewer.exceptions import GitHubAPIError
from reviewer.github_client import (
    BOT_COMMENT_MARKER,
    MAX_PAGINATION_PAGES,
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

        result = find_existing_bot_comment(github, pr_number=10)

        assert result == 42

    def test_returns_none_when_no_marker(self) -> None:
        github = MagicMock(spec=GitHubClient)
        github.list_issue_comments.return_value = [
            {"id": 1, "body": "just a comment"},
        ]

        result = find_existing_bot_comment(github, pr_number=10)

        assert result is None

    def test_skips_comment_with_missing_id(self) -> None:
        github = MagicMock(spec=GitHubClient)
        github.list_issue_comments.return_value = [
            {"body": f"{BOT_COMMENT_MARKER}\nReview here"},
            {"id": 77, "body": f"{BOT_COMMENT_MARKER}\nSecond review"},
        ]

        result = find_existing_bot_comment(github, pr_number=10)

        assert result == 77

    def test_returns_none_when_all_bot_comments_lack_id(self) -> None:
        github = MagicMock(spec=GitHubClient)
        github.list_issue_comments.return_value = [
            {"body": f"{BOT_COMMENT_MARKER}\nReview here"},
        ]

        result = find_existing_bot_comment(github, pr_number=10)

        assert result is None

    def test_returns_none_for_empty_comments(self) -> None:
        github = MagicMock(spec=GitHubClient)
        github.list_issue_comments.return_value = []

        result = find_existing_bot_comment(github, pr_number=10)

        assert result is None


class TestPostOrUpdateComment:
    def test_creates_new_comment_when_none_exists(self) -> None:
        github = MagicMock(spec=GitHubClient)
        github.list_issue_comments.return_value = []

        post_or_update_comment(github, pr_number=10, review_body="Review")

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
            pr_number=10,
            review_body="New review",
        )

        github.update_issue_comment.assert_called_once()
        call_kwargs = github.update_issue_comment.call_args[1]
        assert call_kwargs["comment_id"] == 99
        assert "New review" in call_kwargs["body"]
        github.create_issue_comment.assert_not_called()

    def test_create_comment_marker_precedes_body(self) -> None:
        github = MagicMock(spec=GitHubClient)
        github.list_issue_comments.return_value = []

        post_or_update_comment(github, pr_number=1, review_body="The review")

        body = github.create_issue_comment.call_args[1]["body"]
        assert body.startswith(BOT_COMMENT_MARKER)

    def test_update_preserves_bot_marker_in_body(self) -> None:
        github = MagicMock(spec=GitHubClient)
        github.list_issue_comments.return_value = [
            {"id": 99, "body": f"{BOT_COMMENT_MARKER}\nOld"},
        ]

        post_or_update_comment(github, pr_number=10, review_body="New")

        body = github.update_issue_comment.call_args[1]["body"]
        assert BOT_COMMENT_MARKER in body
        assert "New" in body


def _make_response(
    *,
    status_code: int = 200,
    json_data: object = None,
    links: dict | None = None,
    headers: dict | None = None,
) -> MagicMock:
    """Build a mock requests.Response."""
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.ok = 200 <= status_code < 300
    resp.json.return_value = json_data if json_data is not None else []
    resp.links = links or {}
    resp.headers = headers or {}
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=resp,
        )
    return resp


class TestGitHubClientInit:
    def test_sets_authorization_header(self) -> None:
        client = GitHubClient(token="ghp_test123", repo="owner/repo")

        headers = client._session.headers
        assert headers["Authorization"] == "Bearer ghp_test123"
        assert headers["Accept"] == "application/vnd.github+json"


class TestRequestDefaults:
    @patch.object(requests.Session, "request")
    def test_request_uses_default_timeout(self, mock_request: MagicMock) -> None:
        mock_request.return_value = _make_response(json_data=[])

        client = GitHubClient(token="t", repo="o/r")
        client.get_pr_files(1)

        call_kwargs = mock_request.call_args[1]
        assert call_kwargs.get("timeout") == 30


class TestPaginatedGet:
    @patch.object(GitHubClient, "_request")
    def test_single_page_returns_items(self, mock_request: MagicMock) -> None:
        mock_request.return_value = _make_response(
            json_data=[{"id": 1}, {"id": 2}],
        )

        client = GitHubClient(token="t", repo="o/r")
        result = client._paginated_get("https://api.github.com/test")

        assert result == [{"id": 1}, {"id": 2}]
        assert mock_request.call_count == 1

    @patch.object(GitHubClient, "_request")
    def test_two_pages_concatenated(self, mock_request: MagicMock) -> None:
        page1 = _make_response(
            json_data=[{"id": 1}],
            links={"next": {"url": "https://api.github.com/test?page=2"}},
        )
        page2 = _make_response(json_data=[{"id": 2}])
        mock_request.side_effect = [page1, page2]

        client = GitHubClient(token="t", repo="o/r")
        result = client._paginated_get("https://api.github.com/test")

        assert result == [{"id": 1}, {"id": 2}]
        assert mock_request.call_count == 2

    @patch.object(GitHubClient, "_request")
    def test_caps_at_max_pagination_pages(self, mock_request: MagicMock) -> None:
        page = _make_response(
            json_data=[{"id": 1}],
            links={"next": {"url": "https://api.github.com/test?page=next"}},
        )
        mock_request.return_value = page

        client = GitHubClient(token="t", repo="o/r")
        result = client._paginated_get("https://api.github.com/test")

        assert len(result) == MAX_PAGINATION_PAGES
        assert mock_request.call_count == MAX_PAGINATION_PAGES

    @patch.object(GitHubClient, "_request")
    def test_non_list_response_raises_github_api_error(self, mock_request: MagicMock) -> None:
        mock_request.return_value = _make_response(
            json_data={"message": "Not Found"},
        )

        client = GitHubClient(token="t", repo="o/r")

        with pytest.raises(GitHubAPIError, match="expected list"):
            client._paginated_get("https://api.github.com/test")

    @patch.object(GitHubClient, "_request")
    def test_non_json_response_raises_github_api_error(self, mock_request: MagicMock) -> None:
        resp = _make_response(status_code=200)
        resp.json.side_effect = requests.exceptions.JSONDecodeError("", "", 0)
        mock_request.return_value = resp

        client = GitHubClient(token="t", repo="o/r")

        with pytest.raises(GitHubAPIError, match="non-JSON"):
            client._paginated_get("https://api.github.com/test")


class TestCheckRateLimit:
    def test_403_raises_github_api_error(self) -> None:
        resp = _make_response(
            status_code=403,
            headers={
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": "1700000000",
            },
        )

        with pytest.raises(GitHubAPIError, match="rate limit") as exc_info:
            GitHubClient._check_rate_limit(resp)

        assert "403" in exc_info.value.message
        assert "Remaining: 0" in exc_info.value.message

    def test_429_raises_github_api_error(self) -> None:
        resp = _make_response(
            status_code=429,
            headers={
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": "1700000000",
            },
        )

        with pytest.raises(GitHubAPIError, match="rate limit") as exc_info:
            GitHubClient._check_rate_limit(resp)

        assert "429" in exc_info.value.message

    def test_403_without_rate_limit_raises_permission_error(self) -> None:
        resp = _make_response(
            status_code=403,
            headers={"X-RateLimit-Remaining": "42"},
        )

        with pytest.raises(GitHubAPIError, match="Forbidden"):
            GitHubClient._check_rate_limit(resp)

    def test_403_no_headers_raises_permission_error(self) -> None:
        resp = _make_response(status_code=403, headers={})

        with pytest.raises(GitHubAPIError, match="permissions"):
            GitHubClient._check_rate_limit(resp)

    def test_200_does_not_raise(self) -> None:
        resp = _make_response(status_code=200)

        GitHubClient._check_rate_limit(resp)


class TestRaiseForStatus:
    def test_500_raises_github_api_error(self) -> None:
        resp = _make_response(status_code=500)

        with pytest.raises(GitHubAPIError, match="HTTP 500"):
            GitHubClient._raise_for_status(resp, context="test_op")

    def test_200_does_not_raise(self) -> None:
        resp = _make_response(status_code=200)

        GitHubClient._raise_for_status(resp, context="test_op")


class TestRaiseForStatusDetail:
    def test_includes_github_error_message(self) -> None:
        resp = _make_response(status_code=422)
        resp.json.return_value = {"message": "Validation Failed"}

        with pytest.raises(GitHubAPIError, match="Validation Failed"):
            GitHubClient._raise_for_status(resp, context="test_op")

    def test_handles_non_json_error_body(self) -> None:
        resp = _make_response(status_code=500)
        resp.json.side_effect = requests.exceptions.JSONDecodeError("", "", 0)

        with pytest.raises(GitHubAPIError, match="HTTP 500"):
            GitHubClient._raise_for_status(resp, context="test_op")


class TestNetworkErrorWrapping:
    @patch.object(requests.Session, "request")
    def test_connection_error_raises_github_api_error(self, mock_request: MagicMock) -> None:
        mock_request.side_effect = requests.ConnectionError("DNS failure")

        client = GitHubClient(token="t", repo="o/r")

        with pytest.raises(GitHubAPIError, match="Network error"):
            client.get_pr_files("42")

    @patch.object(requests.Session, "request")
    def test_timeout_raises_github_api_error(self, mock_request: MagicMock) -> None:
        mock_request.side_effect = requests.Timeout("read timed out")

        client = GitHubClient(token="t", repo="o/r")

        with pytest.raises(GitHubAPIError, match="Network error"):
            client.create_issue_comment(pr_number=42, body="test")


class TestCreateAndUpdateComment:
    @patch.object(GitHubClient, "_request")
    def test_create_comment_sends_post(self, mock_request: MagicMock) -> None:
        mock_request.return_value = _make_response(status_code=201)

        client = GitHubClient(token="t", repo="o/r")
        client.create_issue_comment(pr_number=42, body="review text")

        call_args = mock_request.call_args
        assert call_args[0][0] == "POST"
        assert "42/comments" in call_args[0][1]
        assert call_args[1]["json"]["body"] == "review text"

    @patch.object(GitHubClient, "_request")
    def test_update_comment_sends_patch(self, mock_request: MagicMock) -> None:
        mock_request.return_value = _make_response(status_code=200)

        client = GitHubClient(token="t", repo="o/r")
        client.update_issue_comment(comment_id=99, body="updated")

        call_args = mock_request.call_args
        assert call_args[0][0] == "PATCH"
        assert "/comments/99" in call_args[0][1]

    @patch.object(GitHubClient, "_request")
    def test_create_comment_http_error_raises_github_api_error(
        self, mock_request: MagicMock
    ) -> None:
        mock_request.return_value = _make_response(status_code=422)

        client = GitHubClient(token="t", repo="o/r")

        with pytest.raises(GitHubAPIError, match="422"):
            client.create_issue_comment(pr_number=42, body="test")
