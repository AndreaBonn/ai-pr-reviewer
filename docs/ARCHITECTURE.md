# Architecture

Technical documentation for the ai-pr-reviewer internal architecture.

## Component Overview

The system is composed of 6 Python modules orchestrated by `review.py`. External dependencies are GitHub API (for fetching PR data and posting comments) and LLM provider APIs (for generating the review).

```mermaid
%%{init: {'theme': 'default'}}%%
graph LR
  gh_actions["GitHub Actions<br/>PR Event"]
  review["review.py<br/>Orchestrator"]
  config["config.py<br/>Env Parsing"]
  filters["filters.py<br/>File Filtering"]
  prompt_mod["prompt.py<br/>Prompt Builder"]
  gh_client["github_client.py<br/>API Wrapper"]
  providers["providers.py<br/>LLM Strategy"]
  gh_api[("GitHub API")]
  llm_api["LLM APIs<br/>Groq / Gemini /<br/>Anthropic / OpenAI"]

  gh_actions -->|"env vars"| review
  review --> config
  review --> gh_client
  review --> filters
  review --> prompt_mod
  review --> providers
  gh_client -->|"REST"| gh_api
  providers -->|"HTTP"| llm_api

  classDef core fill:#2563eb,stroke:#1d4ed8,color:#fff
  classDef engine fill:#059669,stroke:#047857,color:#fff
  classDef data fill:#d97706,stroke:#b45309,color:#fff
  classDef ext fill:#6b7280,stroke:#4b5563,color:#fff

  class review core
  class config,filters,prompt_mod,providers engine
  class gh_client data
  class gh_actions,gh_api,llm_api ext
```

**Legend:** Blue = orchestrator, Green = internal modules, Orange = data access, Grey = external systems.

## Review Pipeline

End-to-end flow from PR event to posted comment. Each step is a distinct responsibility handled by a dedicated module.

```mermaid
sequenceDiagram
  participant gha as GitHub Actions
  participant rev as review.py
  participant cfg as Config
  participant ghc as GitHubClient
  participant flt as filters
  participant pmt as prompt
  participant llm as LLMProviders
  participant api as GitHub API

  gha->>rev: PR event via env vars
  rev->>cfg: from_env()
  cfg-->>rev: Config instance

  rev->>ghc: get_pr_files(pr_number)
  ghc->>api: GET /pulls/N/files
  api-->>ghc: raw file list
  ghc-->>rev: list of dicts

  rev->>flt: filter_pr_files(files, patterns, max)
  flt-->>rev: PRFile list + skipped

  rev->>pmt: build_prompt(files, title, body)
  Note over pmt: Sanitize PR title/body<br/>against prompt injection
  pmt-->>rev: user_prompt

  rev->>llm: call_llm_with_fallback(chain, prompt)
  llm->>llm: retry with backoff per provider
  llm-->>rev: review text

  rev->>ghc: post_or_update_comment(review)
  ghc->>api: POST or PATCH comment
  api-->>ghc: 201/200 OK
```

Key points:
- `Config.from_env()` validates all environment variables upfront; invalid config fails fast with `ConfigError`
- `filter_pr_files` removes ignored patterns, sorts by change size, caps at `max_files`, and truncates patches to 200 lines
- `build_prompt` sanitizes user-provided PR title/body against prompt injection before embedding them
- `post_or_update_comment` implements an upsert pattern: searches for an existing bot comment marker and updates it, or creates a new one

## Provider Fallback and Retry

The retry/fallback logic is the core resilience mechanism. Each provider gets up to 3 attempts with exponential backoff before the system falls back to the next provider in the chain.

```mermaid
%%{init: {'theme': 'default'}}%%
graph TD
  start_node(["call_llm_with_fallback"])
  pick_provider["Pick next provider<br/>from chain"]
  call_retry["call_llm_with_retry"]
  attempt["Send request to LLM API"]
  check_result{"Success?"}
  check_retryable{"Retryable<br/>error?"}
  backoff["Wait 2s / 4s<br/>exponential backoff"]
  check_attempts{"Attempts<br/>&lt; 3?"}
  more_providers{"More providers<br/>in chain?"}
  success_node(["Return review text"])
  fail_node(["Raise ProviderError"])
  non_retryable["Non-retryable<br/>401 / 403 / 413"]

  start_node --> pick_provider
  pick_provider --> call_retry
  call_retry --> attempt
  attempt --> check_result
  check_result -->|"Yes"| success_node
  check_result -->|"No"| check_retryable
  check_retryable -->|"No"| non_retryable
  non_retryable --> more_providers
  check_retryable -->|"Yes"| check_attempts
  check_attempts -->|"Yes"| backoff
  backoff --> attempt
  check_attempts -->|"No"| more_providers
  more_providers -->|"Yes"| pick_provider
  more_providers -->|"No"| fail_node

  classDef core fill:#2563eb,stroke:#1d4ed8,color:#fff
  classDef engine fill:#059669,stroke:#047857,color:#fff
  classDef ext fill:#6b7280,stroke:#4b5563,color:#fff
  classDef data fill:#d97706,stroke:#b45309,color:#fff

  class start_node,success_node core
  class call_retry,attempt,backoff engine
  class check_result,check_retryable,check_attempts,more_providers data
  class non_retryable,fail_node,pick_provider ext
```

Non-retryable HTTP status codes (401 Unauthorized, 403 Forbidden, 413 Payload Too Large) skip the retry loop entirely and proceed to the next provider. All other errors (timeouts, 429 rate limits, 5xx) trigger exponential backoff retries.
