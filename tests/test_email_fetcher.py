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
