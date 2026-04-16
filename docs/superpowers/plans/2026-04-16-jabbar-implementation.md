# Jabbar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Jabbar — an email-powered financial intelligence TUI that scans Gmail, Yahoo, and Hotmail for financial emails, extracts transaction data via local LLM, analyzes patterns via Claude API, and presents results in an interactive terminal dashboard.

**Architecture:** Six-stage pipeline (config → auth → fetch → preprocess/extract → analyze → TUI). Each stage caches output to disk. IMAP connects to email providers. HTML stripper cleans email bodies. Local LLM (Qwen 7B via LM Studio) extracts structured transaction JSON per email. Claude API does one final analysis pass over all transactions. Textual TUI displays results with charts and tables.

**Tech Stack:** Python 3.14, imaplib (stdlib), html.parser (stdlib), Textual + textual-plotext (TUI), anthropic SDK (Claude API), PyYAML, LM Studio (local LLM via OpenAI-compatible API). No LangChain.

**Design spec:** `docs/superpowers/specs/2026-04-16-analyze-bills-design.md` — read this first for full context on validated decisions and edge cases.

---

## File Map

| File | Responsibility | Created in Task |
|------|---------------|-----------------|
| `src/__init__.py` | Package marker | 1 |
| `src/config.py` | Load/validate config.yaml | 1 |
| `config.example.yaml` | Template config with placeholders | 1 |
| `requirements.txt` | Python dependencies | 1 |
| `src/auth/__init__.py` | Package marker | 2 |
| `src/auth/imap_auth.py` | App password IMAP auth | 2 |
| `src/auth/oauth2_auth.py` | Microsoft OAuth2+PKCE flow | 3 |
| `src/fetch/__init__.py` | Package marker | 4 |
| `src/fetch/email_fetcher.py` | IMAP search, download, cache | 4 |
| `src/preprocess/__init__.py` | Package marker | 5 |
| `src/preprocess/html_stripper.py` | HTML-to-text + MIME body extraction | 5 |
| `src/extract/__init__.py` | Package marker | 6 |
| `src/extract/llm_extractor.py` | Local LLM extraction | 6 |
| `src/analyze/__init__.py` | Package marker | 7 |
| `src/analyze/claude_analyzer.py` | Claude API analysis | 7 |
| `src/tui/__init__.py` | Package marker | 8 |
| `src/tui/app.py` | Main Textual app with all tabs | 8 |
| `src/tui/widgets/__init__.py` | Package marker | 8 |
| `src/tui/widgets/charts.py` | PlotextPlot chart widgets | 8 |
| `src/main.py` | CLI entry point | 9 |
| `tests/` | All test files | 1-9 |

---

### Task 1: Project Scaffold and Config

**Files:**
- Create: `src/__init__.py`, `src/config.py`, `config.example.yaml`, `requirements.txt`
- Create: `tests/__init__.py`, `tests/test_config.py`

- [ ] **Step 1: Write requirements.txt**

```
textual>=0.80.0
textual-plotext>=1.0.0
plotext>=5.3.0
anthropic>=0.40.0
pyyaml>=6.0
```

Run: `source venv/bin/activate && pip install -r requirements.txt`

- [ ] **Step 2: Create config.example.yaml**

```yaml
accounts:
  - name: gmail
    provider: gmail
    email: you@gmail.com
    auth: app_password
    password: "xxxx xxxx xxxx xxxx"
    imap_host: imap.gmail.com
    imap_port: 993
    mailbox: '"[Gmail]/All Mail"'

  - name: yahoo
    provider: yahoo
    email: you@yahoo.com
    auth: app_password
    password: "xxxxxxxxxxxxxxxx"
    imap_host: imap.mail.yahoo.com
    imap_port: 993
    mailbox: INBOX

  - name: hotmail
    provider: hotmail
    email: you@hotmail.com
    auth: oauth2
    client_id: "your-entra-app-client-id"
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
```

- [ ] **Step 3: Write failing test for config loading**

```python
# tests/test_config.py
import os
import tempfile
import pytest
from src.config import load_config, ConfigError


def test_load_config_valid(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
accounts:
  - name: gmail
    provider: gmail
    email: test@gmail.com
    auth: app_password
    password: "testpass"
    imap_host: imap.gmail.com
    imap_port: 993
    mailbox: INBOX
scan:
  months_back: 24
  keywords:
    - receipt
    - payment
extraction:
  llm_endpoint: "http://localhost:1234/v1/chat/completions"
  llm_model: "qwen2.5-7b-instruct-mlx"
  temperature: 0.1
  max_tokens: 500
  max_body_chars: 8000
analysis:
  claude_model: "claude-sonnet-4-20250514"
""")
    config = load_config(str(config_file))
    assert len(config["accounts"]) == 1
    assert config["accounts"][0]["email"] == "test@gmail.com"
    assert config["scan"]["months_back"] == 24
    assert config["extraction"]["llm_endpoint"] == "http://localhost:1234/v1/chat/completions"


def test_load_config_missing_file():
    with pytest.raises(ConfigError, match="not found"):
        load_config("/nonexistent/config.yaml")


def test_load_config_missing_accounts(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
scan:
  months_back: 24
  keywords: []
extraction:
  llm_endpoint: "http://localhost:1234/v1/chat/completions"
  llm_model: "test"
  temperature: 0.1
  max_tokens: 500
  max_body_chars: 8000
analysis:
  claude_model: "test"
""")
    with pytest.raises(ConfigError, match="accounts"):
        load_config(str(config_file))


def test_load_config_missing_auth_fields(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
accounts:
  - name: gmail
    provider: gmail
    email: test@gmail.com
scan:
  months_back: 24
  keywords: [receipt]
extraction:
  llm_endpoint: "http://localhost:1234/v1/chat/completions"
  llm_model: "test"
  temperature: 0.1
  max_tokens: 500
  max_body_chars: 8000
analysis:
  claude_model: "test"
""")
    with pytest.raises(ConfigError, match="auth"):
        load_config(str(config_file))
```

Run: `pytest tests/test_config.py -v`
Expected: FAIL — `src.config` does not exist.

- [ ] **Step 4: Implement config.py**

```python
# src/config.py
import os
import yaml


class ConfigError(Exception):
    pass


def load_config(path: str) -> dict:
    if not os.path.exists(path):
        raise ConfigError(f"Config file not found: {path}. Copy config.example.yaml to config.yaml and fill in your credentials.")

    with open(path) as f:
        config = yaml.safe_load(f)

    if not config or "accounts" not in config or not config["accounts"]:
        raise ConfigError("Config must contain at least one account under 'accounts'.")

    for account in config["accounts"]:
        if "auth" not in account:
            raise ConfigError(f"Account '{account.get('name', '?')}' missing 'auth' field. Must be 'app_password' or 'oauth2'.")
        if account["auth"] == "app_password" and "password" not in account:
            raise ConfigError(f"Account '{account.get('name', '?')}' uses app_password auth but missing 'password' field.")
        if account["auth"] == "oauth2" and "client_id" not in account:
            raise ConfigError(f"Account '{account.get('name', '?')}' uses oauth2 auth but missing 'client_id' field.")

    required_sections = ["scan", "extraction", "analysis"]
    for section in required_sections:
        if section not in config:
            raise ConfigError(f"Config missing required section: '{section}'.")

    return config
```

