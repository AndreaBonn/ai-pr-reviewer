# Sicurezza

**Italiano** | [English](SECURITY.md)

[Torna al README](README.it.md)

---

## Panoramica

AI PR Reviewer è progettato per elaborare input potenzialmente non fidato (titoli PR, descrizioni, diff del codice) e inviarlo ad API LLM di terze parti. La sicurezza è una preoccupazione centrale, non un aspetto secondario.

---

## Quali Dati Vengono Inviati ai Provider LLM

L'action invia i seguenti dati all'API LLM configurata:

| Dato | Inviato | Note |
|------|:-------:|------|
| Titolo PR | Si | Sanitizzato prima dell'inclusione |
| Descrizione PR | Si | Sanitizzata prima dell'inclusione |
| Diff dei file (patch) | Si | Sanitizzati, troncati a 200 righe per file |
| Nomi dei file | Si | Sanitizzati |
| API key | **No** | Passate tramite header HTTP, mai nel corpo del prompt |
| Token GitHub | **No** | Usato solo per le chiamate API GitHub, mai inviato all'LLM |
| Secret del repository | **No** | Mai acceduti o trasmessi |
| Contenuto completo dei file | **No** | Solo le patch diff vengono inviate, non i file completi |

---

## Protezione da Prompt Injection

Tutto il contenuto fornito dall'utente (titolo PR, descrizione, nomi file, diff del codice) viene sanitizzato prima di essere incluso nel prompt LLM. Il sanitizzatore rileva e oscura pattern noti di prompt injection:

- `ignore previous instructions`, `disregard prior context`
- `you are now`, `from now on you must`, `act as DAN`
- `system override`, `override:`, `new instructions`
- Token di injection specifici per LLM: `<|system|>`, `[INST]`, `<<SYS>>`, `</s><s>`, `<system>`
- Confusione di ruoli: sequenze `Human:...Assistant:`
- Direttive `IMPORTANT:` progettate per sovrascrivere le istruzioni di sistema

Il contenuto fornito dall'utente viene:
1. Passato attraverso il filtro di pattern di injection (i pattern rilevati vengono sostituiti con `[REDACTED]`)
2. Troncato alla lunghezza massima (2000 caratteri per titolo/descrizione)
3. Racchiuso in blocchi di codice (` ``` `) nel prompt, con istruzioni esplicite all'LLM di trattarli come dati grezzi

Il system prompt istruisce esplicitamente l'LLM a ignorare qualsiasi istruzione incorporata nel contenuto utente.

---

## Sicurezza delle Credenziali

### I Secret Non Vengono Mai Esposti

- Le **API key** sono passate tramite header HTTP (`Authorization`, `x-api-key`, `x-goog-api-key`), mai incluse nei corpi delle richieste o nel testo del prompt
- **`Config.__repr__`** oscura tutti i campi sensibili — API key e token GitHub vengono visualizzati come `<REDACTED>` nei log
- I **messaggi di errore** (`LLMAPIError`) espongono solo il codice di stato HTTP e il nome del provider, mai i corpi delle risposte o le credenziali
- Il **token GitHub** è usato esclusivamente per le chiamate REST API GitHub e non viene mai inviato a nessun provider LLM

### Validazione degli Input

Tutti gli input di configurazione sono validati all'avvio:

| Input | Validazione |
|-------|------------|
| `LLM_PROVIDER` | Deve corrispondere a un nome di provider noto |
| `LLM_MODEL` | Solo alfanumerici, punti, trattini, underscore, due punti, slash. Max 100 caratteri. Path traversal (`..`) bloccato |
| `REPO_FULL_NAME` | Deve corrispondere al formato `owner/repo` (validato con regex) |
| `PR_NUMBER` | Deve essere un intero positivo |
| `MAX_FILES` | Limitato all'intervallo 1-100 |
| `REVIEW_LANGUAGE` | Deve essere nella whitelist delle lingue supportate |
| Conteggio provider/chiavi | Il numero di provider deve corrispondere al numero di API key |

---

## Sicurezza di Rete

- Tutte le chiamate API utilizzano esclusivamente HTTPS
- I timeout delle richieste sono impostati a 120 secondi per prevenire connessioni sospese
- Ogni chiamata al provider LLM utilizza gli header minimi necessari
- Nessun dato viene memorizzato nella cache o salvato tra le esecuzioni — l'action è stateless

---

## Gestione degli Errori

- Gerarchia di eccezioni personalizzata (`ReviewerError` → `ConfigError`, `ProviderError`, `GitHubAPIError`, `LLMAPIError`, `LLMParseError`) garantisce errori tipizzati e tracciabili
- Nessun `sys.exit()` nei moduli libreria — gli errori si propagano correttamente fino all'entry point
- Gli stack trace in produzione non espongono mai API key o token
- La paginazione dell'API GitHub è limitata per prevenire richieste incontrollate

---

## Dipendenze Minime

L'action ha una singola dipendenza di produzione: `requests`. Questo minimizza la superficie di attacco. Le dipendenze di sviluppo (`pytest`, `ruff`, `pip-audit`) non vengono installate in produzione.

La pipeline CI esegue `pip-audit` su ogni pull request per rilevare vulnerabilità note nelle dipendenze.

---

## Segnalare una Vulnerabilità

Se scopri una vulnerabilità di sicurezza, segnalala tramite [GitHub Issues](https://github.com/AndreaBonn/ai-pr-reviewer/issues) con l'etichetta `security`. Non includere dettagli sensibili nel titolo dell'issue.
