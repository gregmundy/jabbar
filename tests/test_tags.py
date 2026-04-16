import json
from src.ingest.csv_ingest import parse_csv_statement
from src.fetch.email_fetcher import save_raw_email


def test_csv_ingest_carries_tag(tmp_path):
    csv_file = tmp_path / "test.csv"
    csv_file.write_text(
        'Trans. Date,Post Date,Description,Amount,Category\n'
        '04/26/2024,04/27/2024,"HULU 877-8244858 CA",19.25,"Services"\n'
    )
    transactions = parse_csv_statement(str(csv_file), source_name="discover", tag="Personal")
    assert transactions[0]["tag"] == "Personal"


def test_csv_ingest_tag_defaults_to_none(tmp_path):
    csv_file = tmp_path / "test.csv"
    csv_file.write_text(
        'Trans. Date,Post Date,Description,Amount,Category\n'
        '04/26/2024,04/27/2024,"HULU 877-8244858 CA",19.25,"Services"\n'
    )
    transactions = parse_csv_statement(str(csv_file), source_name="discover")
    assert transactions[0]["tag"] is None


def test_tui_loads_tags(tmp_path):
    from src.tui.app import load_tui_data

    extracted_dir = tmp_path / "extracted"
    extracted_dir.mkdir()

    transactions = [
        {"is_transaction": True, "merchant": "A", "amount": 10.0, "date": "2025-01-01",
         "category": "shopping", "email_id": "1", "provider": "gmail", "tag": "Work"},
        {"is_transaction": True, "merchant": "B", "amount": 20.0, "date": "2025-01-02",
         "category": "food_dining", "email_id": "2", "provider": "discover", "tag": "Personal"},
    ]
    (extracted_dir / "transactions.json").write_text(json.dumps(transactions))

    data = load_tui_data(str(tmp_path))
    assert data["transactions"][0]["tag"] == "Work"
    assert data["transactions"][1]["tag"] == "Personal"
