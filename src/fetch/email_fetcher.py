import imaplib
import os
from datetime import datetime, timedelta


def deduplicate_ids(id_sets: list[set]) -> set:
    result = set()
    for s in id_sets:
        result.update(s)
    return result


def search_financial_emails(
    conn: imaplib.IMAP4_SSL,
    keywords: list[str],
    since_date: str,
) -> set[bytes]:
    all_ids = []
    for kw in keywords:
        try:
            status, results = conn.search(None, f'SINCE {since_date} SUBJECT "{kw}"')
            if status == "OK" and results[0]:
                ids = set(results[0].split())
                all_ids.append(ids)
        except imaplib.IMAP4.error:
            continue
    return deduplicate_ids(all_ids)


def save_raw_email(raw: bytes, provider: str, msg_id: str, data_dir: str) -> str:
    dir_path = os.path.join(data_dir, "raw", provider)
    os.makedirs(dir_path, exist_ok=True)
    file_path = os.path.join(dir_path, f"{msg_id}.eml")
    with open(file_path, "wb") as f:
        f.write(raw)
    return file_path


def fetch_and_cache(
    conn: imaplib.IMAP4_SSL,
    msg_ids: set[bytes],
    provider: str,
    data_dir: str,
) -> list[dict]:
    results = []
    total = len(msg_ids)
    for i, msg_id in enumerate(sorted(msg_ids)):
        msg_id_str = msg_id.decode()
        cached_path = os.path.join(data_dir, "raw", provider, f"{msg_id_str}.eml")

        if os.path.exists(cached_path):
            results.append({"msg_id": msg_id_str, "provider": provider, "path": cached_path})
            continue

        try:
            status, data = conn.fetch(msg_id, "(RFC822)")
            if data[0] is not None:
                raw = data[0][1]
                path = save_raw_email(raw, provider, msg_id_str, data_dir)
                results.append({"msg_id": msg_id_str, "provider": provider, "path": path})
        except Exception as e:
            print(f"  Warning: Failed to fetch message {msg_id_str}: {e}")

        if (i + 1) % 50 == 0 or i + 1 == total:
            print(f"  Fetched {i + 1}/{total} emails from {provider}")

    return results


def calculate_since_date(months_back: int) -> str:
    dt = datetime.now() - timedelta(days=months_back * 30)
    return dt.strftime("%d-%b-%Y")
