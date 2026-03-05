"""Report generation for iCloud email classification results.

Produces tier-first summary + cluster-detail reports in terminal (Rich),
JSON, and Markdown formats.
"""

from __future__ import annotations

import json
import os
import time
from collections import defaultdict
from pathlib import Path
from statistics import mean

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from icloud_cleanup.models import Classification, Message, Tier

_TIER_COLORS: dict[Tier, str] = {
    Tier.TRASH: "red",
    Tier.KEEP_ACTIVE: "green",
    Tier.KEEP_HISTORICAL: "blue",
    Tier.REVIEW: "yellow",
}

_TIER_ORDER = [Tier.TRASH, Tier.KEEP_ACTIVE, Tier.KEEP_HISTORICAL, Tier.REVIEW]

# Unicode block chars for confidence histogram (8 levels, high to low)
_BLOCKS = "█▇▆▅▄▃▂▁"


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def _confidence_sparkline(confidences: list[float], bins: int = 10) -> str:
    """Build an inline unicode bar showing confidence distribution shape."""
    if not confidences:
        return ""
    histogram = [0] * bins
    for c in confidences:
        idx = min(int(c * bins), bins - 1)
        histogram[idx] += 1
    if max(histogram) == 0:
        return "." * bins
    max_val = max(histogram)
    result = []
    for count in histogram:
        level = int(count / max_val * (len(_BLOCKS) - 1)) if max_val > 0 else len(_BLOCKS) - 1
        result.append(_BLOCKS[level] if count > 0 else ".")
    return "".join(result)


def _cluster_key(c: Classification) -> str:
    """Normalize cluster label: None or noise (-1) become 'Unclustered'."""
    if c.cluster_id is None or c.cluster_id == -1:
        return "Unclustered"
    return c.cluster_label or f"cluster_{c.cluster_id}"


def _percentile(values: list[float], p: float) -> float:
    """Simple percentile calculation without numpy."""
    if not values:
        return 0.0
    sorted_v = sorted(values)
    k = (len(sorted_v) - 1) * p
    f = int(k)
    c = f + 1
    if c >= len(sorted_v):
        return sorted_v[f]
    return sorted_v[f] + (k - f) * (sorted_v[c] - sorted_v[f])


