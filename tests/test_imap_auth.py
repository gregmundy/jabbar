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
