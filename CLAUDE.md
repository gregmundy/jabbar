# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Jabbar is a Python CLI called "Email Financial Intelligence" that pulls financial emails from multiple IMAP accounts, extracts transactions with a local LLM, analyzes the result with the Anthropic API, and displays insights in a Textual TUI. It also ingests bank statement CSVs as a parallel data source.

Entry point: `src/main.py` (invoke as `uv run python -m src.main <command>`).

Environment is managed by **uv** — `pyproject.toml` + `uv.lock` are authoritative. `uv sync` installs into `.venv/`. There is no `requirements.txt`. The project is configured as a non-package (`[tool.uv] package = false`) because the source layout is `src/` directly, not `src/jabbar/`.

## Commands

All commands take `--config` (default `config.yaml`) and `--data-dir` (default `data`). `config.yaml` must exist and match the shape in `config.example.yaml` — copy it first.

```bash
uv run python -m src.main fetch       # IMAP → data/raw/<provider>/<msg_id>.eml
uv run python -m src.main extract     # raw emails → data/extracted/transactions.json via local LLM
uv run python -m src.main analyze     # transactions → data/analysis/insights.json via Claude API
uv run python -m src.main tui         # launch Textual UI over cached data (no config required)
uv run python -m src.main run         # fetch → extract → analyze → tui in sequence
uv run python -m src.main ingest --csv statement.csv --source discover [--tag Personal]
```

Tests use pytest (in the `dev` dependency group):

```bash
uv run pytest                                           # runs everything; integration tests auto-skip
uv run pytest tests/test_config.py                      # single file
uv run pytest tests/test_config.py::test_load_config_valid  # single test
```

Integration tests in `tests/test_integration.py` require a real `config.yaml` AND a running LM Studio at `http://localhost:1234`; they self-skip otherwise.

## External dependencies that must be running

- **Local LLM** (LM Studio serving `qwen2.5-14b-instruct-mlx` on `http://localhost:1234/v1/chat/completions`) — required for `extract`. `main.py` hits `/v1/models` first and exits if unreachable.
- **Anthropic API** — `analyze` requires `ANTHROPIC_API_KEY` env var; the analyzer raises `RuntimeError` if unset.

## Pipeline architecture

The flow is a four-stage pipeline where each stage writes a file that the next stage reads, so stages can be re-run independently:

1. **fetch** (`src/fetch/email_fetcher.py` + `src/auth/`) — IMAP SEARCH per keyword, dedup msg IDs, fetch RFC822, cache as `.eml`. Two auth paths: `app_password` (Gmail/Yahoo) via `imap_auth.py`, `oauth2` (Hotmail/Outlook — Microsoft consumers endpoint, PKCE, local callback server on port 8400) via `oauth2_auth.py`. Tokens cached in `.hotmail_tokens.json` and refreshed automatically.
2. **extract** (`src/extract/llm_extractor.py`) — for each cached `.eml`, preprocess body via `src/preprocess/html_stripper.py` (prefers text/plain; falls back to stripped HTML), call local LLM with `EXTRACTION_PROMPT`, parse JSON (tolerates ```json fences). Output is append-only and deduped by `email_id` (= IMAP msg_id) so reruns resume.
3. **analyze** (`src/analyze/claude_analyzer.py`) — filters `is_transaction=true`, sends entire transaction list as one message to Claude with `ANALYSIS_PROMPT`. Claude returns alerts, recurring charges, categories, monthly summary, recommendations, scams. Invalid JSON is saved as `raw_response` rather than lost.
4. **tui** (`src/tui/app.py`) — loads `transactions.json` + any `transactions_*.json` (CSV sources), dedupes by `email_id`, overlays `analysis/insights.json`. Tabs: Alerts, Monthly, Categories, Merchants, Transactions, Recurring. The Merchants tab is computed locally in `build_merchant_summary` from raw transactions and overlays recurring metadata from Claude's insights when available.

### CSV ingest is a parallel path

`src/ingest/csv_ingest.py` writes to `data/extracted/transactions_<source>.json` — a separate file per source. The TUI loader globs `transactions*.json` and dedupes by `email_id` (CSV rows get a stable `csv-<source>-<md5>` id). CSV transactions have `extraction_source: "csv"` and skip the LLM entirely. `clean_merchant_name` + `MERCHANT_ALIASES` in that module normalize messy Discover-style descriptions; `CATEGORY_MAP` translates Discover categories into Jabbar's fixed category set.

### The `tag` field

Accounts and CSV imports can set an optional `tag` (e.g. `Personal`, `Work`) that flows through fetch → extract and into each transaction. The TUI only shows the Tag column in the Transactions table when at least one transaction is tagged.

## Category taxonomy (fixed)

The extraction prompt enforces a closed category set: `subscription | utilities | food_dining | food_delivery | services | shopping | insurance | medical | transportation | credit_card | other | scam`. `scam` is also how the extractor flags phishing — it sets `category: "scam"` AND `is_transaction: false` so scams don't pollute spending totals but are still surfaced in `scams_detected`.

## Data directory layout (gitignored)

```
data/
  raw/<provider>/<msg_id>.eml          # fetch output
  extracted/transactions.json          # email extract output
  extracted/transactions_<source>.json # CSV ingest output, one per source
  analysis/insights.json               # Claude analyze output
```

Secrets live in `config.yaml` and `.hotmail_tokens.json`, both gitignored.

## Working conventions

- No external HTTP client library — `urllib.request` is used throughout (extractor, OAuth2 flow, LM Studio healthcheck). Don't add `requests` unless there's a real reason.
- Dependency surface is intentionally tiny — see `pyproject.toml`. Textual + plotext for the UI, anthropic for analysis, pyyaml for config. That's it. Add new deps with `uv add <pkg>`.
- Imports of stage modules are done inside `cmd_*` functions in `main.py` so `jabbar tui` can run without importing `anthropic`/IMAP code.
- LLM JSON parsing uses the same fence-stripping helper pattern in both `llm_extractor.py` and `claude_analyzer.py` — keep them consistent if you touch one.
