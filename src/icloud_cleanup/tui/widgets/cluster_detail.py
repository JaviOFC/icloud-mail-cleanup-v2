"""Cluster detail widget showing emails, senders, and confidence."""

from __future__ import annotations

from datetime import datetime, timezone

from rich.table import Table
from rich.text import Text

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static

from icloud_cleanup.models import Classification, Message
from icloud_cleanup.tui.widgets.confidence_bar import ConfidenceBar


class ClusterDetailWidget(VerticalScroll):
    """Shows detail info for the currently highlighted cluster."""

    DEFAULT_CSS = """
    ClusterDetailWidget {
        height: 1fr;
        padding: 0 1;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._inspect_mode = False

    def compose(self) -> ComposeResult:
        yield Static("Select a cluster to view details", id="detail-content")

    def show_cluster(
        self,
        cluster_data: dict,
        classifications: list[Classification] | None = None,
        messages: list[Message] | None = None,
    ) -> None:
        """Populate detail view for a cluster."""
        content = self.query_one("#detail-content", Static)

        label = cluster_data["label"]
        count = cluster_data["count"]
        size = cluster_data.get("size", 0)
        conf = cluster_data.get("confidence", {})
        mean_conf = conf.get("mean", 0.0)
        tier_value = cluster_data.get("tier", "")
        date_range = cluster_data.get("date_range", {})
        sender_breakdown = cluster_data.get("sender_breakdown", {})
        subjects = cluster_data.get("example_subjects", [])

        lines: list[str] = []
        lines.append(f"[bold]{label}[/bold]")
        if tier_value:
            lines.append(f"Tier: {tier_value}  |  Count: {count}  |  Size: {_format_size(size)}")
        else:
            lines.append(f"Count: {count}  |  Size: {_format_size(size)}")
        lines.append(f"Confidence: {mean_conf:.2f} (min: {conf.get('min', 0):.2f}, max: {conf.get('max', 0):.2f})")

        earliest = date_range.get("earliest")
        latest = date_range.get("latest")
        if earliest and latest:
            try:
                e = datetime.fromtimestamp(earliest, tz=timezone.utc).strftime("%Y-%m-%d")
                l = datetime.fromtimestamp(latest, tz=timezone.utc).strftime("%Y-%m-%d")
                lines.append(f"Date range: {e} to {l}")
            except (ValueError, OSError):
                pass

        if sender_breakdown:
            lines.append("")
            lines.append("[bold]Senders:[/bold]")
            sorted_senders = sorted(sender_breakdown.items(), key=lambda x: -x[1])
            for sender, scount in sorted_senders[:10]:
                lines.append(f"  {sender} ({scount})")

        if subjects:
            lines.append("")
            lines.append("[bold]Example subjects:[/bold]")
            for subj in subjects[:5]:
                lines.append(f"  {subj[:80]}")

        # Inspect mode: show individual emails
        if self._inspect_mode and classifications and messages:
            msg_index = {m.message_id: m for m in messages}
            lines.append("")
            lines.append("[bold]Individual emails:[/bold]")
            for c in classifications:
                msg = msg_index.get(c.message_id)
                if not msg:
                    continue
                subj = msg.subject[:60] if msg.subject else "(no subject)"
                conf_val = f"{c.confidence:.2f}"
                try:
                    date_str = datetime.fromtimestamp(
                        msg.date_received, tz=timezone.utc
                    ).strftime("%Y-%m-%d")
                except (ValueError, OSError):
                    date_str = "?"
                lines.append(
                    f"  {subj}  |  {msg.sender_address}  |  conf: {conf_val}  |  {date_str}"
                )

        content.update("\n".join(lines))

    def set_inspect_mode(self, active: bool) -> None:
        self._inspect_mode = active

    def clear(self) -> None:
        content = self.query_one("#detail-content", Static)
        content.update("Select a cluster to view details")


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    if size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"
