# Security

[Italiano](SECURITY.it.md) | **English**

[Back to README](README.md)

---

## Overview

AI PR Reviewer is designed to process potentially untrusted input (PR titles, descriptions, code diffs) and send it to third-party LLM APIs. Security is a core concern, not an afterthought.

---

## What Data is Sent to LLM Providers

The action sends the following to the configured LLM API:

| Data | Sent | Notes |
|------|:----:|-------|
| PR title | Yes | Sanitized before inclusion |
| PR description | Yes | Sanitized before inclusion |
| File diffs (patches) | Yes | Sanitized, truncated to 200 lines per file |
| File names | Yes | Sanitized |
| API keys | **No** | Passed via HTTP headers, never in the prompt body |
| GitHub token | **No** | Used only for GitHub API calls, never sent to LLM |
| Repository secrets | **No** | Never accessed or transmitted |
| Full file contents | **No** | Only diff patches are sent, not complete files |

---

## Prompt Injection Protection

All user-provided content (PR title, description, file names, code diffs) is sanitized before being included in the LLM prompt. The sanitizer detects and redacts known prompt injection patterns:

- `ignore previous instructions`, `disregard prior context`
- `you are now`, `from now on you must`, `act as DAN`
- `system override`, `override:`, `new instructions`
- LLM-specific injection tokens: `<|system|>`, `[INST]`, `<<SYS>>`, `</s><s>`, `<system>`
- Role confusion: `Human:...Assistant:` sequences
- `IMPORTANT:` directives designed to override system instructions

User-provided content is:
1. Passed through the injection pattern filter (matched patterns are replaced with `[REDACTED]`)
2. Truncated to a maximum length (2000 characters for title/description)
3. Enclosed in fenced code blocks (` ``` `) in the prompt, with explicit instructions to the LLM to treat them as raw data

The system prompt explicitly instructs the LLM to ignore any instructions embedded in user content.

---

## Credential Safety

### Secrets Never Leak

- **API keys** are passed via HTTP headers (`Authorization`, `x-api-key`, `x-goog-api-key`), never included in request bodies or prompt text
- **`Config.__repr__`** redacts all sensitive fields — API keys and GitHub token are displayed as `<REDACTED>` in logs
- **Error messages** (`LLMAPIError`) only expose the HTTP status code and provider name, never response bodies or credentials
- **GitHub token** is used exclusively for GitHub REST API calls and is never sent to any LLM provider

### Input Validation

All configuration inputs are validated at startup:

| Input | Validation |
|-------|-----------|
| `LLM_PROVIDER` | Must match a known provider name |
| `LLM_MODEL` | Alphanumeric, dots, dashes, underscores, colons, slashes only. Max 100 chars. Path traversal (`..`) blocked |
| `REPO_FULL_NAME` | Must match `owner/repo` format (regex-validated) |
| `PR_NUMBER` | Must be a positive integer |
| `MAX_FILES` | Clamped to range 1-100 |
| `REVIEW_LANGUAGE` | Must be in the supported language whitelist |
| Provider/key count | Number of providers must match number of API keys |

---

## Network Security

- All API calls use HTTPS exclusively
- Request timeouts are set to 120 seconds to prevent hanging connections
- Each LLM provider call uses the minimum required headers
- No data is cached or stored between runs — the action is stateless

---

## Error Handling

- Custom exception hierarchy (`ReviewerError` → `ConfigError`, `ProviderError`, `GitHubAPIError`, `LLMAPIError`, `LLMParseError`) ensures errors are typed and traceable
- No `sys.exit()` in library modules — errors propagate cleanly to the entry point
- Stack traces in production never expose API keys or tokens
- GitHub API pagination is capped to prevent runaway requests

---

## Dependency Footprint

The action has a single production dependency: `requests`. This minimizes the attack surface. Dev dependencies (`pytest`, `ruff`, `pip-audit`) are not installed in production.

The CI pipeline runs `pip-audit` on every pull request to detect known vulnerabilities in dependencies.

---

## Reporting a Vulnerability

If you discover a security vulnerability, please report it via [GitHub Issues](https://github.com/AndreaBonn/ai-pr-reviewer/issues) with the label `security`. Do not include sensitive details in the issue title.
