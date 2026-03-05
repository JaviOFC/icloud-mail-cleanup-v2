"""Rich display components for progress bars and summary tables."""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Callable, TypeVar

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
)
from rich.table import Table

from icloud_cleanup.models import TIER_COLORS, Classification, Message, Tier

T = TypeVar("T")


def _format_size(size_bytes: int) -> str:
    """Format byte size as human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def _format_date(timestamp: int | None) -> str:
    """Format Unix timestamp as YYYY-MM-DD."""
    if timestamp is None:
        return "N/A"
    return time.strftime("%Y-%m-%d", time.localtime(timestamp))


def scan_with_progress(
    messages: list[Message],
    callback: Callable[[Message], T],
    label: str = "Scanning...",
) -> list[T]:
    """Iterate messages with a rich progress bar, applying callback to each."""
    results: list[T] = []
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold]{task.description}"),
        MofNCompleteColumn(),
        TimeRemainingColumn(),
    ) as progress:
        task = progress.add_task(label, total=len(messages))
        for msg in messages:
            results.append(callback(msg))
            progress.advance(task)
    return results


def classify_with_progress(
    messages: list[Message],
    classify_fn: Callable[[Message], Classification],
) -> list[Classification]:
    """Classify messages with a rich progress bar."""
    results: list[Classification] = []
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold]{task.description}"),
        MofNCompleteColumn(),
        TimeRemainingColumn(),
    ) as progress:
        task = progress.add_task("Classifying...", total=len(messages))
        for msg in messages:
            results.append(classify_fn(msg))
            progress.advance(task)
    return results


def display_scan_stats(
    stats: dict[str, dict],
    console: Console | None = None,
) -> None:
    """Display sender volume statistics as a rich table (top 25 by count)."""
    console = console or Console()

    sorted_senders = sorted(stats.items(), key=lambda x: x[1]["count"], reverse=True)
    top_25 = sorted_senders[:25]

    table = Table(title="Top Senders by Volume")
    table.add_column("Sender", style="cyan", no_wrap=True, max_width=50)
    table.add_column("Count", justify="right")
    table.add_column("Size", justify="right")
    table.add_column("First Seen", justify="center")
    table.add_column("Last Seen", justify="center")

    for address, data in top_25:
        table.add_row(
            address,
            str(data["count"]),
            _format_size(data["total_size"]),
            _format_date(data["min_date"]),
            _format_date(data["max_date"]),
        )

    total_count = sum(d["count"] for d in stats.values())
    total_size = sum(d["total_size"] for d in stats.values())
    table.add_section()
    table.add_row(
        f"[bold]Total ({len(stats)} senders)",
        f"[bold]{total_count}",
        f"[bold]{_format_size(total_size)}",
        "",
        "",
    )

    console.print(table)


def display_tier_summary(
    classifications: list[Classification],
    console: Console | None = None,
) -> None:
    """Display tier breakdown with count, percentage, and average confidence."""
    console = console or Console()

    tier_groups: dict[Tier, list[Classification]] = defaultdict(list)
    for c in classifications:
        tier_groups[c.tier].append(c)

    total = len(classifications)
    table = Table(title="Classification Summary")
    table.add_column("Tier", style="bold")
    table.add_column("Count", justify="right")
    table.add_column("%", justify="right")
    table.add_column("Avg Confidence", justify="right")

    for tier in Tier:
        group = tier_groups.get(tier, [])
        count = len(group)
        pct = (count / total * 100) if total > 0 else 0
        avg_conf = sum(c.confidence for c in group) / count if count > 0 else 0
        color = TIER_COLORS[tier]
        table.add_row(
            f"[{color}]{tier.value}[/{color}]",
            str(count),
            f"{pct:.1f}%",
            f"{avg_conf:.3f}",
        )

    table.add_section()
    total_avg = sum(c.confidence for c in classifications) / total if total > 0 else 0
    table.add_row("[bold]Total", f"[bold]{total}", "[bold]100.0%", f"[bold]{total_avg:.3f}")

    console.print(table)


def display_reclassification_summary(
    before: dict[Tier, int],
    after: dict[Tier, int],
    console: Console | None = None,
) -> None:
    """Show tier distribution before and after content reclassification."""
    console = console or Console()

    table = Table(title="Reclassification Summary (Before -> After)")
    table.add_column("Tier", style="bold")
    table.add_column("Before", justify="right")
    table.add_column("After", justify="right")
    table.add_column("Change", justify="right")

    for tier in Tier:
        b = before.get(tier, 0)
        a = after.get(tier, 0)
        delta = a - b
        color = TIER_COLORS[tier]
        sign = "+" if delta > 0 else ""
        delta_style = "green" if delta > 0 else "red" if delta < 0 else "dim"
        table.add_row(
            f"[{color}]{tier.value}[/{color}]",
            str(b),
            str(a),
            f"[{delta_style}]{sign}{delta}[/{delta_style}]",
        )

    console.print(table)


def display_cluster_summary(
    cluster_labels: dict[int, list[str]],
    cluster_sizes: dict[int, int],
    console: Console | None = None,
) -> None:
    """Show top clusters with their labels and sizes."""
    console = console or Console()

    sorted_clusters = sorted(cluster_sizes.items(), key=lambda x: x[1], reverse=True)

    table = Table(title="Cluster Summary (Top 20)")
    table.add_column("ID", justify="right")
    table.add_column("Size", justify="right")
    table.add_column("Labels")

    for cid, size in sorted_clusters[:20]:
        labels = cluster_labels.get(cid, [])
        label_str = ", ".join(labels) if labels else "(no labels)"
        table.add_row(str(cid), str(size), label_str)

    total_clustered = sum(cluster_sizes.values())
    table.add_section()
    table.add_row("[bold]Total", f"[bold]{total_clustered}", "")

    console.print(table)


def display_top_senders(
    classifications: list[Classification],
    messages: list[Message],
    console: Console | None = None,
) -> None:
    """Display top 10 senders per tier with count and average confidence."""
    console = console or Console()

    msg_map: dict[int, Message] = {m.message_id: m for m in messages}

    tier_groups: dict[Tier, list[Classification]] = defaultdict(list)
    for c in classifications:
        tier_groups[c.tier].append(c)

    for tier in Tier:
        group = tier_groups.get(tier, [])
        if not group:
            continue

        sender_data: dict[str, list[float]] = defaultdict(list)
        for c in group:
            msg = msg_map.get(c.message_id)
            addr = msg.sender_address.lower() if msg else "unknown"
            sender_data[addr].append(c.confidence)

        sorted_senders = sorted(
            sender_data.items(), key=lambda x: len(x[1]), reverse=True
        )[:10]

        color = TIER_COLORS[tier]
        table = Table(show_header=True)
        table.add_column("Sender", style="cyan", no_wrap=True, max_width=50)
        table.add_column("Count", justify="right")
        table.add_column("Avg Confidence", justify="right")

        for addr, confidences in sorted_senders:
            avg = sum(confidences) / len(confidences)
            table.add_row(addr, str(len(confidences)), f"{avg:.3f}")

        panel = Panel(table, title=f"[{color}]{tier.value}[/{color}] — Top Senders")
        console.print(panel)
