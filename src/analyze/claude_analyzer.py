import json
import os
import re

import anthropic


ANALYSIS_PROMPT = """You are a financial analyst. I'm giving you a JSON array of transactions extracted from email over the last 24 months across multiple email accounts (Gmail, Yahoo, Hotmail).

Your job is to analyze this data and return a structured JSON report. Specifically:

1. **Recurring charges**: Group transactions by merchant. Identify which are recurring (same merchant, regular interval). Calculate monthly cost, detect frequency (monthly, quarterly, annual), and flag any price changes over time.

2. **Alerts**: Flag problems that need attention:
   - "red" severity: scams/phishing, failed/missed payments, accounts at risk
   - "yellow" severity: price increases, billing action required, unusually high charges
   - "green" severity: confirmed recurring charges (informational)

3. **Duplicate detection**: Multiple emails often refer to the same transaction (e.g., "Scheduled Payment", "Payment Received", and the statement all reference one Discover Card payment). Deduplicate — count the charge once.

4. **Categories**: Sum spending by category. Normalize merchant names (e.g., group "Discover Card" variants together).

5. **Monthly summary**: Total spending per month with transaction count.

6. **Recommendations**: Actionable suggestions — what to cancel, investigate, negotiate, or fix. Include estimated savings where possible.

7. **Scam detection**: Emails flagged as category "scam" by the extractor. Add any additional context about why they're suspicious.

Return ONLY valid JSON matching this schema:
{
    "alerts": [{"severity": "red|yellow|green", "type": "string", "merchant": "string", "message": "string", "details": "string with dates and amounts"}],
    "recurring": [{"merchant": "string", "monthly_cost": number, "annual_cost": number, "frequency": "monthly|quarterly|annual", "trend": "stable|increasing|decreasing", "months_active": number, "category": "string"}],
    "categories": {"category_name": number},
    "monthly_summary": [{"month": "YYYY-MM", "total": number, "transaction_count": number}],
    "recommendations": [{"action": "cancel|investigate|negotiate|fix", "merchant": "string", "potential_monthly_savings": number, "reason": "string"}],
    "scams_detected": [{"merchant": "string", "date": "YYYY-MM-DD", "amount_claimed": number, "description": "string", "indicators": ["string"]}]
}"""


def filter_transactions(transactions: list[dict]) -> list[dict]:
    return [t for t in transactions if t.get("is_transaction") is True]


def parse_analysis_response(raw: str) -> dict | None:
    raw = raw.strip()
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
    if fence_match:
        raw = fence_match.group(1).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def analyze_transactions(transactions: list[dict], config: dict, data_dir: str) -> dict:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("Set ANTHROPIC_API_KEY environment variable.")

    filtered = filter_transactions(transactions)
    if not filtered:
        return {"alerts": [], "recurring": [], "categories": {}, "monthly_summary": [], "recommendations": [], "scams_detected": []}

    client = anthropic.Anthropic(api_key=api_key)
    print(f"Analyzing {len(filtered)} transactions with Claude...")

    message = client.messages.create(
        model=config["analysis"]["claude_model"],
        max_tokens=8000,
        system=ANALYSIS_PROMPT,
        messages=[{"role": "user", "content": json.dumps(filtered)}],
    )

    raw_response = message.content[0].text
    result = parse_analysis_response(raw_response)

    if result is None:
        print("Warning: Claude returned invalid JSON. Saving raw response.")
        result = {"raw_response": raw_response, "alerts": [], "recurring": [], "categories": {}, "monthly_summary": [], "recommendations": [], "scams_detected": []}

    output_path = os.path.join(data_dir, "analysis", "insights.json")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(result, f, indent=2)

    print(f"Analysis complete. {len(result.get('alerts', []))} alerts, {len(result.get('recommendations', []))} recommendations.")
    return result
