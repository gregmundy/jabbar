# Jabbar

Email Financial Intelligence — pulls receipts, bills, and statements from your IMAP mailboxes, extracts transactions with a local LLM, analyzes them with Claude, and shows the result in a terminal UI.

## Prerequisites

- **[uv](https://github.com/astral-sh/uv)** for dependency management (`brew install uv`)
- **[LM Studio](https://lmstudio.ai/)** serving `qwen2.5-14b-instruct-mlx` on `http://localhost:1234` — required for the `extract` step
- **Anthropic API key** in `ANTHROPIC_API_KEY` — required for the `analyze` step
- App passwords / OAuth2 client IDs for the email accounts you want to scan

## Setup

```bash
uv sync                                  # install deps into .venv/
cp config.example.yaml config.yaml       # then edit with your accounts
export ANTHROPIC_API_KEY=sk-ant-...
```

`config.yaml` holds one entry per mail account under `accounts:`. Gmail and Yahoo use `auth: app_password`; Hotmail / Outlook use `auth: oauth2` with a Microsoft Entra client ID (the first run opens a browser to authorize, then caches tokens in `.hotmail_tokens.json`). The optional `tag:` field (e.g. `Personal`, `Work`) groups sources in the UI.

Both `config.yaml` and `.hotmail_tokens.json` are gitignored.

## Running the pipeline

The pipeline is four stages. Each writes a file under `data/` that the next stage reads, so you can re-run any stage independently.

```bash
uv run python -m src.main fetch      # IMAP → data/raw/<provider>/<msg_id>.eml
uv run python -m src.main extract    # raw emails → data/extracted/transactions.json  (needs LM Studio)
uv run python -m src.main analyze    # transactions → data/analysis/insights.json     (needs ANTHROPIC_API_KEY)
uv run python -m src.main tui        # terminal UI over cached data
```

Or run everything end-to-end and open the UI at the end:

```bash
uv run python -m src.main run
```

`fetch` and `extract` are both resumable: fetch skips emails already cached as `.eml`, and extract skips emails already present in `transactions.json`. Interrupt them freely.

## Ingesting bank CSVs

Some data isn't in email — credit card statements, for example. Export a CSV from your bank and ingest it directly:

```bash
uv run python -m src.main ingest --csv discover-2025.csv --source discover --tag Personal
```

CSV transactions land in `data/extracted/transactions_<source>.json` (separate file per source) and show up alongside email transactions in the UI. Re-running with the same CSV is idempotent — duplicates are skipped by a stable hash of `date + description + amount`.

The Discover CSV format is supported out of the box; other banks may need adjustments to `src/ingest/csv_ingest.py` (column names and the `CATEGORY_MAP` / `MERCHANT_ALIASES` lookups).

## The TUI

`uv run python -m src.main tui` opens a Textual app with tabs:

- **Alerts** — red/yellow/green flags from Claude (scams, price hikes, confirmed recurring)
- **Monthly** — bar chart of spending per month
- **Categories** — pie of spending by category
- **Merchants** — per-merchant totals, averages, and recurring overlay
- **Transactions** — filterable raw transaction list
- **Recurring** — Claude's detected recurring charges with monthly/annual cost

`q` quits, `d` toggles dark/light.

The TUI reads only from `data/` and does not require `config.yaml`, a local LLM, or an API key — it's safe to hand off a `data/` directory and run the UI on another machine.

## Tests

```bash
uv run pytest                        # all tests; integration tests auto-skip without config.yaml + LM Studio
uv run pytest tests/test_config.py   # single file
```

## Project layout

```
src/
  main.py              # CLI entry point
  auth/                # IMAP app-password + Microsoft OAuth2 (PKCE)
  fetch/               # IMAP search + cache as .eml
  preprocess/          # HTML → text body extraction
  extract/             # local LLM transaction extraction
  analyze/             # Claude analysis
  ingest/              # CSV statement ingestion
  tui/                 # Textual UI + charts
data/                  # gitignored cache — raw/, extracted/, analysis/
```