- [ ] **Step 5: Run tests, verify pass**

Run: `pytest tests/test_config.py -v`
Expected: All 4 tests PASS.

- [ ] **Step 6: Create package __init__.py files**

Create empty files: `src/__init__.py`, `tests/__init__.py`

- [ ] **Step 7: Commit**

```bash
git add src/__init__.py src/config.py config.example.yaml requirements.txt tests/__init__.py tests/test_config.py
git commit -m "feat: project scaffold with config loading and validation"
```

---

### Task 2: IMAP App Password Auth

**Files:**
- Create: `src/auth/__init__.py`, `src/auth/imap_auth.py`
- Create: `tests/test_imap_auth.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_imap_auth.py
import imaplib
from unittest.mock import patch, MagicMock
from src.auth.imap_auth import connect_imap, IMAPAuthError


def test_connect_imap_success():
    mock_conn = MagicMock(spec=imaplib.IMAP4_SSL)
    with patch("src.auth.imap_auth.imaplib.IMAP4_SSL", return_value=mock_conn):
        result = connect_imap("imap.gmail.com", 993, "test@gmail.com", "password123")
        mock_conn.login.assert_called_once_with("test@gmail.com", "password123")
        assert result is mock_conn


def test_connect_imap_auth_failure():
    mock_conn = MagicMock(spec=imaplib.IMAP4_SSL)
    mock_conn.login.side_effect = imaplib.IMAP4.error(b"LOGIN failed")
    with patch("src.auth.imap_auth.imaplib.IMAP4_SSL", return_value=mock_conn):
        try:
            connect_imap("imap.gmail.com", 993, "test@gmail.com", "wrong")
            assert False, "Should have raised IMAPAuthError"
        except IMAPAuthError as e:
            assert "gmail.com" in str(e)


def test_connect_imap_connection_failure():
    with patch("src.auth.imap_auth.imaplib.IMAP4_SSL", side_effect=OSError("Connection refused")):
        try:
            connect_imap("imap.gmail.com", 993, "test@gmail.com", "pass")
            assert False, "Should have raised IMAPAuthError"
        except IMAPAuthError as e:
            assert "connect" in str(e).lower() or "Connection" in str(e)
```

Run: `pytest tests/test_imap_auth.py -v`
Expected: FAIL — module not found.

- [ ] **Step 2: Implement imap_auth.py**

```python
# src/auth/imap_auth.py
import imaplib
import time


class IMAPAuthError(Exception):
    pass


def connect_imap(host: str, port: int, email: str, password: str, retries: int = 3) -> imaplib.IMAP4_SSL:
    last_error = None
    for attempt in range(retries):
        try:
            conn = imaplib.IMAP4_SSL(host, port)
            conn.login(email, password)
            return conn
        except imaplib.IMAP4.error as e:
            raise IMAPAuthError(
                f"Authentication failed for {email} at {host}. "
                f"Check your app password. Error: {e}"
            )
        except (OSError, TimeoutError) as e:
            last_error = e
            if attempt < retries - 1:
                time.sleep(2 ** (attempt + 1))
    raise IMAPAuthError(f"Connection to {host}:{port} failed after {retries} attempts: {last_error}")
```

- [ ] **Step 3: Create __init__.py**

Create empty file: `src/auth/__init__.py`

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/test_imap_auth.py -v`
Expected: All 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/auth/__init__.py src/auth/imap_auth.py tests/test_imap_auth.py
git commit -m "feat: IMAP app password authentication with retry"
```

---

### Task 3: OAuth2+PKCE Auth for Hotmail

**Files:**
- Create: `src/auth/oauth2_auth.py`
- Create: `tests/test_oauth2_auth.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_oauth2_auth.py
import json
import os
import tempfile
from unittest.mock import patch, MagicMock
from src.auth.oauth2_auth import (
    generate_pkce,
    load_cached_tokens,
    save_tokens,
    refresh_access_token,
    build_xoauth2_string,
)


def test_generate_pkce():
    verifier, challenge = generate_pkce()
    assert len(verifier) > 40
    assert len(challenge) > 20
    assert verifier != challenge


def test_build_xoauth2_string():
    result = build_xoauth2_string("user@hotmail.com", "token123")
    assert result == "user=user@hotmail.com\x01auth=Bearer token123\x01\x01"


def test_load_cached_tokens_exists(tmp_path):
    token_file = tmp_path / "tokens.json"
    token_data = {"access_token": "abc", "refresh_token": "def", "expires_in": 3600}
    token_file.write_text(json.dumps(token_data))
    result = load_cached_tokens(str(token_file))
    assert result["access_token"] == "abc"


def test_load_cached_tokens_missing(tmp_path):
    result = load_cached_tokens(str(tmp_path / "nonexistent.json"))
    assert result is None


def test_save_tokens(tmp_path):
    token_file = tmp_path / "tokens.json"
    tokens = {"access_token": "xyz", "refresh_token": "uvw"}
    save_tokens(tokens, str(token_file))
    loaded = json.loads(token_file.read_text())
    assert loaded["access_token"] == "xyz"
```

Run: `pytest tests/test_oauth2_auth.py -v`
Expected: FAIL — module not found.

- [ ] **Step 2: Implement oauth2_auth.py**

