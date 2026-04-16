from textual_plotext import PlotextPlot


class MonthlySpendChart(PlotextPlot):
    def __init__(self, monthly_data: list[dict], **kwargs):
        super().__init__(**kwargs)
        self._monthly_data = monthly_data

    def on_mount(self) -> None:
        if not self._monthly_data:
            return
        months = [d["month"] for d in self._monthly_data]
        totals = [d["total"] for d in self._monthly_data]
        labels = [m[5:] + "\n" + m[:4] for m in months]

        plt = self.plt
        plt.bar(labels, totals, color="cyan")
        plt.title("Monthly Spending")
        plt.ylabel("USD")
        plt.theme("dark")


class CategoryChart(PlotextPlot):
    def __init__(self, categories: dict, **kwargs):
        super().__init__(**kwargs)
        self._categories = categories

    def on_mount(self) -> None:
        if not self._categories:
            return
        sorted_cats = sorted(self._categories.items(), key=lambda x: x[1])
        labels = [c[0] for c in sorted_cats]
        amounts = [c[1] for c in sorted_cats]
        colors = ["red", "yellow", "green", "cyan", "blue", "magenta", "white"]

        plt = self.plt
        plt.bar(labels, amounts, color=colors[: len(labels)], orientation="h")
        plt.title("Spending by Category")
        plt.xlabel("USD")
        plt.theme("dark")
