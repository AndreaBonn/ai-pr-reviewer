"""PR file filtering, sorting, and truncation logic."""

from __future__ import annotations

import fnmatch
import logging
from dataclasses import dataclass

log = logging.getLogger("ai-pr-reviewer")

MAX_PATCH_LINES = 200
MAX_LINE_LENGTH = 500


@dataclass(frozen=True)
class PRFile:
    """A single file changed in the pull request."""

    filename: str
    status: str
    patch: str
    is_truncated: bool = False
    original_lines: int = 0


def filter_pr_files(
    raw_files: list[dict],
    ignore_patterns: list[str],
    max_files: int,
) -> tuple[list[PRFile], list[str]]:
    """Filter, sort, truncate and return PR files ready for the prompt.

    Returns
    -------
    tuple
        (kept files, list of skipped filenames)
    """
    filtered: list[dict] = []
    for f in raw_files:
        filename = f.get("filename")
        if not filename:
            log.warning("Skipping malformed file entry with missing 'filename'")
            continue
        patch = f.get("patch")

        if _matches_any(filename, ignore_patterns):
            continue
        if not patch:
            continue

        filtered.append(f)

    filtered.sort(
        key=lambda f: f.get("additions", 0) + f.get("deletions", 0),
        reverse=True,
    )

    skipped = [f["filename"] for f in filtered[max_files:]]
    kept_raw = filtered[:max_files]

    kept: list[PRFile] = []
    for f in kept_raw:
        patch = f["patch"]
        lines = patch.splitlines()
        total_lines = len(lines)
        is_truncated = total_lines > MAX_PATCH_LINES

        trimmed = [
            line[:MAX_LINE_LENGTH] + " [truncated]" if len(line) > MAX_LINE_LENGTH else line
            for line in lines[:MAX_PATCH_LINES]
        ]
        patch = "\n".join(trimmed)

        status = f.get("status")
        if status is None:
            log.warning(
                "File entry for %r missing 'status' field — defaulting to 'modified'.",
                f["filename"],
            )
            status = "modified"

        kept.append(
            PRFile(
                filename=f["filename"],
                status=status,
                patch=patch,
                is_truncated=is_truncated,
                original_lines=total_lines,
            )
        )

    return kept, skipped


def _matches_any(filename: str, patterns: list[str]) -> bool:
    basename = filename.rsplit("/", maxsplit=1)[-1]
    return any(fnmatch.fnmatch(basename, p) or fnmatch.fnmatch(filename, p) for p in patterns)