```python
# src/auth/oauth2_auth.py
import base64
import hashlib
import http.server
import imaplib
import json
import os
import secrets
import threading
import urllib.parse
import urllib.request
import webbrowser

AUTH_ENDPOINT = "https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize"
TOKEN_ENDPOINT = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
SCOPE = "https://outlook.office.com/IMAP.AccessAsUser.All offline_access"


class OAuth2Error(Exception):
    pass


def generate_pkce() -> tuple[str, str]:
    code_verifier = secrets.token_urlsafe(64)[:128]
    code_challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    return code_verifier, code_challenge


def build_xoauth2_string(user: str, access_token: str) -> str:
    return f"user={user}\x01auth=Bearer {access_token}\x01\x01"


def load_cached_tokens(token_file: str) -> dict | None:
    if not os.path.exists(token_file):
        return None
    with open(token_file) as f:
        return json.load(f)


def save_tokens(tokens: dict, token_file: str) -> None:
    with open(token_file, "w") as f:
        json.dump(tokens, f, indent=2)


def refresh_access_token(client_id: str, refresh_token: str) -> dict:
    data = urllib.parse.urlencode({
        "client_id": client_id,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "scope": SCOPE,
    }).encode()
    req = urllib.request.Request(
        TOKEN_ENDPOINT,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        resp = urllib.request.urlopen(req)
        return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        raise OAuth2Error(f"Token refresh failed: {error_body}")


def authorize_browser(client_id: str, redirect_uri: str) -> dict:
    code_verifier, code_challenge = generate_pkce()
    auth_code_result = {}
    port = int(redirect_uri.split(":")[2].split("/")[0])

    class CallbackHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)
            if "code" in params:
                auth_code_result["code"] = params["code"][0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"<h1>Jabbar: Authorization successful! You can close this tab.</h1>")
            else:
                auth_code_result["error"] = params.get("error", ["unknown"])[0]
                self.send_response(400)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"<h1>Authorization failed.</h1>")

        def log_message(self, format, *args):
            pass

    server = http.server.HTTPServer(("localhost", port), CallbackHandler)
    thread = threading.Thread(target=server.handle_request)
    thread.start()

    auth_url = (
        AUTH_ENDPOINT + "?" + urllib.parse.urlencode({
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": SCOPE,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "response_mode": "query",
        })
    )
    print(f"Opening browser for Microsoft login...")
    print(f"If browser doesn't open, go to:\n{auth_url}\n")
    webbrowser.open(auth_url)

    thread.join(timeout=120)
    server.server_close()

    if "code" not in auth_code_result:
        raise OAuth2Error(f"Browser authorization failed: {auth_code_result}")

    token_data = urllib.parse.urlencode({
        "client_id": client_id,
        "code": auth_code_result["code"],
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
        "code_verifier": code_verifier,
        "scope": SCOPE,
    }).encode()
    req = urllib.request.Request(
        TOKEN_ENDPOINT,
        data=token_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        resp = urllib.request.urlopen(req)
        return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        raise OAuth2Error(f"Token exchange failed: {error_body}")


def get_oauth2_connection(account_config: dict) -> imaplib.IMAP4_SSL:
    client_id = account_config["client_id"]
    redirect_uri = account_config.get("redirect_uri", "http://localhost:8400/callback")
    token_file = account_config.get("token_file", ".hotmail_tokens.json")
    email_addr = account_config["email"]
    host = account_config["imap_host"]
    port = account_config.get("imap_port", 993)

    tokens = load_cached_tokens(token_file)

    if tokens and "refresh_token" in tokens:
        try:
            tokens = refresh_access_token(client_id, tokens["refresh_token"])
            save_tokens(tokens, token_file)
        except OAuth2Error:
            os.remove(token_file)
            tokens = None

    if not tokens:
        tokens = authorize_browser(client_id, redirect_uri)
        save_tokens(tokens, token_file)

    auth_string = build_xoauth2_string(email_addr, tokens["access_token"])
    conn = imaplib.IMAP4_SSL(host, port)
    conn.authenticate("XOAUTH2", lambda x: auth_string.encode())
    return conn
```

- [ ] **Step 3: Run tests, verify pass**

Run: `pytest tests/test_oauth2_auth.py -v`
Expected: All 5 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add src/auth/oauth2_auth.py tests/test_oauth2_auth.py
git commit -m "feat: OAuth2+PKCE authentication for Hotmail/Outlook"
```

---

### Task 4: Email Fetcher

**Files:**
- Create: `src/fetch/__init__.py`, `src/fetch/email_fetcher.py`
- Create: `tests/test_email_fetcher.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_email_fetcher.py
import os
from unittest.mock import MagicMock
from src.fetch.email_fetcher import search_financial_emails, deduplicate_ids, save_raw_email


def test_deduplicate_ids():
    sets = [
        {b"1", b"2", b"3"},
        {b"2", b"3", b"4"},
        {b"4", b"5"},
    ]
    result = deduplicate_ids(sets)
    assert result == {b"1", b"2", b"3", b"4", b"5"}


def test_search_financial_emails():
    mock_conn = MagicMock()
    mock_conn.search.return_value = ("OK", [b"1 2 3"])

    keywords = ["receipt", "payment"]
    result = search_financial_emails(mock_conn, keywords, "16-Apr-2024")
    assert len(result) >= 3  # at least 3 unique IDs
    assert mock_conn.search.call_count == 2


def test_search_financial_emails_empty():
    mock_conn = MagicMock()
    mock_conn.search.return_value = ("OK", [b""])

    result = search_financial_emails(mock_conn, ["receipt"], "16-Apr-2024")
    assert len(result) == 0


def test_save_raw_email(tmp_path):
    raw = b"From: test\r\nSubject: Test\r\n\r\nBody"
    path = save_raw_email(raw, "gmail", "12345", str(tmp_path))
    assert os.path.exists(path)
    with open(path, "rb") as f:
        assert f.read() == raw
```

Run: `pytest tests/test_email_fetcher.py -v`
Expected: FAIL — module not found.

- [ ] **Step 2: Implement email_fetcher.py**

```python
# src/fetch/email_fetcher.py
import imaplib
import os
from datetime import datetime, timedelta


def deduplicate_ids(id_sets: list[set]) -> set:
    result = set()
    for s in id_sets:
        result.update(s)
    return result


def search_financial_emails(
    conn: imaplib.IMAP4_SSL,
    keywords: list[str],
    since_date: str,
) -> set[bytes]:
    all_ids = []
    for kw in keywords:
        try:
            status, results = conn.search(None, f'SINCE {since_date} SUBJECT "{kw}"')
            if status == "OK" and results[0]:
                ids = set(results[0].split())
                all_ids.append(ids)
        except imaplib.IMAP4.error:
            continue
    return deduplicate_ids(all_ids)


def save_raw_email(raw: bytes, provider: str, msg_id: str, data_dir: str) -> str:
    dir_path = os.path.join(data_dir, "raw", provider)
    os.makedirs(dir_path, exist_ok=True)
    file_path = os.path.join(dir_path, f"{msg_id}.eml")
    with open(file_path, "wb") as f:
        f.write(raw)
    return file_path


def fetch_and_cache(
    conn: imaplib.IMAP4_SSL,
    msg_ids: set[bytes],
    provider: str,
    data_dir: str,
) -> list[dict]:
    results = []
    total = len(msg_ids)
    for i, msg_id in enumerate(sorted(msg_ids)):
        msg_id_str = msg_id.decode()
        cached_path = os.path.join(data_dir, "raw", provider, f"{msg_id_str}.eml")

        if os.path.exists(cached_path):
            results.append({"msg_id": msg_id_str, "provider": provider, "path": cached_path})
            continue

        try:
            status, data = conn.fetch(msg_id, "(RFC822)")
            if data[0] is not None:
                raw = data[0][1]
                path = save_raw_email(raw, provider, msg_id_str, data_dir)
                results.append({"msg_id": msg_id_str, "provider": provider, "path": path})
        except Exception as e:
            print(f"  Warning: Failed to fetch message {msg_id_str}: {e}")

        if (i + 1) % 50 == 0 or i + 1 == total:
            print(f"  Fetched {i + 1}/{total} emails from {provider}")

    return results


def calculate_since_date(months_back: int) -> str:
    dt = datetime.now() - timedelta(days=months_back * 30)
    return dt.strftime("%d-%b-%Y")
