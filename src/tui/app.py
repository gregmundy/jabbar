import email as email_lib
import json
import os
import re
from collections import defaultdict
from email.header import decode_header
from email.utils import parseaddr

from rich.markup import escape as esc
from textual.app import App
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.theme import Theme
from textual.widgets import Header, Footer, Static, DataTable, TabbedContent, TabPane, Rule

from src.preprocess.html_stripper import get_email_body
from src.tui.widgets.charts import MonthlySpendChart, CategoryChart


def _norm_merchant(m) -> str:
    return (m or "").strip().lower() if isinstance(m, str) else ""


def _completeness_score(rec: dict) -> int:
    score = 0
    if rec.get("merchant"):
        score += 3
    if rec.get("description"):
        score += 1
    if rec.get("category") and rec.get("category") != "other":
        score += 1
    if rec.get("is_recurring") is not None:
        score += 1
    return score


def _merge_group(records: list[dict]) -> dict:
    if len(records) == 1:
        return records[0]
    best = max(records, key=_completeness_score)
    merged = dict(best)
    ids = sorted({r.get("email_id") for r in records if r.get("email_id")})
    merged["source_email_ids"] = ids
    merged["merge_count"] = len(records)
    return merged


def dedupe_transactions(transactions: list[dict]) -> list[dict]:
    """Collapse transactions that refer to the same real-world charge.

    Keys on (date, rounded amount, normalized merchant). Transactions with an
    empty merchant are absorbed into a uniquely-matching (date, amount) group
    if one exists — this catches the common case where the LLM parses the
    merchant from one email (a statement) but not another (a scheduled-payment
    notice) for the same charge.
    """
    strict: dict[tuple, list[dict]] = defaultdict(list)
    unkeyed: list[dict] = []

    for t in transactions:
        date = t.get("date")
        amt = t.get("amount")
        if not date or amt is None:
            unkeyed.append(t)
            continue
        try:
            amt_key = round(float(amt), 2)
        except (TypeError, ValueError):
            unkeyed.append(t)
            continue
        key = (date, amt_key, _norm_merchant(t.get("merchant")))
        strict[key].append(t)

    da_to_nonempty: dict[tuple, list[tuple]] = defaultdict(list)
    for key in strict:
        date, amt, m = key
        if m:
            da_to_nonempty[(date, amt)].append(key)

    consumed: set[tuple] = set()
    final: dict[tuple, list[dict]] = {}

    for key in list(strict.keys()):
        date, amt, m = key
        if m:
            continue
        candidates = da_to_nonempty.get((date, amt), [])
        if len(candidates) == 1:
            target = candidates[0]
            final.setdefault(target, list(strict[target]))
            final[target].extend(strict[key])
            consumed.add(key)

    for key, records in strict.items():
        if key in consumed:
            continue
        if key not in final:
            final[key] = list(records)

    result = [_merge_group(recs) for recs in final.values()]
    result.extend(unkeyed)
    return result


MERCHANT_BY_DOMAIN = {
    "wellsfargo.com": "Wells Fargo",
    "chase.com": "Chase",
    "jpmorganchase.com": "Chase",
    "discover.com": "Discover",
    "bankofamerica.com": "Bank of America",
    "capitalone.com": "Capital One",
    "americanexpress.com": "American Express",
    "aexp.com": "American Express",
    "usbank.com": "U.S. Bank",
    "pnc.com": "PNC",
    "pncbank.com": "PNC",
    "citibank.com": "Citi",
    "citi.com": "Citi",
    "tdbank.com": "TD Bank",
    "barclaysus.com": "Barclays",
    "usaa.com": "USAA",
    "navyfederal.org": "Navy Federal",
    "synchrony.com": "Synchrony",
    "syf.com": "Synchrony",
    "ally.com": "Ally",
    "fidelity.com": "Fidelity",
    "vanguard.com": "Vanguard",
    "schwab.com": "Charles Schwab",
    "paypal.com": "PayPal",
    "venmo.com": "Venmo",
    "zelle.com": "Zelle",
    "robinhood.com": "Robinhood",
    "coinbase.com": "Coinbase",
    "amazon.com": "Amazon",
    "apple.com": "Apple",
    "google.com": "Google",
    "att.com": "AT&T",
    "verizon.com": "Verizon",
    "comcast.net": "Comcast",
    "xfinity.com": "Xfinity",
    "netflix.com": "Netflix",
    "spotify.com": "Spotify",
    "youtube.com": "YouTube",
    "uber.com": "Uber",
    "lyft.com": "Lyft",
    "doordash.com": "DoorDash",
    "grubhub.com": "Grubhub",
    "progressive.com": "Progressive",
    "geico.com": "GEICO",
    "statefarm.com": "State Farm",
    "allstate.com": "Allstate",
    "anthem.com": "Anthem",
    "firstenergy.com": "FirstEnergy",
    "openai.com": "OpenAI",
    "anthropic.com": "Anthropic",
}


