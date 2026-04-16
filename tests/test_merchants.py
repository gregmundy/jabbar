from src.tui.app import build_merchant_summary


def test_build_merchant_summary_basic():
    tx = [
        {"merchant": "Netflix", "amount": 15.00, "date": "2025-01-15", "category": "subscription"},
        {"merchant": "Netflix", "amount": 15.00, "date": "2025-02-15", "category": "subscription"},
        {"merchant": "Netflix", "amount": 17.00, "date": "2025-03-15", "category": "subscription"},
        {"merchant": "Kroger", "amount": 50.00, "date": "2025-01-10", "category": "food_dining"},
        {"merchant": "Kroger", "amount": 75.00, "date": "2025-01-20", "category": "food_dining"},
    ]
    result = build_merchant_summary(tx)

    assert len(result) == 2
    # Sorted by total descending
    assert result[0]["merchant"] == "Kroger"
    assert result[0]["count"] == 2
    assert result[0]["total"] == 125.00
    assert result[0]["avg"] == 62.50

    assert result[1]["merchant"] == "Netflix"
    assert result[1]["count"] == 3
    assert result[1]["total"] == 47.00
    # avg_monthly is total / months_span where months_span = days / 30
    assert 20.0 < result[1]["avg_monthly"] < 30.0


def test_build_merchant_summary_monthly_avg():
    tx = [
        {"merchant": "AT&T", "amount": 200.00, "date": "2025-01-01", "category": "services"},
        {"merchant": "AT&T", "amount": 200.00, "date": "2025-02-01", "category": "services"},
        {"merchant": "AT&T", "amount": 210.00, "date": "2025-03-01", "category": "services"},
        {"merchant": "AT&T", "amount": 210.00, "date": "2025-04-01", "category": "services"},
    ]
    result = build_merchant_summary(tx)
    assert result[0]["merchant"] == "AT&T"
    # 820 total over ~3 months span (90 days / 30) = ~273/mo
    assert 260.0 < result[0]["avg_monthly"] < 290.0
    assert result[0]["first_seen"] == "2025-01-01"
    assert result[0]["last_seen"] == "2025-04-01"


def test_build_merchant_summary_skips_null_merchants():
    tx = [
        {"merchant": None, "amount": 10.00, "date": "2025-01-01", "category": "other"},
        {"merchant": "Test", "amount": 20.00, "date": "2025-01-01", "category": "other"},
    ]
    result = build_merchant_summary(tx)
    assert len(result) == 1
    assert result[0]["merchant"] == "Test"


def test_build_merchant_summary_skips_negative_amounts():
    tx = [
        {"merchant": "Store", "amount": 50.00, "date": "2025-01-01", "category": "shopping"},
        {"merchant": "Store", "amount": -10.00, "date": "2025-01-05", "category": "shopping"},
    ]
    result = build_merchant_summary(tx)
    assert result[0]["count"] == 1  # only counts positive
    assert result[0]["total"] == 50.00


def test_build_merchant_summary_with_recurring_overlay():
    tx = [
        {"merchant": "Netflix", "amount": 15.00, "date": "2025-01-15", "category": "subscription"},
        {"merchant": "Netflix", "amount": 15.00, "date": "2025-02-15", "category": "subscription"},
    ]
    recurring = [
        {"merchant": "Netflix", "frequency": "monthly", "trend": "stable"},
    ]
    result = build_merchant_summary(tx, recurring=recurring)
    assert result[0]["frequency"] == "monthly"
    assert result[0]["trend"] == "stable"


def test_build_merchant_summary_no_recurring():
    tx = [
        {"merchant": "Random Shop", "amount": 42.00, "date": "2025-01-15", "category": "shopping"},
    ]
    result = build_merchant_summary(tx)
    assert result[0]["frequency"] == ""
    assert result[0]["trend"] == ""
