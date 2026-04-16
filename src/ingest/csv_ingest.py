import csv
import hashlib
import json
import os
import re
from datetime import datetime


# Known merchant prefixes — map messy descriptions to clean names
MERCHANT_ALIASES = {
    "KROGER": "Kroger",
    "ALDI": "Aldi",
    "WALMART": "Walmart",
    "AMAZON MKTPL": "Amazon",
    "AMAZON.COM": "Amazon",
    "AMAZON PRIME": "Amazon Prime",
    "AMAZON KIDS": "Amazon Kids",
    "NETFLIX": "Netflix",
    "HULU": "Hulu",
    "SPOTIFY": "Spotify",
    "PARAMOUNT": "Paramount+",
    "CHATGPT SUBSCRIPTION": "ChatGPT",
    "OPENAI": "ChatGPT",
    "ATT*": "AT&T",
    "ATT* BILL PAYMENT": "AT&T Bill Payment",
    "AUDIBLE": "Audible",
    "APPLE.COM/BILL": "Apple",
    "GOOGLE *YOUTUBE": "YouTube",
    "GOOGLE *GOOGLE ONE": "Google One",
    "DISNEYPLUS": "Disney+",
    "HELP.MAX.COM": "Max",
    "SAMS SCAN": "Sam's Club",
    "COMCAST": "Comcast",
    "ONSTAR": "OnStar",
    "SXM*SIRIUSXM": "SiriusXM",
    "STATE FARM": "State Farm",
    "ACI*FIRSTENERGY": "FirstEnergy",
    "FIRSTENERGY": "FirstEnergy",
    "VECTOR SECURITY": "Vector Security",
    "SAMS CLUB": "Sam's Club",
    "SHEETZ": "Sheetz",
    "BEST BUY": "Best Buy",
    "ADVANCE AUTO": "Advance Auto Parts",
    "TRUGREEN": "TruGreen",
    "APPLEBEES": "Applebee's",
    "EXPERIAN": "Experian",
    "MCDONALDS": "McDonald's",
    "CHICK-FIL-A": "Chick-fil-A",
    "TACO BELL": "Taco Bell",
    "WENDYS": "Wendy's",
    "SUBWAY": "Subway",
    "CHIPOTLE": "Chipotle",
    "LOWES": "Lowe's",
    "LOWE'S": "Lowe's",
    "MORGANTOWN UTIL": "Morgantown Utilities",
    "PIZAZZ DANCE": "Pizazz Dance Academy",
    "INTEREST CHARGE": "Interest Charge",
    "INTERNET PAYMENT": "Payment",
    "HOME DEPOT": "Home Depot",
    "TARGET": "Target",
    "COSTCO": "Costco",
    "DOLLAR GENERAL": "Dollar General",
    "DOLLAR TREE": "Dollar Tree",
    "CVS": "CVS",
    "WALGREENS": "Walgreens",
}

# Map Discover categories to Jabbar categories
CATEGORY_MAP = {
    "Supermarkets": "food_dining",
    "Restaurants": "food_dining",
    "Gasoline": "transportation",
    "Services": "services",
    "Merchandise": "shopping",
    "Medical Services": "medical",
    "Payments and Credits": "credit_card",
    "Interest": "credit_card",
    "Fees": "credit_card",
    "Awards and Rebate Credits": "credit_card",
    "Travel/ Entertainment": "transportation",
    "Warehouse Clubs": "shopping",
    "Home Improvement": "shopping",
    "Automotive": "transportation",
    "Department Stores": "shopping",
    "Government Services": "services",
}

# US state abbreviations for stripping location suffixes
US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC",
}


