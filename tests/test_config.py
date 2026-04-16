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
