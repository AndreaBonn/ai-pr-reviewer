# AI PR Reviewer

GitHub Action that reviews pull requests using LLMs (Groq, Gemini, Anthropic, OpenAI).

## Quick Start

```bash
uv sync --all-extras    # Install dependencies
uv run pytest -v        # Run tests
uv run ruff check .     # Lint
uv run ruff format .    # Format
```

## Architecture

```
review.py           → Entry point / orchestrator
reviewer/
  config.py         → Env var parsing + validation (Config dataclass)
  filters.py        → PR file filtering, sorting, truncation
  github_client.py  → GitHub REST API wrapper
  prompt.py         → LLM prompt construction
  providers.py      → LLM provider strategy pattern (Groq, Gemini, Anthropic, OpenAI)
  exceptions.py     → Custom exception hierarchy
tests/              → Mirrors reviewer/ 1:1
```

## Key Conventions

- Python 3.11+, single production dependency (`requests`)
- Custom exceptions (`ConfigError`, `ProviderError`, `GitHubAPIError`) — no `sys.exit()` in modules
- Strategy pattern for LLM providers — add new ones by subclassing `LLMProvider`
- `Config` is a frozen dataclass with `__repr__` that redacts secrets
- User input (`pr_title`, `pr_body`) is sanitized against prompt injection before building the prompt
- `requirements.txt` uses pinned versions for the GitHub Action; `pyproject.toml` for dev

## Adding a New LLM Provider

1. Create a class in `reviewer/providers.py` extending `LLMProvider`
2. Implement the `call(system, user) -> str` method
3. Add entry to `_PROVIDERS` dict
4. Add test in `tests/test_providers.py`
