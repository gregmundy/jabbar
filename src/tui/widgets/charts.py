from textual_plotext import PlotextPlot


class MonthlySpendChart(PlotextPlot):
    def __init__(self, monthly_data: list[dict], **kwargs):
        super().__init__(**kwargs)
        self._monthly_data = monthly_data

    def on_mount(self) -> None:
        if not self._monthly_data:
            return
        plt = self.plt
        plt.clear_figure()

        months = [d["month"] for d in self._monthly_data]
        totals = [d["total"] for d in self._monthly_data]

        # Abbreviated labels: "Apr\n24"
        labels = []
        for m in months:
            year = m[:4]
            month_num = int(m[5:7])
            month_abbr = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][month_num - 1]
            labels.append(f"{month_abbr}\n'{year[2:]}")

        is_dark = self.app.current_theme.dark if hasattr(self.app, 'current_theme') else True

        if is_dark:
            plt.theme("dark")
            bar_color = (100, 180, 220)
        else:
            plt.theme("clear")
            bar_color = (50, 120, 180)

        plt.bar(labels, totals, color=bar_color, fill=True)
        plt.title("Monthly Spending")
        plt.ylabel("USD ($)")

        if totals:
            avg = sum(totals) / len(totals)
            plt.hline(avg, color=(180, 100, 100))

        self.refresh()


class CategoryChart(PlotextPlot):
    def __init__(self, categories: dict, **kwargs):
        super().__init__(**kwargs)
        self._categories = categories

    def on_mount(self) -> None:
        if not self._categories:
            return
        plt = self.plt
        plt.clear_figure()

        # Filter out credit_card (payment transfers, not spending) and sort
        filtered = {k: v for k, v in self._categories.items() if k != "credit_card"}
        if not filtered:
            filtered = self._categories

        sorted_cats = sorted(filtered.items(), key=lambda x: x[1])
        labels = [c[0].replace("_", " ").title() for c in sorted_cats]
        amounts = [c[1] for c in sorted_cats]

        is_dark = self.app.current_theme.dark if hasattr(self.app, 'current_theme') else True

        if is_dark:
            plt.theme("dark")
            palette = [
                (180, 80, 80),   # muted red
                (200, 160, 60),  # amber
                (80, 170, 120),  # sage
                (100, 180, 220), # steel blue
                (140, 100, 200), # muted purple
                (200, 120, 80),  # terra cotta
                (160, 160, 160), # silver
                (100, 200, 200), # teal
                (200, 140, 180), # dusty rose
                (180, 200, 100), # olive
            ]
        else:
            plt.theme("clear")
            palette = [
                (180, 60, 60),
                (180, 140, 40),
                (40, 140, 90),
                (50, 130, 190),
                (120, 80, 180),
                (180, 100, 60),
                (120, 120, 120),
                (60, 160, 160),
                (180, 100, 140),
                (140, 170, 60),
            ]

        colors = palette[:len(labels)]

        plt.bar(labels, amounts, color=colors, orientation="horizontal", fill=True)
        plt.title("Spending by Category")
        plt.xlabel("USD ($)")

        self.refresh()
