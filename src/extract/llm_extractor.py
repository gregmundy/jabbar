import json
import os
import re
import time
import urllib.request


EXTRACTION_PROMPT = """You are a financial data extractor. Analyze this email and extract any financial transaction.

Return ONLY valid JSON:
{
  "is_transaction": boolean,
  "merchant": string or null,
  "date": "YYYY-MM-DD" or null,
  "amount": number or null,
  "category": "subscription|utilities|food_dining|food_delivery|services|shopping|insurance|medical|transportation|credit_card|other|scam",
  "description": "brief description" or null,
  "is_recurring": boolean or null,
  "payment_method": "description" or null
}

Rules:
- is_transaction is true ONLY for actual charges, payments, receipts, invoices, or statements with amounts
- Marketing, promos, and rewards emails are NOT transactions
- For credit card statements, extract the statement balance as the amount
- Extract the most prominent/total dollar amount, not subtotals
- If the email appears to be a scam or phishing attempt, set category to "scam" and is_transaction to false"""


def parse_llm_response(raw: str) -> dict | None:
    raw = raw.strip()
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
    if fence_match:
        raw = fence_match.group(1).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def extract_transaction(subject: str, body: str, config: dict) -> dict | None:
    endpoint = config["extraction"]["llm_endpoint"]
    payload = {
        "model": config["extraction"]["llm_model"],
        "messages": [
            {"role": "system", "content": EXTRACTION_PROMPT},
            {"role": "user", "content": f"Subject: {subject}\n\nBody:\n{body}"},
        ],
        "temperature": config["extraction"]["temperature"],
        "max_tokens": config["extraction"]["max_tokens"],
    }
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        resp = urllib.request.urlopen(req, timeout=120)
        result = json.loads(resp.read())
        content = result["choices"][0]["message"]["content"]
        return parse_llm_response(content)
    except (urllib.error.URLError, OSError) as e:
        print(f"  LLM error: {e}")
        return None


def extract_all(
    emails: list[dict],
    config: dict,
    data_dir: str,
) -> list[dict]:
    output_path = os.path.join(data_dir, "extracted", "transactions.json")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    existing = []
    existing_ids = set()
    if os.path.exists(output_path):
        with open(output_path) as f:
            existing = json.load(f)
            existing_ids = {e["email_id"] for e in existing}

    to_process = [e for e in emails if e["msg_id"] not in existing_ids]
    skipped = len(emails) - len(to_process)
    if skipped:
        print(f"Skipping {skipped} already-extracted emails, processing {len(to_process)} remaining")

    from src.preprocess.html_stripper import get_email_body

    results = list(existing)
    start_time = time.time()

    for i, email_info in enumerate(to_process):
        with open(email_info["path"], "rb") as f:
            raw = f.read()

        body, source = get_email_body(raw, config["extraction"].get("max_body_chars", 8000))

        import email as email_lib
        from email.header import decode_header

        msg = email_lib.message_from_bytes(raw)
        subject = msg.get("Subject", "")
        if subject:
            decoded = decode_header(subject)
            subject = " ".join(
                p.decode(e or "utf-8") if isinstance(p, bytes) else p
                for p, e in decoded
            )

        extracted = extract_transaction(subject, body, config)

        if extracted:
            extracted["email_id"] = email_info["msg_id"]
            extracted["provider"] = email_info["provider"]
            extracted["raw_subject"] = subject
            extracted["extraction_source"] = source
            results.append(extracted)

        with open(output_path, "w") as f:
            json.dump(results, f, indent=2)

        elapsed = time.time() - start_time
        avg_per = elapsed / (i + 1)
        remaining = avg_per * (len(to_process) - i - 1)
        pct = (i + 1) / len(to_process) * 100
        print(
            f"  Extracting: [{i + 1}/{len(to_process)}] {email_info['provider']} "
            f"— \"{subject[:50]}\" ({pct:.1f}%) "
            f"Elapsed: {elapsed / 60:.0f}m | ETA: {remaining / 60:.0f}m"
        )

    return results
