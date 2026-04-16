# Jabbar — Design Specification

**Jabbar** — Email-powered financial intelligence.

## Purpose

A CLI tool that connects to multiple email accounts (Gmail, Yahoo, Hotmail/Outlook), scans for financial emails, extracts transaction data using a local LLM, analyzes spending patterns using Claude API, and presents results in an interactive TUI (terminal UI).

The goal is to help the user find where they're hemorrhaging cash: forgotten subscriptions, price increases, missed payments, recurring charges, and scam/phishing emails.

## Validated Technical Decisions

The following were tested and validated during the design phase. Do not change these choices unless there is a specific technical reason.

### Email Connectivity
- **IMAP** is the protocol for all providers
- **Gmail**: IMAP with app password, host `imap.gmail.com:993`, search `"[Gmail]/All Mail"` (not just INBOX — 45% of financial emails were in archive)
- **Yahoo**: IMAP with app password, host `imap.mail.yahoo.com:993`, search `INBOX`
- **Hotmail/Outlook**: IMAP with OAuth2+PKCE (basic auth is blocked by Microsoft), host `outlook.office365.com:993`, search `INBOX`
  - OAuth2 uses Microsoft Entra app registration with "Mobile and desktop" platform type
  - "Allow public client flows" must be enabled in Entra
  - Scope: `https://outlook.office.com/IMAP.AccessAsUser.All offline_access`
  - Auth endpoint: `https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize`
  - Token endpoint: `https://login.microsoftonline.com/consumers/oauth2/v2.0/token`
  - Uses PKCE (S256 challenge) — no client secret needed
  - XOAUTH2 SASL mechanism for IMAP auth: `user={email}\x01auth=Bearer {token}\x01\x01`
  - Tokens (including refresh token) are cached locally and reused

