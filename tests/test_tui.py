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
