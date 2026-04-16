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
