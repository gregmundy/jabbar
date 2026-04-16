import json
import os
from collections import defaultdict

from textual.app import App
from textual.containers import VerticalScroll
from textual.widgets import Header, Footer, Static, DataTable, TabbedContent, TabPane

from src.tui.widgets.charts import MonthlySpendChart, CategoryChart


def load_tui_data(data_dir: str) -> dict:
    transactions = []
    insights = {"alerts": [], "recurring": [], "categories": {}, "monthly_summary": [], "recommendations": [], "scams_detected": []}

    tx_path = os.path.join(data_dir, "extracted", "transactions.json")
    if os.path.exists(tx_path):
        with open(tx_path) as f:
            all_tx = json.load(f)
            transactions = [t for t in all_tx if t.get("is_transaction")]

    insights_path = os.path.join(data_dir, "analysis", "insights.json")
    if os.path.exists(insights_path):
        with open(insights_path) as f:
            insights = json.load(f)

    return {"transactions": transactions, "insights": insights}


class JabbarApp(App):
    CSS = """
    Screen { background: $surface; }
    TabbedContent { height: 1fr; }
    #alerts-container { height: 1fr; padding: 1; }
    .alert-red { color: red; margin-bottom: 1; }
    .alert-yellow { color: yellow; margin-bottom: 1; }
    .alert-green { color: green; margin-bottom: 1; }
    PlotextPlot { height: 25; }
    DataTable { height: 1fr; }
    #summary-stats { height: 3; padding: 0 2; background: $primary-background; color: $text; text-style: bold; }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("d", "toggle_dark", "Dark/Light"),
    ]

    def __init__(self, data_dir: str = "data", **kwargs):
        super().__init__(**kwargs)
        self._data_dir = data_dir
        self._data = load_tui_data(data_dir)

    def compose(self):
        yield Header(show_clock=True)

        tx = self._data["transactions"]
        insights = self._data["insights"]

        total = sum(t.get("amount", 0) or 0 for t in tx)
        monthly_summary = insights.get("monthly_summary", [])
        months = len(monthly_summary) if monthly_summary else 1
        avg = total / months if months else 0

        yield Static(
            f"  Jabbar | Total: ${total:,.0f} | Monthly Avg: ${avg:,.0f} | Transactions: {len(tx)}",
            id="summary-stats",
        )

        with TabbedContent():
            with TabPane("Alerts", id="alerts"):
                with VerticalScroll(id="alerts-container"):
                    alerts = insights.get("alerts", [])
                    if not alerts:
                        yield Static("No alerts. Run 'jabbar analyze' to generate insights.")
                    for alert in alerts:
                        sev = alert.get("severity", "green")
                        icon = {"red": "[!]", "yellow": "[~]", "green": "[i]"}.get(sev, "[?]")
                        msg = f"  {icon} {alert.get('type', '').upper()}: {alert.get('merchant', '')} — {alert.get('message', '')}"
                        if alert.get("details"):
                            msg += f"\n      {alert['details']}"
                        css_class = f"alert-{sev}"
                        yield Static(msg, classes=css_class)

            with TabPane("Monthly", id="monthly"):
                yield MonthlySpendChart(monthly_summary)

            with TabPane("Categories", id="categories"):
                cats = insights.get("categories", {})
                if not cats and tx:
                    cats = defaultdict(float)
                    for t in tx:
                        cat = t.get("category", "other") or "other"
                        cats[cat] += t.get("amount", 0) or 0
                    cats = dict(cats)
                yield CategoryChart(cats)

            with TabPane("Transactions", id="transactions"):
                yield DataTable(id="tx-table")

            with TabPane("Recurring", id="recurring"):
                yield DataTable(id="rec-table")

        yield Footer()

    def on_mount(self) -> None:
        tx = self._data["transactions"]
        insights = self._data["insights"]

        table = self.query_one("#tx-table")
        table.add_columns("Date", "Provider", "Merchant", "Amount", "Category", "Description", "Payment")
        table.cursor_type = "row"
        table.zebra_stripes = True

        sorted_tx = sorted(tx, key=lambda t: t.get("date") or "", reverse=True)
        for t in sorted_tx:
            table.add_row(
                t.get("date", ""),
                t.get("provider", ""),
                (t.get("merchant") or "")[:30],
                f"${t['amount']:,.2f}" if t.get("amount") else "",
                t.get("category", ""),
                (t.get("description") or "")[:40],
                (t.get("payment_method") or "")[:20],
            )

        rec_table = self.query_one("#rec-table")
        rec_table.add_columns("Merchant", "Frequency", "Monthly", "Annual", "Trend", "Months Active", "Category")
        rec_table.cursor_type = "row"
        rec_table.zebra_stripes = True

        recurring = insights.get("recurring", [])
        recurring.sort(key=lambda r: r.get("monthly_cost", 0), reverse=True)
        for r in recurring:
            rec_table.add_row(
                (r.get("merchant") or "")[:30],
                r.get("frequency", ""),
                f"${r.get('monthly_cost', 0):,.2f}",
                f"${r.get('annual_cost', 0):,.2f}",
                r.get("trend", ""),
                str(r.get("months_active", "")),
                r.get("category", ""),
            )

    def action_toggle_dark(self) -> None:
        self.dark = not self.dark
