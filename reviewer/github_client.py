"""Thin wrapper around the GitHub REST API."""

from __future__ import annotations

import logging

import requests

from reviewer.exceptions import GitHubAPIError

GITHUB_API = "https://api.github.com"
BOT_COMMENT_MARKER = "<!-- ai-pr-reviewer -->"
MAX_PAGINATION_PAGES = 10

log = logging.getLogger("ai-pr-reviewer")


class GitHubClient:
    """Handles all GitHub API interactions for a single repository."""

    def __init__(self, token: str, repo: str) -> None:
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )
        self._repo = repo

    def get_pr_files(self, pr_number: str) -> list[dict]:
        url = f"{GITHUB_API}/repos/{self._repo}/pulls/{pr_number}/files"
        return self._paginated_get(url)

    def list_issue_comments(self, pr_number: str) -> list[dict]:
        url = f"{GITHUB_API}/repos/{self._repo}/issues/{pr_number}/comments"
        return self._paginated_get(url)

    def create_issue_comment(self, pr_number: str, body: str) -> None:
        url = f"{GITHUB_API}/repos/{self._repo}/issues/{pr_number}/comments"
        resp = self._session.post(url, json={"body": body}, timeout=30)
        self._check_rate_limit(resp)
        resp.raise_for_status()

    def update_issue_comment(self, comment_id: int, body: str) -> None:
        url = f"{GITHUB_API}/repos/{self._repo}/issues/comments/{comment_id}"
        resp = self._session.patch(url, json={"body": body}, timeout=30)
        self._check_rate_limit(resp)
        resp.raise_for_status()

    # -- internal helpers --------------------------------------------------

    def _paginated_get(self, url: str) -> list[dict]:
        results: list[dict] = []
        page_url: str | None = url
        pages_fetched = 0
        while page_url and pages_fetched < MAX_PAGINATION_PAGES:
            resp = self._session.get(page_url, timeout=30)
            self._check_rate_limit(resp)
            resp.raise_for_status()
            results.extend(resp.json())
            page_url = resp.links.get("next", {}).get("url")
            pages_fetched += 1
        if page_url:
            log.warning("Pagination capped at %d pages.", MAX_PAGINATION_PAGES)
        return results

    @staticmethod
    def _check_rate_limit(resp: requests.Response) -> None:
        if resp.status_code == 403:
            remaining = resp.headers.get("X-RateLimit-Remaining", "?")
            reset_ts = resp.headers.get("X-RateLimit-Reset", "?")
            raise GitHubAPIError(
                f"GitHub API rate limit hit. Remaining: {remaining}, resets at: {reset_ts}"
            )


def find_existing_bot_comment(
    github: GitHubClient,
    pr_number: str,
) -> int | None:
    """Return the comment ID of a previous bot review, or None."""
    comments = github.list_issue_comments(pr_number)
    for comment in comments:
        body = comment.get("body", "")
        if BOT_COMMENT_MARKER in body:
            return comment["id"]
    return None


def post_or_update_comment(
    github: GitHubClient,
    pr_number: str,
    review_body: str,
) -> None:
    """Create or update the bot review comment on the PR."""
    full_body = f"{BOT_COMMENT_MARKER}\n{review_body}"
    existing_id = find_existing_bot_comment(github, pr_number)

    if existing_id:
        github.update_issue_comment(comment_id=existing_id, body=full_body)
        log.info("Updated existing review comment (id=%d).", existing_id)
    else:
        github.create_issue_comment(pr_number=pr_number, body=full_body)
        log.info("Created new review comment.")
