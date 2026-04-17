import json
import os
import tempfile
from src.tui.app import (
    dedupe_transactions,
    fill_merchants_from_sender,
    load_tui_data,
    merchant_from_sender,
)


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


def test_dedupe_same_date_amount_merchant():
    """Two records with matching (date, amount, merchant) collapse to one."""
    txs = [
        {"date": "2025-11-29", "amount": 5600.00, "merchant": "Discover", "email_id": "a", "category": "credit_card"},
        {"date": "2025-11-29", "amount": 5600.00, "merchant": "Discover", "email_id": "b", "category": "credit_card"},
    ]
    result = dedupe_transactions(txs)
    assert len(result) == 1
    assert result[0]["merge_count"] == 2
    assert result[0]["source_email_ids"] == ["a", "b"]


def test_dedupe_absorbs_empty_merchant():
    """Empty-merchant record folds into the unique non-empty match."""
    txs = [
        {"date": "2025-11-17", "amount": 305.35, "merchant": "Bank of America", "email_id": "a", "category": "credit_card"},
        {"date": "2025-11-17", "amount": 305.35, "merchant": "", "email_id": "b", "category": "credit_card"},
    ]
    result = dedupe_transactions(txs)
    assert len(result) == 1
    # The merged record keeps the non-empty merchant (higher completeness)
    assert result[0]["merchant"] == "Bank of America"
    assert result[0]["merge_count"] == 2
    assert set(result[0]["source_email_ids"]) == {"a", "b"}


def test_dedupe_preserves_distinct_merchants():
    """Same date/amount with two different non-empty merchants stay separate."""
    txs = [
        {"date": "2025-04-15", "amount": 50.0, "merchant": "Chipotle", "email_id": "a"},
        {"date": "2025-04-15", "amount": 50.0, "merchant": "Target", "email_id": "b"},
    ]
    result = dedupe_transactions(txs)
    assert len(result) == 2


def test_dedupe_ambiguous_empty_not_absorbed():
    """If (date, amount) matches multiple non-empty merchants, empty-merchant stays separate."""
    txs = [
        {"date": "2025-04-15", "amount": 50.0, "merchant": "Chipotle", "email_id": "a"},
        {"date": "2025-04-15", "amount": 50.0, "merchant": "Target", "email_id": "b"},
        {"date": "2025-04-15", "amount": 50.0, "merchant": "", "email_id": "c"},
    ]
    result = dedupe_transactions(txs)
    assert len(result) == 3


def test_dedupe_keeps_records_without_keys():
    """Records missing date or amount pass through unchanged."""
    txs = [
        {"date": None, "amount": 10.0, "merchant": "A", "email_id": "a"},
        {"date": "2025-01-01", "amount": None, "merchant": "B", "email_id": "b"},
    ]
    result = dedupe_transactions(txs)
    assert len(result) == 2
    assert all("merge_count" not in r for r in result)


def test_dedupe_single_record_untouched():
    """A lone record gets no merge_count annotation."""
    tx = {"date": "2025-04-15", "amount": 50.0, "merchant": "Chipotle", "email_id": "a"}
    result = dedupe_transactions([tx])
    assert result == [tx]


def test_merchant_from_sender_exact_domain():
    assert merchant_from_sender("alerts@wellsfargo.com") == "Wells Fargo"
    assert merchant_from_sender("Discover <no-reply@discover.com>") == "Discover"


def test_merchant_from_sender_subdomain_strips_to_root():
    assert merchant_from_sender("noreply@email.wellsfargo.com") == "Wells Fargo"
    assert merchant_from_sender("notify@account.microsoft.com") == "Microsoft"


def test_merchant_from_sender_unknown_domain_title_cases_label():
    # support@ is a generic display name, so it shouldn't interfere with the fallback
    assert merchant_from_sender("<support@acmewidgets.com>") == "Acmewidgets"


def test_merchant_from_sender_pnc_mapped():
    assert merchant_from_sender("alerts@pnc.com") == "PNC"
    assert merchant_from_sender("noreply@secure.pncbank.com") == "PNC"


def test_merchant_from_sender_uses_display_name_when_domain_unknown():
    """Display name is preferred over generic label for unmapped domains."""
    result = merchant_from_sender('"Some Local Credit Union" <alerts@slcu.coop>')
    assert result == "Some Local Credit Union"


def test_merchant_from_sender_skips_generic_display_names():
    """Generic role addresses (no-reply, notifications) fall through to domain fallback."""
    assert merchant_from_sender('"no-reply" <x@acmewidgets.com>') == "Acmewidgets"
    assert merchant_from_sender('"Notifications" <x@acmewidgets.com>') == "Acmewidgets"


def test_merchant_from_sender_handles_display_name_format():
    assert merchant_from_sender("Chase Bank <no-reply@chase.com>") == "Chase"


def test_merchant_from_sender_returns_none_for_bad_input():
    assert merchant_from_sender("") is None
    assert merchant_from_sender(None) is None
    assert merchant_from_sender("not-an-email") is None


def test_fill_merchants_uses_embedded_from_header(tmp_path):
    """Empty-merchant record with from_header on the record gets filled."""
    txs = [
        {"merchant": None, "from_header": "alerts@wellsfargo.com", "provider": "gmail", "email_id": "1"},
        {"merchant": "Chipotle", "from_header": "order@chipotle.com", "provider": "gmail", "email_id": "2"},
    ]
    result = fill_merchants_from_sender(txs, str(tmp_path))
    assert result[0]["merchant"] == "Wells Fargo"
    assert result[0]["merchant_source"] == "sender"
    assert result[1]["merchant"] == "Chipotle"  # untouched
    assert "merchant_source" not in result[1]


def test_fill_merchants_reads_eml_when_header_missing(tmp_path):
    """When from_header isn't cached on the record, fall back to reading the .eml."""
    provider_dir = tmp_path / "raw" / "gmail"
    provider_dir.mkdir(parents=True)
    (provider_dir / "abc.eml").write_bytes(
        b"From: Chase <no-reply@chase.com>\nSubject: Test\n\nbody"
    )
    txs = [{"merchant": "", "provider": "gmail", "email_id": "abc"}]
    result = fill_merchants_from_sender(txs, str(tmp_path))
    assert result[0]["merchant"] == "Chase"
