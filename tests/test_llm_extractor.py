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
