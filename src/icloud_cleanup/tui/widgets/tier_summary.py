"""Tier summary widget showing per-tier counts, sizes, confidence, and sparklines."""

from __future__ import annotations

from rich.table import Table
from rich.text import Text

from textual.widgets import Static

from icloud_cleanup.models import TIER_COLORS, Tier

_TIER_ORDER = [Tier.TRASH, Tier.KEEP_ACTIVE, Tier.KEEP_HISTORICAL, Tier.REVIEW]

# Map Tier color names to Rich style colors
_TIER_RICH_COLORS: dict[str, str] = {
    "red": "red",
    "green": "green",
    "blue": "blue",
    "yellow": "yellow",
}


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    if size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


class TierSummaryWidget(Static):
    """Renders a Rich Table showing tier name, count, size, mean confidence, sparkline."""

    DEFAULT_CSS = """
    TierSummaryWidget {
        width: 100%;
        margin: 1 2;
    }
    """

    def __init__(self, report_data: dict | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._report_data = report_data

    def on_mount(self) -> None:
        if self._report_data:
            self._render_table()

    def update_data(self, report_data: dict) -> None:
        """Refresh widget with new report data."""
        self._report_data = report_data
        self._render_table()

    def _render_table(self) -> None:
        if not self._report_data:
            self.update("No data loaded")
            return

        tiers = self._report_data.get("tiers", {})
        total = self._report_data.get("total_emails", 0)

        table = Table(title=f"Tier Summary ({total:,} emails)")
        table.add_column("Tier", style="bold")
        table.add_column("Count", justify="right")
        table.add_column("Storage", justify="right")
        table.add_column("Confidence", justify="center")
        table.add_column("Distribution", justify="left")

        for tier in _TIER_ORDER:
            td = tiers.get(tier.value, {})
            count = td.get("count", 0)
            if count == 0:
                continue

            color = TIER_COLORS[tier]
            rich_color = _TIER_RICH_COLORS.get(color, color)
            tier_name = Text(tier.value, style=rich_color)

            conf = td.get("confidence", {})
            mean_conf = conf.get("mean", 0.0)

            table.add_row(
                tier_name,
                f"{count:,}",
                _format_size(td.get("size", 0)),
                f"{mean_conf:.2f}",
                td.get("sparkline", ""),
            )

        self.update(table)
