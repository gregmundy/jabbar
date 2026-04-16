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
