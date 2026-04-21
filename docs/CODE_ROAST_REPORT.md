# Code Roast Report — ai-pr-reviewer

## Panoramica

- **Linguaggi rilevati**: Python 3.11+
- **File analizzati**: 10 (5 sorgente + 5 test)
- **Problemi totali**: 13 (CRITICAL 0 · MAJOR 4 · MINOR 6 · NITPICK 3)
- **Contesto rilevato**: GitHub Action pubblica, ruff configurato (E/F/I/N/W/UP), pytest, CI/CD con `test.yml`, nessun mypy
- **Giudizio complessivo**: Codebase solida e ben strutturata per un progetto di questa dimensione — i problemi rimasti riguardano quasi tutti la robustezza dei test e alcuni edge case nel retry logic.

---

## CRITICAL (0 problemi)

Nessuna vulnerabilità critica rilevata.

---

## MAJOR (4 problemi)

### TESTING — Retry logic testato con `MagicMock` che bypassa il type check dell'eccezione

**File**: `tests/test_providers.py` (righe 169–177)
**Problema**: `test_exits_after_max_retries` imposta `provider.call.side_effect = LLMAPIError(...)` — un'istanza di eccezione, non una classe. Quando `side_effect` è un'istanza, mock la solleva correttamente; ma se in futuro `call_llm_with_retry` cambiasse la lista di eccezioni catturate, il test continuerebbe a passare perché `MagicMock.call` è già mockato e non invoca il codice reale. Il test verifica che `SystemExit` venga sollevato dopo esaurimento retry, ma non verifica che il numero di tentativi sia effettivamente `LLM_MAX_RETRIES`. Con 2 retry attuali, `mock_sleep` dovrebbe essere chiamato una sola volta: questo non è asserito.

```python
# Attuale — non verifica il conteggio retry
with pytest.raises(SystemExit):
    call_llm_with_retry(provider, system="s", user="u")

# Corretto
with pytest.raises(SystemExit):
    call_llm_with_retry(provider, system="s", user="u")

assert provider.call.call_count == LLM_MAX_RETRIES
mock_sleep.assert_called_once()  # solo 1 sleep tra 2 tentativi
```

---

### TESTING — `LLMParseError` ritenuta ritentabile senza test che verifichi il comportamento corretto