_GENERIC_DISPLAY_NAME = re.compile(
    r"^(no[-_.\s]?reply|donotreply|do[-_.\s]?not[-_.\s]?reply|notifications?|"
    r"alerts?|info|support|admin|mailer|customer[-_.\s]?service|service|help|team)$",
    re.I,
)


def merchant_from_sender(from_header) -> str | None:
    """Infer a merchant name from an email's From: header.

    Order of preference:
    1. Curated domain map (with root-domain matching so subdomains resolve).
    2. Display name, if it's not a generic role address (e.g., "no-reply").
    3. Second-to-last domain label, title-cased.
    """
    if not from_header or not isinstance(from_header, str):
        return None
    name, addr = parseaddr(from_header)
    if "@" not in (addr or ""):
        return None
    domain = addr.split("@", 1)[1].lower().strip().strip(">")
    if not domain:
        return None

    parts = domain.split(".")
    for i in range(len(parts)):
        root = ".".join(parts[i:])
        if root in MERCHANT_BY_DOMAIN:
            return MERCHANT_BY_DOMAIN[root]

    if name:
        cleaned = re.sub(r"\s+", " ", name).strip().strip('"').strip("'")
        if cleaned and not _GENERIC_DISPLAY_NAME.match(cleaned):
            return cleaned

    if len(parts) >= 2:
        return parts[-2].title()
    return None


def _read_from_header(eml_path: str) -> str | None:
    try:
        with open(eml_path, "rb") as f:
            msg = email_lib.message_from_bytes(f.read())
    except OSError:
        return None
    return msg.get("From")


def fill_merchants_from_sender(transactions: list[dict], data_dir: str) -> list[dict]:
    """Fill empty merchants by inferring from each email's From: header."""
    for t in transactions:
        if t.get("merchant"):
            continue
        from_hdr = t.get("from_header")
        if not from_hdr and t.get("provider") and t.get("email_id"):
            eml_path = os.path.join(data_dir, "raw", t["provider"], f"{t['email_id']}.eml")
            from_hdr = _read_from_header(eml_path)
        if from_hdr:
            inferred = merchant_from_sender(from_hdr)
            if inferred:
                t["merchant"] = inferred
                t["merchant_source"] = "sender"
    return transactions


def load_tui_data(data_dir: str) -> dict:
    transactions = []
    seen_ids = set()
    insights = {"alerts": [], "recurring": [], "categories": {}, "monthly_summary": [], "recommendations": [], "scams_detected": []}

    # Load all transaction files (transactions.json + transactions_*.json)
    extracted_dir = os.path.join(data_dir, "extracted")
    if os.path.isdir(extracted_dir):
        for fname in sorted(os.listdir(extracted_dir)):
            if fname.startswith("transactions") and fname.endswith(".json"):
                fpath = os.path.join(extracted_dir, fname)
                with open(fpath) as f:
                    for t in json.load(f):
                        if t.get("is_transaction"):
                            tid = t.get("email_id", id(t))
                            if tid not in seen_ids:
                                transactions.append(t)
                                seen_ids.add(tid)

    transactions = dedupe_transactions(transactions)
    transactions = fill_merchants_from_sender(transactions, data_dir)

    insights_path = os.path.join(data_dir, "analysis", "insights.json")
    if os.path.exists(insights_path):
        with open(insights_path) as f:
            insights = json.load(f)

    return {"transactions": transactions, "insights": insights}


