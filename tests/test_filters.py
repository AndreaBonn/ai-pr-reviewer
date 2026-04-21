"""Tests for reviewer.filters module."""

from __future__ import annotations

from reviewer.filters import _matches_any, filter_pr_files


def _make_raw_file(
    filename: str = "src/app.py",
    patch: str = "+line1\n-line2",
    status: str = "modified",
    additions: int = 5,
    deletions: int = 3,
) -> dict:
    return {
        "filename": filename,
        "patch": patch,
        "status": status,
        "additions": additions,
        "deletions": deletions,
    }


class TestFilterPrFiles:
    def test_excludes_files_matching_ignore_pattern(self) -> None:
        files = [
            _make_raw_file(filename="package-lock.json"),
            _make_raw_file(filename="src/main.py"),
        ]

        kept, skipped = filter_pr_files(
            files,
            ignore_patterns=["package-lock.json"],
            max_files=20,
        )

        assert len(kept) == 1
        assert kept[0].filename == "src/main.py"

    def test_excludes_files_without_patch(self) -> None:
        files = [
            _make_raw_file(filename="binary.png", patch=None),
            _make_raw_file(filename="src/main.py"),
        ]

        kept, _ = filter_pr_files(files, ignore_patterns=[], max_files=20)

        assert len(kept) == 1
        assert kept[0].filename == "src/main.py"

    def test_excludes_files_with_empty_patch(self) -> None:
        files = [
            _make_raw_file(filename="renamed.py", patch=""),
            _make_raw_file(filename="src/main.py"),
        ]

        kept, _ = filter_pr_files(files, ignore_patterns=[], max_files=20)

        assert len(kept) == 1

    def test_sorts_by_total_changes_descending(self) -> None:
        files = [
            _make_raw_file(filename="small.py", additions=1, deletions=0),
            _make_raw_file(filename="big.py", additions=50, deletions=20),
            _make_raw_file(filename="medium.py", additions=10, deletions=5),
        ]

        kept, _ = filter_pr_files(files, ignore_patterns=[], max_files=20)

        assert [f.filename for f in kept] == ["big.py", "medium.py", "small.py"]

    def test_truncates_to_max_files_and_reports_skipped(self) -> None:
        files = [_make_raw_file(filename=f"file{i}.py", additions=10 - i) for i in range(5)]

        kept, skipped = filter_pr_files(
            files,
            ignore_patterns=[],
            max_files=2,
        )

        assert len(kept) == 2
        assert len(skipped) == 3

    def test_truncates_long_patches(self) -> None:
        long_patch = "\n".join(f"+line{i}" for i in range(300))
        files = [_make_raw_file(patch=long_patch)]

        kept, _ = filter_pr_files(files, ignore_patterns=[], max_files=20)

        assert kept[0].is_truncated is True
        assert kept[0].original_lines == 300
        assert len(kept[0].patch.splitlines()) == 200

    def test_truncates_long_lines(self) -> None:
        long_line = "+" + "x" * 600
        files = [_make_raw_file(patch=long_line)]

        kept, _ = filter_pr_files(files, ignore_patterns=[], max_files=20)

        first_line = kept[0].patch.splitlines()[0]
        assert len(first_line) < 600
        assert "[truncated]" in first_line

    def test_returns_empty_when_all_filtered(self) -> None:
        files = [_make_raw_file(filename="package-lock.json")]

        kept, skipped = filter_pr_files(
            files,
            ignore_patterns=["*.json"],
            max_files=20,
        )

        assert kept == []
        assert skipped == []

    def test_skips_entry_without_filename(self) -> None:
        files = [
            {"patch": "+line", "additions": 1, "deletions": 0},
            _make_raw_file(filename="src/main.py"),
        ]

        kept, _ = filter_pr_files(files, ignore_patterns=[], max_files=20)

        assert len(kept) == 1
        assert kept[0].filename == "src/main.py"

    def test_skips_entry_with_empty_filename(self) -> None:
        files = [
            _make_raw_file(filename=""),
            _make_raw_file(filename="src/main.py"),
        ]

        kept, _ = filter_pr_files(files, ignore_patterns=[], max_files=20)

        assert len(kept) == 1
        assert kept[0].filename == "src/main.py"

    def test_root_file_matches_basename_pattern(self) -> None:
        assert _matches_any("README.md", ["*.md"]) is True


class TestMatchesAny:
    def test_matches_basename(self) -> None:
        assert _matches_any("src/deep/file.min.js", ["*.min.js"]) is True

    def test_matches_full_path(self) -> None:
        assert _matches_any("package-lock.json", ["package-lock.json"]) is True

    def test_no_match(self) -> None:
        assert _matches_any("src/app.py", ["*.lock", "*.min.js"]) is False

    def test_empty_patterns_never_matches(self) -> None:
        assert _matches_any("anything.py", []) is False