```

- [ ] **Step 3: Create __init__.py**

Create empty file: `src/fetch/__init__.py`

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/test_email_fetcher.py -v`
Expected: All 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/fetch/__init__.py src/fetch/email_fetcher.py tests/test_email_fetcher.py
git commit -m "feat: email fetcher with IMAP search, dedup, and caching"
```

---

### Task 5: HTML Stripper and Body Extraction

**Files:**
- Create: `src/preprocess/__init__.py`, `src/preprocess/html_stripper.py`
- Create: `tests/test_html_stripper.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_html_stripper.py
from src.preprocess.html_stripper import strip_html, get_email_body


def test_strip_html_basic():
    html = "<p>Hello <b>world</b></p>"
    result = strip_html(html)
    assert "Hello" in result
    assert "world" in result
    assert "<p>" not in result
    assert "<b>" not in result


def test_strip_html_removes_style():
    html = "<html><head><style>body{color:red;}</style></head><body><p>Content</p></body></html>"
    result = strip_html(html)
    assert "Content" in result
    assert "color:red" not in result


def test_strip_html_removes_script():
    html = "<html><body><script>alert('x')</script><p>Safe</p></body></html>"
    result = strip_html(html)
    assert "Safe" in result
    assert "alert" not in result


def test_strip_html_block_elements_newlines():
    html = "<div>Line1</div><div>Line2</div><p>Line3</p>"
    result = strip_html(html)
    lines = [l for l in result.split("\n") if l.strip()]
    assert len(lines) >= 3


def test_strip_html_collapses_whitespace():
    html = "<p>  lots   of   spaces  </p>"
    result = strip_html(html)
    assert "  " not in result.replace("\n", " ").strip() or "lots of spaces" in result


def test_get_email_body_plain_text():
    raw = b"Content-Type: text/plain\r\n\r\nPlain text body here with enough content to pass the threshold."
    body, source = get_email_body(raw)
    assert "Plain text body" in body
    assert source == "plain"


def test_get_email_body_html_only():
    raw = b"Content-Type: text/html\r\n\r\n<html><body><p>HTML content here that is long enough</p></body></html>"
    body, source = get_email_body(raw)
    assert "HTML content" in body
    assert source == "html_stripped"


def test_get_email_body_truncates():
    long_text = "A" * 10000
    raw = f"Content-Type: text/plain\r\n\r\n{long_text}".encode()
    body, source = get_email_body(raw, max_chars=8000)
    assert len(body) <= 8000
```

Run: `pytest tests/test_html_stripper.py -v`
Expected: FAIL — module not found.

- [ ] **Step 2: Implement html_stripper.py**

```python
# src/preprocess/html_stripper.py
import email
import re
from html.parser import HTMLParser


class SmartHTMLExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.result = []
        self.skip = False
        self.skip_tags = {"style", "script", "head"}

    def handle_starttag(self, tag, attrs):
        if tag in self.skip_tags:
            self.skip = True
        if tag in ("br", "p", "div", "tr", "td", "th", "li", "h1", "h2", "h3", "h4"):
            self.result.append("\n")

    def handle_endtag(self, tag):
        if tag in self.skip_tags:
            self.skip = False

    def handle_data(self, data):
        if not self.skip:
            self.result.append(data)

    def get_text(self) -> str:
        text = "".join(self.result)
        lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
        lines = [l for l in lines if l]
        return "\n".join(lines)


def strip_html(html: str) -> str:
    extractor = SmartHTMLExtractor()
    extractor.feed(html)
    return extractor.get_text()


def get_email_body(raw_email: bytes, max_chars: int = 8000) -> tuple[str, str]:
    msg = email.message_from_bytes(raw_email)

    text_body = ""
    html_body = ""

    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/plain" and not text_body:
                try:
                    text_body = part.get_payload(decode=True).decode("utf-8", errors="replace")
                except Exception:
                    pass
            elif ct == "text/html" and not html_body:
                try:
                    html_body = part.get_payload(decode=True).decode("utf-8", errors="replace")
                except Exception:
                    pass
    else:
        ct = msg.get_content_type()
        try:
            payload = msg.get_payload(decode=True).decode("utf-8", errors="replace")
        except Exception:
            return "", "none"

        if ct == "text/plain":
            text_body = payload
        elif ct == "text/html":
            html_body = payload

    if text_body and len(text_body) > 50:
        return text_body[:max_chars], "plain"
    elif html_body:
        stripped = strip_html(html_body)
        return stripped[:max_chars], "html_stripped"

    return "", "none"
```

- [ ] **Step 3: Create __init__.py**

Create empty file: `src/preprocess/__init__.py`

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/test_html_stripper.py -v`
Expected: All 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/preprocess/__init__.py src/preprocess/html_stripper.py tests/test_html_stripper.py
git commit -m "feat: HTML stripper and MIME body extraction"
```

---

### Task 6: Local LLM Extractor

**Files:**
- Create: `src/extract/__init__.py`, `src/extract/llm_extractor.py`
- Create: `tests/test_llm_extractor.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_llm_extractor.py
import json
from unittest.mock import patch, MagicMock
from src.extract.llm_extractor import (
    parse_llm_response,
    extract_transaction,
    EXTRACTION_PROMPT,
)


def test_parse_llm_response_clean_json():
    raw = '{"is_transaction": true, "merchant": "Test", "amount": 42.00}'
    result = parse_llm_response(raw)
    assert result["is_transaction"] is True
    assert result["merchant"] == "Test"
    assert result["amount"] == 42.00


def test_parse_llm_response_markdown_fenced():
    raw = '```json\n{"is_transaction": false, "merchant": null}\n```'
    result = parse_llm_response(raw)
    assert result["is_transaction"] is False


def test_parse_llm_response_markdown_no_language():
    raw = '```\n{"is_transaction": true, "amount": 10.0}\n```'
    result = parse_llm_response(raw)
    assert result["amount"] == 10.0


def test_parse_llm_response_invalid():
    raw = "I couldn't parse this email, sorry."
    result = parse_llm_response(raw)
    assert result is None


def test_extraction_prompt_exists():
    assert "financial data extractor" in EXTRACTION_PROMPT
    assert "is_transaction" in EXTRACTION_PROMPT
    assert "scam" in EXTRACTION_PROMPT


def test_extract_transaction_calls_api():
    mock_response = {
        "choices": [{
            "message": {
                "content": '{"is_transaction": true, "merchant": "Chipotle", "amount": 17.53}'
            }
        }]
    }
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(mock_response).encode()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    config = {
        "extraction": {
            "llm_endpoint": "http://localhost:1234/v1/chat/completions",
            "llm_model": "qwen2.5-7b-instruct-mlx",
            "temperature": 0.1,
            "max_tokens": 500,
        }
    }

    with patch("src.extract.llm_extractor.urllib.request.urlopen", return_value=mock_resp):
        result = extract_transaction("Order confirmation", "Your order total: $17.53", config)
        assert result["merchant"] == "Chipotle"
        assert result["amount"] == 17.53
```

Run: `pytest tests/test_llm_extractor.py -v`
Expected: FAIL — module not found.

- [ ] **Step 2: Implement llm_extractor.py**

```python
# src/extract/llm_extractor.py
import json
import os
import re
import time
import urllib.request


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