def build_merchant_summary(transactions: list[dict], recurring: list[dict] = None) -> list[dict]:
    from datetime import datetime

    # Build recurring lookup
    rec_lookup = {}
    if recurring:
        for r in recurring:
            rec_lookup[r.get("merchant", "")] = r

    # Group by merchant
    merchants = defaultdict(lambda: {"amounts": [], "dates": [], "category": ""})
    for t in transactions:
        m = t.get("merchant")
        if not m:
            continue
        amt = t.get("amount")
        if amt is not None and amt > 0:
            merchants[m]["amounts"].append(amt)
            if t.get("date"):
                merchants[m]["dates"].append(t["date"])
            if not merchants[m]["category"]:
                merchants[m]["category"] = t.get("category", "")

    # Build summary rows
    result = []
    for merchant, data in merchants.items():
        amounts = data["amounts"]
        dates = sorted(data["dates"])
        if not amounts:
            continue

        total = sum(amounts)
        count = len(amounts)
        avg = total / count

        # Calculate monthly average based on date span
        if len(dates) >= 2:
            try:
                first = datetime.strptime(dates[0], "%Y-%m-%d")
                last = datetime.strptime(dates[-1], "%Y-%m-%d")
                months_span = max(1, (last - first).days / 30)
            except ValueError:
                months_span = 1
            avg_monthly = total / months_span
        else:
            months_span = 1
            avg_monthly = total

        # Overlay recurring info from Claude analysis
        rec = rec_lookup.get(merchant, {})

        result.append({
            "merchant": merchant,
            "count": count,
            "total": total,
            "avg": avg,
            "avg_monthly": avg_monthly,
            "first_seen": dates[0] if dates else "",
            "last_seen": dates[-1] if dates else "",
            "category": data["category"],
            "frequency": rec.get("frequency", ""),
            "trend": rec.get("trend", ""),
        })

    result.sort(key=lambda r: r["total"], reverse=True)
    return result


def _fmt_currency(val: float) -> str:
    if val >= 1_000_000:
        return f"${val / 1_000_000:,.1f}M"
    if val >= 10_000:
        return f"${val / 1_000:,.1f}K"
    return f"${val:,.0f}"


class SummaryCard(Static):
    pass


def _decode_header(value: str) -> str:
    if not value:
        return ""
    decoded = decode_header(value)
    return " ".join(
        p.decode(e or "utf-8", errors="replace") if isinstance(p, bytes) else p
        for p, e in decoded
    )


