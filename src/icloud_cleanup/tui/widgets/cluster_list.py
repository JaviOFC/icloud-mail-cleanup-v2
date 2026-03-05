"""Cluster list widget with multi-select tracking."""

from __future__ import annotations

from dataclasses import dataclass

from rich.text import Text

from textual.message import Message
from textual.widgets import DataTable

from icloud_cleanup.models import TIER_COLORS, Tier

_TIER_RICH_COLORS: dict[str, str] = {
    "red": "red",
    "green": "green",
    "blue": "blue",
    "yellow": "yellow",
}


class ClusterListWidget(DataTable):
    """DataTable showing clusters with multi-select via Space."""

    @dataclass
    class Changed(Message):
        """Posted when the highlighted row changes."""

        cluster_label: str

    DEFAULT_CSS = """
    ClusterListWidget {
        height: 1fr;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(cursor_type="row", zebra_stripes=True, **kwargs)
        self.selected: set[str] = set()
        self._row_labels: list[str] = []
        self._decided: set[str] = set()

    def on_mount(self) -> None:
        self.add_columns("Sel", "Cluster", "Count", "Tier", "Conf", "Dist")

    def load_clusters(
        self,
        clusters: list[dict],
        tier: str | None = None,
        decided: set[str] | None = None,
    ) -> None:
        """Populate rows from report cluster dicts.

        Args:
            clusters: List of cluster dicts from report_data.
            tier: If provided, filter to only this tier (unused -- we show all).
            decided: Set of cluster labels already decided in session.
        """
        self.clear()
        self._row_labels.clear()
        self.selected.clear()
        self._decided = decided or set()

        for cluster in clusters:
            label = cluster["label"]
            self._row_labels.append(label)

            is_decided = label in self._decided
            sel = "\u2713" if is_decided else " "
            name = Text(label, style="dim strike" if is_decided else "")
            count = str(cluster["count"])

            # Determine tier from the cluster's context
            tier_value = cluster.get("tier", "")
            try:
                tier_enum = Tier(tier_value) if tier_value else None
            except ValueError:
                tier_enum = None

            if tier_enum:
                color = TIER_COLORS.get(tier_enum, "white")
                rich_color = _TIER_RICH_COLORS.get(color, color)
                tier_text = Text(tier_value, style=rich_color)
            else:
                tier_text = Text(tier_value)

            conf = cluster.get("confidence", {})
            conf_str = f"{conf.get('mean', 0.0):.2f}"
            sparkline = cluster.get("sparkline", "")

            self.add_row(sel, name, count, tier_text, conf_str, sparkline, key=label)

    def key_space(self) -> None:
        """Toggle selection on the currently highlighted row."""
        if self.cursor_row is None or self.cursor_row >= len(self._row_labels):
            return

        label = self._row_labels[self.cursor_row]
        if label in self._decided:
            return

        if label in self.selected:
            self.selected.discard(label)
            self.update_cell_at((self.cursor_row, 0), " ")
        else:
            self.selected.add(label)
            self.update_cell_at((self.cursor_row, 0), "\u2713")

    def get_selected(self) -> list[str]:
        """Return list of selected cluster labels."""
        return list(self.selected)

    def select_all(self) -> None:
        for i, label in enumerate(self._row_labels):
            if label not in self._decided:
                self.selected.add(label)
                self.update_cell_at((i, 0), "\u2713")

    def deselect_all(self) -> None:
        for i, label in enumerate(self._row_labels):
            if label in self.selected:
                self.selected.discard(label)
                self.update_cell_at((i, 0), " ")

    def mark_decided(self, labels: set[str]) -> None:
        """Visually mark clusters as decided (dimmed with strikethrough)."""
        self._decided.update(labels)
        for i, label in enumerate(self._row_labels):
            if label in labels:
                self.selected.discard(label)
                self.update_cell_at((i, 0), "\u2713")
                self.update_cell_at(
                    (i, 1), Text(label, style="dim strike")
                )

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.cursor_row is not None and event.cursor_row < len(self._row_labels):
            label = self._row_labels[event.cursor_row]
            self.post_message(self.Changed(cluster_label=label))