def parse_llm_response(raw: str) -> dict | None:
    raw = raw.strip()
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
    if fence_match:
        raw = fence_match.group(1).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def extract_transaction(subject: str, body: str, config: dict) -> dict | None:
    endpoint = config["extraction"]["llm_endpoint"]
    payload = {
        "model": config["extraction"]["llm_model"],
        "messages": [
            {"role": "system", "content": EXTRACTION_PROMPT},
            {"role": "user", "content": f"Subject: {subject}\n\nBody:\n{body}"},
        ],
        "temperature": config["extraction"]["temperature"],
        "max_tokens": config["extraction"]["max_tokens"],
    }
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        resp = urllib.request.urlopen(req, timeout=120)
        result = json.loads(resp.read())
        content = result["choices"][0]["message"]["content"]
        return parse_llm_response(content)
    except (urllib.error.URLError, OSError) as e:
        print(f"  LLM error: {e}")
        return None


def extract_all(
    emails: list[dict],
    config: dict,
    data_dir: str,
) -> list[dict]:
    output_path = os.path.join(data_dir, "extracted", "transactions.json")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    existing = []
    existing_ids = set()
    if os.path.exists(output_path):
        with open(output_path) as f:
            existing = json.load(f)
            existing_ids = {e["email_id"] for e in existing}

    to_process = [e for e in emails if e["msg_id"] not in existing_ids]
    skipped = len(emails) - len(to_process)
    if skipped:
        print(f"Skipping {skipped} already-extracted emails, processing {len(to_process)} remaining")

    from src.preprocess.html_stripper import get_email_body

    results = list(existing)
    start_time = time.time()

    for i, email_info in enumerate(to_process):
        with open(email_info["path"], "rb") as f:
            raw = f.read()

        body, source = get_email_body(raw, config["extraction"].get("max_body_chars", 8000))

        import email as email_lib
        from email.header import decode_header

        msg = email_lib.message_from_bytes(raw)
        subject = msg.get("Subject", "")
        if subject:
            decoded = decode_header(subject)
            subject = " ".join(
                p.decode(e or "utf-8") if isinstance(p, bytes) else p
                for p, e in decoded
            )

        extracted = extract_transaction(subject, body, config)

        if extracted:
            extracted["email_id"] = email_info["msg_id"]
            extracted["provider"] = email_info["provider"]
            extracted["raw_subject"] = subject
            extracted["extraction_source"] = source
            results.append(extracted)

        with open(output_path, "w") as f:
            json.dump(results, f, indent=2)

        elapsed = time.time() - start_time
        avg_per = elapsed / (i + 1)
        remaining = avg_per * (len(to_process) - i - 1)
        pct = (i + 1) / len(to_process) * 100
        print(
            f"  Extracting: [{i + 1}/{len(to_process)}] {email_info['provider']} "
            f"— \"{subject[:50]}\" ({pct:.1f}%) "
            f"ETA: {remaining / 60:.0f}m"
        )

    return results
```

- [ ] **Step 3: Create __init__.py**

Create empty file: `src/extract/__init__.py`

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/test_llm_extractor.py -v`
Expected: All 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/extract/__init__.py src/extract/llm_extractor.py tests/test_llm_extractor.py
git commit -m "feat: local LLM transaction extractor with JSON fence handling"
```

---

### Task 7: Claude API Analyzer

**Files:**
- Create: `src/analyze/__init__.py`, `src/analyze/claude_analyzer.py`
- Create: `tests/test_claude_analyzer.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_claude_analyzer.py
import json
from unittest.mock import patch, MagicMock
from src.analyze.claude_analyzer import (
    filter_transactions,
    parse_analysis_response,
    ANALYSIS_PROMPT,
)


def test_filter_transactions():
    transactions = [
        {"is_transaction": True, "merchant": "A", "amount": 10},
        {"is_transaction": False, "merchant": None},
        {"is_transaction": True, "merchant": "B", "amount": 20},
        {"merchant": "C"},  # missing is_transaction
    ]
    result = filter_transactions(transactions)
    assert len(result) == 2
    assert result[0]["merchant"] == "A"
    assert result[1]["merchant"] == "B"


def test_parse_analysis_response_clean():
    data = {"alerts": [], "recurring": [], "categories": {}, "monthly_summary": [], "recommendations": [], "scams_detected": []}
    raw = json.dumps(data)
    result = parse_analysis_response(raw)
    assert "alerts" in result


def test_parse_analysis_response_fenced():
    data = {"alerts": [{"severity": "red", "message": "test"}]}
    raw = f"```json\n{json.dumps(data)}\n```"
    result = parse_analysis_response(raw)
    assert result["alerts"][0]["severity"] == "red"


def test_analysis_prompt_has_required_sections():
    assert "recurring" in ANALYSIS_PROMPT.lower()
    assert "alerts" in ANALYSIS_PROMPT.lower()
    assert "duplicate" in ANALYSIS_PROMPT.lower()
    assert "recommendations" in ANALYSIS_PROMPT.lower()
    assert "scam" in ANALYSIS_PROMPT.lower()
```

Run: `pytest tests/test_claude_analyzer.py -v`
Expected: FAIL — module not found.

- [ ] **Step 2: Implement claude_analyzer.py**

```python
# src/analyze/claude_analyzer.py
import json
import os
import re