class EmailInspectorScreen(ModalScreen):
    BINDINGS = [("escape", "dismiss", "Close")]

    DEFAULT_CSS = """
    EmailInspectorScreen {
        align: center middle;
    }
    #inspector-container {
        width: 90%;
        height: 90%;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }
    #inspector-title {
        background: $primary 20%;
        padding: 0 1;
        margin-bottom: 1;
        text-style: bold;
    }
    #inspector-scroll {
        padding: 0 1;
    }
    .section-header {
        color: $primary;
        text-style: bold;
        margin-top: 1;
    }
    """

    def __init__(self, transaction: dict, data_dir: str):
        super().__init__()
        self.transaction = transaction
        self.data_dir = data_dir

    def compose(self):
        with Container(id="inspector-container"):
            email_id = self.transaction.get("email_id", "")
            yield Static(f"Email: {email_id}   —   Esc to close", id="inspector-title")
            with VerticalScroll(id="inspector-scroll"):
                yield Static(self._render_metadata())
                body = self._render_body()
                if body:
                    yield Static("── Body (what the LLM saw) ──", classes="section-header")
                    yield Static(body, markup=False)

    def _eml_path(self) -> str | None:
        provider = self.transaction.get("provider")
        email_id = self.transaction.get("email_id")
        if not provider or not email_id:
            return None
        return os.path.join(self.data_dir, "raw", provider, f"{email_id}.eml")

    def _render_metadata(self) -> str:
        t = self.transaction
        source = t.get("extraction_source", "")
        lines: list[str] = []

        if source == "csv":
            lines.append(f"[b]Source:[/] CSV ({esc(t.get('provider') or '')})")
            raw_desc = t.get("raw_subject") or ""
            lines.append(f"[b]Description:[/] {esc(raw_desc)}")
        else:
            eml_path = self._eml_path()
            if eml_path and os.path.exists(eml_path):
                try:
                    with open(eml_path, "rb") as f:
                        msg = email_lib.message_from_bytes(f.read())
                    lines.append(f"[b]From:[/] {esc(_decode_header(msg.get('From', '')))}")
                    lines.append(f"[b]Subject:[/] {esc(_decode_header(msg.get('Subject', '')))}")
                    lines.append(f"[b]Date:[/] {esc(msg.get('Date', '—'))}")
                except OSError as e:
                    lines.append(f"[dim]Could not read {esc(eml_path)}: {esc(str(e))}[/]")
            else:
                lines.append(f"[dim]No .eml file at {esc(eml_path or 'unknown path')}[/]")

        provider = t.get("provider") or "—"
        tag = t.get("tag") or "—"
        lines.append(f"[b]Provider:[/] {esc(provider)}   [b]Tag:[/] {esc(tag)}")

        merge_count = t.get("merge_count")
        if merge_count:
            sources = t.get("source_email_ids") or []
            lines.append(f"[b]Merged from:[/] {merge_count} emails  [dim]{esc(', '.join(sources))}[/]")

        lines.append("")
        lines.append("[b]── Extracted ──[/]")

        amt = t.get("amount")
        amt_str = f"${amt:,.2f}" if isinstance(amt, (int, float)) else "—"
        merchant_display = esc(str(t.get("merchant") or "—"))
        if t.get("merchant_source") == "sender":
            merchant_display += " [dim](inferred from sender)[/]"
        lines.append(f"[b]Merchant:[/] {merchant_display}")
        lines.append(f"[b]Amount:[/] {esc(amt_str)}   [b]Date:[/] {esc(str(t.get('date') or '—'))}")
        category = (t.get("category") or "—").replace("_", " ")
        lines.append(f"[b]Category:[/] {esc(category)}")
        lines.append(f"[b]Recurring:[/] {esc(str(t.get('is_recurring')))}")
        desc = t.get("description")
        if desc:
            lines.append(f"[b]Description:[/] {esc(str(desc))}")

        return "\n".join(lines)

    def _render_body(self) -> str:
        if self.transaction.get("extraction_source") == "csv":
            return ""
        eml_path = self._eml_path()
        if not eml_path or not os.path.exists(eml_path):
            return ""
        try:
            with open(eml_path, "rb") as f:
                raw = f.read()
        except OSError:
            return ""
        body, _ = get_email_body(raw, 20000)
        return body

    def action_dismiss(self):
        self.dismiss()


