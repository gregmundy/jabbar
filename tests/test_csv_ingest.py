import json
import os
from src.ingest.csv_ingest import (
    clean_merchant_name,
    map_category,
    parse_csv_statement,
    ingest_csv,
)


def test_clean_merchant_name_strips_location():
    assert clean_merchant_name("KROGER #755 MORGANTOWN WV") == "Kroger"


def test_clean_merchant_name_strips_phone():
    assert clean_merchant_name("ATT* BILL PAYMENT 800-331-0500 TX") == "AT&T Bill Payment"


def test_clean_merchant_name_strips_card_details():
    # SQ (Square) merchants — extracts business name from messy description
    result = clean_merchant_name(
        "SQ *JOE@LEVERAGEFITNES GOSQ.COM WVAPPLE PAY ENDING IN 27270001152921513980395759"
    )
    assert "Joe" in result
    assert "APPLE PAY" not in result


def test_clean_merchant_name_hulu():
    assert clean_merchant_name("HULU 877-8244858 CA HULU.COM/BILLCAHULU 877-8244858 CA") == "Hulu"


def test_clean_merchant_name_netflix():
    assert clean_merchant_name("NETFLIX.COM NETFLIX.COM CA30417894556830240") == "Netflix"


def test_clean_merchant_name_spotify():
    assert clean_merchant_name("SPOTIFY P2C06B8730 8777781161 NY") == "Spotify"


def test_map_category_supermarkets():
    assert map_category("Supermarkets") == "food_dining"


def test_map_category_restaurants():
    assert map_category("Restaurants") == "food_dining"


def test_map_category_gasoline():
    assert map_category("Gasoline") == "transportation"


def test_map_category_services():
    assert map_category("Services") == "services"


def test_map_category_merchandise():
    assert map_category("Merchandise") == "shopping"


def test_map_category_medical():
    assert map_category("Medical Services") == "medical"


def test_map_category_unknown():
    assert map_category("Something Weird") == "other"


def test_map_category_payments_credits():
    assert map_category("Payments and Credits") == "credit_card"


def test_parse_csv_statement(tmp_path):
    csv_file = tmp_path / "test.csv"
    csv_file.write_text(
        'Trans. Date,Post Date,Description,Amount,Category\n'
        '04/26/2024,04/27/2024,"HULU 877-8244858 CA",19.25,"Services"\n'
        '04/28/2024,04/28/2024,"KROGER #755 MORGANTOWN WV",69.12,"Supermarkets"\n'
        '05/05/2024,05/07/2024,"BEST BUY 00008326295 MORGANTOWN WV",-3.11,"Payments and Credits"\n'
    )
    transactions = parse_csv_statement(str(csv_file), source_name="discover")
    assert len(transactions) == 3

    assert transactions[0]["merchant"] == "Hulu"
    assert transactions[0]["amount"] == 19.25
    assert transactions[0]["date"] == "2024-04-26"
    assert transactions[0]["is_transaction"] is True
    assert transactions[0]["provider"] == "discover"
    assert transactions[0]["category"] == "services"

    assert transactions[1]["merchant"] == "Kroger"
    assert transactions[1]["category"] == "food_dining"

    # Negative amount (refund/credit)
    assert transactions[2]["amount"] == -3.11
    assert transactions[2]["category"] == "credit_card"


def test_parse_csv_preserves_raw_description(tmp_path):
    csv_file = tmp_path / "test.csv"
    csv_file.write_text(
        'Trans. Date,Post Date,Description,Amount,Category\n'
        '04/26/2024,04/27/2024,"NETFLIX.COM NETFLIX.COM CA30417894556830240",24.60,"Services"\n'
    )
    transactions = parse_csv_statement(str(csv_file), source_name="discover")
    assert transactions[0]["raw_subject"] == "NETFLIX.COM NETFLIX.COM CA30417894556830240"
    assert transactions[0]["merchant"] == "Netflix"


def test_ingest_csv_writes_source_file(tmp_path):
    csv_file = tmp_path / "test.csv"
    csv_file.write_text(
        'Trans. Date,Post Date,Description,Amount,Category\n'
        '04/26/2024,04/27/2024,"HULU 877-8244858 CA",19.25,"Services"\n'
    )

    result = ingest_csv(str(csv_file), "discover", str(tmp_path))
    assert len(result) == 1

    # Verify file was written to source-specific path
    output_path = tmp_path / "extracted" / "transactions_discover.json"
    assert output_path.exists()
    with open(output_path) as f:
        saved = json.load(f)
    assert len(saved) == 1


def test_ingest_csv_deduplicates(tmp_path):
    csv_file = tmp_path / "test.csv"
    csv_file.write_text(
        'Trans. Date,Post Date,Description,Amount,Category\n'
        '04/26/2024,04/27/2024,"HULU 877-8244858 CA",19.25,"Services"\n'
    )

    # Ingest twice
    ingest_csv(str(csv_file), "discover", str(tmp_path))
    result = ingest_csv(str(csv_file), "discover", str(tmp_path))

    # Should not duplicate
    assert len(result) == 1