**File**: `reviewer/providers.py` (riga 230), `tests/test_providers.py` (righe 179–189)
**Problema**: `call_llm_with_retry` ritenta su `LLMParseError`, il che è discutibile: se il provider risponde con HTTP 200 ma struttura JSON inattesa, ritentare la stessa chiamata produrrà quasi certamente lo stesso errore (il modello non cambia risposta tra un retry e l'altro). Il retry ha senso per errori transitori di rete (`requests.RequestException`) e per errori server temporanei (`LLMAPIError` con 5xx). Per `LLMParseError` è uno spreco di tempo e token.

Il test `test_retries_on_parse_error` verifica che il retry avvenga — ma non mette in discussione se dovrebbe avvenire.

**Come fixare**: Rimuovere `LLMParseError` dalla lista delle eccezioni ritentabili in `call_llm_with_retry`; fare fail immediato con `sys.exit(1)` loggando il provider name e un hint su come segnalare il bug. Aggiornare il test per verificare il nuovo comportamento (zero retry su parse error).

---

### ARCHITECTURE — `sys.exit` nei moduli interni rende il codice non componibile

**File**: `reviewer/config.py` (righe 65, 77, 86), `reviewer/providers.py` (righe 216, 248), `reviewer/github_client.py` (riga 76)
**Problema**: `sys.exit(1)` è disseminato in sei punti nei moduli di libreria. Questo accoppia il comportamento di terminazione al codice che dovrebbe essere pura logica. Conseguenze concrete:

1. I test che vogliono verificare il comportamento di errore devono fare `pytest.raises(SystemExit)` — non possono verificare il messaggio di errore specifico.
2. Se si volesse aggiungere un wrapper CLI alternativo a `review.py`, ogni errore di configurazione terminerebbe il processo invece di permettere al caller di decidere.
3. L'entry point `review.py` non può fare cleanup prima di uscire (es. chiudere connessioni, scrivere log finali).

**Come fixare**: Nei moduli interni, sollevare eccezioni custom (`ConfigError`, `ProviderError`) invece di chiamare `sys.exit`. Centralizzare la gestione in `review.py::main()`:

```python
# review.py
def main() -> None:
    try:
        cfg = Config.from_env()
        ...
    except ConfigError as exc:
        log.error("%s", exc)
        sys.exit(1)
```

---

### TESTING — Nessun test per `main()` in `review.py`

**File**: `review.py`
**Problema**: L'entry point `main()` non ha copertura di test. Contiene logica non banale: il branch "no reviewable files" che posta un commento di fallback, e l'orchestrazione completa del flusso. Un refactoring errato di `main()` non verrebbe rilevato da nessun test esistente.

**Come fixare**: Aggiungere `tests/test_review.py` con almeno due scenari: flusso completo con mock di `GitHubClient` e `LLMProvider`, e il branch "nessun file reviewabile".

---

## MINOR (6 problemi)

### RESILIENCE — Retry con backoff lineare, non esponenziale

**File**: `reviewer/providers.py` (riga 233)
**Problema**: Il commento della funzione dice "exponential backoff" ma l'implementazione è lineare: `delay = LLM_RETRY_BASE_DELAY * attempt`, che produce 5s e 10s — non 5s e 25s come sarebbe esponenziale. Non è un bug critico (funziona comunque), ma il docstring è fuorviante.

```python
# Attuale (lineare)
delay = LLM_RETRY_BASE_DELAY * attempt  # 5, 10

# Esponenziale (coerente con il docstring)
delay = LLM_RETRY_BASE_DELAY * (2 ** (attempt - 1))  # 5, 25
```

---

### ROBUSTNESS — `f["filename"]` senza `.get()` nella lista `skipped`

**File**: `reviewer/filters.py` (riga 53)
**Problema**: `skipped = [f["filename"] for f in filtered[max_files:]]` — tutti i file oltre `max_files` sono stati già filtrati e validati (hanno `filename` e `patch`), ma accedere con `[]` invece di `.get()` è inconsistente col resto della funzione che usa `.get()` ovunque (righe 38, 49, 58). Se un dict malformato entra nell'input, crasha con `KeyError` invece di un errore chiaro.

---

### DESIGN — `Config.ignore_patterns` dichiarato come `list[str]` su frozen dataclass

**File**: `reviewer/config.py` (riga 27)
**Problema**: La dataclass è `frozen=True`, ma `ignore_patterns: list[str]` è un tipo mutabile. Il freeze impedisce la riassegnazione dell'attributo ma non la mutazione della lista (`cfg.ignore_patterns.append("x")` funziona silenziosamente). Per una dataclass veramente immutabile, usare `tuple[str, ...]`.

```python
# Attuale
ignore_patterns: list[str]

# Corretto per frozen dataclass
ignore_patterns: tuple[str, ...]

# In from_env():
ignore_patterns=tuple(patterns),
```

---

### TESTING — Test `test_does_not_leak_api_key` verifica string literals fragili

**File**: `tests/test_providers.py` (righe 53–55)
**Problema**: Il test asserisce che `"sk-"` e `"key"` non siano nella rappresentazione stringa dell'errore. Questo è un test di stringa letterale fragile: se la rappresentazione dell'errore cambia, il test potrebbe passare anche se la chiave viene esposta in un altro formato. Inoltre, `LLMAPIError.__init__` riceve `provider` come stringa, non l'API key — non c'è meccanismo per cui la chiave possa mai apparire in questo errore. Il test verifica un'invariante che non può essere violata dall'implementazione attuale.

**Come fixare**: Rimuovere il test `test_does_not_leak_api_key` (è tautologico) e aggiungere invece un test che verifichi che `_post_json` non includa l'API key nel messaggio di `LLMAPIError`:

```python
def test_llm_api_error_does_not_include_response_body(self) -> None:
    # Verifica che il messaggio non contenga dati della risposta
    # (che potrebbero includere error details con info sensibili)
    err = LLMAPIError(status_code=403, provider="GroqProvider")
    assert len(str(err)) < 100  # nessun payload JSON nel messaggio
```

---

### DESIGN — `action.yml` usa `pip install` invece di `uv`

**File**: `action.yml` (riga 39)
**Problema**: L'installazione usa `pip install -r requirements.txt`. Il progetto ha `pyproject.toml` con `uv` come toolchain dichiarata (`dependency-groups` nella sezione dev). Usare `uv pip install` o `uv sync` sarebbe più coerente, più veloce (uv è significativamente più rapido di pip), e garantisce la stessa versione delle dipendenze del dev environment.

```yaml
# Attuale
run: pip install -r ${{ github.action_path }}/requirements.txt

# Coerente col toolchain del progetto
- uses: astral-sh/setup-uv@v4
- run: uv pip install -r ${{ github.action_path }}/requirements.txt
```

---

### TESTING — Nessun test per il branch `_check_rate_limit` in `GitHubClient`

**File**: `tests/test_github_client.py`, `reviewer/github_client.py` (righe 66–76)
**Problema**: `_check_rate_limit` chiama `sys.exit(1)` quando riceve HTTP 403. Questo path non è testato. Il test esistente per `TestFindExistingBotComment` usa `MagicMock(spec=GitHubClient)` che bypassa completamente l'implementazione reale. Non c'è nessun test che verifichi il comportamento di `_paginated_get` o `_check_rate_limit` con risposte 403.

---

## NITPICK (3 problemi)

### `requirements.txt` è un file di una riga con versione non pinnata

**File**: `requirements.txt`
`requests>=2.31.0` — versione lower-bound, non pinnata. In una GitHub Action pubblica, questo significa che ogni run installa la versione più recente disponibile. Per riproducibilità, usare una versione esatta o derivare da `uv.lock`.

---

### `action.yml` — `language` input non documenta tutte le lingue supportate

**File**: `action.yml` (riga 18)
La description dice `"english" or "italian"` ma `config.py` supporta anche `french`, `spanish`, `german`. La documentazione è incompleta.

---

### `_review_template()` — funzione di 57 righe, supera il limite

**File**: `reviewer/prompt.py` (righe 71–128)
La funzione restituisce una stringa costante. Non ha logica interna. Potrebbe essere dichiarata come costante di modulo `REVIEW_TEMPLATE = "..."` invece di una funzione, eliminando il problema del limite di righe e rendendo più chiaro che non ha comportamento dinamico.

---

## Priorità di Refactoring Consigliate

1. **`sys.exit` nei moduli interni** — Sostituire con eccezioni custom. Sblocca testabilità di `main()`, permette cleanup prima dell'uscita, elimina l'accoppiamento tra logica di libreria e processo. Fix sistematico che impatta config, providers, github_client.

2. **Test per `main()`** — Aggiungere `tests/test_review.py`. Il flusso completo non è coperto da nessun test esistente; un refactoring silenzioso di `review.py` è attualmente invisibile.

3. **Rimuovere `LLMParseError` dal retry** — Risposte 200 con schema errato non cambiano al retry. Fail immediato con errore chiaro. Risparmia latenza (fino a 15s di sleep inutile) e token LLM consumati.

4. **`ignore_patterns: tuple[str, ...]`** — Fix a una riga con impatto semantico: la frozen dataclass diventa veramente immutabile.

5. **Documentazione `action.yml`** — Aggiornare il campo `language` con tutte le 5 lingue supportate. Errore puramente documentativo ma visibile agli utenti dell'Action.

---

## Verdict finale

Il codice è ben scritto: architettura a strati chiara, Strategy pattern applicato correttamente, type hints completi, logging strutturato. I problemi rimasti sono concentrati in due aree: il `sys.exit` pervasivo nei moduli interni (scelta deliberata ma che ostacola la testabilità) e alcuni gap nella test suite, tra cui l'assenza totale di copertura per `main()`. Non è un codebase da refactorare — è un codebase da rifinire.

---

*Report generato il 2026-04-21*
