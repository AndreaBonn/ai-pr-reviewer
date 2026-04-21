"""Entry point for the AI PR Reviewer GitHub Action."""

from __future__ import annotations

import logging
import sys

from reviewer.config import Config
from reviewer.exceptions import ReviewerError
from reviewer.filters import filter_pr_files
from reviewer.github_client import GitHubClient, post_or_update_comment
from reviewer.prompt import SYSTEM_PROMPT, build_prompt
from reviewer.providers import call_llm_with_retry, get_provider

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s | %(message)s",
)
log = logging.getLogger("ai-pr-reviewer")


def main() -> None:
    cfg = Config.from_env()

    github = GitHubClient(token=cfg.github_token, repo=cfg.repo)
    log.info(
        "Reviewing PR #%s on %s (provider=%s, language=%s)",
        cfg.pr_number,
        cfg.repo,
        cfg.llm_provider,
        cfg.language,
    )

    raw_files = github.get_pr_files(cfg.pr_number)
    log.info("Fetched %d file(s) from GitHub API.", len(raw_files))

    files, skipped = filter_pr_files(
        raw_files,
        ignore_patterns=cfg.ignore_patterns,
        max_files=cfg.max_files,
    )

    if not files:
        log.info("No reviewable files — posting 'nothing to review'.")
        post_or_update_comment(
            github,
            pr_number=cfg.pr_number,
            review_body=(
                "## 🤖 AI Code Review\n\n"
                "Nothing to review — no reviewable file changes "
                "detected in this PR."
            ),
        )
        return

    log.info(
        "Reviewing %d file(s) (%d skipped).",
        len(files),
        len(skipped),
    )

    prompt = build_prompt(
        files,
        pr_title=cfg.pr_title,
        pr_body=cfg.pr_body,
        language=cfg.language,
        total_files=len(raw_files),
        skipped=skipped,
    )

    provider = get_provider(
        name=cfg.llm_provider,
        api_key=cfg.llm_api_key,
        model=cfg.llm_model,
    )
    review = call_llm_with_retry(
        provider,
        system=SYSTEM_PROMPT,
        user=prompt,
    )

    post_or_update_comment(
        github,
        pr_number=cfg.pr_number,
        review_body=review,
    )
    log.info("Review posted successfully.")


if __name__ == "__main__":
    try:
        main()
    except ReviewerError as exc:
        log.error("%s", exc.message)
        sys.exit(1)
