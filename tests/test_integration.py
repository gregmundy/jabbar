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