class JabbarApp(App):
    CSS = """
    Screen {
        background: $surface;
    }

    /* ── Summary Bar ── */
    #summary-bar {
        height: 3;
        layout: horizontal;
        padding: 0 1;
        background: $primary 15%;
    }
    .summary-card {
        width: 1fr;
        height: 3;
        content-align: center middle;
        text-style: bold;
        padding: 0 1;
    }
    .summary-card.-accent {
        color: $primary;
    }

    /* ── Tabs ── */
    TabbedContent {
        height: 1fr;
    }
    TabPane {
        padding: 0;
    }
    Underline > .underline--bar {
        color: $primary 40%;
    }

    /* ── Alerts ── */
    #alerts-container {
        height: 1fr;
        padding: 1 2;
    }
    .alert-card {
        margin-bottom: 1;
        padding: 1 2;
        background: $panel;
    }
    .alert-card.-red {
        border-left: thick $error;
    }
    .alert-card.-red .alert-icon {
        color: $error;
    }
    .alert-card.-yellow {
        border-left: thick $warning;
    }
    .alert-card.-yellow .alert-icon {
        color: $warning;
    }
    .alert-card.-green {
        border-left: thick $success;
    }
    .alert-card.-green .alert-icon {
        color: $success;
    }
    .alert-type {
        text-style: bold;
        text-opacity: 70%;
    }
    .alert-merchant {
        text-style: bold;
    }
    .alert-message {
        text-opacity: 85%;
    }
    .alert-details {
        text-opacity: 50%;
        margin-top: 0;
    }

    /* ── Recommendations ── */
    #recs-section {
        height: auto;
        max-height: 12;
        padding: 1 2;
        background: $primary 8%;
        margin: 0 0 1 0;
    }
    .rec-header {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    .rec-item {
        margin-bottom: 0;
        text-opacity: 85%;
    }

    /* ── Charts ── */
    PlotextPlot {
        height: 1fr;
        min-height: 20;
        margin: 1 2;
    }

    /* ── Data Tables ── */
    DataTable {
        height: 1fr;
        margin: 0 1;
    }
    DataTable > .datatable--header {
        text-style: bold;
        background: $primary 15%;
    }
    DataTable > .datatable--cursor {
        background: $primary 30%;
    }

    /* ── Footer ── */
    Footer {
        background: $panel;
    }

    /* ── Empty State ── */
    .empty-state {
        content-align: center middle;
        height: 1fr;
        text-opacity: 40%;
        text-style: italic;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("d", "toggle_dark", "Dark/Light"),
        ("r", "reload", "Reload"),
    ]

    def __init__(self, data_dir: str = "data", **kwargs):
        super().__init__(**kwargs)
        self._data_dir = data_dir
        self._data = load_tui_data(data_dir)
        self._tx_by_id: dict[str, dict] = {}

    def on_mount(self) -> None:
        self._setup_table_columns()
        self._populate_table_rows()

    def compose(self):
        yield Header(show_clock=True)

        tx = self._data["transactions"]
        insights = self._data["insights"]

        # Compute stats
        amounts = [t.get("amount", 0) or 0 for t in tx]
        total = sum(a for a in amounts if a > 0)
        monthly_summary = insights.get("monthly_summary", [])
        months = len(monthly_summary) if monthly_summary else 1
        avg = total / months if months else 0
        alerts = insights.get("alerts", [])
        red_count = sum(1 for a in alerts if a.get("severity") == "red")
        yellow_count = sum(1 for a in alerts if a.get("severity") == "yellow")
        recurring = insights.get("recurring", [])
        recurring_total = sum(r.get("monthly_cost", 0) for r in recurring)

        # Summary bar
        with Horizontal(id="summary-bar"):
            yield SummaryCard(f"TOTAL SPEND\n{_fmt_currency(total)}", id="sc-total", classes="summary-card -accent")
            yield SummaryCard(f"MONTHLY AVG\n{_fmt_currency(avg)}", id="sc-monthly", classes="summary-card")
            yield SummaryCard(f"RECURRING\n{_fmt_currency(recurring_total)}/mo", id="sc-recurring", classes="summary-card")
            yield SummaryCard(f"TRANSACTIONS\n{len(tx):,}", id="sc-tx", classes="summary-card")
            if red_count or yellow_count:
                alert_str = f"{red_count} critical" if red_count else ""
                if yellow_count:
                    alert_str += f"{'  ' if alert_str else ''}{yellow_count} warnings"
                yield SummaryCard(f"ALERTS\n{alert_str}", id="sc-alerts", classes="summary-card -accent")

        with TabbedContent():
            # ── Alerts Tab ──
            with TabPane("Alerts", id="alerts"):
                with VerticalScroll(id="alerts-container"):
                    recs = insights.get("recommendations", [])
                    if recs:
                        with Vertical(id="recs-section"):
                            yield Static("RECOMMENDATIONS", classes="rec-header")
                            for rec in recs[:5]:
                                action = rec.get("action", "").upper()
                                merchant = rec.get("merchant", "")
                                savings = rec.get("potential_monthly_savings", 0)
                                reason = rec.get("reason", "")
                                savings_str = f" — save ~${savings:.0f}/mo" if savings else ""
                                yield Static(
                                    f"  [{action}] {merchant}{savings_str}\n    {reason}",
                                    classes="rec-item",
                                )

                    if not alerts:
                        yield Static("No alerts. Run 'jabbar analyze' to generate insights.", classes="empty-state")

                    # Group alerts by severity
                    for severity in ("red", "yellow", "green"):
                        sev_alerts = [a for a in alerts if a.get("severity") == severity]
                        if not sev_alerts:
                            continue
                        for alert in sev_alerts:
                            icon = {"red": "▲", "yellow": "●", "green": "◆"}.get(severity, "?")
                            atype = alert.get("type", "").replace("_", " ").upper()
                            merchant = alert.get("merchant", "")
                            message = alert.get("message", "")
                            details = alert.get("details", "")

                            content = f"{icon} {atype}  {merchant}\n{message}"
                            if details:
                                content += f"\n{details}"

                            yield Static(content, classes=f"alert-card -{severity}")

            # ── Monthly Tab ──
            with TabPane("Monthly", id="monthly"):
                yield MonthlySpendChart(monthly_summary)

            # ── Categories Tab ──
            with TabPane("Categories", id="categories"):
                cats = insights.get("categories", {})
                if not cats and tx:
                    cats = defaultdict(float)
                    for t in tx:
                        cat = t.get("category", "other") or "other"
                        cats[cat] += t.get("amount", 0) or 0
                    cats = dict(cats)
                yield CategoryChart(cats)

            # ── Merchants Tab ──
            with TabPane("Merchants", id="merchants"):
                yield DataTable(id="merchant-table")

            # ── Transactions Tab ──
            with TabPane("Transactions", id="transactions"):
                yield DataTable(id="tx-table")

            # ── Recurring Tab ──
            with TabPane("Recurring", id="recurring"):
                yield DataTable(id="rec-table")

        yield Footer()

    def _setup_table_columns(self) -> None:
        tx = self._data["transactions"]

        merchant_table = self.query_one("#merchant-table")
        merchant_table.add_columns(
            "Merchant", "Count", "Total", "Avg", "Monthly Avg", "Frequency", "Trend", "First Seen", "Last Seen", "Category"
        )
        merchant_table.cursor_type = "row"
        merchant_table.zebra_stripes = True

        tx_table = self.query_one("#tx-table")
        has_tags = any(t.get("tag") for t in tx)
        columns = ["Date", "Source", "Merchant", "Amount", "Category", "Description"]
        if has_tags:
            columns.insert(2, "Tag")
        tx_table.add_columns(*columns)
        tx_table.cursor_type = "row"
        tx_table.zebra_stripes = True
        self._tx_has_tag_col = has_tags

        rec_table = self.query_one("#rec-table")
        rec_table.add_columns("Merchant", "Freq", "Monthly", "Annual", "Trend", "Active", "Category")
        rec_table.cursor_type = "row"
        rec_table.zebra_stripes = True

    def _populate_table_rows(self) -> None:
        tx = self._data["transactions"]
        insights = self._data["insights"]

        # Merchant summary table
        merchant_table = self.query_one("#merchant-table")
        recurring = insights.get("recurring", [])
        merchant_rows = build_merchant_summary(tx, recurring=recurring)
        for m in merchant_rows:
            trend = m["trend"]
            trend_icon = {"increasing": "↑", "decreasing": "↓", "stable": "→"}.get(trend, "")
            freq = m["frequency"]
            merchant_table.add_row(
                m["merchant"][:30],
                str(m["count"]),
                f"${m['total']:,.2f}",
                f"${m['avg']:,.2f}",
                f"${m['avg_monthly']:,.2f}",
                freq if freq else "—",
                f"{trend_icon} {trend}" if trend else "—",
                m["first_seen"],
                m["last_seen"],
                (m["category"] or "").replace("_", " "),
            )

        # Transaction table
        table = self.query_one("#tx-table")
        has_tags = getattr(self, "_tx_has_tag_col", False)
        self._tx_by_id.clear()

        sorted_tx = sorted(tx, key=lambda t: t.get("date") or "", reverse=True)
        for t in sorted_tx:
            amt = t.get("amount")
            if amt is not None:
                amt_str = f"${amt:,.2f}" if amt >= 0 else f"-${abs(amt):,.2f}"
            else:
                amt_str = ""
            row = [
                t.get("date", ""),
                t.get("provider", ""),
                (t.get("merchant") or "")[:30],
                amt_str,
                (t.get("category") or "").replace("_", " "),
                (t.get("description") or "")[:50],
            ]
            if has_tags:
                row.insert(2, t.get("tag") or "")
            row_key = t.get("email_id")
            if row_key:
                self._tx_by_id[row_key] = t
                table.add_row(*row, key=row_key)
            else:
                table.add_row(*row)

        # Recurring table
        rec_table = self.query_one("#rec-table")
        recurring_sorted = sorted(recurring, key=lambda r: r.get("monthly_cost", 0), reverse=True)
        for r in recurring_sorted:
            trend = r.get("trend", "")
            trend_icon = {"increasing": "↑", "decreasing": "↓", "stable": "→"}.get(trend, "")
            rec_table.add_row(
                (r.get("merchant") or "")[:30],
                r.get("frequency", ""),
                f"${r.get('monthly_cost', 0):,.2f}",
                f"${r.get('annual_cost', 0):,.2f}",
                f"{trend_icon} {trend}",
                f"{r.get('months_active', '')} mo",
                (r.get("category") or "").replace("_", " "),
            )

    def _update_summary(self) -> None:
        tx = self._data["transactions"]
        insights = self._data["insights"]

        amounts = [t.get("amount", 0) or 0 for t in tx]
        total = sum(a for a in amounts if a > 0)
        monthly_summary = insights.get("monthly_summary", [])
        months = len(monthly_summary) if monthly_summary else 1
        avg = total / months if months else 0
        recurring_total = sum(r.get("monthly_cost", 0) for r in insights.get("recurring", []))

        self.query_one("#sc-total", Static).update(f"TOTAL SPEND\n{_fmt_currency(total)}")
        self.query_one("#sc-monthly", Static).update(f"MONTHLY AVG\n{_fmt_currency(avg)}")
        self.query_one("#sc-recurring", Static).update(f"RECURRING\n{_fmt_currency(recurring_total)}/mo")
        self.query_one("#sc-tx", Static).update(f"TRANSACTIONS\n{len(tx):,}")

    def action_reload(self) -> None:
        try:
            self._data = load_tui_data(self._data_dir)
        except (OSError, json.JSONDecodeError) as e:
            self.notify(f"Reload failed: {e}", severity="warning", timeout=3)
            return

        for table_id in ("#tx-table", "#merchant-table", "#rec-table"):
            self.query_one(table_id).clear()

        self._populate_table_rows()
        self._update_summary()

        self.notify(f"Reloaded — {len(self._data['transactions'])} transactions", timeout=2)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.data_table.id != "tx-table":
            return
        row_key = getattr(event.row_key, "value", event.row_key)
        if not row_key:
            return
        tx = self._tx_by_id.get(row_key)
        if tx:
            self.push_screen(EmailInspectorScreen(tx, self._data_dir))
