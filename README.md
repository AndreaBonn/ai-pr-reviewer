# 🤖 AI PR Reviewer

[![GitHub Actions](https://img.shields.io/badge/GitHub%20Action-AI%20PR%20Review-purple?logo=github)](https://github.com/AndreaBonn/ai-pr-reviewer)

A **GitHub Action** that automatically reviews Pull Requests using an LLM and posts a structured code review as a PR comment. Supports **Groq**, **Gemini**, **Anthropic (Claude)** and **OpenAI**.

---

## Quick Start

### 1. Add your API key as a repository secret

Go to **Settings → Secrets and variables → Actions** and create a secret for your chosen provider (e.g. `GROQ_API_KEY`).

### 2. Create the workflow file

Add `.github/workflows/ai-review.yml` to your repository:

```yaml
name: AI PR Review

on:
  pull_request:
    types: [opened, synchronize, reopened]

jobs:
  review:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write
    steps:
      - uses: actions/checkout@v4
      - uses: AndreaBonn/ai-pr-reviewer@v1
        with:
          llm_provider: 'groq'
          llm_api_key: ${{ secrets.GROQ_API_KEY }}
          github_token: ${{ secrets.GITHUB_TOKEN }}
```

### 3. Open a Pull Request

The bot will automatically post a review comment. If you push new commits, the existing comment is updated (not duplicated).

---

## Inputs

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `llm_provider` | No | `groq` | LLM provider: `groq`, `gemini`, `anthropic`, `openai` |
| `llm_api_key` | **Yes** | — | API key for the chosen provider |
| `llm_model` | No | Provider default | Override default model (e.g. `llama-3.1-8b`, `gpt-4o`) |
| `github_token` | **Yes** | — | GitHub token for posting comments |
| `language` | No | `english` | Review language: `english`, `italian`, `french`, `spanish`, `german` |
| `max_files` | No | `20` | Max files to review (avoids token limits) |
| `ignore_patterns` | No | `*.lock,*.min.js,*.min.css,package-lock.json,yarn.lock` | Comma-separated glob patterns to skip |

---

## Supported Providers

| Provider | Cost | Default Model | Speed | Quality |
|----------|------|---------------|-------|---------|
| **Groq** | Free | `llama-3.3-70b-versatile` | ⚡⚡⚡ | ★★★★ |
| **Gemini** | Free | `gemini-2.0-flash` | ⚡⚡ | ★★★★ |
| **Anthropic** | Paid | `claude-sonnet-4-5` | ⚡⚡ | ★★★★★ |
| **OpenAI** | Paid | `gpt-4o-mini` | ⚡⚡ | ★★★★ |

### Getting API Keys

- **Groq** (free): [console.groq.com](https://console.groq.com)
- **Gemini** (free): [aistudio.google.com](https://aistudio.google.com)
- **Anthropic** (paid): [console.anthropic.com](https://console.anthropic.com)
- **OpenAI** (paid): [platform.openai.com](https://platform.openai.com)

---

## Review Structure

The generated review covers:

| Section | What it checks |
|---------|---------------|
| **Summary** | Overall assessment of the PR |
| **Bugs & Logic Issues** | Bugs, logic errors, unhandled edge cases, error handling gaps |
| **Security** | Secrets, injection, unsafe deserialization, auth gaps |
| **Performance & Scalability** | N+1 queries, blocking I/O, missing pagination |
| **Breaking Changes** | Modified signatures, changed return types, schema changes |
| **Testing Gaps** | Missing coverage for new/changed logic |
| **What's Done Well** | Specific positive highlights |

---

## Example Output

When the action runs, a comment like this appears on your PR:

> ## 🤖 AI Code Review
>
> ### 📋 Summary
> This PR adds a new `parse_config()` function to handle YAML configuration loading. The approach is clean, but error handling needs attention.
>
> ### 🐛 Bug & Issues
> **`config/parser.py` line 42:** `parse_date()` doesn't handle empty strings — will raise `ValueError` at runtime.
>
> ### 🔒 Security
> **`config/parser.py` line 15:** API key logged via `print(config)` on line 31. Remove or redact sensitive fields.
>
> *...and more sections...*

---

## Provider-Specific Secrets

| Secret | When needed |
|--------|------------|
| `GROQ_API_KEY` | If using Groq |
| `GEMINI_API_KEY` | If using Gemini |
| `ANTHROPIC_API_KEY` | If using Anthropic |
| `OPENAI_API_KEY` | If using OpenAI |

> `GITHUB_TOKEN` is automatically available — no configuration needed.

---

## Permissions

The workflow needs read access to contents and write access to pull requests:

```yaml
permissions:
  contents: read
  pull-requests: write
```

Or enable it globally: **Settings → Actions → General → Workflow permissions → Read and write permissions**.

---

## Privacy

This action sends the following data to the configured LLM provider (Groq, Gemini, Anthropic, or OpenAI):

- PR title, description, and file diffs
- File names and change metadata

No credentials or secrets are included in the prompt. However, if your PR description or code diffs contain sensitive information, that data will be transmitted to the third-party LLM API. For private repositories with sensitive data, review your provider's data retention policy.

---

## Limitations

- Very large diffs (>100 files) are capped at `max_files` to avoid token limits
- Individual file patches are truncated to 200 lines
- AI-generated reviews do not replace human code review
- Binary files are automatically skipped

---

## License

MIT