def build_report_data(
    classifications: list[Classification],
    messages: list[Message],
) -> dict:
    """Build structured report data from classifications and messages.

    Groups by tier, then by cluster within each tier, computing per-group
    statistics for count, storage, confidence, subjects, senders, dates.
    """
    msg_index: dict[int, Message] = {m.message_id: m for m in messages}

    tiers: dict[str, dict] = {}
    for tier in _TIER_ORDER:
        tier_items = [c for c in classifications if c.tier == tier]
        tier_confs = [c.confidence for c in tier_items]
        tier_size = sum(
            msg_index[c.message_id].size
            for c in tier_items
            if c.message_id in msg_index
        )

        # Group by cluster within tier
        cluster_groups: dict[str, list[Classification]] = defaultdict(list)
        for c in tier_items:
            cluster_groups[_cluster_key(c)].append(c)

        clusters = []
        for label, items in sorted(cluster_groups.items(), key=lambda x: -len(x[1])):
            confs = [c.confidence for c in items]
            item_msgs = [msg_index[c.message_id] for c in items if c.message_id in msg_index]

            # Sender breakdown
            sender_counts: dict[str, int] = defaultdict(int)
            for m in item_msgs:
                sender_counts[m.sender_address] += 1

            # Example subjects (up to 5 unique)
            subjects = []
            seen: set[str] = set()
            for m in item_msgs:
                if m.subject not in seen:
                    subjects.append(m.subject)
                    seen.add(m.subject)
                if len(subjects) >= 5:
                    break

            # Date range
            dates = [m.date_received for m in item_msgs]
            date_range = {
                "earliest": min(dates) if dates else None,
                "latest": max(dates) if dates else None,
            }

            cluster_size = sum(m.size for m in item_msgs)

            clusters.append({
                "label": label,
                "count": len(items),
                "size": cluster_size,
                "confidence": {
                    "min": min(confs) if confs else 0.0,
                    "max": max(confs) if confs else 0.0,
                    "mean": mean(confs) if confs else 0.0,
                },
                "example_subjects": subjects,
                "sender_breakdown": dict(sender_counts),
                "date_range": date_range,
                "sparkline": _confidence_sparkline(confs),
            })

        tiers[tier.value] = {
            "count": len(tier_items),
            "size": tier_size,
            "confidence": {
                "min": min(tier_confs) if tier_confs else 0.0,
                "max": max(tier_confs) if tier_confs else 0.0,
                "mean": mean(tier_confs) if tier_confs else 0.0,
                "p25": _percentile(tier_confs, 0.25),
                "p75": _percentile(tier_confs, 0.75),
            },
            "clusters": clusters,
            "sparkline": _confidence_sparkline(tier_confs),
        }

    return {
        "tiers": tiers,
        "total_emails": len(classifications),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def render_terminal_report(report_data: dict, console: Console | None = None) -> None:
    """Render report as Rich terminal output with tier summary and cluster detail."""
    console = console or Console()

    total = report_data["total_emails"]
    console.print(
        f"\n[bold]iCloud Mail Cleanup Report[/bold]  "
        f"({total} emails, generated {report_data['generated_at']})\n"
    )

    # Tier summary table
    summary = Table(title="Tier Summary")
    summary.add_column("Tier", style="bold")
    summary.add_column("Count", justify="right")
    summary.add_column("Storage", justify="right")
    summary.add_column("Confidence", justify="center")
    summary.add_column("Distribution", justify="left")

    for tier in _TIER_ORDER:
        td = report_data["tiers"][tier.value]
        if td["count"] == 0:
            continue
        color = _TIER_COLORS[tier]
        conf = td["confidence"]
        summary.add_row(
            f"[{color}]{tier.value}[/{color}]",
            str(td["count"]),
            _format_size(td["size"]),
            f"{conf['min']:.2f}-{conf['max']:.2f} (avg {conf['mean']:.2f})",
            td.get("sparkline", ""),
        )
    console.print(summary)

    # Per-tier cluster detail panels
    for tier in _TIER_ORDER:
        td = report_data["tiers"][tier.value]
        if not td["clusters"]:
            continue

        color = _TIER_COLORS[tier]
        cluster_table = Table(show_header=True)
        cluster_table.add_column("Cluster", style="cyan", max_width=30)
        cluster_table.add_column("Count", justify="right")
        cluster_table.add_column("Storage", justify="right")
        cluster_table.add_column("Confidence", justify="center")
        cluster_table.add_column("Example Subjects", max_width=50)

        for cl in td["clusters"]:
            subjects_str = "; ".join(cl["example_subjects"][:3])
            if len(subjects_str) > 50:
                subjects_str = subjects_str[:47] + "..."
            conf = cl["confidence"]
            cluster_table.add_row(
                cl["label"],
                str(cl["count"]),
                _format_size(cl["size"]),
                f"{conf['min']:.2f}-{conf['max']:.2f}",
                subjects_str,
            )

        panel = Panel(
            cluster_table,
            title=f"[{color}]{tier.value}[/{color}] Clusters ({td['count']} emails)",
        )
        console.print(panel)


def export_json_report(report_data: dict, output_path: Path) -> Path:
    """Export report data as JSON with atomic write."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = Path(str(output_path) + ".tmp")
    with open(tmp_path, "w") as f:
        json.dump(report_data, f, indent=2, default=str)
    os.replace(tmp_path, output_path)
    return output_path


def export_markdown_report(report_data: dict, output_path: Path) -> Path:
    """Export report data as Markdown with tier tables and cluster details."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []

    total = report_data["total_emails"]
    lines.append(f"# iCloud Mail Cleanup Report")
    lines.append("")
    lines.append(f"**Generated:** {report_data['generated_at']}  ")
    lines.append(f"**Total emails:** {total}")
    lines.append("")

    # Tier summary table
    lines.append("## Tier Summary")
    lines.append("")
    lines.append("| Tier | Count | Storage | Confidence | Distribution |")
    lines.append("|------|------:|--------:|:----------:|:-------------|")

    for tier in _TIER_ORDER:
        td = report_data["tiers"][tier.value]
        conf = td["confidence"]
        conf_str = f"{conf['min']:.2f}-{conf['max']:.2f}" if td["count"] > 0 else "N/A"
        sparkline = td.get("sparkline", "")
        lines.append(
            f"| {tier.value} | {td['count']} | {_format_size(td['size'])} | {conf_str} | {sparkline} |"
        )
    lines.append("")

    # Per-tier cluster detail
    for tier in _TIER_ORDER:
        td = report_data["tiers"][tier.value]
        if not td["clusters"]:
            continue

        lines.append(f"## {tier.value} ({td['count']} emails, {_format_size(td['size'])})")
        lines.append("")
        lines.append("| Cluster | Count | Storage | Confidence | Top Senders | Example Subjects |")
        lines.append("|---------|------:|--------:|:----------:|:------------|:-----------------|")

        for cl in td["clusters"]:
            conf = cl["confidence"]
            senders = ", ".join(
                f"{s} ({n})"
                for s, n in sorted(cl["sender_breakdown"].items(), key=lambda x: -x[1])[:3]
            )
            subjects = "; ".join(cl["example_subjects"][:3])
            if len(subjects) > 60:
                subjects = subjects[:57] + "..."
            lines.append(
                f"| {cl['label']} | {cl['count']} | {_format_size(cl['size'])} "
                f"| {conf['min']:.2f}-{conf['max']:.2f} | {senders} | {subjects} |"
            )
        lines.append("")

    content = "\n".join(lines)
    tmp_path = Path(str(output_path) + ".tmp")
    with open(tmp_path, "w") as f:
        f.write(content)
    os.replace(tmp_path, output_path)
    return output_path


def generate_report(
    classifications: list[Classification],
    messages: list[Message],
    output_dir: Path,
    *,
    format: str = "all",
) -> dict:
    """Dispatch report generation to the appropriate format(s).

    Args:
        format: One of "terminal", "json", "markdown", "all"

    Returns dict with keys for each format generated, values are output paths or "rendered".
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    data = build_report_data(classifications, messages)
    result: dict[str, str] = {}

    if format in ("terminal", "all"):
        render_terminal_report(data)
        result["terminal"] = "rendered"

    if format in ("json", "all"):
        path = export_json_report(data, output_dir / "report.json")
        result["json"] = str(path)

    if format in ("markdown", "all"):
        path = export_markdown_report(data, output_dir / "report.md")
        result["markdown"] = str(path)

    return result
