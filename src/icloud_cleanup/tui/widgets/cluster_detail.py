"""Cluster detail widget showing emails, senders, and confidence."""

from __future__ import annotations

from datetime import datetime, timezone

from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widgets import DataTable, Static

from icloud_cleanup.models import Classification, Message

# Max rows to display in inspect DataTable at once
_INSPECT_PAGE_SIZE = 200


class ClusterDetailWidget(Vertical):
    """Shows detail info for the currently highlighted cluster."""

    DEFAULT_CSS = """
    ClusterDetailWidget {
        height: 1fr;
    }
    #detail-overview {
        height: auto;
        max-height: 50%;
        padding: 0 1;
    }
    #inspect-header {
        height: 1;
        text-style: bold;
        padding: 0 1;
        background: $panel;
    }
    #inspect-table {
        height: 1fr;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._inspect_mode = False
        self._current_classifications: list[Classification] = []
        self._current_messages: list[Message] = []

    def compose(self) -> ComposeResult:
        yield VerticalScroll(
            Static(
                "[dim]Navigate the cluster list and select one to view details.[/dim]",
                id="detail-content",
                markup=True,
            ),
            id="detail-overview",
        )
        yield Static("", id="inspect-header", markup=True)
        yield DataTable(id="inspect-table", cursor_type="row", zebra_stripes=True)

    def on_mount(self) -> None:
        table = self.query_one("#inspect-table", DataTable)
        table.add_columns("Subject", "Sender", "Date", "Conf")
        table.display = False
        self.query_one("#inspect-header").display = False

    def show_cluster(
        self,
        cluster_data: dict,
        classifications: list[Classification] | None = None,
        messages: list[Message] | None = None,
    ) -> None:
        """Populate detail view for a cluster."""
        self._current_classifications = classifications or []
        self._current_messages = messages or []

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

        # --- Overview section ---
        lines.append(f"[bold]{label}[/bold]")
        if tier_value:
            lines.append(f"Tier: {tier_value}  |  Count: {count:,}  |  Size: {_format_size(size)}")
        else:
            lines.append(f"Count: {count:,}  |  Size: {_format_size(size)}")
        lines.append(
            f"Confidence: {mean_conf:.2f} "
            f"(min: {conf.get('min', 0):.2f}, max: {conf.get('max', 0):.2f})"
        )

        earliest = date_range.get("earliest")
        latest = date_range.get("latest")
        if earliest and latest:
            try:
                e = datetime.fromtimestamp(earliest, tz=timezone.utc).strftime("%Y-%m-%d")
                l = datetime.fromtimestamp(latest, tz=timezone.utc).strftime("%Y-%m-%d")
                lines.append(f"Date range: {e} to {l}")
            except (ValueError, OSError):
                pass

        # --- Top Senders section ---
        lines.append("")
        if sender_breakdown:
            total_senders = len(sender_breakdown)
            showing = min(25, total_senders)
            lines.append(f"[bold]Top Senders[/bold]  ({total_senders} unique)")
            sorted_senders = sorted(sender_breakdown.items(), key=lambda x: -x[1])
            total_msgs = sum(sender_breakdown.values())
            for sender, scount in sorted_senders[:25]:
                pct = (scount / total_msgs * 100) if total_msgs else 0
                lines.append(f"  {sender} — {scount:,} ({pct:.0f}%)")
            if total_senders > 25:
                lines.append(f"  [dim]... and {total_senders - 25} more senders[/dim]")
        else:
            lines.append("[dim]No sender data available. Run Pipeline (1) to populate.[/dim]")

        # --- Example Subjects section ---
        lines.append("")
        if subjects:
            total_subjects = len(subjects)
            showing = min(20, total_subjects)
            lines.append(f"[bold]Example Subjects[/bold]  (showing {showing})")
            for subj in subjects[:20]:
                lines.append(f"  {subj[:100]}")
            if total_subjects > 20:
                lines.append(f"  [dim]... and {total_subjects - 20} more[/dim]")
        else:
            lines.append("[dim]No example subjects available.[/dim]")

        if not self._inspect_mode:
            lines.append("")
            lines.append("[dim]Press [bold]I[/bold] to inspect individual emails[/dim]")

        content.update("\n".join(lines))

        # Update inspect table if active
        if self._inspect_mode:
            self._populate_inspect_table()

    def _populate_inspect_table(self) -> None:
        """Fill the inspect DataTable with individual email data."""
        table = self.query_one("#inspect-table", DataTable)
        header = self.query_one("#inspect-header", Static)

        classifications = self._current_classifications
        messages = self._current_messages

        if not classifications:
            header.update("[bold]Individual Emails[/bold]  (no classification data)")
            header.display = True
            table.display = False
            return

        msg_index = {m.message_id: m for m in messages} if messages else {}

        table.clear()
        total = len(classifications)
        showing = min(_INSPECT_PAGE_SIZE, total)
        header.update(
            f"[bold]Individual Emails[/bold]  (showing {showing:,} of {total:,})"
        )
        header.display = True
        table.display = True

        for c in classifications[:_INSPECT_PAGE_SIZE]:
            msg = msg_index.get(c.message_id)
            if msg:
                subj = msg.subject[:80] if msg.subject else "(no subject)"
                sender = msg.sender_address or "(unknown)"
                try:
                    date_str = datetime.fromtimestamp(
                        msg.date_received, tz=timezone.utc
                    ).strftime("%Y-%m-%d")
                except (ValueError, OSError):
                    date_str = "?"
            else:
                subj = f"msg#{c.message_id}"
                sender = ""
                date_str = ""

            conf_str = f"{c.confidence:.2f}"
            table.add_row(subj, sender, date_str, conf_str)

    def set_inspect_mode(self, active: bool) -> None:
        self._inspect_mode = active
        table = self.query_one("#inspect-table", DataTable)
        header = self.query_one("#inspect-header", Static)
        if active:
            self._populate_inspect_table()
        else:
            table.display = False
            header.display = False

    def clear(self) -> None:
        content = self.query_one("#detail-content", Static)
        content.update("[dim]Navigate the cluster list and select one to view details.[/dim]")
        table = self.query_one("#inspect-table", DataTable)
        table.clear()
        table.display = False
        self.query_one("#inspect-header").display = False


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    if size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"
