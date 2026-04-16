import json
import os
from collections import defaultdict

from textual.app import App
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.theme import Theme
from textual.widgets import Header, Footer, Static, DataTable, TabbedContent, TabPane, Rule

from src.tui.widgets.charts import MonthlySpendChart, CategoryChart


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
    ]

    def __init__(self, data_dir: str = "data", **kwargs):
        super().__init__(**kwargs)
        self._data_dir = data_dir
        self._data = load_tui_data(data_dir)

    def on_mount(self) -> None:
        self._populate_tables()

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
            yield SummaryCard(f"TOTAL SPEND\n{_fmt_currency(total)}", classes="summary-card -accent")
            yield SummaryCard(f"MONTHLY AVG\n{_fmt_currency(avg)}", classes="summary-card")
            yield SummaryCard(f"RECURRING\n{_fmt_currency(recurring_total)}/mo", classes="summary-card")
            yield SummaryCard(f"TRANSACTIONS\n{len(tx):,}", classes="summary-card")
            if red_count or yellow_count:
                alert_str = f"{red_count} critical" if red_count else ""
                if yellow_count:
                    alert_str += f"{'  ' if alert_str else ''}{yellow_count} warnings"
                yield SummaryCard(f"ALERTS\n{alert_str}", classes="summary-card -accent")

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

    def _populate_tables(self) -> None:
        tx = self._data["transactions"]
        insights = self._data["insights"]

        # Merchant summary table
        merchant_table = self.query_one("#merchant-table")
        merchant_table.add_columns(
            "Merchant", "Count", "Total", "Avg", "Monthly Avg", "Frequency", "Trend", "First Seen", "Last Seen", "Category"
        )
        merchant_table.cursor_type = "row"
        merchant_table.zebra_stripes = True

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
        has_tags = any(t.get("tag") for t in tx)
        columns = ["Date", "Source", "Merchant", "Amount", "Category", "Description"]
        if has_tags:
            columns.insert(2, "Tag")
        table.add_columns(*columns)
        table.cursor_type = "row"
        table.zebra_stripes = True

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
            table.add_row(*row)

        # Recurring table
        rec_table = self.query_one("#rec-table")
        rec_table.add_columns("Merchant", "Freq", "Monthly", "Annual", "Trend", "Active", "Category")
        rec_table.cursor_type = "row"
        rec_table.zebra_stripes = True

        recurring = insights.get("recurring", [])
        recurring.sort(key=lambda r: r.get("monthly_cost", 0), reverse=True)
        for r in recurring:
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