### IMAP Search Strategy
- Search within a configurable date range (default: 24 months)
- Use individual keyword searches, NOT compound OR queries (Yahoo's IMAP rejects complex OR nesting)
- Keywords: `receipt`, `payment`, `invoice`, `order`, `charge`, `billing`, `subscription`, `renewal`, `purchase`, `transaction`, `statement`, `autopay`, `trial`, `refund`
- Deduplicate message IDs across keyword searches before processing
- Date format for IMAP SINCE: `%d-%b-%Y` (e.g., `16-Apr-2024`)

### HTML Preprocessing
- A lightweight HTML-to-text stripper is **required** before sending email content to the local LLM
- This was validated to improve accuracy (6/8 to 8/8) and speed (35s avg to 9s avg per email)
- Implementation: subclass `html.parser.HTMLParser`, skip `<style>`, `<script>`, `<head>` tags, insert `\n` on block elements (`br`, `p`, `div`, `tr`, `td`, `th`, `li`, `h1`-`h4`), collapse whitespace
- Prefer plain text MIME part when available (>50 chars); fall back to stripped HTML
- Truncate body to 8000 chars after stripping

### Local LLM Extraction
- **Model**: Qwen2.5-7B-Instruct (MLX 4-bit quantization for Apple Silicon)
- **Runtime**: LM Studio exposing OpenAI-compatible API on `http://localhost:1234`
- **Context**: 32768 tokens
- **Temperature**: 0.1
- **Max tokens**: 500
- Uses a single generic extraction prompt (no per-sender templates needed)
- The LLM does NOT receive raw HTML — always preprocessed text
- No "architect" LLM needed for per-email extraction — the local model handles it

### Extraction Prompt (validated, use exactly this)

```
You are a financial data extractor. Analyze this email and extract any financial transaction.

Return ONLY valid JSON:
{
  "is_transaction": boolean,
  "merchant": string or null,
  "date": "YYYY-MM-DD" or null,
  "amount": number or null,
  "category": "subscription|utilities|food_dining|food_delivery|services|shopping|insurance|medical|transportation|credit_card|other|scam",
  "description": "brief description" or null,
  "is_recurring": boolean or null,
  "payment_method": "description" or null
}

Rules:
- is_transaction is true ONLY for actual charges, payments, receipts, invoices, or statements with amounts
- Marketing, promos, and rewards emails are NOT transactions
- For credit card statements, extract the statement balance as the amount
- Extract the most prominent/total dollar amount, not subtotals
- If the email appears to be a scam or phishing attempt, set category to "scam" and is_transaction to false
```

Input format sent to the LLM: `Subject: {subject}\n\nBody:\n{body}`

### Claude API Analysis
- Used ONLY for the final analysis pass — one API call over the aggregated structured JSON
- Claude receives the array of extracted transactions (no raw email content)
- Claude's job: detect patterns, group recurring charges, identify anomalies (price increases, missed payments, potential scams), generate actionable insights
- This keeps cost minimal and keeps raw email data local

### TUI Framework
- **Textual** for the terminal UI
- **textual-plotext** for charts (bar charts, line charts rendered as Unicode in terminal)
- Tabs: Alerts, Monthly Spending, Categories, Transactions, Recurring
- Sortable/filterable data tables
- Color-coded severity levels for alerts

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        config.yaml                          │
│  (email accounts, date range, LLM endpoint, Claude API key) │
└──────────────────────────┬──────────────────────────────────┘
                           │
                    ┌──────▼──────┐
                    │    Auth     │
                    │             │
                    │ Gmail: IMAP │
                    │ Yahoo: IMAP │
                    │ Hotmail:    │
                    │  OAuth2+    │
                    │  PKCE       │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │   Fetch     │
                    │             │
                    │ IMAP search │
                    │ by keyword  │
                    │ deduplicate │
                    │ download    │
                    │ cache raw   │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │ Preprocess  │
                    │             │
                    │ MIME parse  │
                    │ HTML strip  │
                    │ text clean  │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  Extract    │
                    │             │
                    │ Local LLM   │
                    │ (Qwen 7B)   │
                    │ → JSON per  │
                    │   email     │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  Analyze    │
                    │             │
                    │ Claude API  │
                    │ patterns,   │
                    │ anomalies,  │
                    │ insights    │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │   Report    │
                    │             │
                    │ Textual TUI │
                    │ with charts │
                    │ and tables  │
                    └─────────────┘
```

Each stage writes output to disk so stages can be re-run independently:
- `data/raw/{provider}/{message_id}.eml` — cached raw emails
- `data/extracted/transactions.json` — LLM extraction results
- `data/analysis/insights.json` — Claude analysis results
- `.hotmail_tokens.json` — OAuth2 tokens (gitignored)

## File Structure

```
jabbar/
├── config.yaml              # User configuration (gitignored)
├── config.example.yaml      # Template with placeholder values
├── requirements.txt         # Python dependencies
├── venv/                    # Virtual environment
├── src/
│   ├── __init__.py
│   ├── main.py              # CLI entry point, orchestrates pipeline
│   ├── config.py            # Load and validate config.yaml
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── imap_auth.py     # App password IMAP auth (Gmail, Yahoo)
│   │   └── oauth2_auth.py   # OAuth2+PKCE flow (Hotmail/Outlook)
│   ├── fetch/
│   │   ├── __init__.py
│   │   └── email_fetcher.py # IMAP search, download, cache
│   ├── preprocess/
│   │   ├── __init__.py
│   │   └── html_stripper.py # HTML to clean text
│   ├── extract/
│   │   ├── __init__.py
│   │   └── llm_extractor.py # Local LLM extraction via OpenAI-compatible API
│   ├── analyze/
│   │   ├── __init__.py
│   │   └── claude_analyzer.py  # Claude API final analysis
│   └── tui/
│       ├── __init__.py
│       ├── app.py           # Main Textual app
│       ├── screens/
│       │   ├── __init__.py
│       │   ├── alerts.py    # Alerts tab
│       │   ├── monthly.py   # Monthly spending chart
│       │   ├── categories.py # Category breakdown chart
│       │   ├── transactions.py # Transaction table
│       │   └── recurring.py # Recurring charges table
│       └── widgets/
│           ├── __init__.py
│           └── charts.py    # PlotextPlot subclasses
├── data/                    # Cached data (gitignored)
│   ├── raw/
│   │   ├── gmail/
│   │   ├── yahoo/
│   │   └── hotmail/
│   ├── extracted/
│   │   └── transactions.json
│   └── analysis/
│       └── insights.json
├── docs/
│   └── superpowers/
│       └── specs/
│           └── 2026-04-16-analyze-bills-design.md
└── .gitignore
```

## Configuration

`config.yaml` format:

```yaml
accounts:
  - name: gmail
    provider: gmail
    email: gregmundy@gmail.com
    auth: app_password
    password: "xxxx xxxx xxxx xxxx"
    imap_host: imap.gmail.com
    imap_port: 993
    mailbox: '"[Gmail]/All Mail"'

  - name: yahoo
    provider: yahoo
    email: dragenpenn2@yahoo.com
    auth: app_password
    password: "xxxxxxxxxxxxxxxx"
    imap_host: imap.mail.yahoo.com
    imap_port: 993
    mailbox: INBOX

  - name: hotmail
    provider: hotmail
    email: gmundy2@hotmail.com
    auth: oauth2
    client_id: "fa0ce242-f1fc-43a9-a172-12113cf7cdbd"
    redirect_uri: "http://localhost:8400/callback"
    token_file: ".hotmail_tokens.json"
    imap_host: outlook.office365.com
    imap_port: 993
    mailbox: INBOX

scan:
  months_back: 24
  keywords:
    - receipt
    - payment
    - invoice
    - order
    - charge
    - billing
    - subscription
    - renewal
    - purchase
    - transaction
    - statement
    - autopay
    - trial
    - refund

extraction:
  llm_endpoint: "http://localhost:1234/v1/chat/completions"
  llm_model: "qwen2.5-7b-instruct-mlx"
  temperature: 0.1
  max_tokens: 500
  max_body_chars: 8000

analysis:
  claude_model: "claude-sonnet-4-20250514"
  # API key loaded from ANTHROPIC_API_KEY env var
```

## Component Specifications

### auth/imap_auth.py

Connects to IMAP using app password. Returns an authenticated `imaplib.IMAP4_SSL` connection.

```python
def connect_imap(host: str, port: int, email: str, password: str) -> imaplib.IMAP4_SSL:
    """Connect and login via app password. Returns authenticated IMAP connection."""
```

### auth/oauth2_auth.py

Handles Microsoft OAuth2+PKCE flow. Caches tokens to disk. Refreshes automatically when expired.

```python
def get_oauth2_connection(config: dict) -> imaplib.IMAP4_SSL:
    """
    1. Check for cached tokens in token_file
    2. If valid, use access_token for XOAUTH2 IMAP auth
    3. If expired, use refresh_token to get new access_token
    4. If no tokens, launch browser auth flow:
       a. Generate PKCE code_verifier + code_challenge (S256)
       b. Start local HTTP server on redirect_uri port
       c. Open browser to Microsoft authorize endpoint
       d. Receive auth code via callback
       e. Exchange auth code + code_verifier for tokens
       f. Cache tokens to disk
    5. Authenticate IMAP with XOAUTH2
    """
```

XOAUTH2 auth string format: `user={email}\x01auth=Bearer {access_token}\x01\x01`

### fetch/email_fetcher.py

Searches mailbox for financial emails and caches them locally.

```python
def fetch_financial_emails(connection: imaplib.IMAP4_SSL, config: dict) -> list[dict]:
    """
    1. Select mailbox (readonly=True)
    2. Calculate SINCE date from months_back config
    3. For each keyword, run: SEARCH SINCE {date} SUBJECT "{keyword}"
    4. Deduplicate message IDs across all keyword searches
    5. For each unique message ID:
       a. Check if already cached in data/raw/{provider}/{msg_id}.eml
       b. If not cached, FETCH (RFC822) and save to cache
    6. Return list of {msg_id, provider, cached_path}
    """
```

Important IMAP notes:
- Yahoo rejects compound OR queries — use individual SEARCH commands per keyword
- Gmail requires quoted mailbox name: `'"[Gmail]/All Mail"'`
- Always use `readonly=True` when selecting mailbox
- Handle connection timeouts gracefully

### preprocess/html_stripper.py

Converts HTML email bodies to clean text for LLM extraction.

```python
class SmartHTMLExtractor(HTMLParser):
    """
    Subclass html.parser.HTMLParser:
    - Skip content inside <style>, <script>, <head> tags
    - Insert newline on block elements: br, p, div, tr, td, th, li, h1-h4
    - Collect all other text content
    - Post-process: collapse whitespace per line, remove empty lines
    """

def get_email_body(raw_email: bytes) -> tuple[str, str]:
    """
    Parse MIME message. Return (cleaned_body, source_type).
    1. Walk MIME parts
    2. If text/plain exists and len > 50: use it, truncate to 8000 chars
    3. Else if text/html exists: strip HTML, truncate to 8000 chars
    4. Return (body_text, "plain" | "html_stripped" | "none")
    """
```

### extract/llm_extractor.py

Sends preprocessed emails to local LLM for structured extraction.

```python
EXTRACTION_PROMPT = """You are a financial data extractor. Analyze this email and extract any financial transaction.

Return ONLY valid JSON:
{
  "is_transaction": boolean,
  "merchant": string or null,
  "date": "YYYY-MM-DD" or null,
  "amount": number or null,
  "category": "subscription|utilities|food_dining|food_delivery|services|shopping|insurance|medical|transportation|credit_card|other|scam",
  "description": "brief description" or null,
  "is_recurring": boolean or null,
  "payment_method": "description" or null
}

Rules:
- is_transaction is true ONLY for actual charges, payments, receipts, invoices, or statements with amounts
- Marketing, promos, and rewards emails are NOT transactions
- For credit card statements, extract the statement balance as the amount
- Extract the most prominent/total dollar amount, not subtotals
- If the email appears to be a scam or phishing attempt, set category to "scam" and is_transaction to false"""


def extract_transaction(subject: str, body: str, config: dict) -> dict:
    """
    Send to local LLM via OpenAI-compatible API.
    POST to {llm_endpoint} with:
      model: config.llm_model
      messages: [system: EXTRACTION_PROMPT, user: "Subject: {subject}\n\nBody:\n{body}"]
      temperature: 0.1
      max_tokens: 500
    Parse response JSON. Handle malformed JSON gracefully (regex extract from markdown fences).
    Return extracted dict with added fields: email_id, provider, raw_subject, extraction_source.
    """

def extract_all(emails: list[dict], config: dict) -> list[dict]:
    """
    Process all emails through extract_transaction.
    Show progress (N/M processed).
    Skip already-extracted emails (check transactions.json cache).
    Save results incrementally to data/extracted/transactions.json.
    Expected throughput: ~9 seconds per email on Apple Silicon with Qwen 7B MLX 4-bit.
    """
```

JSON parsing note: The local LLM sometimes wraps JSON in markdown fences (` ```json ... ``` `). The parser must handle this — strip fences before `json.loads()`.

### analyze/claude_analyzer.py

Sends structured transaction data to Claude API for high-level analysis.

```python
ANALYSIS_PROMPT = """You are a financial analyst. I'm giving you a JSON array of transactions extracted from email over the last 24 months across multiple email accounts (Gmail, Yahoo, Hotmail).

Your job is to analyze this data and return a structured JSON report. Specifically:

1. **Recurring charges**: Group transactions by merchant. Identify which are recurring (same merchant, regular interval). Calculate monthly cost, detect frequency (monthly, quarterly, annual), and flag any price changes over time.

2. **Alerts**: Flag problems that need attention:
   - "red" severity: scams/phishing, failed/missed payments, accounts at risk
   - "yellow" severity: price increases, billing action required, unusually high charges
   - "green" severity: confirmed recurring charges (informational)

3. **Duplicate detection**: Multiple emails often refer to the same transaction (e.g., "Scheduled Payment", "Payment Received", and the statement all reference one Discover Card payment). Deduplicate — count the charge once.

4. **Categories**: Sum spending by category. Normalize merchant names (e.g., group "Discover Card" variants together).

5. **Monthly summary**: Total spending per month with transaction count.

6. **Recommendations**: Actionable suggestions — what to cancel, investigate, negotiate, or fix. Include estimated savings where possible.

7. **Scam detection**: Emails flagged as category "scam" by the extractor. Add any additional context about why they're suspicious.

Return ONLY valid JSON matching this schema:
{
    "alerts": [{"severity": "red|yellow|green", "type": "string (e.g., missed_payment, price_increase, scam, failed_payment, action_required, recurring)", "merchant": "string", "message": "string", "details": "string with dates and amounts"}],
    "recurring": [{"merchant": "string", "monthly_cost": number, "annual_cost": number, "frequency": "monthly|quarterly|annual", "trend": "stable|increasing|decreasing", "months_active": number, "category": "string"}],
    "categories": {"category_name": total_as_number},
    "monthly_summary": [{"month": "YYYY-MM", "total": number, "transaction_count": number}],
    "recommendations": [{"action": "cancel|investigate|negotiate|fix", "merchant": "string", "potential_monthly_savings": number, "reason": "string"}],
    "scams_detected": [{"merchant": "string", "date": "YYYY-MM-DD", "amount_claimed": number, "description": "string", "indicators": ["string"]}]
}
"""

def analyze_transactions(transactions: list[dict], config: dict) -> dict:
    """
    Filter to is_transaction=True entries only.
    Send as JSON array to Claude API with ANALYSIS_PROMPT as system message.
    Use anthropic Python SDK.
    Parse response JSON (handle markdown fences).
    Save to data/analysis/insights.json.
    """
```

### Scam Detection Responsibilities

The local LLM and Claude have different scam detection roles:
- **Local LLM** (per-email): Sets `category: "scam"` on obviously fake purchase/charge notifications. This is a first-pass flag based on email content alone.
- **Claude** (analysis pass): Reviews all scam-flagged emails, adds context (e.g., "SPF failed, sender domain mismatch"), and may flag additional suspicious patterns the local model missed (e.g., a merchant that only appears once with an unusually high amount).

### tui/app.py

Main Textual application.

```python
class JabbarApp(App):
    """
    TUI with tabbed interface:
    
    Header: Shows "Jabbar" title with clock
    
    Summary bar: Total tracked spend, monthly average, emails scanned, connected providers
    
    Tabs:
    1. Alerts — Color-coded list of flagged items
       - Red: scams, missed payments, failed payments
       - Yellow: price increases, action required items
       - Green: recurring charges confirmed
       
    2. Monthly — Bar chart (via textual-plotext) showing monthly spend over time
       - X axis: months
       - Y axis: USD
       
    3. Categories — Horizontal bar chart of spending by category
       - Categories: subscription, utilities, food_dining, food_delivery, 
         services, shopping, insurance, medical, transportation, credit_card
         
    4. Transactions — Sortable DataTable
       - Columns: Date, Provider, Merchant, Amount, Category, Description, Payment Method
       - Sortable by any column
       - Row cursor for selection
       - Zebra striping
       
    5. Recurring — DataTable of recurring charges
       - Columns: Merchant, Frequency, Monthly Cost, Total (24mo), Trend, Status
       - Sorted by monthly cost descending
    
    Footer: Keybindings — q=quit, d=dark/light toggle, /=filter, tab=next tab
    
    Data source: Loads from data/extracted/transactions.json and data/analysis/insights.json
    """
```

## Branding

- Product name: **Jabbar**
- TUI header title: "Jabbar"
- TUI subtitle: "Email Financial Intelligence"
- CLI command: `jabbar` (via setuptools entry_points or a shell alias to `python -m src.main`)

## CLI Entry Point

```
Usage: jabbar [command]  # or: python -m src.main [command]

Commands:
  setup     — Interactive config creation (prompts for email accounts)
  fetch     — Connect to all accounts and download financial emails
  extract   — Run local LLM extraction on cached emails
  analyze   — Run Claude API analysis on extracted transactions
  run       — Full pipeline: fetch → extract → analyze → display TUI
  tui       — Launch TUI with existing data (no fetching/extraction)

Default (no command): run
```

## Dependencies

```
# requirements.txt
textual>=0.80.0
textual-plotext>=1.0.0
plotext>=5.3.0
anthropic>=0.40.0
pyyaml>=6.0
```

No other dependencies. The following are stdlib:
- `imaplib` — IMAP connectivity
- `email` — MIME parsing
- `html.parser` — HTML stripping
- `http.server` — OAuth2 callback server
- `json`, `urllib`, `hashlib`, `secrets`, `base64` — OAuth2 PKCE flow

Do NOT use LangChain, LlamaIndex, or any LLM framework. Direct HTTP calls to LM Studio's API.

## .gitignore

```
venv/
data/
config.yaml
.hotmail_tokens.json
__pycache__/
*.pyc
.env
```

## Performance Expectations

Based on testing with real data:

| Stage | Speed | Notes |
|-------|-------|-------|
| IMAP fetch (753 emails) | ~3 min | One-time; cached after first run |
| HTML stripping | <1s total | In-memory, fast |
| LLM extraction | ~9s per email | ~113 min for 753 emails; cached, incremental |
| Claude analysis | ~30s | Single API call over JSON |
| TUI launch | <2s | Reads cached JSON |

Re-runs after initial fetch+extract are fast — only new emails need processing.

## Data Volumes (from testing)

| Provider | Total Emails | Financial Emails | With Amounts |
|----------|-------------|-----------------|--------------|
| Gmail (All Mail) | 13,235 | 753 | ~185 (regex), more with LLM |
| Yahoo | 2,111 | 361 | TBD |
| Hotmail | 629 | 134 | TBD |
| **Total** | **15,975** | **1,248** | — |

## Error Handling

| Scenario | Behavior |
|----------|----------|
| LM Studio not running | Print clear error: "Local LLM not available at {endpoint}. Start LM Studio and load Qwen2.5-7B-Instruct." Exit. |
| LM Studio returns malformed JSON | Attempt regex extraction from markdown fences. If still invalid, log warning, skip email, continue processing. |
| IMAP connection timeout | Retry up to 3 times with exponential backoff (2s, 4s, 8s). If all fail, log error, skip provider, continue with others. |
| IMAP auth failure | Print clear error with provider-specific guidance (e.g., "Gmail: check app password" or "Hotmail: re-run OAuth flow"). |
| OAuth2 token expired | Automatically refresh using refresh_token. If refresh fails, prompt user to re-authenticate via browser. |
| OAuth2 refresh token expired | Delete cached token file, re-run full browser auth flow. |
| Claude API key missing | Print error: "Set ANTHROPIC_API_KEY environment variable." Exit. |
| Claude API error | Print error with details. Analysis can be skipped — TUI can display raw extracted data without insights. |
| config.yaml missing | Print error pointing to config.example.yaml. Exit. |
| No financial emails found | Display empty TUI with a message: "No financial emails found. Check your config and date range." |

## Progress Display

The extraction stage processes ~1,248 emails at ~9s each (~3 hours total for first run). Progress must be visible:

- Print: `Extracting: [142/753] gmail — "Your receipt from Anthropic" (18.9%)`
- Show elapsed time and estimated time remaining
- Save results incrementally after each email (not in a batch at the end) — if the process is interrupted, already-extracted emails are cached
- On re-run, skip already-extracted emails: `Skipping 142 already-extracted emails, processing 611 remaining`

## Known Edge Cases

1. **Duplicate transactions**: Same charge appears as "Scheduled Payment," "We've received your payment," and in statement balance (Discover Card pattern). The Claude analysis pass should deduplicate these.
2. **Marketing vs. receipts**: Same sender sends both marketing and receipts (McDonald's, Uber Eats). The LLM correctly distinguishes these (validated 16/16).
3. **No-amount reminders**: Payment due reminders without dollar amounts (Xfinity pattern). LLM correctly returns null for amount.
4. **Scam emails**: Fake purchase notifications (Windows Defender $555.68). LLM should flag as scam category; SPF/DKIM failure in headers is an additional signal.
5. **Yahoo IMAP quirks**: No compound OR in SEARCH queries. Use individual keyword searches.
6. **Gmail mailbox quoting**: `[Gmail]/All Mail` must be double-quoted in IMAP select: `'"[Gmail]/All Mail"'`
7. **LLM JSON in markdown fences**: Local model sometimes wraps JSON in ` ```json ... ``` `. Parser must strip these.
8. **OAuth2 token refresh**: Hotmail tokens expire (typically 1 hour). Must refresh using refresh_token before re-fetching.

## Future Enhancements (out of scope for v1)

- **Plaid integration** — Connect bank/credit card accounts directly for transaction data. Would add a new data source alongside email, feeding into the same transaction model and TUI.
- **Web UI** — Upgrade from TUI to a local web dashboard (Flask/FastAPI + React). The data layer is designed to support this.
- **OAuth2 for Gmail/Yahoo** — Replace app passwords with OAuth2 for all providers.
- **Scheduled runs** — Cron job to fetch new emails periodically and alert on new findings.
- **Email body amount extraction improvements** — For emails where the LLM can't find amounts (heavily templated HTML), try sender-specific regex patterns as fallback.