import anthropic


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
    "alerts": [{"severity": "red|yellow|green", "type": "string", "merchant": "string", "message": "string", "details": "string with dates and amounts"}],
    "recurring": [{"merchant": "string", "monthly_cost": number, "annual_cost": number, "frequency": "monthly|quarterly|annual", "trend": "stable|increasing|decreasing", "months_active": number, "category": "string"}],
    "categories": {"category_name": number},
    "monthly_summary": [{"month": "YYYY-MM", "total": number, "transaction_count": number}],
    "recommendations": [{"action": "cancel|investigate|negotiate|fix", "merchant": "string", "potential_monthly_savings": number, "reason": "string"}],
    "scams_detected": [{"merchant": "string", "date": "YYYY-MM-DD", "amount_claimed": number, "description": "string", "indicators": ["string"]}]
}"""


def filter_transactions(transactions: list[dict]) -> list[dict]:
    return [t for t in transactions if t.get("is_transaction") is True]


def parse_analysis_response(raw: str) -> dict | None:
    raw = raw.strip()
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
    if fence_match:
        raw = fence_match.group(1).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def analyze_transactions(transactions: list[dict], config: dict, data_dir: str) -> dict:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("Set ANTHROPIC_API_KEY environment variable.")

    filtered = filter_transactions(transactions)
    if not filtered:
        return {"alerts": [], "recurring": [], "categories": {}, "monthly_summary": [], "recommendations": [], "scams_detected": []}

    client = anthropic.Anthropic(api_key=api_key)
    print(f"Analyzing {len(filtered)} transactions with Claude...")

    message = client.messages.create(
        model=config["analysis"]["claude_model"],
        max_tokens=8000,
        system=ANALYSIS_PROMPT,
        messages=[{"role": "user", "content": json.dumps(filtered)}],
    )

    raw_response = message.content[0].text
    result = parse_analysis_response(raw_response)

    if result is None:
        print("Warning: Claude returned invalid JSON. Saving raw response.")
        result = {"raw_response": raw_response, "alerts": [], "recurring": [], "categories": {}, "monthly_summary": [], "recommendations": [], "scams_detected": []}

    output_path = os.path.join(data_dir, "analysis", "insights.json")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(result, f, indent=2)

    print(f"Analysis complete. {len(result.get('alerts', []))} alerts, {len(result.get('recommendations', []))} recommendations.")
    return result
```

- [ ] **Step 3: Create __init__.py**

Create empty file: `src/analyze/__init__.py`

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/test_claude_analyzer.py -v`
Expected: All 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/analyze/__init__.py src/analyze/claude_analyzer.py tests/test_claude_analyzer.py
git commit -m "feat: Claude API analyzer for transaction pattern detection"
```

---

### Task 8: Textual TUI

**Files:**
- Create: `src/tui/__init__.py`, `src/tui/app.py`, `src/tui/widgets/__init__.py`, `src/tui/widgets/charts.py`
- Create: `tests/test_tui.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_tui.py
import json
import os
import tempfile
from src.tui.app import load_tui_data


def test_load_tui_data_both_files(tmp_path):
    extracted_dir = tmp_path / "extracted"
    extracted_dir.mkdir()
    analysis_dir = tmp_path / "analysis"
    analysis_dir.mkdir()

    transactions = [
        {"is_transaction": True, "merchant": "Test", "amount": 10.0, "date": "2025-01-01",
         "category": "shopping", "description": "test", "provider": "gmail",
         "payment_method": "Visa", "email_id": "1", "raw_subject": "Test"},
    ]
    insights = {
        "alerts": [{"severity": "red", "type": "test", "merchant": "X", "message": "msg", "details": "det"}],
        "recurring": [],
        "categories": {"shopping": 10.0},
        "monthly_summary": [{"month": "2025-01", "total": 10.0, "transaction_count": 1}],
        "recommendations": [],
        "scams_detected": [],
    }

    (extracted_dir / "transactions.json").write_text(json.dumps(transactions))
    (analysis_dir / "insights.json").write_text(json.dumps(insights))

    data = load_tui_data(str(tmp_path))
    assert len(data["transactions"]) == 1
    assert data["transactions"][0]["merchant"] == "Test"
    assert len(data["insights"]["alerts"]) == 1


def test_load_tui_data_no_insights(tmp_path):
    extracted_dir = tmp_path / "extracted"
    extracted_dir.mkdir()

    transactions = [
        {"is_transaction": True, "merchant": "Test", "amount": 5.0, "date": "2025-02-01",
         "category": "food_dining", "email_id": "2", "provider": "yahoo"},
    ]
    (extracted_dir / "transactions.json").write_text(json.dumps(transactions))

    data = load_tui_data(str(tmp_path))
    assert len(data["transactions"]) == 1
    assert data["insights"]["alerts"] == []


def test_load_tui_data_empty(tmp_path):
    data = load_tui_data(str(tmp_path))
    assert data["transactions"] == []
    assert data["insights"]["alerts"] == []
```

Run: `pytest tests/test_tui.py -v`
Expected: FAIL — module not found.

- [ ] **Step 2: Implement chart widgets**

```python
# src/tui/widgets/__init__.py
```

```python
# src/tui/widgets/charts.py
from textual_plotext import PlotextPlot


class MonthlySpendChart(PlotextPlot):
    def __init__(self, monthly_data: list[dict], **kwargs):
        super().__init__(**kwargs)
        self._monthly_data = monthly_data

    def on_mount(self) -> None:
        if not self._monthly_data:
            return
        months = [d["month"] for d in self._monthly_data]
        totals = [d["total"] for d in self._monthly_data]
        labels = [m[5:] + "\n" + m[:4] for m in months]

        plt = self.plt
        plt.bar(labels, totals, color="cyan")
        plt.title("Monthly Spending")
        plt.ylabel("USD")
        plt.theme("dark")


class CategoryChart(PlotextPlot):
    def __init__(self, categories: dict, **kwargs):
        super().__init__(**kwargs)
        self._categories = categories

    def on_mount(self) -> None:
        if not self._categories:
            return
        sorted_cats = sorted(self._categories.items(), key=lambda x: x[1])
        labels = [c[0] for c in sorted_cats]
        amounts = [c[1] for c in sorted_cats]
        colors = ["red", "yellow", "green", "cyan", "blue", "magenta", "white"]

        plt = self.plt
        plt.bar(labels, amounts, color=colors[: len(labels)], orientation="h")
        plt.title("Spending by Category")
        plt.xlabel("USD")
        plt.theme("dark")
```

- [ ] **Step 3: Implement main TUI app**

```python
# src/tui/app.py
import json
import os
from collections import defaultdict

from textual.app import App
from textual.containers import VerticalScroll
from textual.widgets import Header, Footer, Static, DataTable, TabbedContent, TabPane

from src.tui.widgets.charts import MonthlySpendChart, CategoryChart


def load_tui_data(data_dir: str) -> dict:
    transactions = []
    insights = {"alerts": [], "recurring": [], "categories": {}, "monthly_summary": [], "recommendations": [], "scams_detected": []}

    tx_path = os.path.join(data_dir, "extracted", "transactions.json")
    if os.path.exists(tx_path):
        with open(tx_path) as f:
            all_tx = json.load(f)
            transactions = [t for t in all_tx if t.get("is_transaction")]

    insights_path = os.path.join(data_dir, "analysis", "insights.json")
    if os.path.exists(insights_path):
        with open(insights_path) as f:
            insights = json.load(f)

    return {"transactions": transactions, "insights": insights}


class JabbarApp(App):
    CSS = """
    Screen { background: $surface; }
    TabbedContent { height: 1fr; }
    #alerts-container { height: 1fr; padding: 1; }
    .alert-red { color: red; margin-bottom: 1; }
    .alert-yellow { color: yellow; margin-bottom: 1; }
    .alert-green { color: green; margin-bottom: 1; }
    PlotextPlot { height: 25; }
    DataTable { height: 1fr; }
    #summary-stats { height: 3; padding: 0 2; background: $primary-background; color: $text; text-style: bold; }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("d", "toggle_dark", "Dark/Light"),
    ]

    def __init__(self, data_dir: str = "data", **kwargs):
        super().__init__(**kwargs)
        self._data_dir = data_dir
        self._data = load_tui_data(data_dir)

    def compose(self):
        yield Header(show_clock=True)

        tx = self._data["transactions"]
        insights = self._data["insights"]

        total = sum(t.get("amount", 0) or 0 for t in tx)
        monthly_summary = insights.get("monthly_summary", [])
        months = len(monthly_summary) if monthly_summary else 1
        avg = total / months if months else 0

        yield Static(
            f"  Jabbar | Total: ${total:,.0f} | Monthly Avg: ${avg:,.0f} | Transactions: {len(tx)}",
            id="summary-stats",
        )

        with TabbedContent():
            with TabPane("Alerts", id="alerts"):
                with VerticalScroll(id="alerts-container"):
                    alerts = insights.get("alerts", [])
                    if not alerts:
                        yield Static("No alerts. Run 'jabbar analyze' to generate insights.")
                    for alert in alerts:
                        sev = alert.get("severity", "green")
                        icon = {"red": "[!]", "yellow": "[~]", "green": "[i]"}.get(sev, "[?]")
                        msg = f"  {icon} {alert.get('type', '').upper()}: {alert.get('merchant', '')} — {alert.get('message', '')}"
                        if alert.get("details"):
                            msg += f"\n      {alert['details']}"
                        css_class = f"alert-{sev}"
                        yield Static(msg, classes=css_class)

            with TabPane("Monthly", id="monthly"):
                yield MonthlySpendChart(monthly_summary)

            with TabPane("Categories", id="categories"):
                cats = insights.get("categories", {})
                if not cats and tx:
                    cats = defaultdict(float)
                    for t in tx:
                        cat = t.get("category", "other") or "other"
                        cats[cat] += t.get("amount", 0) or 0
                    cats = dict(cats)
                yield CategoryChart(cats)

            with TabPane("Transactions", id="transactions"):
                yield DataTable(id="tx-table")

            with TabPane("Recurring", id="recurring"):
                yield DataTable(id="rec-table")

        yield Footer()

    def on_mount(self) -> None:
        tx = self._data["transactions"]
        insights = self._data["insights"]

        table = self.query_one("#tx-table")
        table.add_columns("Date", "Provider", "Merchant", "Amount", "Category", "Description", "Payment")
        table.cursor_type = "row"
        table.zebra_stripes = True

        sorted_tx = sorted(tx, key=lambda t: t.get("date") or "", reverse=True)
        for t in sorted_tx:
            table.add_row(
                t.get("date", ""),
                t.get("provider", ""),
                (t.get("merchant") or "")[:30],
                f"${t['amount']:,.2f}" if t.get("amount") else "",
                t.get("category", ""),
                (t.get("description") or "")[:40],
                (t.get("payment_method") or "")[:20],
            )

        rec_table = self.query_one("#rec-table")
        rec_table.add_columns("Merchant", "Frequency", "Monthly", "Annual", "Trend", "Months Active", "Category")
        rec_table.cursor_type = "row"
        rec_table.zebra_stripes = True

        recurring = insights.get("recurring", [])
        recurring.sort(key=lambda r: r.get("monthly_cost", 0), reverse=True)
        for r in recurring:
            rec_table.add_row(
                (r.get("merchant") or "")[:30],
                r.get("frequency", ""),
                f"${r.get('monthly_cost', 0):,.2f}",
                f"${r.get('annual_cost', 0):,.2f}",
                r.get("trend", ""),
                str(r.get("months_active", "")),
                r.get("category", ""),
            )

    def action_toggle_dark(self) -> None:
        self.dark = not self.dark