def clean_merchant_name(description: str) -> str:
    desc = description.strip().strip('"')

    # Check known aliases first (longest match wins)
    desc_upper = desc.upper()
    best_match = ""
    best_name = ""
    for prefix, name in MERCHANT_ALIASES.items():
        if desc_upper.startswith(prefix.upper()) and len(prefix) > len(best_match):
            best_match = prefix
            best_name = name
    if best_name:
        return best_name

    # Generic cleanup for unknown merchants
    # Strip phone numbers
    cleaned = re.sub(r'\d{3}-\d{3}-\d{4}', '', desc)
    # Strip long digit sequences (transaction IDs, card numbers)
    cleaned = re.sub(r'\d{8,}', '', cleaned)
    # Strip APPLE PAY ENDING IN... patterns
    cleaned = re.sub(r'APPLE PAY ENDING IN.*', '', cleaned, flags=re.IGNORECASE)
    # Strip URLs
    cleaned = re.sub(r'\S+\.(COM|NET|ORG)\S*', '', cleaned, flags=re.IGNORECASE)
    # Strip store numbers like #755, #8326295
    cleaned = re.sub(r'#\d+', '', cleaned)

    # Split into words and strip location (city + state at the end)
    words = cleaned.split()
    # Remove trailing state abbreviation
    while words and words[-1].upper().rstrip('.,') in US_STATES:
        words.pop()
    # Remove trailing city name (typically ALL CAPS word before state)
    # Heuristic: remove trailing uppercase words that look like city names
    # Keep at least 2 words so we don't strip the actual merchant name
    while len(words) > 2 and words[-1].isupper() and len(words[-1]) > 1:
        words.pop()

    # Strip common prefixes
    name = ' '.join(words).strip()
    for prefix in ('SQ *', 'TST* ', 'SQ*', 'ACT*', 'ACI*', 'FSP*', 'LOY*'):
        if name.upper().startswith(prefix):
            name = name[len(prefix):]

    # Title case
    name = name.strip(' *.,;#').title()

    return name if name else description.title()


def map_category(discover_category: str) -> str:
    return CATEGORY_MAP.get(discover_category, "other")


def parse_csv_statement(
    csv_path: str,
    source_name: str = "bank_csv",
) -> list[dict]:
    transactions = []

    with open(csv_path, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw_desc = row.get("Description", "").strip().strip('"')
            trans_date = row.get("Trans. Date", "")
            amount_str = row.get("Amount", "0")
            category = row.get("Category", "").strip().strip('"')

            # Parse date from MM/DD/YYYY to YYYY-MM-DD
            try:
                date = datetime.strptime(trans_date, "%m/%d/%Y").strftime("%Y-%m-%d")
            except ValueError:
                date = trans_date

            # Parse amount
            try:
                amount = float(amount_str)
            except ValueError:
                amount = 0.0

            # Generate stable ID from date + description + amount
            id_string = f"{source_name}:{trans_date}:{raw_desc}:{amount_str}"
            email_id = f"csv-{source_name}-{hashlib.md5(id_string.encode()).hexdigest()[:12]}"

            merchant = clean_merchant_name(raw_desc)
            jabbar_category = map_category(category)

            transactions.append({
                "is_transaction": True,
                "merchant": merchant,
                "date": date,
                "amount": amount,
                "category": jabbar_category,
                "description": raw_desc[:80],
                "is_recurring": None,
                "payment_method": source_name,
                "email_id": email_id,
                "provider": source_name,
                "raw_subject": raw_desc,
                "extraction_source": "csv",
            })

    return transactions


def ingest_csv(
    csv_path: str,
    source_name: str,
    data_dir: str,
) -> list[dict]:
    output_path = os.path.join(data_dir, "extracted", f"transactions_{source_name}.json")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Load existing transactions for this source
    existing = []
    existing_ids = set()
    if os.path.exists(output_path):
        with open(output_path) as f:
            existing = json.load(f)
            existing_ids = {t["email_id"] for t in existing if "email_id" in t}

    # Parse new transactions
    new_transactions = parse_csv_statement(csv_path, source_name)

    # Deduplicate
    added = 0
    for tx in new_transactions:
        if tx["email_id"] not in existing_ids:
            existing.append(tx)
            existing_ids.add(tx["email_id"])
            added += 1

    # Save
    with open(output_path, "w") as f:
        json.dump(existing, f, indent=2)

    print(f"Ingested {added} transactions from {csv_path} ({len(new_transactions) - added} duplicates skipped)")
    print(f"Saved to {output_path} ({len(existing)} transactions)")

    return existing