```

- [ ] **Step 4: Create __init__.py files**

Create empty files: `src/tui/__init__.py`, `src/tui/widgets/__init__.py`

- [ ] **Step 5: Run tests, verify pass**

Run: `pytest tests/test_tui.py -v`
Expected: All 3 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/tui/ tests/test_tui.py
git commit -m "feat: Jabbar TUI with alerts, charts, transactions, and recurring tabs"
```

---

### Task 9: CLI Entry Point

**Files:**
- Create: `src/main.py`
- Create: `tests/test_main.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_main.py
from unittest.mock import patch
from src.main import parse_args


def test_parse_args_default():
    args = parse_args([])
    assert args.command == "run"


def test_parse_args_fetch():
    args = parse_args(["fetch"])
    assert args.command == "fetch"


def test_parse_args_tui():
    args = parse_args(["tui"])
    assert args.command == "tui"


def test_parse_args_config():
    args = parse_args(["--config", "custom.yaml", "fetch"])
    assert args.config == "custom.yaml"
    assert args.command == "fetch"
```

Run: `pytest tests/test_main.py -v`
Expected: FAIL — module not found.

- [ ] **Step 2: Implement main.py**

```python
# src/main.py
import argparse
import sys
import os


def parse_args(argv: list[str] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="jabbar",
        description="Jabbar — Email Financial Intelligence",
    )
    parser.add_argument(
        "--config", default="config.yaml",
        help="Path to config.yaml (default: config.yaml)",
    )
    parser.add_argument(
        "--data-dir", default="data",
        help="Path to data directory (default: data)",
    )
    parser.add_argument(
        "command", nargs="?", default="run",
        choices=["setup", "fetch", "extract", "analyze", "run", "tui"],
        help="Command to run (default: run)",
    )
    return parser.parse_args(argv)


def cmd_fetch(config: dict, data_dir: str) -> list[dict]:
    from src.auth.imap_auth import connect_imap
    from src.auth.oauth2_auth import get_oauth2_connection
    from src.fetch.email_fetcher import (
        search_financial_emails,
        fetch_and_cache,
        calculate_since_date,
    )

    since = calculate_since_date(config["scan"]["months_back"])
    keywords = config["scan"]["keywords"]
    all_emails = []

    for account in config["accounts"]:
        name = account["name"]
        print(f"\nConnecting to {name} ({account['email']})...")

        try:
            if account["auth"] == "app_password":
                conn = connect_imap(
                    account["imap_host"], account["imap_port"],
                    account["email"], account["password"],
                )
            elif account["auth"] == "oauth2":
                conn = get_oauth2_connection(account)
            else:
                print(f"  Unknown auth type: {account['auth']}")
                continue

            mailbox = account.get("mailbox", "INBOX")
            conn.select(mailbox, readonly=True)

            print(f"  Searching for financial emails since {since}...")
            msg_ids = search_financial_emails(conn, keywords, since)
            print(f"  Found {len(msg_ids)} financial emails")

            emails = fetch_and_cache(conn, msg_ids, name, data_dir)
            all_emails.extend(emails)

            conn.logout()
            print(f"  Done with {name}: {len(emails)} emails cached")

        except Exception as e:
            print(f"  Error with {name}: {e}")
            continue

    print(f"\nTotal: {len(all_emails)} emails across {len(config['accounts'])} accounts")
    return all_emails


def cmd_extract(config: dict, data_dir: str, emails: list[dict] = None) -> list[dict]:
    from src.extract.llm_extractor import extract_all
    import os
    import json

    if emails is None:
        emails = []
        raw_dir = os.path.join(data_dir, "raw")
        if os.path.exists(raw_dir):
            for provider in os.listdir(raw_dir):
                provider_dir = os.path.join(raw_dir, provider)
                if os.path.isdir(provider_dir):
                    for fname in os.listdir(provider_dir):
                        if fname.endswith(".eml"):
                            msg_id = fname[:-4]
                            emails.append({
                                "msg_id": msg_id,
                                "provider": provider,
                                "path": os.path.join(provider_dir, fname),
                            })

    if not emails:
        print("No emails to extract. Run 'jabbar fetch' first.")
        return []

    endpoint = config["extraction"]["llm_endpoint"]
    print(f"\nChecking LLM at {endpoint}...")
    try:
        import urllib.request
        req = urllib.request.Request(f"{endpoint.rsplit('/', 1)[0]}/models")
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        print(f"Error: Local LLM not available at {endpoint}.")
        print("Start LM Studio and load Qwen2.5-7B-Instruct.")
        sys.exit(1)

    print(f"Extracting transactions from {len(emails)} emails...")
    return extract_all(emails, config, data_dir)


def cmd_analyze(config: dict, data_dir: str, transactions: list[dict] = None) -> dict:
    from src.analyze.claude_analyzer import analyze_transactions
    import json
    import os

    if transactions is None:
        tx_path = os.path.join(data_dir, "extracted", "transactions.json")
        if not os.path.exists(tx_path):
            print("No transactions found. Run 'jabbar extract' first.")
            return {}
        with open(tx_path) as f:
            transactions = json.load(f)

    return analyze_transactions(transactions, config, data_dir)


def cmd_tui(data_dir: str) -> None:
    from src.tui.app import JabbarApp
    app = JabbarApp(data_dir=data_dir)
    app.title = "Jabbar"
    app.sub_title = "Email Financial Intelligence"
    app.run()


def main(argv: list[str] = None) -> None:
    args = parse_args(argv)

    if args.command == "tui":
        cmd_tui(args.data_dir)
        return

    from src.config import load_config, ConfigError
    try:
        config = load_config(args.config)
    except ConfigError as e:
        print(f"Config error: {e}")
        sys.exit(1)

    if args.command == "fetch":
        cmd_fetch(config, args.data_dir)
    elif args.command == "extract":
        cmd_extract(config, args.data_dir)
    elif args.command == "analyze":
        cmd_analyze(config, args.data_dir)
    elif args.command == "run":
        emails = cmd_fetch(config, args.data_dir)
        transactions = cmd_extract(config, args.data_dir, emails)
        try:
            cmd_analyze(config, args.data_dir, transactions)
        except Exception as e:
            print(f"Analysis skipped: {e}")
        cmd_tui(args.data_dir)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run tests, verify pass**

Run: `pytest tests/test_main.py -v`
Expected: All 4 tests PASS.

- [ ] **Step 4: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/main.py tests/test_main.py
git commit -m "feat: Jabbar CLI entry point with fetch/extract/analyze/tui commands"
```

---

### Task 10: Integration Test with Real Data

This task uses the existing test data and config to verify the full pipeline works end-to-end.

**Files:**
- Create: `tests/test_integration.py`

- [ ] **Step 1: Write integration test**

```python
# tests/test_integration.py
"""
Integration test — requires:
- config.yaml with real credentials
- LM Studio running with Qwen2.5-7B-Instruct
Skip if not available.
"""
import json
import os
import pytest
from src.config import load_config, ConfigError


def config_available():
    try:
        load_config("config.yaml")
        return True
    except (ConfigError, FileNotFoundError):
        return False


def lm_studio_available():
    import urllib.request
    try:
        urllib.request.urlopen("http://localhost:1234/v1/models", timeout=3)
        return True
    except Exception:
        return False


@pytest.mark.skipif(not config_available(), reason="config.yaml not found")
def test_fetch_one_account():
    config = load_config("config.yaml")
    account = config["accounts"][0]

    if account["auth"] == "app_password":
        from src.auth.imap_auth import connect_imap
        conn = connect_imap(account["imap_host"], account["imap_port"], account["email"], account["password"])
    else:
        from src.auth.oauth2_auth import get_oauth2_connection
        conn = get_oauth2_connection(account)

    from src.fetch.email_fetcher import search_financial_emails, calculate_since_date
    conn.select(account.get("mailbox", "INBOX"), readonly=True)
    since = calculate_since_date(1)  # just 1 month for speed
    ids = search_financial_emails(conn, ["receipt", "payment"], since)
    conn.logout()

    assert isinstance(ids, set)


@pytest.mark.skipif(
    not (config_available() and lm_studio_available()),
    reason="config.yaml or LM Studio not available",
)
def test_extract_one_email():
    from src.extract.llm_extractor import extract_transaction

    config = load_config("config.yaml")
    result = extract_transaction(
        "Your receipt from Chipotle",
        "Order total: $17.53\nChicken Bowl\nDate: 2026-04-15",
        config,
    )
    assert result is not None
    assert result.get("is_transaction") is True
    assert result.get("amount") == 17.53 or result.get("amount") is not None
```

- [ ] **Step 2: Run integration tests**

Run: `pytest tests/test_integration.py -v -s`
Expected: Tests pass if config.yaml and LM Studio are available; skip otherwise.

- [ ] **Step 3: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: integration tests for fetch and extract pipeline"
```

---

### Task 11: Gitignore and Config Hygiene

**Files:**
- Create: `.gitignore` (if not already present or incomplete)

- [ ] **Step 1: Ensure .gitignore covers all sensitive/generated files**

```
venv/
data/
config.yaml
.hotmail_tokens.json
__pycache__/
*.pyc
.env
```

Verify with: `git status` — no sensitive files should appear.

- [ ] **Step 2: Commit**

```bash
git add .gitignore
git commit -m "chore: ensure .gitignore covers all sensitive files"
```

---

## Implementation Notes for the Executing LLM

These are critical details that the tests won't catch:

1. **Gmail mailbox quoting**: When selecting the Gmail mailbox in `cmd_fetch`, the config value `'"[Gmail]/All Mail"'` already includes the IMAP quoting. Pass it directly to `conn.select()`.

2. **OAuth2 full re-auth**: In `get_oauth2_connection`, if both the access token AND refresh token are expired/invalid, delete the cached token file and fall through to the browser auth flow. The current implementation does this — don't regress it.

3. **IMAP retry with backoff**: `connect_imap` uses `time.sleep(2 ** (attempt + 1))` for exponential backoff on connection failures (2s, 4s, 8s). Auth failures raise immediately — don't retry those.

4. **Progress display**: `extract_all` should print elapsed time alongside ETA. The current implementation shows ETA but not elapsed — add elapsed time to the progress line.

5. **TUI without insights**: The TUI must work even if `insights.json` doesn't exist (e.g., Claude analysis was skipped). It falls back to computing categories from raw transaction data. Test this by running `jabbar tui` after `extract` but before `analyze`.

6. **Error messages**: When IMAP auth fails, include the provider name and specific guidance:
   - Gmail/Yahoo: "Check your app password"
   - Hotmail: "Re-run the OAuth flow — your token may have expired"

---

## Post-Implementation Checklist

After all tasks are complete, verify:

- [ ] `pytest tests/ -v` — all tests pass
- [ ] `python -m src.main fetch` — connects to all 3 accounts, downloads emails
- [ ] `python -m src.main extract` — local LLM extracts transactions (check `data/extracted/transactions.json`)
- [ ] `python -m src.main analyze` — Claude generates insights (check `data/analysis/insights.json`)
- [ ] `python -m src.main tui` — TUI launches with all 5 tabs populated
- [ ] `python -m src.main` — full pipeline runs end to end
